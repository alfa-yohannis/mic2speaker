"""Start-up code: pick the audio adapters, create the Qt application, show the form."""

import sys

from PyQt5.QtWidgets import QApplication

from mic2speaker.audio.audio_device_provider import AudioDeviceProvider
from mic2speaker.audio.audio_device_watcher import AudioDeviceWatcher
from mic2speaker.audio.audio_loopback import AudioLoopback
from mic2speaker.audio.linux_audio_device_provider import LinuxAudioDeviceProvider
from mic2speaker.audio.linux_audio_device_watcher import LinuxAudioDeviceWatcher
from mic2speaker.audio.linux_audio_loopback import LinuxAudioLoopback
from mic2speaker.ui.main_window import MainWindow


class UnsupportedPlatformError(Exception):
    """Raised when there is no audio adapter for this operating system yet."""


class Mic2SpeakerApp:
    """Owns the Qt application object and the main window for one run."""

    APPLICATION_NAME = "Mic2Speaker"

    def __init__(self, command_line_args: list[str]) -> None:
        self._qt_application = QApplication(command_line_args)
        self._qt_application.setApplicationName(self.APPLICATION_NAME)
        device_provider = self._create_device_provider()
        audio_loopback = self._create_audio_loopback()
        device_watcher = self._create_device_watcher()
        self._main_window = MainWindow(device_provider, audio_loopback, device_watcher)

    def run(self) -> int:
        """Show the main window and wait until the user closes it.

        Returns the exit code for the process.
        """
        self._main_window.show()
        exit_code = self._qt_application.exec_()
        return exit_code

    @staticmethod
    def _create_device_provider() -> AudioDeviceProvider:
        """Return the adapter that lists audio devices on this operating system.

        Only Linux has adapters so far. The Windows ones will be picked here
        and in the two methods below once they exist.
        """
        if sys.platform.startswith("linux"):
            return LinuxAudioDeviceProvider()
        raise UnsupportedPlatformError(f"Mic2Speaker does not support {sys.platform} yet.")

    @staticmethod
    def _create_audio_loopback() -> AudioLoopback:
        """Return the adapter that plays a microphone through a speaker on this operating system."""
        if sys.platform.startswith("linux"):
            return LinuxAudioLoopback()
        raise UnsupportedPlatformError(f"Mic2Speaker does not support {sys.platform} yet.")

    @staticmethod
    def _create_device_watcher() -> AudioDeviceWatcher:
        """Return the adapter that notices devices being plugged in or out on this operating system."""
        if sys.platform.startswith("linux"):
            return LinuxAudioDeviceWatcher()
        raise UnsupportedPlatformError(f"Mic2Speaker does not support {sys.platform} yet.")


def main() -> int:
    """Run the app with the current command-line arguments."""
    try:
        app = Mic2SpeakerApp(sys.argv)
    except UnsupportedPlatformError as error:
        print(error, file=sys.stderr)
        return 1
    exit_code = app.run()
    return exit_code
