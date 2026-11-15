"""Integration tests for the Linux adapters against the real PipeWire server.

Each test creates temporary virtual devices: a silent microphone and
speakers that play into nothing. No sound reaches the real speakers, and the
virtual devices are removed again after each test. The tests are skipped when
pactl or pw-loopback is missing.
"""

import json
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest
from PyQt5.QtWidgets import QApplication

from mic2speaker.audio.audio_device import AudioDevice
from mic2speaker.audio.linux_audio_device_provider import LinuxAudioDeviceProvider
from mic2speaker.audio.linux_audio_device_watcher import LinuxAudioDeviceWatcher
from mic2speaker.audio.linux_audio_loopback import LinuxAudioLoopback

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
CAPTURE_STREAM_NAME = "input.mic2speaker"
PLAYBACK_STREAM_NAME = "output.mic2speaker"
WAIT_TIMEOUT_SECONDS = 3.0
WATCHER_RESTART_TIMEOUT_SECONDS = 5.0
WATCHER_START_SECONDS = 0.5
POLL_INTERVAL_SECONDS = 0.05

# Runs in a separate process: start the sound, say so, then wait to be killed.
APP_THAT_GETS_KILLED = """
import sys
from PyQt5.QtCore import QCoreApplication
from mic2speaker.audio.audio_device import AudioDevice
from mic2speaker.audio.linux_audio_loopback import LinuxAudioLoopback

application = QCoreApplication(sys.argv)
loopback = LinuxAudioLoopback()
microphone = AudioDevice(sys.argv[1], "microphone")
speaker = AudioDevice(sys.argv[2], "speaker")
loopback.start(microphone, speaker, on_stopped=print)
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


def capture_sources() -> list[str]:
    """Return the names of the devices our capture stream reads from."""
    source_names = device_names_by_index("sources")
    connected = []
    for stream in read_pactl_list("source-outputs"):
        if stream["properties"].get("node.name") == CAPTURE_STREAM_NAME:
            source_name = source_names.get(stream["source"])
            connected.append(source_name)
    return connected


def playback_sinks() -> list[str]:
    """Return the names of the devices our playback stream writes to."""
    sink_names = device_names_by_index("sinks")
    connected = []
    for stream in read_pactl_list("sink-inputs"):
        if stream["properties"].get("node.name") == PLAYBACK_STREAM_NAME:
            sink_name = sink_names.get(stream["sink"])
            connected.append(sink_name)
    return connected


def our_pactl_subscribe_process_id() -> int | None:
    """Return the id of the ``pactl subscribe`` process that this test process started."""
    test_process_id = str(os.getpid())
    command = ["pgrep", "-P", test_process_id, "-f", "pactl subscribe"]
    completed_process = subprocess.run(command, capture_output=True, text=True)
    output = completed_process.stdout.strip()
    if not output:
        return None
    first_line = output.splitlines()[0]
    return int(first_line)


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


@pytest.fixture
def virtual_devices(qt_application) -> VirtualDevices:
    """A virtual microphone and two virtual speakers, removed after the test."""
    devices = VirtualDevices()
    devices.add_microphone(TEST_MICROPHONE)
    devices.add_speaker(TEST_SPEAKER_A)
    devices.add_speaker(TEST_SPEAKER_B)
    yield devices
    devices.remove_all()


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

    loopback.start(TEST_MICROPHONE, TEST_SPEAKER_A, on_stopped=stop_recorder.record)

    assert wait_until(lambda: playback_sinks() == [TEST_SPEAKER_A.system_name])
    assert capture_sources() == [TEST_MICROPHONE.system_name]
    assert loopback.is_running()

    loopback.stop()

    assert not loopback.is_running()
    assert wait_until(lambda: playback_sinks() == [])
    assert stop_recorder.reasons == []


def test_starting_again_moves_the_sound_to_the_new_speaker(virtual_devices, loopback):
    stop_recorder = StopRecorder()
    loopback.start(TEST_MICROPHONE, TEST_SPEAKER_A, on_stopped=stop_recorder.record)

    loopback.start(TEST_MICROPHONE, TEST_SPEAKER_B, on_stopped=stop_recorder.record)

    assert wait_until(lambda: playback_sinks() == [TEST_SPEAKER_B.system_name])
    assert stop_recorder.reasons == []


def test_unplugging_the_speaker_stops_the_sound_instead_of_moving_it(virtual_devices, loopback):
    stop_recorder = StopRecorder()
    loopback.start(TEST_MICROPHONE, TEST_SPEAKER_A, on_stopped=stop_recorder.record)
    assert wait_until(lambda: playback_sinks() == [TEST_SPEAKER_A.system_name])

    virtual_devices.unplug(TEST_SPEAKER_A)

    assert wait_until(lambda: stop_recorder.reasons != [])
    assert stop_recorder.reasons == [LinuxAudioLoopback.DEVICE_GONE_REASON]
    assert not loopback.is_running()
    assert playback_sinks() == []


def test_sound_stops_when_the_app_is_killed(virtual_devices):
    command = [
        sys.executable, "-c", APP_THAT_GETS_KILLED,
        TEST_MICROPHONE.system_name, TEST_SPEAKER_A.system_name,
    ]
    app_process = subprocess.Popen(command, stdout=subprocess.PIPE, text=True, cwd=PROJECT_DIR)
    first_line = app_process.stdout.readline()
    assert first_line.strip() == "STARTED"
    assert wait_until(lambda: playback_sinks() == [TEST_SPEAKER_A.system_name])

    app_process.kill()
    app_process.wait()

    assert wait_until(lambda: playback_sinks() == [])


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

    loopback.start(TEST_MICROPHONE, TEST_SPEAKER_A, on_stopped=stop_recorder.record)
    assert wait_until(lambda: playback_sinks() == [TEST_SPEAKER_A.system_name])
    loopback.stop()
    keep_qt_running_for(1.0)

    assert change_counter.count == 0


def test_watcher_comes_back_after_pactl_subscribe_dies(virtual_devices, device_watcher):
    change_counter = ChangeCounter()
    device_watcher.start(on_devices_changed=change_counter.record)
    keep_qt_running_for(WATCHER_START_SECONDS)
    first_process_id = our_pactl_subscribe_process_id()
    assert first_process_id is not None

    os.kill(first_process_id, signal.SIGKILL)

    # After the restart the watcher reports one change, so the lists are read again.
    assert wait_until(lambda: change_counter.count >= 1, timeout_seconds=WATCHER_RESTART_TIMEOUT_SECONDS)
    second_process_id = our_pactl_subscribe_process_id()
    assert second_process_id is not None
    assert second_process_id != first_process_id
