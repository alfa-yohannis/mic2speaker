"""A volume slider with a number box for typing an exact value."""

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import QHBoxLayout, QSlider, QSpinBox, QWidget


class VolumeSlider(QWidget):
    """A horizontal slider with a number box, such as "80%", next to it.

    Drag the slider, or type an exact value in the box and press Enter; the
    two always show the same value. Emits ``volume_changed(int)`` with the
    new value in percent, once for every change.
    """

    volume_changed = pyqtSignal(int)

    VALUE_BOX_NAME = "volume_value_box"
    VALUE_BOX_SUFFIX = "%"
    VALUE_BOX_MINIMUM_WIDTH_PX = 72

    def __init__(self, minimum_percent: int, maximum_percent: int, initial_percent: int) -> None:
        """Create the slider and its number box.

        Args:
            minimum_percent: The lowest value.
            maximum_percent: The highest value.
            initial_percent: The value to start with.
        """
        super().__init__()
        self._slider = QSlider(Qt.Horizontal)
        self._slider.setRange(minimum_percent, maximum_percent)
        self._slider.setValue(initial_percent)

        self._value_box = QSpinBox()
        self._value_box.setObjectName(self.VALUE_BOX_NAME)
        self._value_box.setRange(minimum_percent, maximum_percent)
        self._value_box.setValue(initial_percent)
        self._value_box.setSuffix(self.VALUE_BOX_SUFFIX)
        self._value_box.setMinimumWidth(self.VALUE_BOX_MINIMUM_WIDTH_PX)
        # Use a typed number when Enter is pressed or the box loses focus, not
        # after every digit; typing "120" would otherwise pass 1 % and 12 %.
        self._value_box.setKeyboardTracking(False)

        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._slider)
        layout.addWidget(self._value_box)
        self.setLayout(layout)

        self._slider.valueChanged.connect(self._handle_slider_moved)
        self._value_box.valueChanged.connect(self._handle_number_entered)

    def volume(self) -> int:
        """Return the current value in percent."""
        return self._slider.value()

    def set_volume(self, volume_percent: int) -> None:
        """Move the slider to ``volume_percent``, as if the user had dragged it there."""
        self._slider.setValue(volume_percent)

    def value_text(self) -> str:
        """Return the text in the number box, for example "80%"."""
        return self._value_box.text()

    def _handle_slider_moved(self, volume_percent: int) -> None:
        """Show the slider's new value in the number box and pass it on.

        This is the only place that emits volume_changed, so every change is
        reported once, whether it started at the slider or at the box.
        """
        self._value_box.setValue(volume_percent)
        self.volume_changed.emit(volume_percent)

    def _handle_number_entered(self, volume_percent: int) -> None:
        """Move the slider to the typed number; the slider then reports the change."""
        self._slider.setValue(volume_percent)
