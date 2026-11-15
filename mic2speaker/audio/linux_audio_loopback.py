"""Linux adapter that plays a microphone through a speaker with ``pw-loopback``.

``pw-loopback`` is a small PipeWire program that copies sound from one device
to another for as long as it runs. This adapter starts it when the sound is
switched on and ends it when the sound is switched off.
"""

import shutil
from collections.abc import Callable

from PyQt5.QtCore import QProcess

from mic2speaker.audio.audio_device import AudioDevice
from mic2speaker.audio.audio_loopback import AudioLoopback, AudioLoopbackError
from mic2speaker.audio.linux_child_process import command_that_ends_with_app


class LinuxAudioLoopback(AudioLoopback):
    """Routes the sound by running ``pw-loopback`` in the background.

    Both ends are pinned to the chosen devices with
    ``node.dont-reconnect=true``. If a device is unplugged, PipeWire ends the
    stream instead of moving the sound to another speaker, pw-loopback exits,
    and the ``on_stopped`` callback reports it.
    """

    PW_LOOPBACK_COMMAND = "pw-loopback"
    LOOPBACK_NAME = "mic2speaker"
    STREAM_PROPERTIES = "node.dont-reconnect=true media.name=Mic2Speaker"

    # How long the sound waits in the buffer, in milliseconds. Lower is more
    # immediate; raise it (for example to 20) if the sound crackles.
    LATENCY_MS = 10

    START_TIMEOUT_MS = 3000
    STOP_TIMEOUT_MS = 2000
    DEVICE_GONE_REASON = "the microphone or speaker is no longer available."

    def __init__(self) -> None:
        """Create a loopback that is not playing yet."""
        self._process: QProcess | None = None
        self._on_stopped: Callable[[str], None] | None = None

    def start(
        self,
        microphone: AudioDevice,
        speaker: AudioDevice,
        on_stopped: Callable[[str], None],
    ) -> None:
        """Start pw-loopback from ``microphone`` to ``speaker``.

        Raises AudioLoopbackError if pw-loopback is missing or does not start.
        """
        self.stop()
        pw_loopback_path = shutil.which(self.PW_LOOPBACK_COMMAND)
        if pw_loopback_path is None:
            raise AudioLoopbackError("pw-loopback is not installed. It comes with PipeWire.")

        command = self._build_command(microphone, speaker)
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
            error_text = process.errorString()
            raise AudioLoopbackError(f"pw-loopback did not start: {error_text}")

    def stop(self) -> None:
        """End pw-loopback if it is running. ``on_stopped`` is not called."""
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

    def is_running(self) -> bool:
        """Return True while pw-loopback is running."""
        if self._process is None:
            return False
        process_state = self._process.state()
        return process_state != QProcess.NotRunning

    def _build_command(self, microphone: AudioDevice, speaker: AudioDevice) -> list[str]:
        """Return the command line that copies sound from ``microphone`` to ``speaker``.

        The command is wrapped so that pw-loopback ends when the app dies,
        even after a crash.
        """
        latency_text = str(self.LATENCY_MS)
        pw_loopback_command = [
            self.PW_LOOPBACK_COMMAND,
            "--name", self.LOOPBACK_NAME,
            "--latency", latency_text,
            "--capture", microphone.system_name,
            "--capture-props", self.STREAM_PROPERTIES,
            "--playback", speaker.system_name,
            "--playback-props", self.STREAM_PROPERTIES,
        ]
        return command_that_ends_with_app(pw_loopback_command)

    def _handle_process_finished(self) -> None:
        """Called by Qt when pw-loopback exits without stop() asking it to.

        The process object stays in ``self._process`` until the next start().
        Qt is still sending the finished signal at this point, and deleting
        the object now could crash the app.
        """
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
