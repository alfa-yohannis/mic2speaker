"""The AudioFilters class: which anti-feedback filters the user switched on."""

from dataclasses import dataclass


@dataclass(frozen=True)
class AudioFilters:
    """The optional filters between the microphone and the speaker.

    Attributes:
        echo_canceller: Remove the speaker's sound from the microphone signal.
        frequency_shifter: Shift the sound up a few hertz, so that feedback
            builds up more slowly.
        noise_gate: Mute the microphone while nobody speaks.
    """

    echo_canceller: bool = False
    frequency_shifter: bool = False
    noise_gate: bool = False

    def any_enabled(self) -> bool:
        """Return True if at least one filter is switched on."""
        return self.echo_canceller or self.frequency_shifter or self.noise_gate

    def enabled_names(self) -> list[str]:
        """Return the names of the switched-on filters, for messages to the user."""
        names = []
        if self.echo_canceller:
            names.append("echo canceller")
        if self.frequency_shifter:
            names.append("frequency shifter")
        if self.noise_gate:
            names.append("noise gate")
        return names
