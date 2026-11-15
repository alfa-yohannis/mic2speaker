"""A large ON/OFF toggle button."""

from PyQt5.QtWidgets import QPushButton


class ToggleButton(QPushButton):
    """A button that stays down (ON) or up (OFF) each time it is clicked.

    The text and colour follow the state, so the user can see at a glance
    whether the sound is on. Read the state with ``isChecked()`` and react to
    changes through the ``toggled`` signal.
    """

    ON_TEXT = "ON"
    OFF_TEXT = "OFF"
    ON_STYLE_SHEET = "background-color: #2e7d32; color: white; border-radius: 10px;"
    OFF_STYLE_SHEET = "background-color: #757575; color: white; border-radius: 10px;"
    FONT_POINT_SIZE = 18
    MINIMUM_HEIGHT_PX = 64

    def __init__(self) -> None:
        super().__init__()
        self.setCheckable(True)
        self.setMinimumHeight(self.MINIMUM_HEIGHT_PX)
        self._use_large_bold_font()
        self.toggled.connect(self._show_state)
        self._show_state(False)

    def _use_large_bold_font(self) -> None:
        """Make the ON/OFF text big enough to read at a glance."""
        button_font = self.font()
        button_font.setPointSize(self.FONT_POINT_SIZE)
        button_font.setBold(True)
        self.setFont(button_font)

    def _show_state(self, is_on: bool) -> None:
        """Change the text and colour to match ``is_on``."""
        if is_on:
            self.setText(self.ON_TEXT)
            self.setStyleSheet(self.ON_STYLE_SHEET)
        else:
            self.setText(self.OFF_TEXT)
            self.setStyleSheet(self.OFF_STYLE_SHEET)
