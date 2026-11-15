# Adding Windows support

Mic2Speaker runs on Linux only for now. The form does not depend on the operating system: everything that touches audio sits behind three interfaces, `AudioDeviceProvider`, `AudioLoopback`, and `AudioDeviceWatcher`, and Linux implements them with `pactl`, `pw-loopback`, and `pactl subscribe` (see [ARCHITECTURE.md](ARCHITECTURE.md)). Adding Windows means writing three more adapter classes, choosing them in `app.py`, and adding a Windows launcher. Nothing in `mic2speaker/ui` has to change.

This guide describes one way to do it, using [sounddevice](https://python-sounddevice.readthedocs.io/) (Python bindings for the PortAudio library) with Windows' WASAPI audio API. The code below is a starting point that has not been run on Windows yet, so test each step on a Windows machine.

## What to add

| File | Class | Implements |
|---|---|---|
| `mic2speaker/audio/windows_wasapi.py` | (helper functions) | finds WASAPI devices through PortAudio |
| `mic2speaker/audio/windows_audio_device_provider.py` | `WindowsAudioDeviceProvider` | `AudioDeviceProvider` |
| `mic2speaker/audio/windows_audio_loopback.py` | `WindowsAudioLoopback` | `AudioLoopback` |
| `mic2speaker/audio/windows_audio_device_watcher.py` | `WindowsAudioDeviceWatcher` | `AudioDeviceWatcher` |
| `run.bat` | | the Windows version of `run.sh` |

You also change `mic2speaker/app.py` and `requirements.txt`, and add tests.

## Rules every adapter must follow

The form relies on the rules below. The Linux adapters follow them, and `tests/test_main_window.py` assumes them.

`AudioDeviceProvider`:

1. `system_name` identifies a device and stays the same between refreshes and restarts. The dropdown uses it to keep the user's choice when the lists are refilled.
2. `display_name` is the text the user sees.
3. At most one device per list has `is_default=True`, namely the one Windows currently uses. The dropdown selects it when the user has not picked anything else.
4. `list_microphones()` returns only devices that can record, and `list_speakers()` only devices that can play.
5. When the audio system cannot be asked, raise `AudioDeviceError` and no other exception type. The form shows its message in the status bar.

`AudioLoopback`:

1. `start()` stops any sound that is already playing before it starts the new route.
2. When the sound cannot start, `start()` raises `AudioLoopbackError` with a short message for the user.
3. The sound never moves to a device the user did not pick. If a device disappears, the sound stops.
4. When the sound stops by itself, call `on_stopped(reason)` once, on the Qt main thread. Do not call it when `stop()` ended the sound.
5. `stop()` can be called at any time, also when nothing is playing.
6. The sound stops when the app exits or crashes.
7. The delay stays low. The Linux adapter buffers about 10 ms.

`AudioDeviceWatcher`:

1. Call `on_devices_changed()` on the Qt main thread after a device was plugged in or out, or after the default device changed.
2. An extra call is harmless, because the form only reads the lists again, but the app's own sound starting or stopping should not cause calls.
3. `stop()` can be called at any time, and no calls follow it.

## Why sounddevice and WASAPI

Windows has no ready-made command like `pw-loopback`, so the Windows adapter copies the sound itself: it opens a PortAudio stream that reads from the microphone and writes to the speaker. PortAudio reaches Windows audio through several "host APIs". WASAPI is the current Windows audio API and has less delay than the older MME and DirectSound host APIs, which list the same devices again. This guide therefore uses WASAPI devices only.

The stream lives inside the app's process, so it ends when the process ends. That covers loopback rule 6 without anything like Linux's `setpriv`.

## Step 1: dependencies

Add the Windows-only packages to `requirements.txt` with environment markers, so Linux installs stay unchanged:

```
PyQt5>=5.15,<5.16
sounddevice; sys_platform == "win32"
numpy; sys_platform == "win32"
```

`sounddevice.Stream` passes audio as NumPy arrays, which is why `numpy` is listed. On Windows the `sounddevice` wheel includes the PortAudio library, so nothing else needs installing.

## Step 2: finding WASAPI devices

PortAudio numbers its devices, but the numbers change when a device is plugged in or out. The adapters therefore store the device name as `system_name` and look up the current number only when they need it. Both adapters use these helpers in `mic2speaker/audio/windows_wasapi.py`:

```python
"""Helpers that find Windows WASAPI devices through PortAudio (sounddevice)."""

import sounddevice

WASAPI_HOST_API_NAME = "Windows WASAPI"
INPUT_CHANNELS_KEY = "max_input_channels"
OUTPUT_CHANNELS_KEY = "max_output_channels"


def find_wasapi_host_api() -> dict | None:
    """Return PortAudio's description of the WASAPI host API, or None if it is missing."""
    for host_api in sounddevice.query_hostapis():
        if host_api["name"] == WASAPI_HOST_API_NAME:
            return host_api
    return None


def find_wasapi_device_index(device_name: str, channels_key: str) -> int | None:
    """Return PortAudio's current number for the WASAPI device called ``device_name``.

    ``channels_key`` is INPUT_CHANNELS_KEY for microphones and
    OUTPUT_CHANNELS_KEY for speakers. Returns None if no such device is
    connected.
    """
    host_api = find_wasapi_host_api()
    if host_api is None:
        return None
    for device_index in host_api["devices"]:
        device_info = sounddevice.query_devices(device_index)
        if device_info["name"] == device_name and device_info[channels_key] > 0:
            return device_index
    return None
```

## Step 3: WindowsAudioDeviceProvider

```python
"""Windows adapter that lists audio devices through PortAudio's WASAPI host API."""

import sounddevice

from mic2speaker.audio.audio_device import AudioDevice
from mic2speaker.audio.audio_device_provider import AudioDeviceError, AudioDeviceProvider
from mic2speaker.audio.windows_wasapi import INPUT_CHANNELS_KEY, OUTPUT_CHANNELS_KEY, find_wasapi_host_api


class WindowsAudioDeviceProvider(AudioDeviceProvider):
    """Lists microphones and speakers by asking PortAudio for WASAPI devices.

    The device name is used as system_name, because PortAudio's device
    numbers change when devices are plugged in or out.
    """

    def list_microphones(self) -> list[AudioDevice]:
        """Return every WASAPI device that can record."""
        return self._list_devices(INPUT_CHANNELS_KEY, "default_input_device")

    def list_speakers(self) -> list[AudioDevice]:
        """Return every WASAPI device that can play."""
        return self._list_devices(OUTPUT_CHANNELS_KEY, "default_output_device")

    def _list_devices(self, channels_key: str, default_device_key: str) -> list[AudioDevice]:
        """Read the WASAPI devices, turning PortAudio errors into AudioDeviceError."""
        try:
            return self._read_wasapi_devices(channels_key, default_device_key)
        except sounddevice.PortAudioError as error:
            error_text = str(error)
            raise AudioDeviceError(error_text) from error

    def _read_wasapi_devices(self, channels_key: str, default_device_key: str) -> list[AudioDevice]:
        """Return the WASAPI devices that have channels of the kind ``channels_key`` names."""
        host_api = find_wasapi_host_api()
        if host_api is None:
            raise AudioDeviceError("Windows WASAPI audio is not available.")

        default_device_index = host_api[default_device_key]
        devices = []
        for device_index in host_api["devices"]:
            device_info = sounddevice.query_devices(device_index)
            if device_info[channels_key] == 0:
                continue
            device_name = device_info["name"]
            is_default = device_index == default_device_index
            audio_device = AudioDevice(
                system_name=device_name,
                display_name=device_name,
                is_default=is_default,
            )
            devices.append(audio_device)
        return devices
```

PortAudio reads the device list once, when it starts. A device plugged in later shows up only after PortAudio restarts, and that applies to Devices > Redetect inputs and outputs too. The simplest first version accepts this and asks the user to restart the app after plugging in a new device. sounddevice has no public function to restart PortAudio. The usual workaround is to call `sounddevice._terminate()` and then `sounddevice._initialize()` at the start of `_list_devices()`, but both are private and may change. Restarting PortAudio also cuts any open stream, so only do it when `WindowsAudioLoopback` is not running.

## Step 4: WindowsAudioLoopback

```python
"""Windows adapter that plays a microphone through a speaker with a PortAudio stream."""

from collections.abc import Callable

import sounddevice
from PyQt5.QtCore import QTimer

from mic2speaker.audio.audio_device import AudioDevice
from mic2speaker.audio.audio_loopback import AudioLoopback, AudioLoopbackError
from mic2speaker.audio.windows_wasapi import INPUT_CHANNELS_KEY, OUTPUT_CHANNELS_KEY, find_wasapi_device_index


class WindowsAudioLoopback(AudioLoopback):
    """Copies sound from a microphone to a speaker inside this process.

    PortAudio calls _copy_microphone_to_speaker() on its own audio thread for
    every small block of sound. That method must stay short and must not touch
    Qt. A QTimer on the Qt main thread checks whether the stream is still
    running and reports an unexpected stop through on_stopped.
    """

    LATENCY_SECONDS = 0.010
    SAMPLE_RATE = 48000
    MICROPHONE_CHANNELS = 1
    SPEAKER_CHANNELS = 2
    HEALTH_CHECK_INTERVAL_MS = 500
    DEVICE_GONE_REASON = "the microphone or speaker is no longer available."

    def __init__(self) -> None:
        """Create a loopback that is not playing yet. A QApplication must exist already."""
        self._stream: sounddevice.Stream | None = None
        self._on_stopped: Callable[[str], None] | None = None
        self._health_timer = QTimer()
        self._health_timer.setInterval(self.HEALTH_CHECK_INTERVAL_MS)
        self._health_timer.timeout.connect(self._check_stream_is_running)

    def start(
        self,
        microphone: AudioDevice,
        speaker: AudioDevice,
        on_stopped: Callable[[str], None],
    ) -> None:
        """Open a stream from ``microphone`` to ``speaker`` and start it."""
        self.stop()
        microphone_index = find_wasapi_device_index(microphone.system_name, INPUT_CHANNELS_KEY)
        speaker_index = find_wasapi_device_index(speaker.system_name, OUTPUT_CHANNELS_KEY)
        if microphone_index is None or speaker_index is None:
            raise AudioLoopbackError(self.DEVICE_GONE_REASON)

        device_indexes = (microphone_index, speaker_index)
        channel_counts = (self.MICROPHONE_CHANNELS, self.SPEAKER_CHANNELS)
        try:
            stream = sounddevice.Stream(
                device=device_indexes,
                channels=channel_counts,
                samplerate=self.SAMPLE_RATE,
                latency=self.LATENCY_SECONDS,
                callback=self._copy_microphone_to_speaker,
            )
            stream.start()
        except sounddevice.PortAudioError as error:
            error_text = str(error)
            raise AudioLoopbackError(error_text) from error

        self._stream = stream
        self._on_stopped = on_stopped
        self._health_timer.start()

    def stop(self) -> None:
        """Stop and close the stream. on_stopped is not called."""
        self._health_timer.stop()
        if self._stream is None:
            return
        stream = self._stream
        self._stream = None
        stream.stop()
        stream.close()

    def is_running(self) -> bool:
        """Return True while the stream is running."""
        if self._stream is None:
            return False
        return self._stream.active

    def _copy_microphone_to_speaker(self, microphone_block, speaker_block, frame_count, time_info, status) -> None:
        """Copy one block of sound. Runs on PortAudio's audio thread.

        The microphone block has one column and the speaker block has two, so
        NumPy copies the microphone into both speaker channels.
        """
        speaker_block[:] = microphone_block

    def _check_stream_is_running(self) -> None:
        """Report a stream that stopped by itself. Runs on the Qt main thread."""
        if self.is_running():
            return
        self.stop()
        self._on_stopped(self.DEVICE_GONE_REASON)
```

Things to check on a real Windows machine:

- Sample rates. In WASAPI shared mode each device runs at the rate chosen in the Windows Sound settings. If the microphone and the speaker use different rates, opening the stream at 48000 Hz fails. Either set both devices to 48000 Hz, or pass `extra_settings=sounddevice.WasapiSettings(auto_convert=True)` to `sounddevice.Stream` if your sounddevice version supports that option, so that Windows converts the rate.
- One stream across two devices. If PortAudio refuses to open a single stream for two different devices, use a `sounddevice.InputStream` and a `sounddevice.OutputStream` joined by a small queue instead.
- Unplugging. Check that `stream.active` turns False when a device is unplugged. If it stays True, store the time of the last call in `_copy_microphone_to_speaker` and treat a gap of more than a second as a stop in `_check_stream_is_running`.
- Errors while stopping. `stream.stop()` on a stream whose device is gone may raise `sounddevice.PortAudioError`. Catch it in `stop()` so that loopback rule 5 holds.
- Identical device names. Two identical USB devices get the same name, and this code always picks the first one. Add a number to `system_name` if that matters.
- Stereo microphones. `MICROPHONE_CHANNELS = 1` records the first channel only, so a stereo microphone plays its left channel on both speaker channels.

## Step 5: WindowsAudioDeviceWatcher

A first version can leave automatic detection out. The user then picks up new devices with Devices > Redetect inputs and outputs (F5), which works once the provider restarts PortAudio (see Step 3):

```python
"""Windows device watcher, first version: it does not watch yet."""

from collections.abc import Callable

from mic2speaker.audio.audio_device_watcher import AudioDeviceWatcher


class WindowsAudioDeviceWatcher(AudioDeviceWatcher):
    """Never reports a change; new devices are found with Devices > Redetect inputs and outputs."""

    def start(self, on_devices_changed: Callable[[], None]) -> None:
        """Do nothing; see the class docstring."""

    def stop(self) -> None:
        """Do nothing; see the class docstring."""
```

For real watching, Windows reports device changes through the `IMMNotificationClient` COM interface, whose methods include `OnDeviceAdded`, `OnDeviceRemoved`, `OnDeviceStateChanged`, and `OnDefaultDeviceChanged`. Python can implement it with the `comtypes` package. Windows calls these methods on its own thread, so they must not call `on_devices_changed` directly. Let them set a flag instead, and have a `QTimer` on the Qt main thread check the flag, clear it, and call back. As with the manual redetect, the new device only appears in the lists if the provider restarts PortAudio.

## Step 6: choose the adapters in app.py

Add a Windows branch to the three factory methods in `Mic2SpeakerApp`. Import the Windows classes inside the branch, so Linux never needs `sounddevice` installed:

```python
    @staticmethod
    def _create_device_provider() -> AudioDeviceProvider:
        """Return the adapter that lists audio devices on this operating system."""
        if sys.platform.startswith("linux"):
            return LinuxAudioDeviceProvider()
        if sys.platform == "win32":
            from mic2speaker.audio.windows_audio_device_provider import WindowsAudioDeviceProvider
            return WindowsAudioDeviceProvider()
        raise UnsupportedPlatformError(f"Mic2Speaker does not support {sys.platform} yet.")

    @staticmethod
    def _create_audio_loopback() -> AudioLoopback:
        """Return the adapter that plays a microphone through a speaker on this operating system."""
        if sys.platform.startswith("linux"):
            return LinuxAudioLoopback()
        if sys.platform == "win32":
            from mic2speaker.audio.windows_audio_loopback import WindowsAudioLoopback
            return WindowsAudioLoopback()
        raise UnsupportedPlatformError(f"Mic2Speaker does not support {sys.platform} yet.")

    @staticmethod
    def _create_device_watcher() -> AudioDeviceWatcher:
        """Return the adapter that notices devices being plugged in or out on this operating system."""
        if sys.platform.startswith("linux"):
            return LinuxAudioDeviceWatcher()
        if sys.platform == "win32":
            from mic2speaker.audio.windows_audio_device_watcher import WindowsAudioDeviceWatcher
            return WindowsAudioDeviceWatcher()
        raise UnsupportedPlatformError(f"Mic2Speaker does not support {sys.platform} yet.")
```

`Mic2SpeakerApp.__init__` already creates the adapters after the `QApplication`, which `WindowsAudioLoopback` needs for its `QTimer`.

## Step 7: run.bat

```bat
@echo off
rem Launcher for Mic2Speaker on Windows.
rem Runs the app with the Python of the project's own virtual environment
rem (.venv). On the first run it creates .venv and installs requirements.txt.

setlocal
set "PROJECT_DIR=%~dp0"
set "VENV_PYTHON=%PROJECT_DIR%.venv\Scripts\python.exe"

if not exist "%VENV_PYTHON%" (
    echo Creating the virtual environment in %PROJECT_DIR%.venv ...
    py -3 -m venv "%PROJECT_DIR%.venv" || exit /b 1
    "%VENV_PYTHON%" -m pip install --requirement "%PROJECT_DIR%requirements.txt" || exit /b 1
)

cd /d "%PROJECT_DIR%"
"%VENV_PYTHON%" -m mic2speaker %*
```

`py` is the Python launcher that the python.org installer adds. If pip starts compiling PyQt5 or PyQt5-sip during the first run, that Python version has no ready-made Windows wheel; use a slightly older Python instead.

## Step 8: tests

- The current unit tests (`tests/test_main_window.py`, `tests/test_linux_audio_device_provider.py`, and `tests/test_linux_audio_device_watcher.py`) do not touch real audio and should pass on Windows unchanged. `tests/test_linux_audio_integration.py` skips itself because `pactl` and `pw-loopback` are missing.
- Add `tests/test_windows_audio_device_provider.py`. Replace `sounddevice.query_hostapis` and `sounddevice.query_devices` with fakes through pytest's `monkeypatch`, the same way `tests/test_linux_audio_device_provider.py` replaces `subprocess.run`, and check the default marking, the channel filtering, and the `AudioDeviceError` cases. Begin the file with `sounddevice = pytest.importorskip("sounddevice")` so that Linux skips it.
- Windows has no built-in virtual audio devices, so a test like the Linux integration tests needs real devices or a virtual cable driver such as VB-CABLE. Give such tests a new `windows` marker (declare it in `pytest.ini`), skip them on other systems, and wear headphones when you run them, because they play real sound.

## Checklist

- [ ] `requirements.txt` lists `sounddevice` and `numpy` for `win32`
- [ ] `mic2speaker/audio/windows_wasapi.py`
- [ ] `WindowsAudioDeviceProvider` follows the provider rules
- [ ] `WindowsAudioLoopback` follows the loopback rules, with unplugging checked on real hardware
- [ ] `WindowsAudioDeviceWatcher`, as a do-nothing first version or with `IMMNotificationClient`
- [ ] `app.py` picks the Windows adapters on `win32`
- [ ] `run.bat`
- [ ] tests for the Windows adapters, and the existing tests pass on Windows
- [ ] README.md lists the Windows requirements and `run.bat`; ARCHITECTURE.md no longer says "not written yet"
