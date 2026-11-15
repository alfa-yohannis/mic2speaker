"""Integration tests for the Linux adapters against the real PipeWire server.

Each test creates temporary virtual devices: silent microphones, a
microphone that plays test tones, and speakers that play into nothing. No
sound reaches the real speakers, and the virtual devices are removed again
after each test. The tests are skipped when pactl or pw-loopback is missing.
"""

import json
import math
import os
import shutil
import signal
import struct
import subprocess
import sys
import time
import wave
from dataclasses import dataclass
from pathlib import Path

import pytest
from PyQt5.QtWidgets import QApplication

from mic2speaker.audio.audio_device import AudioDevice
from mic2speaker.audio.audio_filters import AudioFilters
from mic2speaker.audio.linux_audio_device_provider import LinuxAudioDeviceProvider
from mic2speaker.audio.linux_audio_device_watcher import LinuxAudioDeviceWatcher
from mic2speaker.audio.linux_audio_loopback import LinuxAudioLoopback
from mic2speaker.audio.linux_node_names import (
    CAPTURE_STREAM_NAME,
    ECHO_CANCEL_CAPTURE_NAME,
    ECHO_CANCEL_REFERENCE_NAME,
    ECHO_CANCEL_SOURCE_NAME,
    FILTERED_MICROPHONE_NAME,
    FILTERS_CAPTURE_NAME,
    OWN_DEVICE_PREFIX,
    PLAYBACK_STREAM_NAME,
)

PACTL_PATH = shutil.which("pactl")
PW_LOOPBACK_PATH = shutil.which("pw-loopback")
PIPEWIRE_TOOLS_MISSING = PACTL_PATH is None or PW_LOOPBACK_PATH is None

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(PIPEWIRE_TOOLS_MISSING, reason="needs PipeWire's pactl and pw-loopback"),
]

PROJECT_DIR = Path(__file__).resolve().parent.parent
TEST_MICROPHONE = AudioDevice("m2s_test_microphone", "M2S-Test-Microphone")
TEST_SPEAKER_A = AudioDevice("m2s_test_speaker_a", "M2S-Test-Speaker-A")
TEST_SPEAKER_B = AudioDevice("m2s_test_speaker_b", "M2S-Test-Speaker-B")
TEST_SPEAKER_C = AudioDevice("m2s_test_speaker_c", "M2S-Test-Speaker-C")
TONE_MICROPHONE = AudioDevice("m2s_test_tone_microphone", "M2S-Test-Tone-Microphone")
TONE_INPUT_NAME = "m2s_test_tone_input"
NO_FILTERS = AudioFilters()
ALL_FILTERS = AudioFilters(echo_canceller=True, frequency_shifter=True, noise_gate=True)

WAIT_TIMEOUT_SECONDS = 3.0
WATCHER_RESTART_TIMEOUT_SECONDS = 5.0
WATCHER_START_SECONDS = 0.5
POLL_INTERVAL_SECONDS = 0.05

SAMPLE_RATE = 48000
TONE_FREQUENCY_HZ = 1000
TONE_SECONDS = 2.0
TONE_SETTLE_SECONDS = 0.5
RECORD_SECONDS = "1"
QUIET_TONE_DBFS = -70
LOUD_TONE_DBFS = -20

# Runs in a separate process: start the sound, say so, then wait to be killed.
APP_THAT_GETS_KILLED = """
import sys
from PyQt5.QtCore import QCoreApplication
from mic2speaker.audio.audio_device import AudioDevice
from mic2speaker.audio.audio_filters import AudioFilters
from mic2speaker.audio.linux_audio_loopback import LinuxAudioLoopback

application = QCoreApplication(sys.argv)
loopback = LinuxAudioLoopback()
microphone = AudioDevice(sys.argv[1], "microphone")
speaker = AudioDevice(sys.argv[2], "speaker")
loopback.start(microphone, speaker, AudioFilters(), on_stopped=print)
print("STARTED", flush=True)
application.exec_()
"""


def run_pactl(arguments: list[str]) -> str:
    """Run pactl and return its output. The test fails if pactl fails."""
    command = ["pactl"] + arguments
    completed_process = subprocess.run(command, capture_output=True, text=True, check=True)
    return completed_process.stdout.strip()


def read_pactl_list(kind: str) -> list[dict]:
    """Return ``pactl list <kind>`` as parsed JSON, for example kind="sinks"."""
    output = run_pactl(["--format=json", "list", kind])
    return json.loads(output)


def device_names_by_index(kind: str) -> dict[int, str]:
    """Map each device's pactl index to its name, for kind "sinks" or "sources"."""
    names = {}
    for device in read_pactl_list(kind):
        names[device["index"]] = device["name"]
    return names


def sources_read_by(stream_name: str) -> list[str]:
    """Return the names of the sources that the recording stream ``stream_name`` reads."""
    source_names = device_names_by_index("sources")
    connected = []
    for stream in read_pactl_list("source-outputs"):
        if stream["properties"].get("node.name") == stream_name:
            source_name = source_names.get(stream["source"])
            connected.append(source_name)
    return connected


def sinks_written_by(stream_name: str) -> list[str]:
    """Return the names of the sinks that the playback stream ``stream_name`` writes to."""
    sink_names = device_names_by_index("sinks")
    connected = []
    for stream in read_pactl_list("sink-inputs"):
        if stream["properties"].get("node.name") == stream_name:
            sink_name = sink_names.get(stream["sink"])
            connected.append(sink_name)
    return connected


def playback_volume_text() -> str | None:
    """Return the volume of our playback stream, for example "40%", or None if it is not there."""
    for stream in read_pactl_list("sink-inputs"):
        if stream["properties"].get("node.name") == PLAYBACK_STREAM_NAME:
            return stream["volume"]["front-left"]["value_percent"]
    return None


def own_virtual_devices() -> list[str]:
    """Return the names of the virtual devices that Mic2Speaker's filters created."""
    names = []
    for kind in ("sources", "sinks"):
        for device in read_pactl_list(kind):
            if device["name"].startswith(OWN_DEVICE_PREFIX):
                names.append(device["name"])
    return names


def child_process_ids(command_pattern: str) -> list[int]:
    """Return the ids of this test process's children whose command line matches ``command_pattern``."""
    test_process_id = str(os.getpid())
    command = ["pgrep", "-P", test_process_id, "-f", command_pattern]
    completed_process = subprocess.run(command, capture_output=True, text=True)
    process_ids = []
    for line in completed_process.stdout.splitlines():
        process_ids.append(int(line))
    return process_ids


def wait_until(condition, timeout_seconds: float = WAIT_TIMEOUT_SECONDS) -> bool:
    """Let Qt handle its events until ``condition()`` is true or time runs out."""
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        QApplication.processEvents()
        if condition():
            return True
        time.sleep(POLL_INTERVAL_SECONDS)
    return False


def keep_qt_running_for(seconds: float) -> None:
    """Let Qt handle its events for ``seconds``."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        QApplication.processEvents()
        time.sleep(POLL_INTERVAL_SECONDS)


def write_tone(path: Path, level_dbfs: float) -> None:
    """Write a mono 1 kHz sine wave at ``level_dbfs`` (peak) into the WAV file ``path``."""
    amplitude = 32767 * 10 ** (level_dbfs / 20)
    sample_count = int(SAMPLE_RATE * TONE_SECONDS)
    samples = bytearray()
    for sample_number in range(sample_count):
        angle = 2 * math.pi * TONE_FREQUENCY_HZ * sample_number / SAMPLE_RATE
        sample_value = int(amplitude * math.sin(angle))
        samples += struct.pack("<h", sample_value)
    with wave.open(str(path), "wb") as wave_file:
        wave_file.setnchannels(1)
        wave_file.setsampwidth(2)
        wave_file.setframerate(SAMPLE_RATE)
        wave_file.writeframes(bytes(samples))


def rms_dbfs(raw_samples: bytes) -> float:
    """Return the RMS level of signed 16-bit samples in dBFS, or -inf for silence."""
    sample_count = len(raw_samples) // 2
    if sample_count == 0:
        return -math.inf
    samples = struct.unpack(f"<{sample_count}h", raw_samples[: sample_count * 2])
    square_sum = 0
    for sample in samples:
        square_sum += sample * sample
    rms = math.sqrt(square_sum / sample_count)
    if rms == 0:
        return -math.inf
    return 20 * math.log10(rms / 32768)


def record_speaker(speaker: AudioDevice) -> bytes:
    """Record about one second of what ``speaker`` plays, from its monitor."""
    command = [
        "timeout", RECORD_SECONDS, "pw-record", "--target", speaker.system_name,
        "-P", "stream.capture.sink=true", "--format", "s16", "--channels", "1",
        "--rate", str(SAMPLE_RATE), "-",
    ]
    completed_process = subprocess.run(command, capture_output=True)
    return completed_process.stdout


def skip_unless_supported(filters: AudioFilters) -> None:
    """Skip the test if this computer cannot run one of ``filters``, giving the reason."""
    loopback = LinuxAudioLoopback()
    support = loopback.filter_support()
    problems = support.problems_with(filters)
    if problems:
        problem_text = " ".join(problems)
        pytest.skip(problem_text)


class VirtualDevices:
    """Temporary virtual devices on the PipeWire server."""

    def __init__(self) -> None:
        self._module_ids: dict[str, str] = {}

    def add_microphone(self, device: AudioDevice) -> None:
        """Add a silent virtual microphone."""
        self._load_null_sink(device, ["media.class=Audio/Source/Virtual"])

    def add_speaker(self, device: AudioDevice) -> None:
        """Add a virtual speaker that plays into nothing."""
        self._load_null_sink(device, [])

    def unplug(self, device: AudioDevice) -> None:
        """Remove one device, as if its cable was pulled out."""
        module_id = self._module_ids.pop(device.system_name)
        run_pactl(["unload-module", module_id])

    def remove_all(self) -> None:
        """Remove every device that is still there."""
        for module_id in self._module_ids.values():
            run_pactl(["unload-module", module_id])
        self._module_ids.clear()

    def _load_null_sink(self, device: AudioDevice, extra_arguments: list[str]) -> None:
        """Create the device with PulseAudio's null-sink module and remember its module id."""
        name_argument = f"sink_name={device.system_name}"
        description_argument = f"sink_properties=device.description={device.display_name}"
        arguments = ["load-module", "module-null-sink"] + extra_arguments + [name_argument, description_argument]
        module_id = run_pactl(arguments)
        self._module_ids[device.system_name] = module_id


class ToneMicrophone:
    """A virtual microphone that "hears" whatever is played into TONE_INPUT_NAME.

    It is a pw-loopback from a virtual sink to a virtual source, which is the
    usual way to make a virtual microphone in PipeWire.
    """

    def __init__(self) -> None:
        command = [
            "pw-loopback", "--name", "m2s_test_tone_microphone",
            "--capture-props", f"media.class=Audio/Sink node.name={TONE_INPUT_NAME}",
            "--playback-props", f"media.class=Audio/Source node.name={TONE_MICROPHONE.system_name}",
        ]
        self._process = subprocess.Popen(command)

    def play(self, tone_path: Path) -> subprocess.Popen:
        """Start playing ``tone_path`` into the microphone and return the player process."""
        command = ["pw-play", "--target", TONE_INPUT_NAME, str(tone_path)]
        return subprocess.Popen(command)

    def remove(self) -> None:
        """End the virtual microphone."""
        self._process.terminate()
        self._process.wait()


@dataclass(frozen=True)
class ToneFiles:
    """The two test tones: one below the noise gate's threshold and one well above it."""

    quiet: Path
    loud: Path


class StopRecorder:
    """Collects the reasons passed to an on_stopped callback."""

    def __init__(self) -> None:
        self.reasons: list[str] = []

    def record(self, reason: str) -> None:
        """Use this method as the on_stopped callback."""
        self.reasons.append(reason)


class ChangeCounter:
    """Counts the calls to an on_devices_changed callback."""

    def __init__(self) -> None:
        self.count = 0

    def record(self) -> None:
        """Use this method as the on_devices_changed callback."""
        self.count += 1


@pytest.fixture(autouse=True)
def no_other_mic2speaker_playing():
    """Skip while another Mic2Speaker plays sound, because its streams and devices have our names."""
    other_playback_streams = sinks_written_by(PLAYBACK_STREAM_NAME)
    other_virtual_devices = own_virtual_devices()
    if other_playback_streams or other_virtual_devices:
        pytest.skip("Another Mic2Speaker is playing sound. Switch it OFF and run the tests again.")


@pytest.fixture
def virtual_devices(qt_application) -> VirtualDevices:
    """A silent virtual microphone and two virtual speakers, removed after the test."""
    devices = VirtualDevices()
    devices.add_microphone(TEST_MICROPHONE)
    devices.add_speaker(TEST_SPEAKER_A)
    devices.add_speaker(TEST_SPEAKER_B)
    yield devices
    devices.remove_all()


@pytest.fixture
def tone_microphone(virtual_devices) -> ToneMicrophone:
    """A virtual microphone that test tones can be played into."""
    microphone = ToneMicrophone()
    keep_qt_running_for(WATCHER_START_SECONDS)
    yield microphone
    microphone.remove()


@pytest.fixture(scope="module")
def tone_files(tmp_path_factory) -> ToneFiles:
    """A quiet and a loud test tone as WAV files."""
    tone_directory = tmp_path_factory.mktemp("tones")
    quiet_path = tone_directory / "quiet.wav"
    loud_path = tone_directory / "loud.wav"
    write_tone(quiet_path, QUIET_TONE_DBFS)
    write_tone(loud_path, LOUD_TONE_DBFS)
    return ToneFiles(quiet=quiet_path, loud=loud_path)


@pytest.fixture
def loopback(qt_application) -> LinuxAudioLoopback:
    """A Linux loopback that is stopped again after the test."""
    audio_loopback = LinuxAudioLoopback()
    yield audio_loopback
    audio_loopback.stop()


@pytest.fixture
def device_watcher(qt_application) -> LinuxAudioDeviceWatcher:
    """A Linux device watcher that is stopped again after the test."""
    watcher = LinuxAudioDeviceWatcher()
    yield watcher
    watcher.stop()


def speaker_level_while_playing(tone_microphone: ToneMicrophone, tone_path: Path) -> float:
    """Play ``tone_path`` into the tone microphone and return the level that reaches speaker A."""
    player = tone_microphone.play(tone_path)
    keep_qt_running_for(TONE_SETTLE_SECONDS)
    recording = record_speaker(TEST_SPEAKER_A)
    player.wait()
    return rms_dbfs(recording)


def test_device_provider_lists_the_virtual_devices(virtual_devices):
    provider = LinuxAudioDeviceProvider()

    microphones = provider.list_microphones()
    speakers = provider.list_speakers()

    microphone_names = [device.system_name for device in microphones]
    speaker_names = [device.system_name for device in speakers]
    monitor_of_speaker_a = TEST_SPEAKER_A.system_name + ".monitor"
    assert TEST_MICROPHONE.system_name in microphone_names
    assert monitor_of_speaker_a not in microphone_names
    assert TEST_SPEAKER_A.system_name in speaker_names
    assert TEST_SPEAKER_B.system_name in speaker_names


def test_start_connects_the_chosen_devices_and_stop_disconnects_them(virtual_devices, loopback):
    stop_recorder = StopRecorder()

    loopback.start(TEST_MICROPHONE, TEST_SPEAKER_A, NO_FILTERS, on_stopped=stop_recorder.record)

    assert wait_until(lambda: sinks_written_by(PLAYBACK_STREAM_NAME) == [TEST_SPEAKER_A.system_name])
    assert sources_read_by(CAPTURE_STREAM_NAME) == [TEST_MICROPHONE.system_name]
    assert loopback.is_running()

    loopback.stop()

    assert not loopback.is_running()
    assert wait_until(lambda: sinks_written_by(PLAYBACK_STREAM_NAME) == [])
    assert stop_recorder.reasons == []


def test_starting_again_moves_the_sound_to_the_new_speaker(virtual_devices, loopback):
    stop_recorder = StopRecorder()
    loopback.start(TEST_MICROPHONE, TEST_SPEAKER_A, NO_FILTERS, on_stopped=stop_recorder.record)

    loopback.start(TEST_MICROPHONE, TEST_SPEAKER_B, NO_FILTERS, on_stopped=stop_recorder.record)

    assert wait_until(lambda: sinks_written_by(PLAYBACK_STREAM_NAME) == [TEST_SPEAKER_B.system_name])
    assert stop_recorder.reasons == []


def test_unplugging_the_speaker_stops_the_sound_instead_of_moving_it(virtual_devices, loopback):
    stop_recorder = StopRecorder()
    loopback.start(TEST_MICROPHONE, TEST_SPEAKER_A, NO_FILTERS, on_stopped=stop_recorder.record)
    assert wait_until(lambda: sinks_written_by(PLAYBACK_STREAM_NAME) == [TEST_SPEAKER_A.system_name])

    virtual_devices.unplug(TEST_SPEAKER_A)

    assert wait_until(lambda: stop_recorder.reasons != [])
    assert stop_recorder.reasons == [LinuxAudioLoopback.DEVICE_GONE_REASON]
    assert not loopback.is_running()
    assert sinks_written_by(PLAYBACK_STREAM_NAME) == []


def test_sound_stops_when_the_app_is_killed(virtual_devices):
    command = [
        sys.executable, "-c", APP_THAT_GETS_KILLED,
        TEST_MICROPHONE.system_name, TEST_SPEAKER_A.system_name,
    ]
    app_process = subprocess.Popen(command, stdout=subprocess.PIPE, text=True, cwd=PROJECT_DIR)
    try:
        first_line = app_process.stdout.readline()
        assert first_line.strip() == "STARTED"
        assert wait_until(lambda: sinks_written_by(PLAYBACK_STREAM_NAME) == [TEST_SPEAKER_A.system_name])

        app_process.kill()
        app_process.wait()

        assert wait_until(lambda: sinks_written_by(PLAYBACK_STREAM_NAME) == [])
    finally:
        # A failed assertion must not leave the pretend app running.
        if app_process.poll() is None:
            app_process.kill()
            app_process.wait()


def test_volume_is_applied_at_start_and_while_playing(virtual_devices, loopback):
    stop_recorder = StopRecorder()
    loopback.set_volume(40)

    loopback.start(TEST_MICROPHONE, TEST_SPEAKER_A, NO_FILTERS, on_stopped=stop_recorder.record)

    assert wait_until(lambda: playback_volume_text() == "40%")

    loopback.set_volume(70)

    assert wait_until(lambda: playback_volume_text() == "70%")


def test_every_filter_reported_as_available_can_start(virtual_devices, loopback):
    support = loopback.filter_support()
    filters_to_try = [
        (AudioFilters(echo_canceller=True), support.echo_canceller),
        (AudioFilters(frequency_shifter=True), support.frequency_shifter),
        (AudioFilters(noise_gate=True), support.noise_gate),
    ]
    stop_recorder = StopRecorder()
    tried_count = 0
    for filters, availability in filters_to_try:
        if not availability.is_available:
            continue
        loopback.start(TEST_MICROPHONE, TEST_SPEAKER_A, filters, on_stopped=stop_recorder.record)
        assert wait_until(lambda: sinks_written_by(PLAYBACK_STREAM_NAME) == [TEST_SPEAKER_A.system_name])
        loopback.stop()
        tried_count += 1

    if tried_count == 0:
        pytest.skip("No filter is available on this computer.")
    assert stop_recorder.reasons == []


def test_noise_gate_and_shifter_sit_between_the_microphone_and_the_speaker(virtual_devices, loopback):
    stop_recorder = StopRecorder()
    filters = AudioFilters(noise_gate=True, frequency_shifter=True)
    skip_unless_supported(filters)

    loopback.start(TEST_MICROPHONE, TEST_SPEAKER_A, filters, on_stopped=stop_recorder.record)

    assert wait_until(lambda: sinks_written_by(PLAYBACK_STREAM_NAME) == [TEST_SPEAKER_A.system_name])
    assert sources_read_by(CAPTURE_STREAM_NAME) == [FILTERED_MICROPHONE_NAME]
    assert sources_read_by(FILTERS_CAPTURE_NAME) == [TEST_MICROPHONE.system_name]


def test_echo_canceller_compares_the_microphone_with_the_speaker(virtual_devices, loopback):
    stop_recorder = StopRecorder()
    filters = AudioFilters(echo_canceller=True)
    skip_unless_supported(filters)

    loopback.start(TEST_MICROPHONE, TEST_SPEAKER_A, filters, on_stopped=stop_recorder.record)

    assert wait_until(lambda: sinks_written_by(PLAYBACK_STREAM_NAME) == [TEST_SPEAKER_A.system_name])
    assert sources_read_by(CAPTURE_STREAM_NAME) == [ECHO_CANCEL_SOURCE_NAME]
    assert sources_read_by(ECHO_CANCEL_CAPTURE_NAME) == [TEST_MICROPHONE.system_name]
    monitor_of_speaker_a = TEST_SPEAKER_A.system_name + ".monitor"
    assert sources_read_by(ECHO_CANCEL_REFERENCE_NAME) == [monitor_of_speaker_a]


def test_stop_ends_the_filter_process_and_its_virtual_devices(virtual_devices, loopback):
    stop_recorder = StopRecorder()
    skip_unless_supported(ALL_FILTERS)
    loopback.start(TEST_MICROPHONE, TEST_SPEAKER_A, ALL_FILTERS, on_stopped=stop_recorder.record)
    assert wait_until(lambda: sinks_written_by(PLAYBACK_STREAM_NAME) == [TEST_SPEAKER_A.system_name])

    loopback.stop()

    assert child_process_ids("pipewire -c") == []
    assert wait_until(lambda: own_virtual_devices() == [])
    assert stop_recorder.reasons == []


def test_unplugging_the_speaker_with_all_filters_stops_everything(virtual_devices, loopback):
    stop_recorder = StopRecorder()
    skip_unless_supported(ALL_FILTERS)
    loopback.start(TEST_MICROPHONE, TEST_SPEAKER_A, ALL_FILTERS, on_stopped=stop_recorder.record)
    assert wait_until(lambda: sinks_written_by(PLAYBACK_STREAM_NAME) == [TEST_SPEAKER_A.system_name])

    virtual_devices.unplug(TEST_SPEAKER_A)

    assert wait_until(lambda: stop_recorder.reasons != [])
    assert not loopback.is_running()
    assert child_process_ids("pipewire -c") == []
    assert wait_until(lambda: own_virtual_devices() == [])


def test_unplugging_the_microphone_with_filters_stops_everything(virtual_devices, loopback):
    stop_recorder = StopRecorder()
    filters = AudioFilters(noise_gate=True)
    skip_unless_supported(filters)
    loopback.start(TEST_MICROPHONE, TEST_SPEAKER_A, filters, on_stopped=stop_recorder.record)
    assert wait_until(lambda: sinks_written_by(PLAYBACK_STREAM_NAME) == [TEST_SPEAKER_A.system_name])

    virtual_devices.unplug(TEST_MICROPHONE)

    assert wait_until(lambda: stop_recorder.reasons != [])
    assert not loopback.is_running()
    assert child_process_ids("pipewire -c") == []


def test_noise_gate_blocks_a_quiet_tone_and_passes_a_loud_one(tone_microphone, tone_files, loopback):
    stop_recorder = StopRecorder()
    filters = AudioFilters(noise_gate=True)
    skip_unless_supported(filters)
    loopback.start(TONE_MICROPHONE, TEST_SPEAKER_A, filters, on_stopped=stop_recorder.record)
    assert wait_until(lambda: sinks_written_by(PLAYBACK_STREAM_NAME) == [TEST_SPEAKER_A.system_name])

    quiet_level = speaker_level_while_playing(tone_microphone, tone_files.quiet)
    loud_level = speaker_level_while_playing(tone_microphone, tone_files.loud)

    assert quiet_level < -100
    assert loud_level > LOUD_TONE_DBFS - 10


def test_frequency_shifter_keeps_the_volume(tone_microphone, tone_files, loopback):
    stop_recorder = StopRecorder()
    skip_unless_supported(AudioFilters(frequency_shifter=True))
    loopback.start(TONE_MICROPHONE, TEST_SPEAKER_A, NO_FILTERS, on_stopped=stop_recorder.record)
    assert wait_until(lambda: sinks_written_by(PLAYBACK_STREAM_NAME) == [TEST_SPEAKER_A.system_name])
    level_without_filter = speaker_level_while_playing(tone_microphone, tone_files.loud)

    filters = AudioFilters(frequency_shifter=True)
    loopback.start(TONE_MICROPHONE, TEST_SPEAKER_A, filters, on_stopped=stop_recorder.record)
    assert wait_until(lambda: sinks_written_by(PLAYBACK_STREAM_NAME) == [TEST_SPEAKER_A.system_name])
    level_with_filter = speaker_level_while_playing(tone_microphone, tone_files.loud)

    assert abs(level_with_filter - level_without_filter) < 2


def test_watcher_reports_a_device_being_plugged_in_and_out(virtual_devices, device_watcher):
    change_counter = ChangeCounter()
    device_watcher.start(on_devices_changed=change_counter.record)
    keep_qt_running_for(WATCHER_START_SECONDS)

    virtual_devices.add_speaker(TEST_SPEAKER_C)
    assert wait_until(lambda: change_counter.count >= 1)
    count_after_plugging_in = change_counter.count

    virtual_devices.unplug(TEST_SPEAKER_C)
    assert wait_until(lambda: change_counter.count > count_after_plugging_in)


def test_watcher_ignores_the_apps_own_sound(virtual_devices, device_watcher, loopback):
    change_counter = ChangeCounter()
    device_watcher.start(on_devices_changed=change_counter.record)
    keep_qt_running_for(WATCHER_START_SECONDS)
    stop_recorder = StopRecorder()

    loopback.start(TEST_MICROPHONE, TEST_SPEAKER_A, NO_FILTERS, on_stopped=stop_recorder.record)
    assert wait_until(lambda: sinks_written_by(PLAYBACK_STREAM_NAME) == [TEST_SPEAKER_A.system_name])
    loopback.stop()
    keep_qt_running_for(1.0)

    assert change_counter.count == 0


def test_watcher_comes_back_after_pactl_subscribe_dies(virtual_devices, device_watcher):
    change_counter = ChangeCounter()
    device_watcher.start(on_devices_changed=change_counter.record)
    keep_qt_running_for(WATCHER_START_SECONDS)
    first_process_ids = child_process_ids("pactl subscribe")
    assert len(first_process_ids) == 1

    os.kill(first_process_ids[0], signal.SIGKILL)

    # After the restart the watcher reports one change, so the lists are read again.
    assert wait_until(lambda: change_counter.count >= 1, timeout_seconds=WATCHER_RESTART_TIMEOUT_SECONDS)
    second_process_ids = child_process_ids("pactl subscribe")
    assert len(second_process_ids) == 1
    assert second_process_ids != first_process_ids
