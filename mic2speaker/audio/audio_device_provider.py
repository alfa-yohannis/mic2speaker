"""The interface that every operating system's device adapter implements."""

from abc import ABC, abstractmethod

from mic2speaker.audio.audio_device import AudioDevice


class AudioDeviceError(Exception):
    """Raised when the audio system cannot be asked for its devices."""


class AudioDeviceProvider(ABC):
    """Lists the microphones and speakers on this computer.

    Each operating system has its own subclass (an adapter), for example
    LinuxAudioDeviceProvider. The form only calls the methods below, so a
    Windows adapter can be added later without changing the form.
    """

    @abstractmethod
    def list_microphones(self) -> list[AudioDevice]:
        """Return every microphone the user can pick.

        Raises AudioDeviceError if the audio system cannot be reached.
        """

    @abstractmethod
    def list_speakers(self) -> list[AudioDevice]:
        """Return every speaker the user can pick.

        Raises AudioDeviceError if the audio system cannot be reached.
        """
