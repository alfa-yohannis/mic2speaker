"""A helper that operates the main window the way a person would."""

from PyQt5.QtWidgets import QAction

from mic2speaker.ui.device_combo_box import DeviceComboBox
from mic2speaker.ui.main_window import MainWindow
from mic2speaker.ui.toggle_button import ToggleButton


class SimulatedUser:
    """Clicks, picks, and reads on a MainWindow, so tests read like user actions.

    The widgets are looked up by their object names, so the tests do not
    depend on the window's private attributes.
    """

    def __init__(self, window: MainWindow) -> None:
        self._window = window
        self._microphone_combo = window.findChild(DeviceComboBox, MainWindow.MICROPHONE_COMBO_NAME)
        self._speaker_combo = window.findChild(DeviceComboBox, MainWindow.SPEAKER_COMBO_NAME)
        self._toggle_button = window.findChild(ToggleButton, MainWindow.TOGGLE_BUTTON_NAME)
        self._redetect_action = window.findChild(QAction, MainWindow.REDETECT_ACTION_NAME)

    def click_toggle(self) -> None:
        """Click the ON/OFF button once."""
        self._toggle_button.click()

    def redetect_devices(self) -> None:
        """Choose Devices > Redetect inputs and outputs."""
        self._redetect_action.trigger()

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
