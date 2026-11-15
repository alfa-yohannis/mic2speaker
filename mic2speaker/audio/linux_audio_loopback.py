"""Linux adapter that plays a microphone through a speaker with ``pw-loopback``.

``pw-loopback`` is a small PipeWire program that copies sound from one device
to another for as long as it runs. This adapter starts it when the sound is
switched on and ends it when the sound is switched off. When filters are
switched on, LinuxFilterProcess runs them first, and pw-loopback reads the
filtered virtual microphone instead of the real one.
"""

import shutil
import time
from collections.abc import Callable

from PyQt5.QtCore import QProcess

from mic2speaker.audio.audio_device import AudioDevice
from mic2speaker.audio.audio_filters import AudioFilters
from mic2speaker.audio.audio_loopback import AudioLoopback, AudioLoopbackError
from mic2speaker.audio.linux_child_process import command_that_ends_with_app
from mic2speaker.audio.linux_filter_process import LinuxFilterProcess
from mic2speaker.audio.linux_node_names import LOOPBACK_NAME, PLAYBACK_STREAM_NAME
from mic2speaker.audio.linux_pactl import PactlError, read_pactl_list, run_pactl


class LinuxAudioLoopback(AudioLoopback):
    """Routes the sound by running ``pw-loopback`` in the background.

    Both ends are pinned to the chosen devices with
    ``node.dont-reconnect=true``. If a device is unplugged, PipeWire ends the
    stream instead of moving the sound to another speaker, pw-loopback exits,
    and the ``on_stopped`` callback reports it.

    The volume is the volume of pw-loopback's playback stream, set with
    ``pactl set-sink-input-volume``.
    """

    PW_LOOPBACK_COMMAND = "pw-loopback"
    STREAM_PROPERTIES = "node.dont-reconnect=true media.name=Mic2Speaker"

    # How long the sound waits in the buffer, in milliseconds. Lower is more
    # immediate; raise it (for example to 20) if the sound crackles.
    LATENCY_MS = 10

    START_TIMEOUT_MS = 3000
    STOP_TIMEOUT_MS = 2000
    STREAM_WAIT_TIMEOUT_SECONDS = 2.0
    POLL_INTERVAL_SECONDS = 0.05
    DEVICE_GONE_REASON = "the microphone or speaker is no longer available."

    def __init__(self) -> None:
        """Create a loopback that is not playing yet."""
        self._process: QProcess | None = None
        self._on_stopped: Callable[[str], None] | None = None
        self._filter_process = LinuxFilterProcess()
        self._volume_percent = self.DEFAULT_VOLUME_PERCENT
        self._playback_stream_index: int | None = None

    def start(
        self,
        microphone: AudioDevice,
        speaker: AudioDevice,
        filters: AudioFilters,
        on_stopped: Callable[[str], None],
    ) -> None:
        """Start the filters, if any, and then pw-loopback from the microphone to ``speaker``.

        Raises AudioLoopbackError if pw-loopback or a filter is missing, or
        if they do not start.
        """
        self.stop()
        pw_loopback_path = shutil.which(self.PW_LOOPBACK_COMMAND)
        if pw_loopback_path is None:
            raise AudioLoopbackError("pw-loopback is not installed. It comes with PipeWire.")

        capture_target_name = microphone.system_name
        if filters.any_enabled():
            capture_target_name = self._filter_process.start(microphone, speaker, filters)

        command = self._build_command(capture_target_name, speaker.system_name)
        self._start_pw_loopback(command, on_stopped)
        self._playback_stream_index = self._wait_for_playback_stream()
        self._apply_volume()

    def stop(self) -> None:
        """End pw-loopback and the filters if they run. ``on_stopped`` is not called."""
        self._end_pw_loopback()
        self._filter_process.stop()
        self._playback_stream_index = None

    def is_running(self) -> bool:
        """Return True while pw-loopback is running."""
        if self._process is None:
            return False
        process_state = self._process.state()
        return process_state != QProcess.NotRunning

    def set_volume(self, volume_percent: int) -> None:
        """Remember the volume, and apply it right away if the sound is playing."""
        self._volume_percent = volume_percent
        if self.is_running():
            self._apply_volume()

    def _build_command(self, capture_target_name: str, playback_target_name: str) -> list[str]:
        """Return the command line that copies sound from one node to the other.

        The command is wrapped so that pw-loopback ends when the app dies,
        even after a crash.
        """
        latency_text = str(self.LATENCY_MS)
        pw_loopback_command = [
            self.PW_LOOPBACK_COMMAND,
            "--name", LOOPBACK_NAME,
            "--latency", latency_text,
            "--capture", capture_target_name,
            "--capture-props", self.STREAM_PROPERTIES,
            "--playback", playback_target_name,
            "--playback-props", self.STREAM_PROPERTIES,
        ]
        return command_that_ends_with_app(pw_loopback_command)

    def _start_pw_loopback(self, command: list[str], on_stopped: Callable[[str], None]) -> None:
        """Run ``command`` in a QProcess and listen for it ending.

        Raises AudioLoopbackError, after stopping the filters, if it does not start.
        """
        program = command[0]
        arguments = command[1:]
        process = QProcess()
        process.setProgram(program)
        process.setArguments(arguments)
        process.setProcessChannelMode(QProcess.MergedChannels)
        process.finished.connect(self._handle_process_finished)
        self._process = process
        self._on_stopped = on_stopped
        process.start()

        started = process.waitForStarted(self.START_TIMEOUT_MS)
        if not started:
            self._filter_process.stop()
            error_text = process.errorString()
            raise AudioLoopbackError(f"pw-loopback did not start: {error_text}")

    def _end_pw_loopback(self) -> None:
        """End pw-loopback if it is running, without reporting it as an unexpected stop."""
        if not self.is_running():
            return
        process = self._process
        # Ending it on purpose is not an unexpected stop, so stop listening first.
        process.finished.disconnect(self._handle_process_finished)
        process.terminate()
        finished_in_time = process.waitForFinished(self.STOP_TIMEOUT_MS)
        if not finished_in_time:
            process.kill()
            process.waitForFinished(self.STOP_TIMEOUT_MS)

    def _wait_for_playback_stream(self) -> int | None:
        """Wait until pw-loopback's playback stream appears and return its pactl index.

        Returns None if it does not appear in time, for example because a
        device is missing; pw-loopback then exits and reports the stop.
        """
        deadline = time.monotonic() + self.STREAM_WAIT_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            stream_index = self._find_playback_stream_index()
            if stream_index is not None:
                return stream_index
            time.sleep(self.POLL_INTERVAL_SECONDS)
        return None

    @staticmethod
    def _find_playback_stream_index() -> int | None:
        """Return the pactl index of pw-loopback's playback stream, or None if it is not there."""
        try:
            playback_streams = read_pactl_list("sink-inputs")
        except PactlError:
            return None
        for stream in playback_streams:
            stream_name = stream["properties"].get("node.name")
            if stream_name == PLAYBACK_STREAM_NAME:
                return stream["index"]
        return None

    def _apply_volume(self) -> None:
        """Set the playback stream's volume to the remembered value.

        Raises AudioLoopbackError if pactl cannot change it.
        """
        if self._playback_stream_index is None:
            return
        stream_index_text = str(self._playback_stream_index)
        volume_text = f"{self._volume_percent}%"
        try:
            run_pactl(["set-sink-input-volume", stream_index_text, volume_text])
        except PactlError as error:
            error_text = str(error)
            raise AudioLoopbackError(error_text) from error

    def _handle_process_finished(self) -> None:
        """Called by Qt when pw-loopback exits without stop() asking it to.

        The filters are stopped as well. The process object stays in
        ``self._process`` until the next start(): Qt is still sending the
        finished signal at this point, and deleting the object now could
        crash the app.
        """
        self._filter_process.stop()
        self._playback_stream_index = None
        output_text = self._read_process_output()
        if output_text:
            reason = output_text
        else:
            reason = self.DEVICE_GONE_REASON
        self._on_stopped(reason)

    def _read_process_output(self) -> str:
        """Return what pw-loopback printed, without surrounding blank lines."""
        output_bytes = self._process.readAllStandardOutput()
        raw_output = output_bytes.data()
        output_text = raw_output.decode("utf-8", errors="replace")
        return output_text.strip()
