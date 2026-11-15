# Architecture

The form in `mic2speaker/ui` talks to the operating system only through three interfaces in `mic2speaker/audio`. Each operating system implements those interfaces in its own adapter classes, and `mic2speaker/app.py` picks the adapters for the system it runs on and hands them to the form.

```
app.py ── creates ──► MainWindow(device_provider, audio_loopback, device_watcher)
                          │
                          ├── AudioDeviceProvider ◄── LinuxAudioDeviceProvider    (pactl)
                          │   lists microphones   ◄── WindowsAudioDeviceProvider  (not written yet)
                          │   and speakers
                          │
                          ├── AudioLoopback       ◄── LinuxAudioLoopback          (pw-loopback)
                          │   plays a microphone  ◄── WindowsAudioLoopback        (not written yet)
                          │   through a speaker
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
| `MainWindow` | `ui/main_window.py` | the form; reacts to the toggle, the dropdowns, the menu, and device changes |
| `DeviceComboBox` | `ui/device_combo_box.py` | dropdown of `AudioDevice` items; keeps the user's choice when the list is refilled |
| `ToggleButton` | `ui/toggle_button.py` | the ON/OFF button; its text and colour follow its state |
| `AudioDevice` | `audio/audio_device.py` | one microphone or speaker: `system_name`, `display_name`, `is_default` |
| `AudioDeviceProvider` | `audio/audio_device_provider.py` | interface with `list_microphones()` and `list_speakers()` |
| `AudioLoopback` | `audio/audio_loopback.py` | interface with `start()`, `stop()`, and `is_running()` |
| `AudioDeviceWatcher` | `audio/audio_device_watcher.py` | interface with `start(on_devices_changed)` and `stop()` |
| `LinuxAudioDeviceProvider` | `audio/linux_audio_device_provider.py` | Linux adapter; reads the devices with `pactl --format=json` |
| `LinuxAudioLoopback` | `audio/linux_audio_loopback.py` | Linux adapter; runs `pw-loopback` in the background |
| `LinuxAudioDeviceWatcher` | `audio/linux_audio_device_watcher.py` | Linux adapter; reads the events that `pactl subscribe` prints |

`audio/linux_child_process.py` holds `command_that_ends_with_app()`, which the two Linux adapters that start programs both use (see [When the app closes or crashes](#when-the-app-closes-or-crashes)).

`AudioDevice.system_name` is the name the audio system uses (on Linux, for example, `alsa_input.usb-...mono-fallback`). It stays the same between runs, which lets `DeviceComboBox` keep the user's choice when the lists are refilled. `display_name` is what the user sees.

## What happens when you click ON

1. `ToggleButton` emits `toggled(True)`, and `MainWindow._handle_toggle` calls `_start_sound`.
2. `_start_sound` reads the selected `AudioDevice` from each dropdown and calls `audio_loopback.start(microphone, speaker, on_stopped=self._handle_sound_stopped)`.
3. On Linux, `LinuxAudioLoopback.start` ends any running `pw-loopback` and starts a new one:

   ```
   setpriv --pdeathsig TERM -- pw-loopback --name mic2speaker --latency 10 \
       --capture <microphone system_name> \
       --capture-props "node.dont-reconnect=true media.name=Mic2Speaker" \
       --playback <speaker system_name> \
       --playback-props "node.dont-reconnect=true media.name=Mic2Speaker"
   ```

4. The status bar shows "Playing <microphone> through <speaker>."

Picking another device while the toggle is ON repeats steps 2 to 4 with the new device. Clicking OFF calls `audio_loopback.stop()`, which ends `pw-loopback`.

## When a device is plugged in or out

`LinuxAudioDeviceWatcher` keeps `pactl subscribe` running. That command prints a line for every change on the audio server, such as `Event 'new' on sink #57`. The watcher reacts to new or removed sinks (speakers) and sources (microphones), and to `change` events on the server, which is how a new system default device shows up. It ignores `change` events on sinks and sources, because those fire on every volume change and whenever a device starts playing, including for Mic2Speaker's own sound. It runs `pactl` with `LC_ALL=C` because pactl translates the line format.

Plugging in a USB headset produces several events in quick succession, so the watcher waits until the events have been quiet for 300 ms and then calls `MainWindow._handle_devices_changed` once. That method refills both dropdowns and leaves the status bar alone. Devices that are still connected stay selected, so sound that is playing goes on. If `pactl subscribe` exits, for example because PipeWire restarted, the watcher starts it again after two seconds and reports one change so that the lists are read again.

Devices > Redetect inputs and outputs (F5) calls `MainWindow.redetect_devices`, which refills the dropdowns the same way and also shows how many devices it found.

## When a device in use is unplugged

Both streams carry `node.dont-reconnect=true`. Without it, WirePlumber (PipeWire's session manager) would move the sound to another device, for example from unplugged USB speakers to the laptop speakers next to the microphone. With it, WirePlumber destroys the stream and `pw-loopback` exits.

`LinuxAudioLoopback` notices the exit through `QProcess.finished` and calls the `on_stopped` callback. `MainWindow._handle_sound_stopped` then turns the toggle OFF, refills the device lists, and shows the reason in the status bar. When the app itself calls `stop()`, the adapter disconnects from `finished` first, so a requested stop is never reported as an unexpected one.

## When the app closes or crashes

`MainWindow.closeEvent` stops the device watcher and the sound before the window closes. For crashes, both `pw-loopback` and `pactl subscribe` are started through `command_that_ends_with_app()`, which puts `setpriv --pdeathsig TERM` in front of the command. setpriv asks the Linux kernel to send the program SIGTERM when its parent (the app) dies, so the microphone cannot keep playing without a window to switch it off. If `setpriv` is not installed, the programs are started directly and this protection is lost.

## Tests

`tests/fakes.py` has `FakeDeviceProvider`, `FakeAudioLoopback`, and `FakeDeviceWatcher`, which implement the three interfaces without making sound. `tests/simulated_user.py` has `SimulatedUser`, which clicks, picks, and chooses menu items on the form the way a person would, finding the widgets with `findChild()` and their object names. With these, `tests/test_main_window.py` checks the form's behaviour on any operating system.

`tests/test_linux_audio_integration.py` checks the Linux adapters against the real PipeWire server, using temporary virtual devices made with `pactl load-module module-null-sink`. Besides the loopback, it checks that the watcher notices a virtual speaker being plugged in and out, ignores the app's own sound, and recovers after `pactl subscribe` is killed.
