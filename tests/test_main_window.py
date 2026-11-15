"""Tests for the main form, with fake audio adapters instead of real sound."""

import pytest

from mic2speaker.audio.audio_device import AudioDevice
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
