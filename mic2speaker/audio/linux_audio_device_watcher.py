"""Linux adapter that notices when audio devices are plugged in or out.

It runs ``pactl subscribe``, which prints one line for every change on the
audio server, and reacts to the lines about microphones (sources), speakers
(sinks), and the server's default devices.
"""

import shutil
from collections.abc import Callable

from PyQt5.QtCore import QProcess, QProcessEnvironment, QTimer

from mic2speaker.audio.audio_device_watcher import AudioDeviceWatcher
from mic2speaker.audio.linux_child_process import command_that_ends_with_app

# (event type, facility) pairs that mean the device lists may have changed.
# "change" on a sink or source is left out: it fires on every volume change
# and whenever a device starts or stops playing, including for our own sound.
DEVICE_CHANGE_EVENTS = {
    ("new", "sink"),
    ("remove", "sink"),
    ("new", "source"),
    ("remove", "source"),
    ("change", "server"),
}


def is_device_change_line(line: str) -> bool:
    """Tell whether one ``pactl subscribe`` line reports a device change.

    The lines look like ``Event 'new' on sink #57``.
    """
    words = line.split()
    if len(words) < 4 or words[0] != "Event":
        return False
    event_type = words[1].strip("'")
    facility = words[3]
    return (event_type, facility) in DEVICE_CHANGE_EVENTS


class LinuxAudioDeviceWatcher(AudioDeviceWatcher):
    """Reports devices being plugged in or out, using ``pactl subscribe``.

    Plugging in one USB headset produces several events in a row, so the
    watcher waits until the events have been quiet for SETTLE_TIME_MS and
    then calls back once. If ``pactl subscribe`` exits, for example because
    the audio server restarted, it is started again after RESTART_DELAY_MS.
    """

    PACTL_COMMAND = "pactl"
    PACTL_SUBSCRIBE_COMMAND = ["pactl", "subscribe"]
    SETTLE_TIME_MS = 300
    RESTART_DELAY_MS = 2000
    STOP_TIMEOUT_MS = 1000

    def __init__(self) -> None:
        """Create a watcher that is not watching yet. A QApplication must exist already."""
        self._process: QProcess | None = None
        self._on_devices_changed: Callable[[], None] | None = None

        self._settle_timer = QTimer()
        self._settle_timer.setSingleShot(True)
        self._settle_timer.setInterval(self.SETTLE_TIME_MS)
        self._settle_timer.timeout.connect(self._report_change)

        self._restart_timer = QTimer()
        self._restart_timer.setSingleShot(True)
        self._restart_timer.setInterval(self.RESTART_DELAY_MS)
        self._restart_timer.timeout.connect(self._restart_process)

    def start(self, on_devices_changed: Callable[[], None]) -> None:
        """Start ``pactl subscribe``. Without pactl the watcher stays idle."""
        self.stop()
        self._on_devices_changed = on_devices_changed
        pactl_path = shutil.which(self.PACTL_COMMAND)
        if pactl_path is None:
            return
        self._start_process()

    def stop(self) -> None:
        """End ``pactl subscribe`` and forget any pending change."""
        self._settle_timer.stop()
        self._restart_timer.stop()
        if self._process is None:
            return
        process = self._process
        self._process = None
        # Ending it on purpose must not schedule a restart.
        process.finished.disconnect(self._handle_process_finished)
        process.kill()
        process.waitForFinished(self.STOP_TIMEOUT_MS)

    def _start_process(self) -> None:
        """Run ``pactl subscribe`` and listen to what it prints."""
        command = command_that_ends_with_app(self.PACTL_SUBSCRIBE_COMMAND)
        program = command[0]
        arguments = command[1:]

        # pactl translates its messages; the C locale keeps the English
        # "Event ... on ..." form that is_device_change_line() reads.
        environment = QProcessEnvironment.systemEnvironment()
        environment.insert("LC_ALL", "C")

        process = QProcess()
        process.setProgram(program)
        process.setArguments(arguments)
        process.setProcessEnvironment(environment)
        process.readyReadStandardOutput.connect(self._read_events)
        process.finished.connect(self._handle_process_finished)
        self._process = process
        process.start()

    def _read_events(self) -> None:
        """Read every complete line ``pactl subscribe`` printed and react to device changes."""
        while self._process.canReadLine():
            line_bytes = self._process.readLine()
            raw_line = line_bytes.data()
            line = raw_line.decode("utf-8", errors="replace")
            if is_device_change_line(line):
                # Restarting the timer turns a burst of events into one call.
                self._settle_timer.start()

    def _report_change(self) -> None:
        """Call back once the burst of events has settled."""
        self._on_devices_changed()

    def _handle_process_finished(self) -> None:
        """Called by Qt when ``pactl subscribe`` exits by itself; try again later.

        The process object stays in ``self._process`` until the restart,
        because Qt is still sending the finished signal at this point.
        """
        self._restart_timer.start()

    def _restart_process(self) -> None:
        """Start ``pactl subscribe`` again and report a change.

        Devices may have come or gone while the watcher was down, so the form
        reads the lists again.
        """
        self._start_process()
        self._settle_timer.start()
