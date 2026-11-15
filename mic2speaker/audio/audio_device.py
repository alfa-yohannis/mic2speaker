"""The AudioDevice class, shared by the form and the audio adapters."""

from dataclasses import dataclass


@dataclass(frozen=True)
class AudioDevice:
    """A microphone or speaker as the operating system reports it.

    Attributes:
        system_name: The name the audio system uses for the device, for
            example "alsa_input.usb-...mono-fallback". It stays the same
            between runs, so it is safe to save and look up later.
        display_name: The name shown to the user, for example "USB Audio Mono".
        is_default: True if the operating system currently uses this device
            by default.
    """

    system_name: str
    display_name: str
    is_default: bool = False
