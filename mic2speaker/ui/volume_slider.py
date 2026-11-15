"""A volume slider that shows its value in percent."""

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import QHBoxLayout, QLabel, QSlider, QWidget


class VolumeSlider(QWidget):
    """A horizontal slider with the current volume, such as "80%", next to it.

    Emits ``volume_changed(int)`` with the new value in percent whenever the
    user moves the slider.
    """

    volume_changed = pyqtSignal(int)

    VALUE_LABEL_MINIMUM_WIDTH_PX = 44

    def __init__(self, minimum_percent: int, maximum_percent: int, initial_percent: int) -> None:
        """Create the slider.

        Args:
            minimum_percent: The value at the left end.
            maximum_percent: The value at the right end.
            initial_percent: The value to start with.
        """
        super().__init__()
        self._slider = QSlider(Qt.Horizontal)
        self._slider.setRange(minimum_percent, maximum_percent)
        self._slider.setValue(initial_percent)
        self._value_label = QLabel()
        self._value_label.setMinimumWidth(self.VALUE_LABEL_MINIMUM_WIDTH_PX)
        self._value_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._slider)
        layout.addWidget(self._value_label)
        self.setLayout(layout)

        self._show_value(initial_percent)
        self._slider.valueChanged.connect(self._handle_value_changed)

    def volume(self) -> int:
        """Return the current value in percent."""
        return self._slider.value()

    def set_volume(self, volume_percent: int) -> None:
        """Move the slider to ``volume_percent``, as if the user had dragged it there."""
        self._slider.setValue(volume_percent)

    def value_text(self) -> str:
        """Return the text next to the slider, for example "80%"."""
        return self._value_label.text()

    def _handle_value_changed(self, volume_percent: int) -> None:
        """Show the new value and pass it on."""
        self._show_value(volume_percent)
        self.volume_changed.emit(volume_percent)

    def _show_value(self, volume_percent: int) -> None:
        """Write ``volume_percent`` into the label next to the slider."""
        self._value_label.setText(f"{volume_percent}%")
