# Architecture

The form in `mic2speaker/ui` talks to the operating system only through three interfaces in `mic2speaker/audio`. Each operating system implements those interfaces in its own adapter classes, and `mic2speaker/app.py` picks the adapters for the system it runs on and hands them to the form.

```
app.py ── creates ──► MainWindow(device_provider, audio_loopback, device_watcher)
                          │
                          ├── AudioDeviceProvider ◄── LinuxAudioDeviceProvider    (pactl)
                          │   lists microphones   ◄── WindowsAudioDeviceProvider  (not written yet)
                          │   and speakers
                          │
                          ├── AudioLoopback       ◄── LinuxAudioLoopback          (pw-loopback, filters
                          │   plays a microphone  ◄── WindowsAudioLoopback         in "pipewire -c")
                          │   through a speaker                                    (not written yet)
                          │
                          └── AudioDeviceWatcher  ◄── LinuxAudioDeviceWatcher     (pactl subscribe)
                              reports devices     ◄── WindowsAudioDeviceWatcher   (not written yet)
                              plugged in or out
```

The form never imports an adapter. Supporting another operating system therefore means writing three adapter classes and choosing them in `app.py`; the form and its tests stay as they are. [WINDOWS.md](WINDOWS.md) walks through this for Windows.

## Classes

| Class | Module | Job |
|---|---|---|
| `Mic2SpeakerApp` | `app.py` | creates the Qt application, picks the adapters, shows the window |
| `MainWindow` | `ui/main_window.py` | the form; reacts to the toggle, the dropdowns, the slider, the menus, and device changes |
| `DeviceComboBox` | `ui/device_combo_box.py` | dropdown of `AudioDevice` items; keeps the user's choice when the list is refilled |
| `VolumeSlider` | `ui/volume_slider.py` | slider from 0 to 150 % with its value next to it |
| `ToggleButton` | `ui/toggle_button.py` | the ON/OFF button; its text and colour follow its state |
| `AudioDevice` | `audio/audio_device.py` | one microphone or speaker: `system_name`, `display_name`, `is_default` |
| `AudioFilters` | `audio/audio_filters.py` | which of the echo canceller, frequency shifter, and noise gate are on |
| `AudioDeviceProvider` | `audio/audio_device_provider.py` | interface with `list_microphones()` and `list_speakers()` |
| `AudioLoopback` | `audio/audio_loopback.py` | interface with `start(microphone, speaker, filters, on_stopped)`, `stop()`, `is_running()`, and `set_volume()` |
| `AudioDeviceWatcher` | `audio/audio_device_watcher.py` | interface with `start(on_devices_changed)` and `stop()` |
| `LinuxAudioDeviceProvider` | `audio/linux_audio_device_provider.py` | Linux adapter; reads the devices with `pactl --format=json` |
| `LinuxAudioLoopback` | `audio/linux_audio_loopback.py` | Linux adapter; runs `pw-loopback` and sets the volume of its stream |
| `LinuxFilterProcess` | `audio/linux_filter_process.py` | runs the filters in a `pipewire -c <config>` helper process |
| `LinuxFilterConfig` | `audio/linux_filter_config.py` | builds that config for one set of filters |
| `LinuxAudioDeviceWatcher` | `audio/linux_audio_device_watcher.py` | Linux adapter; reads the events that `pactl subscribe` prints |

Three small helper modules support the Linux classes. `linux_pactl.py` runs `pactl` and turns its failures into one exception type, `linux_node_names.py` holds the names of the PipeWire nodes the app creates, and `linux_child_process.py` holds `command_that_ends_with_app()` (see [When the app closes or crashes](#when-the-app-closes-or-crashes)).

`AudioDevice.system_name` is the name the audio system uses (on Linux, for example, `alsa_input.usb-...mono-fallback`). It stays the same between runs, which lets `DeviceComboBox` keep the user's choice when the lists are refilled. `display_name` is what the user sees.

## What happens when you click ON

1. `ToggleButton` emits `toggled(True)`, and `MainWindow._handle_toggle` calls `_start_sound`.
2. `_start_sound` reads the selected `AudioDevice` from each dropdown and the ticked items of the Filters menu, and calls `audio_loopback.start(microphone, speaker, filters, on_stopped=self._handle_sound_stopped)`.
3. On Linux, `LinuxAudioLoopback.start` stops anything still running. If a filter is ticked, it first starts the filters (see [Filters](#filters)) and reads their virtual microphone instead of the real one. Then it starts `pw-loopback`:

   ```
   setpriv --pdeathsig TERM -- pw-loopback --name mic2speaker --latency 10 \
       --capture <microphone, or the filters' virtual microphone> \
       --capture-props "node.dont-reconnect=true media.name=Mic2Speaker" \
       --playback <speaker system_name> \
       --playback-props "node.dont-reconnect=true media.name=Mic2Speaker"
   ```

4. It waits for the playback stream to appear and sets its volume with `pactl set-sink-input-volume`.
5. The status bar shows "Playing <microphone> through <speaker>.", followed by the active filters if there are any.

Picking another device or ticking a filter while the toggle is ON repeats steps 2 to 5. Moving the volume slider calls `audio_loopback.set_volume()`, which changes the stream's volume at once. Clicking OFF calls `audio_loopback.stop()`, which ends `pw-loopback` and the filters.

WirePlumber remembers the last volume of each stream and sets it again when the stream appears. Because the app sets the slider's value right after the stream appears, the slider's value is what you hear.

## Filters

The filters run in a helper process started with `pipewire -c <config file>`. `LinuxFilterConfig` builds the config as Python dictionaries and `LinuxFilterProcess` saves it as JSON, which PipeWire's SPA-JSON format accepts, in a temporary directory. Depending on the ticked filters, the sound takes this path:

```
microphone ─► echo canceller ─► noise gate ─► frequency shifter ─► virtual microphone ─► pw-loopback ─► speaker
                   ▲                                                                                        │
                   └──────────────────────────────── speaker monitor ───────────────────────────────────────┘
```

- The echo canceller is PipeWire's `libpipewire-module-echo-cancel` with the WebRTC library, noise suppression, and the high-pass filter, without automatic gain (which would raise the feedback). It runs in monitor mode: it takes the sound to remove from the speaker's monitor. The other mode, in which pw-loopback would play into a sink that belongs to the echo canceller, makes a loop between the canceller's own nodes, and WirePlumber refuses to link such loops.
- The noise gate (`gate_1410.so` from swh-plugins) and the frequency shifter (`bode_shifter_1431.so`, shifted up 5 Hz) run in `libpipewire-module-filter-chain`. The shifter's output is 6 dB quieter than its input, so PipeWire's built-in `linear` plugin doubles it again.
- The last filter offers its output as a virtual microphone (`mic2speaker_echo_cancel_source` or `mic2speaker_filtered_microphone`), which pw-loopback reads.

`LinuxFilterProcess.start` waits until that virtual microphone appears before pw-loopback starts, because pw-loopback would otherwise give up on its missing target. The virtual devices all start with `mic2speaker`, and `LinuxAudioDeviceProvider` leaves them out of the dropdowns.

## When a device is plugged in or out

`LinuxAudioDeviceWatcher` keeps `pactl subscribe` running. That command prints a line for every change on the audio server, such as `Event 'new' on sink #57`. The watcher reacts to new or removed sinks (speakers) and sources (microphones), and to `change` events on the server, which is how a new system default device shows up. It ignores `change` events on sinks and sources, because those fire on every volume change and whenever a device starts playing, including for Mic2Speaker's own sound. It runs `pactl` with `LC_ALL=C` because pactl translates the line format.

Plugging in a USB headset produces several events in quick succession, so the watcher waits until the events have been quiet for 300 ms and then calls `MainWindow._handle_devices_changed` once. That method refills both dropdowns and leaves the status bar alone. Devices that are still connected stay selected, so sound that is playing goes on. If `pactl subscribe` exits, for example because PipeWire restarted, the watcher starts it again after two seconds and reports one change so that the lists are read again.

Devices > Redetect inputs and outputs (F5) calls `MainWindow.redetect_devices`, which refills the dropdowns the same way and also shows how many devices it found.

## When a device in use is unplugged

Every stream carries `node.dont-reconnect=true`: pw-loopback's two streams and, when filters run, the streams of the echo canceller and the filter chain. Without it, WirePlumber (PipeWire's session manager) would move the sound to another device, for example from unplugged USB speakers to the laptop speakers next to the microphone. With it, WirePlumber destroys the stream instead. A filter whose stream is destroyed unloads itself, its virtual microphone disappears, and that in turn ends pw-loopback's capture stream. Either way, `pw-loopback` exits.

`LinuxAudioLoopback` notices the exit through `QProcess.finished`, ends the filter process (which keeps running even with nothing left in it), and calls the `on_stopped` callback. `MainWindow._handle_sound_stopped` then turns the toggle OFF, refills the device lists, and shows the reason in the status bar. When the app itself calls `stop()`, the adapter disconnects from `finished` first, so a requested stop is never reported as an unexpected one.

## When the app closes or crashes

`MainWindow.closeEvent` stops the device watcher and the sound before the window closes. For crashes, `pw-loopback`, `pipewire -c`, and `pactl subscribe` are all started through `command_that_ends_with_app()`, which puts `setpriv --pdeathsig TERM` in front of the command. setpriv asks the Linux kernel to send the program SIGTERM when its parent (the app) dies, so the microphone cannot keep playing without a window to switch it off. If `setpriv` is not installed, the programs are started directly and this protection is lost.

## Tests

`tests/fakes.py` has `FakeDeviceProvider`, `FakeAudioLoopback`, and `FakeDeviceWatcher`, which implement the three interfaces without making sound. `tests/simulated_user.py` has `SimulatedUser`, which clicks, picks, drags the slider, and ticks menu items on the form the way a person would, finding the widgets with `findChild()` and their object names. With these, `tests/test_main_window.py` checks the form's behaviour on any operating system. `tests/test_linux_filter_config.py` checks the filter config for each combination of filters, with empty files standing in for the LADSPA plugins.

`tests/test_linux_audio_integration.py` checks the Linux adapters against the real PipeWire server, using temporary virtual devices made with `pactl load-module module-null-sink`. It checks how every filter is linked, that unplugging the microphone or the speaker ends everything, and that the watcher notices devices and ignores the app's own sound. For the filters' effect it plays test tones into a virtual microphone and measures what reaches a virtual speaker: the noise gate must block a -70 dBFS tone and pass a -20 dBFS one, and the frequency shifter must keep the level within 2 dB.
