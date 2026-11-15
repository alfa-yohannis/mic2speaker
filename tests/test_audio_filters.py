"""Tests for AudioFilters and FilterSupport."""

from mic2speaker.audio.audio_filters import AudioFilters, FilterAvailability, FilterSupport

ALL_FILTERS = AudioFilters(echo_canceller=True, frequency_shifter=True, noise_gate=True)
MISSING_GATE_REASON = "Needs gate_1410.so from the swh-plugins package."
MISSING_GATE = FilterAvailability(is_available=False, reason=MISSING_GATE_REASON)


def test_enabled_names_follow_the_menu_order():
    assert ALL_FILTERS.enabled_names() == ["echo canceller", "frequency shifter", "noise gate"]


def test_no_problems_when_every_filter_is_available():
    support = FilterSupport()

    assert support.problems_with(ALL_FILTERS) == []


def test_switched_on_filter_that_cannot_run_is_a_problem():
    support = FilterSupport(noise_gate=MISSING_GATE)
    filters = AudioFilters(noise_gate=True)

    problems = support.problems_with(filters)

    assert problems == [f"The noise gate is not available. {MISSING_GATE_REASON}"]


def test_switched_off_filter_that_cannot_run_is_no_problem():
    support = FilterSupport(noise_gate=MISSING_GATE)
    filters = AudioFilters(echo_canceller=True)

    assert support.problems_with(filters) == []
