"""The interface for noticing when audio devices are plugged in or out."""

from abc import ABC, abstractmethod
from collections.abc import Callable


class AudioDeviceWatcher(ABC):
    """Tells the form when the lists of microphones or speakers may have changed.

    Each operating system has its own subclass (an adapter), for example
    LinuxAudioDeviceWatcher. After a change, the form reads the lists again
    from its AudioDeviceProvider.
    """

    @abstractmethod
    def start(self, on_devices_changed: Callable[[], None]) -> None:
        """Start watching.

        ``on_devices_changed`` is called on the Qt main thread after a device
        was plugged in or out, or after the system default device changed.
        A burst of changes may lead to a single call.
        """

    @abstractmethod
    def stop(self) -> None:
        """Stop watching. Does nothing if the watcher is not running."""
