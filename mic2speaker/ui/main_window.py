"""The main form: pick a microphone and a speaker, and switch the sound on or off."""

from PyQt5.QtGui import QCloseEvent, QIcon
from PyQt5.QtWidgets import QAction, QFormLayout, QMainWindow, QMenu, QMessageBox, QVBoxLayout, QWidget

from mic2speaker.audio.audio_device import AudioDevice
from mic2speaker.audio.audio_device_provider import AudioDeviceError, AudioDeviceProvider
from mic2speaker.audio.audio_device_watcher import AudioDeviceWatcher
from mic2speaker.audio.audio_filters import AudioFilters
from mic2speaker.audio.audio_loopback import AudioLoopback, AudioLoopbackError
from mic2speaker.ui.device_combo_box import DeviceComboBox
from mic2speaker.ui.toggle_button import ToggleButton
from mic2speaker.ui.volume_slider import VolumeSlider


class MainWindow(QMainWindow):
    """The only window of the app.

    It has a menu bar, a microphone dropdown, a speaker dropdown, a volume
    slider, an ON/OFF toggle, and a status bar. Switching the toggle ON plays
    the selected microphone through the selected speaker, through the filters
    ticked in the Filters menu. The dropdowns update by themselves when a
    device is plugged in or out, and Devices > Redetect inputs and outputs
    updates them by hand.

    The form reaches the operating system only through three adapters
    (AudioDeviceProvider, AudioLoopback, and AudioDeviceWatcher), so the same
    form works on every supported system.
    """

    WINDOW_TITLE = "Mic2Speaker"
    WINDOW_ICON_NAME = "audio-input-microphone"
    DEFAULT_WIDTH_PX = 560
    DEFAULT_HEIGHT_PX = 300
    ABOUT_TITLE = "About Mic2Speaker"
    ABOUT_TEXT = (
        "Mic2Speaker plays the selected microphone through the selected "
        "speaker on this computer."
    )
    SOUND_OFF_MESSAGE = "Sound is off."
    PICK_DEVICES_MESSAGE = "Pick a microphone and a speaker first."

    ECHO_CANCELLER_TEXT = "&Echo canceller (WebRTC)"
    ECHO_CANCELLER_TIP = "Remove the speaker's sound from the microphone signal."
    FREQUENCY_SHIFTER_TEXT = "&Frequency shifter"
    FREQUENCY_SHIFTER_TIP = "Shift the sound up 5 Hz so that feedback builds up more slowly."
    NOISE_GATE_TEXT = "&Noise gate"
    NOISE_GATE_TIP = "Mute the microphone while nobody speaks."

    # Object names let tests find the widgets and the menu items with findChild().
    MICROPHONE_COMBO_NAME = "microphone_combo"
    SPEAKER_COMBO_NAME = "speaker_combo"
    VOLUME_SLIDER_NAME = "volume_slider"
    TOGGLE_BUTTON_NAME = "toggle_button"
    REDETECT_ACTION_NAME = "redetect_action"
    ECHO_CANCELLER_ACTION_NAME = "echo_canceller_action"
    FREQUENCY_SHIFTER_ACTION_NAME = "frequency_shifter_action"
    NOISE_GATE_ACTION_NAME = "noise_gate_action"

    def __init__(
        self,
        device_provider: AudioDeviceProvider,
        audio_loopback: AudioLoopback,
        device_watcher: AudioDeviceWatcher,
    ) -> None:
        """Build the form, fill the dropdowns, and start watching for device changes.

        Args:
            device_provider: The adapter that lists the microphones and
                speakers of this operating system.
            audio_loopback: The adapter that plays a microphone through a
                speaker on this operating system.
            device_watcher: The adapter that reports devices being plugged
                in or out on this operating system.
        """
        super().__init__()
        self._device_provider = device_provider
        self._audio_loopback = audio_loopback
        self._device_watcher = device_watcher
        self._microphone_combo = DeviceComboBox(empty_text="No microphone found")
        self._speaker_combo = DeviceComboBox(empty_text="No speaker found")
        self._volume_slider = VolumeSlider(
            minimum_percent=AudioLoopback.MINIMUM_VOLUME_PERCENT,
            maximum_percent=AudioLoopback.MAXIMUM_VOLUME_PERCENT,
            initial_percent=AudioLoopback.DEFAULT_VOLUME_PERCENT,
        )
        self._toggle_button = ToggleButton()
        self._status_bar = self.statusBar()

        self._name_widgets()
        self._set_up_window()
        self._build_menu_bar()
        self._build_form()
        self._connect_signals()
        self._handle_volume_changed(AudioLoopback.DEFAULT_VOLUME_PERCENT)
        self.redetect_devices()
        self._device_watcher.start(on_devices_changed=self._handle_devices_changed)

    def redetect_devices(self) -> None:
        """Detect the microphones and speakers again and say how many were found.

        Devices > Redetect inputs and outputs (F5) calls this.
        """
        devices_loaded = self._load_device_lists()
        if not devices_loaded:
            return
        microphone_count = self._microphone_combo.device_count()
        speaker_count = self._speaker_combo.device_count()
        self._status_bar.showMessage(
            f"Found {microphone_count} microphone(s) and {speaker_count} speaker(s)."
        )

    def closeEvent(self, event: QCloseEvent) -> None:
        """Stop watching for devices and stop the sound before the window closes."""
        self._device_watcher.stop()
        self._audio_loopback.stop()
        super().closeEvent(event)

    def _name_widgets(self) -> None:
        """Give the main widgets object names, so tests can find them."""
        self._microphone_combo.setObjectName(self.MICROPHONE_COMBO_NAME)
        self._speaker_combo.setObjectName(self.SPEAKER_COMBO_NAME)
        self._volume_slider.setObjectName(self.VOLUME_SLIDER_NAME)
        self._toggle_button.setObjectName(self.TOGGLE_BUTTON_NAME)

    def _set_up_window(self) -> None:
        """Set the title, icon, and starting size."""
        self.setWindowTitle(self.WINDOW_TITLE)
        window_icon = QIcon.fromTheme(self.WINDOW_ICON_NAME)
        self.setWindowIcon(window_icon)
        self.resize(self.DEFAULT_WIDTH_PX, self.DEFAULT_HEIGHT_PX)

    def _build_menu_bar(self) -> None:
        """Create the File, Devices, Filters, and Help menus."""
        menu_bar = self.menuBar()

        file_menu = menu_bar.addMenu("&File")
        quit_action = file_menu.addAction("&Quit")
        quit_action.setShortcut("Ctrl+Q")
        quit_action.triggered.connect(self.close)

        devices_menu = menu_bar.addMenu("&Devices")
        redetect_action = devices_menu.addAction("&Redetect inputs and outputs")
        redetect_action.setObjectName(self.REDETECT_ACTION_NAME)
        redetect_action.setShortcut("F5")
        redetect_action.triggered.connect(self.redetect_devices)

        filters_menu = menu_bar.addMenu("Fi&lters")
        self._echo_canceller_action = self._add_filter_item(
            filters_menu, self.ECHO_CANCELLER_TEXT, self.ECHO_CANCELLER_TIP, self.ECHO_CANCELLER_ACTION_NAME
        )
        self._frequency_shifter_action = self._add_filter_item(
            filters_menu, self.FREQUENCY_SHIFTER_TEXT, self.FREQUENCY_SHIFTER_TIP, self.FREQUENCY_SHIFTER_ACTION_NAME
        )
        self._noise_gate_action = self._add_filter_item(
            filters_menu, self.NOISE_GATE_TEXT, self.NOISE_GATE_TIP, self.NOISE_GATE_ACTION_NAME
        )

        help_menu = menu_bar.addMenu("&Help")
        about_action = help_menu.addAction("&About Mic2Speaker")
        about_action.triggered.connect(self._show_about_dialog)

    @staticmethod
    def _add_filter_item(filters_menu: QMenu, text: str, status_tip: str, object_name: str) -> QAction:
        """Add one tickable filter to the Filters menu and return it."""
        filter_action = filters_menu.addAction(text)
        filter_action.setCheckable(True)
        filter_action.setStatusTip(status_tip)
        filter_action.setObjectName(object_name)
        return filter_action

    def _build_form(self) -> None:
        """Lay out the dropdowns and the volume slider, with the toggle below them."""
        device_form = QFormLayout()
        # Stretch the dropdowns and the slider to the full width so they line up.
        device_form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        device_form.addRow("Input (microphone):", self._microphone_combo)
        device_form.addRow("Output (speaker):", self._speaker_combo)
        device_form.addRow("Volume:", self._volume_slider)

        main_layout = QVBoxLayout()
        main_layout.addLayout(device_form)
        main_layout.addStretch()
        main_layout.addWidget(self._toggle_button)

        central_widget = QWidget()
        central_widget.setLayout(main_layout)
        self.setCentralWidget(central_widget)

    def _connect_signals(self) -> None:
        """React to the toggle, the dropdowns, the volume slider, and the filter items."""
        self._toggle_button.toggled.connect(self._handle_toggle)
        self._microphone_combo.activated.connect(self._handle_device_picked)
        self._speaker_combo.activated.connect(self._handle_device_picked)
        self._volume_slider.volume_changed.connect(self._handle_volume_changed)
        self._echo_canceller_action.toggled.connect(self._handle_filters_changed)
        self._frequency_shifter_action.toggled.connect(self._handle_filters_changed)
        self._noise_gate_action.toggled.connect(self._handle_filters_changed)

    def _handle_toggle(self, is_on: bool) -> None:
        """Start or stop the sound when the toggle changes."""
        if is_on:
            self._start_sound()
        else:
            self._stop_sound()

    def _handle_device_picked(self) -> None:
        """Move the sound to the newly picked device right away if it is on."""
        if self._toggle_button.isChecked():
            self._start_sound()

    def _handle_filters_changed(self) -> None:
        """Restart the sound with the new filters right away if it is on.

        While the sound is off, the ticked filters are used at the next start.
        """
        if self._toggle_button.isChecked():
            self._start_sound()

    def _handle_volume_changed(self, volume_percent: int) -> None:
        """Pass the slider's value to the loopback, which applies it at once if sound plays."""
        try:
            self._audio_loopback.set_volume(volume_percent)
        except AudioLoopbackError as error:
            self._status_bar.showMessage(f"Could not change the volume: {error}")

    def _handle_devices_changed(self) -> None:
        """Update the dropdowns after a device was plugged in or out.

        The device watcher calls this. The status bar is left alone, so a
        message such as "The sound stopped: ..." stays visible. Devices that
        are still connected stay selected, so sound that is playing goes on.
        """
        self._load_device_lists()

    def _handle_sound_stopped(self, reason: str) -> None:
        """Turn the toggle OFF after the sound stopped by itself, and show why.

        The loopback adapter calls this, for example when a device is unplugged.
        """
        self._toggle_button.setChecked(False)
        self._load_device_lists()
        self._status_bar.showMessage(f"The sound stopped: {reason}")

    def _load_device_lists(self) -> bool:
        """Read the devices from the provider and refill both dropdowns.

        Returns False, after showing the error in the status bar, when the
        devices cannot be read.
        """
        try:
            microphones = self._device_provider.list_microphones()
            speakers = self._device_provider.list_speakers()
        except AudioDeviceError as error:
            self._microphone_combo.show_devices([])
            self._speaker_combo.show_devices([])
            self._status_bar.showMessage(f"Could not read the audio devices: {error}")
            return False

        self._microphone_combo.show_devices(microphones)
        self._speaker_combo.show_devices(speakers)
        return True

    def _selected_filters(self) -> AudioFilters:
        """Return the filters that are ticked in the Filters menu."""
        return AudioFilters(
            echo_canceller=self._echo_canceller_action.isChecked(),
            frequency_shifter=self._frequency_shifter_action.isChecked(),
            noise_gate=self._noise_gate_action.isChecked(),
        )

    def _start_sound(self) -> None:
        """Play the selected microphone through the selected speaker, with the ticked filters."""
        microphone = self._microphone_combo.selected_device()
        speaker = self._speaker_combo.selected_device()
        if microphone is None or speaker is None:
            self._toggle_button.setChecked(False)
            self._status_bar.showMessage(self.PICK_DEVICES_MESSAGE)
            return

        filters = self._selected_filters()
        try:
            self._audio_loopback.start(microphone, speaker, filters, on_stopped=self._handle_sound_stopped)
        except AudioLoopbackError as error:
            self._toggle_button.setChecked(False)
            self._status_bar.showMessage(f"Could not start the sound: {error}")
            return

        playing_message = self._playing_message(microphone, speaker, filters)
        self._status_bar.showMessage(playing_message)

    @staticmethod
    def _playing_message(microphone: AudioDevice, speaker: AudioDevice, filters: AudioFilters) -> str:
        """Return the status text for sound that plays, naming the active filters."""
        message = f"Playing {microphone.display_name} through {speaker.display_name}"
        filter_names = filters.enabled_names()
        if filter_names:
            filter_list = ", ".join(filter_names)
            message = f"{message} (filters: {filter_list})"
        return message + "."

    def _stop_sound(self) -> None:
        """Stop the sound."""
        self._audio_loopback.stop()
        self._status_bar.showMessage(self.SOUND_OFF_MESSAGE)

    def _show_about_dialog(self) -> None:
        """Show the Help > About box."""
        QMessageBox.about(self, self.ABOUT_TITLE, self.ABOUT_TEXT)
