"""A dropdown that lists audio devices."""

from PyQt5.QtWidgets import QComboBox

from mic2speaker.audio.audio_device import AudioDevice


class DeviceComboBox(QComboBox):
    """A dropdown of microphones or speakers.

    Each item shows the device's display name and keeps the AudioDevice
    itself as hidden item data, so the form can ask which device is selected.
    """

    DEFAULT_DEVICE_MARK = " (default)"

    def __init__(self, empty_text: str) -> None:
        """Create an empty dropdown.

        Args:
            empty_text: What to show when there is no device to pick,
                for example "No microphone found".
        """
        super().__init__()
        self._empty_text = empty_text
        self._device_count = 0

    def show_devices(self, devices: list[AudioDevice]) -> None:
        """Replace the items with ``devices``.

        The device that was selected before stays selected if it is still in
        the list. Otherwise the system default device is selected.
        """
        previous_device = self.selected_device()
        self.clear()
        self._device_count = len(devices)

        if not devices:
            self.addItem(self._empty_text)
            self.setEnabled(False)
            return

        self.setEnabled(True)
        for device in devices:
            item_text = self._item_text(device)
            self.addItem(item_text, device)

        index_to_select = self._index_to_select(devices, previous_device)
        self.setCurrentIndex(index_to_select)

    def selected_device(self) -> AudioDevice | None:
        """Return the selected device, or None when there is no device to pick."""
        return self.currentData()

    def device_count(self) -> int:
        """Return how many devices the dropdown lists; the "No ... found" item does not count."""
        return self._device_count

    def _item_text(self, device: AudioDevice) -> str:
        """Return the text shown for ``device``, marking the system default."""
        if device.is_default:
            return device.display_name + self.DEFAULT_DEVICE_MARK
        return device.display_name

    @staticmethod
    def _index_to_select(devices: list[AudioDevice], previous_device: AudioDevice | None) -> int:
        """Pick the previous device if it is still listed, else the default, else the first."""
        if previous_device is not None:
            for index, device in enumerate(devices):
                if device.system_name == previous_device.system_name:
                    return index
        for index, device in enumerate(devices):
            if device.is_default:
                return index
        return 0
