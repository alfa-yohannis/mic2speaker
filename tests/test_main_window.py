"""Tests for the main form, with fake audio adapters instead of real sound."""

import pytest

from mic2speaker.audio.audio_device import AudioDevice
from mic2speaker.audio.audio_filters import AudioFilters, FilterAvailability, FilterSupport
from mic2speaker.ui.main_window import MainWindow
from tests.fakes import FakeAudioLoopback, FakeDeviceProvider, FakeDeviceWatcher
from tests.simulated_user import SimulatedUser

BUILT_IN_MICROPHONE = AudioDevice("alsa_input.builtin", "Built-in Microphone")
USB_MICROPHONE = AudioDevice("alsa_input.usb", "USB Microphone", is_default=True)
HEADSET_MICROPHONE = AudioDevice("bluez_input.headset", "Headset Microphone")
BUILT_IN_SPEAKER = AudioDevice("alsa_output.builtin", "Built-in Speaker")
USB_SPEAKER = AudioDevice("alsa_output.usb", "USB Speaker", is_default=True)
HDMI_SPEAKER = AudioDevice("alsa_output.hdmi", "HDMI Speaker")
DEVICE_GONE_REASON = "the microphone or speaker is no longer available."
MISSING_GATE_REASON = "Needs gate_1410.so from the swh-plugins package."
MISSING_GATE = FilterAvailability(is_available=False, reason=MISSING_GATE_REASON)


@pytest.fixture
def device_provider() -> FakeDeviceProvider:
    """Two microphones and two speakers; the USB ones are the system defaults."""
    return FakeDeviceProvider(
        microphones=[BUILT_IN_MICROPHONE, USB_MICROPHONE],
        speakers=[BUILT_IN_SPEAKER, USB_SPEAKER],
    )


@pytest.fixture
def audio_loopback() -> FakeAudioLoopback:
    """A loopback that only records what the form asks for."""
    return FakeAudioLoopback()


@pytest.fixture
def device_watcher() -> FakeDeviceWatcher:
    """A watcher that reports a device change only when the test says so."""
    return FakeDeviceWatcher()


@pytest.fixture
def window(qt_application, device_provider, audio_loopback, device_watcher) -> MainWindow:
    """The main window wired to the fake adapters."""
    main_window = MainWindow(device_provider, audio_loopback, device_watcher)
    yield main_window
    main_window.close()


@pytest.fixture
def user(window) -> SimulatedUser:
    """A simulated person using the main window."""
    return SimulatedUser(window)


class TestStartingState:
    def test_dropdowns_select_the_system_default_devices(self, user):
        assert user.selected_microphone_text() == "USB Microphone (default)"
        assert user.selected_speaker_text() == "USB Speaker (default)"

    def test_toggle_starts_off_and_no_sound_plays(self, user, audio_loopback):
        assert user.toggle_text() == "OFF"
        assert audio_loopback.started_routes == []

    def test_status_bar_counts_the_devices(self, user):
        assert user.status_text() == "Found 2 microphone(s) and 2 speaker(s)."

    def test_device_watcher_is_running(self, user, device_watcher):
        assert device_watcher.is_watching


class TestToggle:
    def test_on_plays_the_selected_microphone_through_the_selected_speaker(self, user, audio_loopback):
        user.click_toggle()

        assert user.toggle_text() == "ON"
        assert audio_loopback.started_routes == [(USB_MICROPHONE, USB_SPEAKER)]
        assert user.status_text() == "Playing USB Microphone through USB Speaker."

    def test_off_stops_the_sound(self, user, audio_loopback):
        user.click_toggle()
        user.click_toggle()

        assert user.toggle_text() == "OFF"
        assert not audio_loopback.is_running()
        assert user.status_text() == "Sound is off."

    def test_failed_start_turns_the_toggle_back_off_and_says_why(self, user, audio_loopback):
        audio_loopback.start_error_message = "pw-loopback is not installed."

        user.click_toggle()

        assert user.toggle_text() == "OFF"
        assert user.status_text() == "Could not start the sound: pw-loopback is not installed."

    def test_on_needs_a_microphone_and_a_speaker(self, qt_application, audio_loopback, device_watcher):
        provider_without_devices = FakeDeviceProvider(microphones=[], speakers=[])
        window = MainWindow(provider_without_devices, audio_loopback, device_watcher)
        user = SimulatedUser(window)

        user.click_toggle()

        assert user.toggle_text() == "OFF"
        assert audio_loopback.started_routes == []
        assert user.status_text() == "Pick a microphone and a speaker first."


class TestPickingDevices:
    def test_picking_a_speaker_while_on_moves_the_sound_right_away(self, user, audio_loopback):
        user.click_toggle()

        user.pick_speaker("Built-in Speaker")

        assert audio_loopback.started_routes == [
            (USB_MICROPHONE, USB_SPEAKER),
            (USB_MICROPHONE, BUILT_IN_SPEAKER),
        ]
        assert user.status_text() == "Playing USB Microphone through Built-in Speaker."

    def test_picking_a_device_while_off_does_not_start_the_sound(self, user, audio_loopback):
        user.pick_microphone("Built-in Microphone")

        assert audio_loopback.started_routes == []


class TestRedetecting:
    def test_menu_item_finds_a_new_device_and_reports_the_count(self, user, device_provider):
        device_provider.speakers = [BUILT_IN_SPEAKER, USB_SPEAKER, HDMI_SPEAKER]

        user.redetect_devices()

        assert user.speaker_choices() == ["Built-in Speaker", "USB Speaker (default)", "HDMI Speaker"]
        assert user.status_text() == "Found 2 microphone(s) and 3 speaker(s)."

    def test_redetecting_keeps_the_picked_device(self, user):
        user.pick_microphone("Built-in Microphone")

        user.redetect_devices()

        assert user.selected_microphone_text() == "Built-in Microphone"

    def test_plugged_in_device_appears_by_itself(self, user, device_provider, device_watcher):
        device_provider.microphones = [BUILT_IN_MICROPHONE, USB_MICROPHONE, HEADSET_MICROPHONE]

        device_watcher.report_change()

        assert user.microphone_choices() == [
            "Built-in Microphone",
            "USB Microphone (default)",
            "Headset Microphone",
        ]

    def test_automatic_update_keeps_the_sound_playing(self, user, audio_loopback, device_provider, device_watcher):
        user.click_toggle()
        device_provider.speakers = [BUILT_IN_SPEAKER, USB_SPEAKER, HDMI_SPEAKER]

        device_watcher.report_change()

        assert audio_loopback.is_running()
        assert audio_loopback.started_routes == [(USB_MICROPHONE, USB_SPEAKER)]
        assert user.selected_speaker_text() == "USB Speaker (default)"
        assert user.status_text() == "Playing USB Microphone through USB Speaker."

    def test_automatic_update_keeps_the_stop_reason_visible(self, user, audio_loopback, device_watcher):
        user.click_toggle()
        audio_loopback.stop_by_itself(DEVICE_GONE_REASON)

        device_watcher.report_change()

        assert user.status_text() == f"The sound stopped: {DEVICE_GONE_REASON}"


class TestFilters:
    def test_sound_starts_without_filters_by_default(self, user, audio_loopback):
        user.click_toggle()

        assert audio_loopback.started_filters == [AudioFilters()]

    def test_ticking_a_filter_while_on_restarts_the_sound_with_it(self, user, audio_loopback):
        user.click_toggle()

        user.toggle_noise_gate()

        assert audio_loopback.started_filters == [AudioFilters(), AudioFilters(noise_gate=True)]
        assert user.status_text() == "Playing USB Microphone through USB Speaker (filters: noise gate)."

    def test_ticking_a_filter_while_off_takes_effect_at_the_next_start(self, user, audio_loopback):
        user.toggle_echo_canceller()

        assert audio_loopback.started_filters == []

        user.click_toggle()

        assert audio_loopback.started_filters == [AudioFilters(echo_canceller=True)]

    def test_status_bar_names_every_ticked_filter(self, user):
        user.toggle_echo_canceller()
        user.toggle_frequency_shifter()
        user.toggle_noise_gate()

        user.click_toggle()

        assert user.status_text() == (
            "Playing USB Microphone through USB Speaker "
            "(filters: echo canceller, frequency shifter, noise gate)."
        )

    def test_unticking_a_filter_while_on_restarts_the_sound_without_it(self, user, audio_loopback):
        user.toggle_frequency_shifter()
        user.click_toggle()

        user.toggle_frequency_shifter()

        assert audio_loopback.started_filters == [AudioFilters(frequency_shifter=True), AudioFilters()]

    def test_filter_items_say_what_they_do(self, user):
        noise_gate_item = user.noise_gate_item()

        assert noise_gate_item.isEnabled()
        assert noise_gate_item.toolTip() == MainWindow.NOISE_GATE_TIP

    def test_filter_this_computer_cannot_run_is_greyed_out_with_the_reason(
        self, qt_application, device_provider, device_watcher
    ):
        audio_loopback = FakeAudioLoopback()
        audio_loopback.filter_support_result = FilterSupport(noise_gate=MISSING_GATE)

        window = MainWindow(device_provider, audio_loopback, device_watcher)
        user = SimulatedUser(window)

        noise_gate_item = user.noise_gate_item()
        assert not noise_gate_item.isEnabled()
        assert noise_gate_item.text() == "&Noise gate (not available)"
        assert noise_gate_item.toolTip() == MISSING_GATE_REASON
        assert user.echo_canceller_item().isEnabled()
        assert user.frequency_shifter_item().isEnabled()

    def test_greyed_out_filter_is_never_used(self, qt_application, device_provider, device_watcher):
        audio_loopback = FakeAudioLoopback()
        audio_loopback.filter_support_result = FilterSupport(noise_gate=MISSING_GATE)
        window = MainWindow(device_provider, audio_loopback, device_watcher)
        user = SimulatedUser(window)

        user.toggle_noise_gate()
        user.click_toggle()

        assert audio_loopback.started_filters == [AudioFilters()]

    def test_missing_filter_turns_the_toggle_back_off_and_says_why(self, user, audio_loopback):
        audio_loopback.start_error_message = "gate_1410.so was not found."
        user.toggle_noise_gate()

        user.click_toggle()

        assert user.toggle_text() == "OFF"
        assert user.status_text() == "Could not start the sound: gate_1410.so was not found."


class TestVolume:
    def test_volume_starts_at_100_percent(self, user, audio_loopback):
        assert audio_loopback.volume_percent == 100
        assert user.volume_text() == "100%"

    def test_moving_the_slider_changes_the_volume(self, user, audio_loopback):
        user.set_volume(40)

        assert audio_loopback.volume_percent == 40
        assert user.volume_text() == "40%"

    def test_typing_a_number_sets_that_exact_volume(self, user, audio_loopback):
        user.type_volume("73")

        assert audio_loopback.volume_percent == 73
        assert user.volume_text() == "73%"
        assert user.slider_volume() == 73

    def test_typed_number_takes_effect_when_enter_is_pressed(self, user, audio_loopback):
        user.type_into_volume_box("73")

        assert audio_loopback.volume_percent == 100

        user.press_enter_in_volume_box()

        assert audio_loopback.volume_percent == 73

    def test_volume_can_go_above_100_percent(self, user, audio_loopback):
        user.set_volume(150)

        assert audio_loopback.volume_percent == 150

    def test_volume_error_is_shown_in_the_status_bar(self, user, audio_loopback):
        audio_loopback.volume_error_message = "pactl failed: No such entity"

        user.set_volume(50)

        assert user.status_text() == "Could not change the volume: pactl failed: No such entity"


class TestUnexpectedStop:
    def test_unplugged_device_turns_the_toggle_off_and_says_why(self, user, audio_loopback, device_provider):
        user.click_toggle()
        device_provider.speakers = [BUILT_IN_SPEAKER]

        audio_loopback.stop_by_itself(DEVICE_GONE_REASON)

        assert user.toggle_text() == "OFF"
        assert user.status_text() == f"The sound stopped: {DEVICE_GONE_REASON}"
        assert user.speaker_choices() == ["Built-in Speaker"]


class TestDeviceErrors:
    def test_unreachable_audio_system_shows_placeholders_and_the_reason(
        self, qt_application, audio_loopback, device_watcher
    ):
        failing_provider = FakeDeviceProvider(microphones=[], speakers=[])
        failing_provider.error_message = "pactl failed: Connection refused"

        window = MainWindow(failing_provider, audio_loopback, device_watcher)
        user = SimulatedUser(window)

        assert user.microphone_choices() == ["No microphone found"]
        assert user.speaker_choices() == ["No speaker found"]
        assert user.status_text() == "Could not read the audio devices: pactl failed: Connection refused"


class TestClosing:
    def test_closing_the_window_stops_the_sound(self, user, audio_loopback):
        user.click_toggle()

        user.close_window()

        assert not audio_loopback.is_running()

    def test_closing_the_window_stops_the_device_watcher(self, user, device_watcher):
        user.close_window()

        assert not device_watcher.is_watching
