"""Stand-ins for the audio adapters, so the form can be tested without real audio."""

from collections.abc import Callable

from mic2speaker.audio.audio_device import AudioDevice
from mic2speaker.audio.audio_device_provider import AudioDeviceError, AudioDeviceProvider
from mic2speaker.audio.audio_device_watcher import AudioDeviceWatcher
from mic2speaker.audio.audio_loopback import AudioLoopback, AudioLoopbackError


class FakeDeviceProvider(AudioDeviceProvider):
    """Returns device lists that a test sets, or fails when the test asks it to."""

    def __init__(self, microphones: list[AudioDevice], speakers: list[AudioDevice]) -> None:
        self.microphones = microphones
        self.speakers = speakers
        self.error_message: str | None = None

    def list_microphones(self) -> list[AudioDevice]:
        """Return the microphones the test set, or raise if error_message is set."""
        self._raise_if_failing()
        return self.microphones

    def list_speakers(self) -> list[AudioDevice]:
        """Return the speakers the test set, or raise if error_message is set."""
        self._raise_if_failing()
        return self.speakers

    def _raise_if_failing(self) -> None:
        """Raise AudioDeviceError when the test has set an error message."""
        if self.error_message is not None:
            raise AudioDeviceError(self.error_message)


class FakeAudioLoopback(AudioLoopback):
    """Records what the form asks for instead of playing sound.

    Attributes:
        started_routes: One (microphone, speaker) pair for every start() call.
        start_error_message: When set, start() fails with this message.
    """

    def __init__(self) -> None:
        self.started_routes: list[tuple[AudioDevice, AudioDevice]] = []
        self.start_error_message: str | None = None
        self._running = False
        self._on_stopped: Callable[[str], None] | None = None

    def start(
        self,
        microphone: AudioDevice,
        speaker: AudioDevice,
        on_stopped: Callable[[str], None],
    ) -> None:
        """Remember the route, or fail if the test set start_error_message."""
        if self.start_error_message is not None:
            raise AudioLoopbackError(self.start_error_message)
        self.started_routes.append((microphone, speaker))
        self._running = True
        self._on_stopped = on_stopped

    def stop(self) -> None:
        """Mark the sound as stopped."""
        self._running = False

    def is_running(self) -> bool:
        """Return True between start() and stop()."""
        return self._running

    def stop_by_itself(self, reason: str) -> None:
        """Pretend the sound stopped on its own, for example because a device was unplugged."""
        self._running = False
        self._on_stopped(reason)


class FakeDeviceWatcher(AudioDeviceWatcher):
    """Reports a device change only when the test calls report_change()."""

    def __init__(self) -> None:
        self.is_watching = False
        self._on_devices_changed: Callable[[], None] | None = None

    def start(self, on_devices_changed: Callable[[], None]) -> None:
        """Remember the callback and mark the watcher as running."""
        self.is_watching = True
        self._on_devices_changed = on_devices_changed

    def stop(self) -> None:
        """Mark the watcher as stopped."""
        self.is_watching = False

    def report_change(self) -> None:
        """Pretend a device was plugged in or out."""
        self._on_devices_changed()
