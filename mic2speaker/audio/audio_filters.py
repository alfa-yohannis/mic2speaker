"""Which anti-feedback filters the user switched on, and which ones this computer can run."""

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


@dataclass(frozen=True)
class FilterAvailability:
    """Whether one filter can run on this computer.

    Attributes:
        is_available: True if the filter can run.
        reason: Why the filter cannot run, written for the user, for example
            "Needs gate_1410.so from the swh-plugins package." Empty when the
            filter can run.
    """

    is_available: bool
    reason: str = ""


AVAILABLE = FilterAvailability(is_available=True)


@dataclass(frozen=True)
class FilterSupport:
    """Which of the three filters this computer can run.

    Each audio adapter reports this, because what a filter needs differs
    between operating systems and from one machine to the next.
    """

    echo_canceller: FilterAvailability = AVAILABLE
    frequency_shifter: FilterAvailability = AVAILABLE
    noise_gate: FilterAvailability = AVAILABLE

    def problems_with(self, filters: AudioFilters) -> list[str]:
        """Return one message for each switched-on filter in ``filters`` that cannot run."""
        problems = []
        if filters.echo_canceller and not self.echo_canceller.is_available:
            problems.append(f"The echo canceller is not available. {self.echo_canceller.reason}")
        if filters.frequency_shifter and not self.frequency_shifter.is_available:
            problems.append(f"The frequency shifter is not available. {self.frequency_shifter.reason}")
        if filters.noise_gate and not self.noise_gate.is_available:
            problems.append(f"The noise gate is not available. {self.noise_gate.reason}")
        return problems
