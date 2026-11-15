"""The interface that every operating system's sound-routing adapter implements."""

from abc import ABC, abstractmethod
from collections.abc import Callable

from mic2speaker.audio.audio_device import AudioDevice


class AudioLoopbackError(Exception):
    """Raised when the sound cannot be routed from the microphone to the speaker."""


class AudioLoopback(ABC):
    """Plays a microphone through a speaker until it is told to stop.

    Each operating system has its own subclass (an adapter), for example
    LinuxAudioLoopback. The form only calls the methods below, so a Windows
    adapter can be added later without changing the form.
    """

    @abstractmethod
    def start(
        self,
        microphone: AudioDevice,
        speaker: AudioDevice,
        on_stopped: Callable[[str], None],
    ) -> None:
        """Start playing ``microphone`` through ``speaker``.

        Sound that is already playing is stopped first. If the sound later
        stops by itself, for example because a device was unplugged,
        ``on_stopped`` is called with a short reason. It is not called when
        ``stop()`` ends the sound.

        Raises AudioLoopbackError if the sound cannot be started.
        """

    @abstractmethod
    def stop(self) -> None:
        """Stop the sound. Does nothing if no sound is playing."""

    @abstractmethod
    def is_running(self) -> bool:
        """Return True while the microphone is playing through the speaker."""
