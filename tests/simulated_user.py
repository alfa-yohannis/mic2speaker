"""A helper that operates the main window the way a person would."""

from PyQt5.QtCore import Qt
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QAction, QSpinBox

from mic2speaker.ui.device_combo_box import DeviceComboBox
from mic2speaker.ui.main_window import MainWindow
from mic2speaker.ui.toggle_button import ToggleButton
from mic2speaker.ui.volume_slider import VolumeSlider


class SimulatedUser:
    """Clicks, picks, and reads on a MainWindow, so tests read like user actions.

    The widgets and menu items are looked up by their object names, so the
    tests do not depend on the window's private attributes.
    """

    def __init__(self, window: MainWindow) -> None:
        self._window = window
        self._microphone_combo = window.findChild(DeviceComboBox, MainWindow.MICROPHONE_COMBO_NAME)
        self._speaker_combo = window.findChild(DeviceComboBox, MainWindow.SPEAKER_COMBO_NAME)
        self._volume_slider = window.findChild(VolumeSlider, MainWindow.VOLUME_SLIDER_NAME)
        self._volume_box = window.findChild(QSpinBox, VolumeSlider.VALUE_BOX_NAME)
        self._toggle_button = window.findChild(ToggleButton, MainWindow.TOGGLE_BUTTON_NAME)
        self._redetect_action = window.findChild(QAction, MainWindow.REDETECT_ACTION_NAME)
        self._echo_canceller_action = window.findChild(QAction, MainWindow.ECHO_CANCELLER_ACTION_NAME)
        self._frequency_shifter_action = window.findChild(QAction, MainWindow.FREQUENCY_SHIFTER_ACTION_NAME)
        self._noise_gate_action = window.findChild(QAction, MainWindow.NOISE_GATE_ACTION_NAME)

    def click_toggle(self) -> None:
        """Click the ON/OFF button once."""
        self._toggle_button.click()

    def redetect_devices(self) -> None:
        """Choose Devices > Redetect inputs and outputs."""
        self._redetect_action.trigger()

    def toggle_echo_canceller(self) -> None:
        """Tick or untick Filters > Echo canceller."""
        self._click_menu_item(self._echo_canceller_action)

    def toggle_frequency_shifter(self) -> None:
        """Tick or untick Filters > Frequency shifter."""
        self._click_menu_item(self._frequency_shifter_action)

    def toggle_noise_gate(self) -> None:
        """Tick or untick Filters > Noise gate."""
        self._click_menu_item(self._noise_gate_action)

    def echo_canceller_item(self) -> QAction:
        """Return the Filters > Echo canceller menu item, to look at its state."""
        return self._echo_canceller_action

    def frequency_shifter_item(self) -> QAction:
        """Return the Filters > Frequency shifter menu item, to look at its state."""
        return self._frequency_shifter_action

    def noise_gate_item(self) -> QAction:
        """Return the Filters > Noise gate menu item, to look at its state."""
        return self._noise_gate_action

    def set_volume(self, volume_percent: int) -> None:
        """Drag the volume slider to ``volume_percent``."""
        self._volume_slider.set_volume(volume_percent)

    def type_volume(self, volume_text: str) -> None:
        """Type ``volume_text`` into the number box next to the slider and press Enter."""
        self.type_into_volume_box(volume_text)
        self.press_enter_in_volume_box()

    def type_into_volume_box(self, volume_text: str) -> None:
        """Replace the number in the volume box with ``volume_text``, without pressing Enter."""
        self._volume_box.selectAll()
        QTest.keyClicks(self._volume_box, volume_text)

    def press_enter_in_volume_box(self) -> None:
        """Press Enter in the volume box."""
        QTest.keyClick(self._volume_box, Qt.Key_Return)

    def slider_volume(self) -> int:
        """Return where the volume slider stands, in percent."""
        return self._volume_slider.volume()

    def pick_microphone(self, display_name: str) -> None:
        """Choose the microphone called ``display_name`` in the dropdown."""
        self._pick(self._microphone_combo, display_name)

    def pick_speaker(self, display_name: str) -> None:
        """Choose the speaker called ``display_name`` in the dropdown."""
        self._pick(self._speaker_combo, display_name)

    def close_window(self) -> None:
        """Close the window, as with the window's close button."""
        self._window.close()

    def toggle_text(self) -> str:
        """Return the text on the toggle: "ON" or "OFF"."""
        return self._toggle_button.text()

    def volume_text(self) -> str:
        """Return the text next to the volume slider, for example "80%"."""
        return self._volume_slider.value_text()

    def status_text(self) -> str:
        """Return the message in the status bar."""
        status_bar = self._window.statusBar()
        return status_bar.currentMessage()

    def microphone_choices(self) -> list[str]:
        """Return every item text in the microphone dropdown."""
        return self._item_texts(self._microphone_combo)

    def speaker_choices(self) -> list[str]:
        """Return every item text in the speaker dropdown."""
        return self._item_texts(self._speaker_combo)

    def selected_microphone_text(self) -> str:
        """Return the text of the selected microphone."""
        return self._microphone_combo.currentText()

    def selected_speaker_text(self) -> str:
        """Return the text of the selected speaker."""
        return self._speaker_combo.currentText()

    @staticmethod
    def _click_menu_item(menu_item: QAction) -> None:
        """Click ``menu_item``. A greyed-out item ignores the click, as in the real menu."""
        if menu_item.isEnabled():
            menu_item.trigger()

    @staticmethod
    def _pick(combo: DeviceComboBox, display_name: str) -> None:
        """Select the device called ``display_name`` and send the signal a real click sends."""
        for index in range(combo.count()):
            device = combo.itemData(index)
            if device is not None and device.display_name == display_name:
                combo.setCurrentIndex(index)
                combo.activated.emit(index)
                return
        raise ValueError(f"{display_name!r} is not in the dropdown")

    @staticmethod
    def _item_texts(combo: DeviceComboBox) -> list[str]:
        """Return the text of every item in ``combo``."""
        texts = []
        for index in range(combo.count()):
            item_text = combo.itemText(index)
            texts.append(item_text)
        return texts
