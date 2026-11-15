# Architecture

The form in `mic2speaker/ui` talks to the operating system only through three interfaces in `mic2speaker/audio`. Each operating system implements those interfaces in its own adapter classes, and `mic2speaker/app.py` picks the adapters for the system it runs on and hands them to the form.

The diagrams on this page are written in [Mermaid](https://mermaid.js.org/). GitHub shows them as pictures; in VS Code, the "Markdown Preview Mermaid Support" extension does the same in the Markdown preview. A colour means the same thing in every diagram:

| Colour | Part |
|---|---|
| pink | the form and its widgets |
| yellow, dashed border | interfaces |
| green | Linux adapters and their helpers |
| lavender, dashed border | Windows adapters, not written yet |
| blue | programs the adapters start |
| orange | PipeWire and the audio devices |
| purple | the app object and the user |
| mint | small data classes |

## Components

```mermaid
%%{init: {"theme": "base", "themeVariables": {"lineColor": "#64748b", "primaryTextColor": "#000000", "primaryBorderColor": "#000000", "textColor": "#000000", "titleColor": "#000000", "edgeLabelBackground": "#ffffff", "fontSize": "14px"}}}%%
flowchart TB
    app["<b>Mic2SpeakerApp<br/>app.py</b>"]

    subgraph ui ["<b>ui: the form</b>"]
        main_window["<b>MainWindow</b>"]
        widgets["<b>DeviceComboBox<br/>VolumeSlider<br/>ToggleButton</b>"]
    end

    subgraph interfaces ["<b>audio: interfaces</b>"]
        device_provider["<b>«interface»<br/>AudioDeviceProvider</b>"]
        audio_loopback["<b>«interface»<br/>AudioLoopback</b>"]
        device_watcher["<b>«interface»<br/>AudioDeviceWatcher</b>"]
    end

    subgraph linux_adapters ["<b>audio: Linux adapters</b>"]
        linux_provider["<b>LinuxAudioDeviceProvider</b>"]
        linux_loopback["<b>LinuxAudioLoopback</b>"]
        linux_watcher["<b>LinuxAudioDeviceWatcher</b>"]
        filter_process["<b>LinuxFilterProcess</b>"]
        support_checker["<b>LinuxFilterSupportChecker</b>"]
    end

    subgraph windows_adapters ["<b>audio: Windows adapters, not written yet</b>"]
        windows_provider["<b>WindowsAudioDeviceProvider</b>"]
        windows_loopback["<b>WindowsAudioLoopback</b>"]
        windows_watcher["<b>WindowsAudioDeviceWatcher</b>"]
    end

    subgraph linux_programs ["<b>Linux programs</b>"]
        pactl_subscribe["<b>pactl subscribe</b>"]
        pw_loopback["<b>pw-loopback</b>"]
        pactl["<b>pactl</b>"]
        pipewire_helper["<b>pipewire -c filters.conf</b>"]
    end

    pipewire_server[("<b>PipeWire server<br/>and WirePlumber</b>")]

    app --> main_window
    main_window --- widgets
    main_window --> device_provider
    main_window --> audio_loopback
    main_window --> device_watcher

    device_provider -.-> linux_provider
    audio_loopback -.-> linux_loopback
    device_watcher -.-> linux_watcher
    device_provider -.-> windows_provider
    audio_loopback -.-> windows_loopback
    device_watcher -.-> windows_watcher

    linux_loopback --> filter_process
    linux_loopback --> support_checker
    linux_provider --> pactl
    linux_loopback --> pw_loopback
    filter_process --> pipewire_helper
    linux_watcher --> pactl_subscribe
    pactl & pactl_subscribe & pw_loopback & pipewire_helper --> pipewire_server

    classDef app_part fill:#f3e8ff,stroke:#000000,color:#000000
    classDef form_part fill:#fce7f3,stroke:#000000,color:#000000
    classDef interface_part fill:#fef9c3,stroke:#000000,color:#000000,stroke-dasharray:5 3
    classDef linux_part fill:#dcfce7,stroke:#000000,color:#000000
    classDef windows_part fill:#ede9fe,stroke:#000000,color:#000000,stroke-dasharray:5 3
    classDef program_part fill:#dbeafe,stroke:#000000,color:#000000
    classDef pipewire_part fill:#ffedd5,stroke:#000000,color:#000000

    class app app_part
    class main_window,widgets form_part
    class device_provider,audio_loopback,device_watcher interface_part
    class linux_provider,linux_loopback,linux_watcher,filter_process,support_checker linux_part
    class windows_provider,windows_loopback,windows_watcher windows_part
    class pactl,pactl_subscribe,pw_loopback,pipewire_helper program_part
    class pipewire_server pipewire_part

    style ui fill:#fdf2f8,stroke:#000000,color:#000000
    style interfaces fill:#fefce8,stroke:#000000,color:#000000
    style linux_adapters fill:#f0fdf4,stroke:#000000,color:#000000
    style windows_adapters fill:#f5f3ff,stroke:#000000,color:#000000
    style linux_programs fill:#eff6ff,stroke:#000000,color:#000000
```

Solid arrows point to what a part uses or starts. Dotted arrows point from an interface to the classes that implement it. Two arrows are left out to keep the picture readable: `Mic2SpeakerApp` also creates the adapters for the operating system it runs on and hands them to `MainWindow`, and `LinuxAudioLoopback` also runs `pactl` to set the volume.

The form never imports an adapter. Supporting another operating system therefore means writing three adapter classes and choosing them in `app.py`; the form and its tests stay as they are. [WINDOWS.md](WINDOWS.md) walks through this for Windows.

## Classes

The form and the interfaces it depends on:

```mermaid
%%{init: {"theme": "base", "themeVariables": {"lineColor": "#64748b", "primaryTextColor": "#000000", "primaryBorderColor": "#000000", "textColor": "#000000", "titleColor": "#000000", "fontSize": "14px"}}}%%
classDiagram
    direction TB
    class Mic2SpeakerApp {
        +run() int
    }
    class MainWindow {
        +redetect_devices()
    }
    class DeviceComboBox {
        +show_devices(devices)
        +selected_device() AudioDevice
        +device_count() int
    }
    class VolumeSlider {
        +volume_changed(int) signal
        +volume() int
        +set_volume(volume_percent)
    }
    class ToggleButton {
        +toggled(bool) signal
        +isChecked() bool
    }
    class AudioDeviceProvider {
        <<interface>>
        +list_microphones() list~AudioDevice~
        +list_speakers() list~AudioDevice~
    }
    class AudioLoopback {
        <<interface>>
        +start(microphone, speaker, filters, on_stopped)
        +stop()
        +is_running() bool
        +set_volume(volume_percent)
        +filter_support() FilterSupport
    }
    class AudioDeviceWatcher {
        <<interface>>
        +start(on_devices_changed)
        +stop()
    }
    class AudioDevice {
        +system_name: str
        +display_name: str
        +is_default: bool
    }
    class AudioFilters {
        +echo_canceller: bool
        +frequency_shifter: bool
        +noise_gate: bool
        +any_enabled() bool
        +enabled_names() list~str~
    }
    class FilterSupport {
        +echo_canceller: FilterAvailability
        +frequency_shifter: FilterAvailability
        +noise_gate: FilterAvailability
        +problems_with(filters) list~str~
    }
    class FilterAvailability {
        +is_available: bool
        +reason: str
    }

    Mic2SpeakerApp *-- MainWindow
    MainWindow *-- DeviceComboBox
    MainWindow *-- VolumeSlider
    MainWindow *-- ToggleButton
    MainWindow --> AudioDeviceProvider
    MainWindow --> AudioLoopback
    MainWindow --> AudioDeviceWatcher
    AudioDeviceProvider ..> AudioDevice : returns
    DeviceComboBox ..> AudioDevice : shows
    AudioLoopback ..> AudioFilters : takes
    AudioLoopback ..> FilterSupport : reports
    FilterSupport *-- FilterAvailability

    style Mic2SpeakerApp fill:#f3e8ff,stroke:#000000,color:#000000
    style MainWindow fill:#fce7f3,stroke:#000000,color:#000000
    style DeviceComboBox fill:#fce7f3,stroke:#000000,color:#000000
    style VolumeSlider fill:#fce7f3,stroke:#000000,color:#000000
    style ToggleButton fill:#fce7f3,stroke:#000000,color:#000000
    style AudioDeviceProvider fill:#fef9c3,stroke:#000000,color:#000000,stroke-dasharray:5 3
    style AudioLoopback fill:#fef9c3,stroke:#000000,color:#000000,stroke-dasharray:5 3
    style AudioDeviceWatcher fill:#fef9c3,stroke:#000000,color:#000000,stroke-dasharray:5 3
    style AudioDevice fill:#ccfbf1,stroke:#000000,color:#000000
    style AudioFilters fill:#ccfbf1,stroke:#000000,color:#000000
    style FilterSupport fill:#ccfbf1,stroke:#000000,color:#000000
    style FilterAvailability fill:#ccfbf1,stroke:#000000,color:#000000
```

The Linux adapters and the classes they use:

```mermaid
%%{init: {"theme": "base", "themeVariables": {"lineColor": "#64748b", "primaryTextColor": "#000000", "primaryBorderColor": "#000000", "textColor": "#000000", "titleColor": "#000000", "fontSize": "14px"}}}%%
classDiagram
    direction TB
    class AudioDeviceProvider
    <<interface>> AudioDeviceProvider
    class AudioLoopback
    <<interface>> AudioLoopback
    class AudioDeviceWatcher
    <<interface>> AudioDeviceWatcher

    class LinuxAudioDeviceProvider {
        +list_microphones() list~AudioDevice~
        +list_speakers() list~AudioDevice~
    }
    class LinuxAudioLoopback {
        +LATENCY_MS = 10
        +start(microphone, speaker, filters, on_stopped)
        +stop()
        +set_volume(volume_percent)
        +filter_support() FilterSupport
    }
    class LinuxAudioDeviceWatcher {
        +SETTLE_TIME_MS = 300
        +RESTART_DELAY_MS = 2000
        +start(on_devices_changed)
        +stop()
    }
    class LinuxFilterProcess {
        +start(microphone, speaker, filters) str
        +stop()
    }
    class LinuxFilterConfig {
        +build() dict
        +output_source_name() str
    }
    class FilterStage {
        +name: str
        +label: str
        +input_port: str
        +output_port: str
        +controls: dict
        +plugin_file: str or None
    }
    class LinuxFilterSupportChecker {
        +check() FilterSupport
    }

    AudioDeviceProvider <|.. LinuxAudioDeviceProvider
    AudioLoopback <|.. LinuxAudioLoopback
    AudioDeviceWatcher <|.. LinuxAudioDeviceWatcher
    LinuxAudioLoopback *-- LinuxFilterProcess
    LinuxAudioLoopback ..> LinuxFilterSupportChecker : asks
    LinuxFilterProcess ..> LinuxFilterConfig : builds
    LinuxFilterConfig ..> FilterStage : chains
    LinuxFilterSupportChecker ..> FilterStage : looks for its plugin

    style AudioDeviceProvider fill:#fef9c3,stroke:#000000,color:#000000,stroke-dasharray:5 3
    style AudioLoopback fill:#fef9c3,stroke:#000000,color:#000000,stroke-dasharray:5 3
    style AudioDeviceWatcher fill:#fef9c3,stroke:#000000,color:#000000,stroke-dasharray:5 3
    style LinuxAudioDeviceProvider fill:#dcfce7,stroke:#000000,color:#000000
    style LinuxAudioLoopback fill:#dcfce7,stroke:#000000,color:#000000
    style LinuxAudioDeviceWatcher fill:#dcfce7,stroke:#000000,color:#000000
    style LinuxFilterProcess fill:#dcfce7,stroke:#000000,color:#000000
    style LinuxFilterConfig fill:#dcfce7,stroke:#000000,color:#000000
    style LinuxFilterSupportChecker fill:#dcfce7,stroke:#000000,color:#000000
    style FilterStage fill:#ccfbf1,stroke:#000000,color:#000000
```

The helper modules `linux_pactl` and `linux_child_process`, which most of these classes use, are left out of the diagram; the paragraph below the table describes them.

| Class | Module | Job |
|---|---|---|
| `Mic2SpeakerApp` | `app.py` | creates the Qt application, picks the adapters, shows the window |
| `MainWindow` | `ui/main_window.py` | the form; reacts to the toggle, the dropdowns, the slider, the menus, and device changes |
| `DeviceComboBox` | `ui/device_combo_box.py` | dropdown of `AudioDevice` items; keeps the user's choice when the list is refilled |
| `VolumeSlider` | `ui/volume_slider.py` | slider from 0 to 150 % with a number box for typing an exact value |
| `ToggleButton` | `ui/toggle_button.py` | the ON/OFF button; its text and colour follow its state |
| `AudioDevice` | `audio/audio_device.py` | one microphone or speaker: `system_name`, `display_name`, `is_default` |
| `AudioFilters` | `audio/audio_filters.py` | which of the echo canceller, frequency shifter, and noise gate are on |
| `FilterSupport`, `FilterAvailability` | `audio/audio_filters.py` | which filters this computer can run, and why the others cannot |
| `AudioDeviceProvider` | `audio/audio_device_provider.py` | interface with `list_microphones()` and `list_speakers()` |
| `AudioLoopback` | `audio/audio_loopback.py` | interface with `start(microphone, speaker, filters, on_stopped)`, `stop()`, `is_running()`, `set_volume()`, and `filter_support()` |
| `AudioDeviceWatcher` | `audio/audio_device_watcher.py` | interface with `start(on_devices_changed)` and `stop()` |
| `LinuxAudioDeviceProvider` | `audio/linux_audio_device_provider.py` | Linux adapter; reads the devices with `pactl --format=json` |
| `LinuxAudioLoopback` | `audio/linux_audio_loopback.py` | Linux adapter; runs `pw-loopback` and sets the volume of its stream |
| `LinuxFilterProcess` | `audio/linux_filter_process.py` | runs the filters in a `pipewire -c <config>` helper process |
| `LinuxFilterConfig` | `audio/linux_filter_config.py` | builds that config for one set of filters |
| `LinuxFilterSupportChecker` | `audio/linux_filter_support.py` | finds out which filters this Linux computer can run, by looking for files |
| `LinuxAudioDeviceWatcher` | `audio/linux_audio_device_watcher.py` | Linux adapter; reads the events that `pactl subscribe` prints |

Three small helper modules support the Linux classes. `linux_pactl.py` runs `pactl` and turns its failures into one exception type, `linux_node_names.py` holds the names of the PipeWire nodes the app creates, and `linux_child_process.py` holds `command_that_ends_with_app()` (see [When the app closes or crashes](#when-the-app-closes-or-crashes)).

`AudioDevice.system_name` is the name the audio system uses (on Linux, for example, `alsa_input.usb-...mono-fallback`). It stays the same between runs, which lets `DeviceComboBox` keep the user's choice when the lists are refilled. `display_name` is what the user sees.

## What happens when you click ON

```mermaid
%%{init: {"theme": "base", "themeVariables": {"primaryTextColor": "#000000", "primaryBorderColor": "#000000", "textColor": "#000000", "titleColor": "#000000", "actorBkg": "#ffffff", "actorBorder": "#000000", "actorTextColor": "#000000", "actorLineColor": "#94a3b8", "signalColor": "#475569", "signalTextColor": "#000000", "labelBoxBkgColor": "#fef9c3", "labelBoxBorderColor": "#000000", "labelTextColor": "#000000", "loopTextColor": "#000000", "noteBkgColor": "#fef9c3", "noteBorderColor": "#000000", "noteTextColor": "#000000", "fontSize": "14px"}, "sequence": {"actorFontWeight": "bold"}}}%%
sequenceDiagram
    box rgb(243,232,255) User
        actor User
    end
    box rgb(252,231,243) Form
        participant Toggle as ToggleButton
        participant Window as MainWindow
    end
    box rgb(220,252,231) Linux adapters
        participant Loopback as LinuxAudioLoopback
        participant Checker as LinuxFilterSupportChecker
        participant Filters as LinuxFilterProcess
    end
    box rgb(219,234,254) Programs
        participant System as pactl, pw-loopback, pipewire
    end

    User->>Toggle: click
    Toggle->>Window: toggled(True)
    Window->>Window: read the dropdowns and the Filters menu
    Window->>Loopback: start(microphone, speaker, filters, on_stopped)
    Loopback->>Loopback: stop() whatever still runs
    opt a filter is ticked
        Loopback->>Checker: check()
        Checker-->>Loopback: FilterSupport
        Loopback->>Filters: start(microphone, speaker, filters)
        Filters->>System: pipewire -c filters.conf
        loop until the virtual microphone appears, at most 3 s
            Filters->>System: pactl list sources
        end
        Filters-->>Loopback: name of the virtual microphone
    end
    Loopback->>System: pw-loopback --capture ... --playback ...
    loop until the playback stream appears, at most 2 s
        Loopback->>System: pactl list sink-inputs
    end
    Loopback->>System: pactl set-sink-input-volume
    Loopback-->>Window: returns
    Window->>User: status bar: Playing ... through ...
```

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

Every way the start can end, including the errors the user sees:

```mermaid
%%{init: {"theme": "base", "themeVariables": {"lineColor": "#64748b", "primaryTextColor": "#000000", "primaryBorderColor": "#000000", "textColor": "#000000", "titleColor": "#000000", "edgeLabelBackground": "#ffffff", "fontSize": "14px"}}}%%
flowchart TD
    switched_on(["<b>User switches ON</b>"]) --> devices_chosen{"<b>Microphone and<br/>speaker selected?</b>"}
    devices_chosen -- no --> pick_devices[/"<b>Status: Pick a microphone and a speaker first.</b>"/]
    pick_devices --> toggle_off(["<b>Toggle goes back to OFF</b>"])
    devices_chosen -- yes --> stop_old["<b>Stop the sound and filters that still run</b>"]
    stop_old --> filter_ticked{"<b>Any filter<br/>ticked?</b>"}
    filter_ticked -- no --> start_loopback
    filter_ticked -- yes --> filters_supported{"<b>Can this computer<br/>run them?</b>"}
    filters_supported -- no --> could_not_start[/"<b>Status: Could not start the sound, with the reason</b>"/]
    could_not_start --> toggle_off
    filters_supported -- yes --> start_filters["<b>Start pipewire -c filters.conf</b>"]
    start_filters --> source_ready{"<b>Virtual microphone<br/>within 3 s?</b>"}
    source_ready -- no --> stop_filters["<b>Stop the filter process</b>"]
    stop_filters --> could_not_start
    source_ready -- yes --> start_loopback["<b>Start pw-loopback to the speaker</b>"]
    start_loopback --> loopback_started{"<b>pw-loopback<br/>started?</b>"}
    loopback_started -- no --> could_not_start
    loopback_started -- yes --> set_volume["<b>Wait for the playback stream<br/>and set its volume</b>"]
    set_volume --> playing(["<b>Status: Playing ... through ...</b>"])

    classDef start_step fill:#f3e8ff,stroke:#000000,color:#000000
    classDef decision_step fill:#fef9c3,stroke:#000000,color:#000000
    classDef action_step fill:#dbeafe,stroke:#000000,color:#000000
    classDef error_step fill:#ffe4e6,stroke:#000000,color:#000000
    classDef success_step fill:#dcfce7,stroke:#000000,color:#000000

    class switched_on start_step
    class devices_chosen,filter_ticked,filters_supported,source_ready,loopback_started decision_step
    class stop_old,start_filters,stop_filters,start_loopback,set_volume action_step
    class pick_devices,could_not_start,toggle_off error_step
    class playing success_step
```

Picking another device or ticking a filter while the toggle is ON repeats this from the start. Moving the volume slider calls `audio_loopback.set_volume()`, which changes the stream's volume at once. Clicking OFF calls `audio_loopback.stop()`, which ends `pw-loopback` and the filters.

WirePlumber remembers the last volume of each stream and sets it again when the stream appears. Because the app sets the slider's value right after the stream appears, the slider's value is what you hear.

## Filters

The filters run in a helper process started with `pipewire -c <config file>`. `LinuxFilterConfig` builds the config as Python dictionaries and `LinuxFilterProcess` saves it as JSON, which PipeWire's SPA-JSON format accepts, in a temporary directory. With every filter ticked, the sound takes this path; a filter that is not ticked is simply left out of the chain:

```mermaid
%%{init: {"theme": "base", "themeVariables": {"lineColor": "#64748b", "primaryTextColor": "#000000", "primaryBorderColor": "#000000", "textColor": "#000000", "titleColor": "#000000", "edgeLabelBackground": "#ffffff", "fontSize": "14px"}}}%%
flowchart LR
    microphone(["<b>Microphone</b>"])

    subgraph helper ["<b>pipewire -c filters.conf</b>"]
        echo_canceller["<b>Echo canceller<br/>WebRTC, monitor mode</b>"]
        noise_gate["<b>Noise gate<br/>gate_1410.so</b>"]
        frequency_shifter["<b>Frequency shifter<br/>bode_shifter_1431.so<br/>+5 Hz</b>"]
        makeup_gain["<b>Makeup gain<br/>built-in linear, ×2</b>"]
        virtual_microphone(["<b>Virtual microphone</b>"])
    end

    pw_loopback["<b>pw-loopback<br/>10 ms buffer, volume</b>"]
    speaker(["<b>Speaker</b>"])

    microphone --> echo_canceller --> noise_gate --> frequency_shifter --> makeup_gain --> virtual_microphone
    virtual_microphone --> pw_loopback --> speaker
    speaker -.->|"monitor: what the speaker plays"| echo_canceller

    classDef device_part fill:#ffedd5,stroke:#000000,color:#000000
    classDef filter_part fill:#dcfce7,stroke:#000000,color:#000000
    classDef virtual_part fill:#ccfbf1,stroke:#000000,color:#000000
    classDef program_part fill:#dbeafe,stroke:#000000,color:#000000

    class microphone,speaker device_part
    class echo_canceller,noise_gate,frequency_shifter,makeup_gain filter_part
    class virtual_microphone virtual_part
    class pw_loopback program_part

    style helper fill:#eff6ff,stroke:#000000,color:#000000
```

- The echo canceller is PipeWire's `libpipewire-module-echo-cancel` with the WebRTC library, noise suppression, and the high-pass filter, without automatic gain (which would raise the feedback). It runs in monitor mode: it takes the sound to remove from the speaker's monitor. The other mode, in which pw-loopback would play into a sink that belongs to the echo canceller, makes a loop between the canceller's own nodes, and WirePlumber refuses to link such loops.
- The noise gate (`gate_1410.so` from swh-plugins) and the frequency shifter (`bode_shifter_1431.so`, shifted up 5 Hz) run in `libpipewire-module-filter-chain`. The shifter's output is 6 dB quieter than its input, so PipeWire's built-in `linear` plugin doubles it again.
- The last filter offers its output as a virtual microphone (`mic2speaker_echo_cancel_source` or `mic2speaker_filtered_microphone`), which pw-loopback reads.

`LinuxFilterProcess.start` waits until that virtual microphone appears before pw-loopback starts, because pw-loopback would otherwise give up on its missing target. The virtual devices all start with `mic2speaker`, and `LinuxAudioDeviceProvider` leaves them out of the dropdowns.

### Which filters can run

Other computers may lack some of these parts. `LinuxAudioLoopback.filter_support()` asks `LinuxFilterSupportChecker`, which only looks for files and starts nothing:

| Filter | Needs |
|---|---|
| all three | the `pipewire` program |
| echo canceller | the echo-cancel module with the text `monitor.mode` inside it (older PipeWire versions lack monitor mode), and the WebRTC plugin |
| noise gate | the filter-chain module and `gate_1410.so` |
| frequency shifter | the filter-chain module and `bode_shifter_1431.so` |

The result is a `FilterSupport` with one `FilterAvailability` per filter. `MainWindow` greys out the filters that cannot run, adds "(not available)" to their names, and puts the reason, such as the package to install, in their tooltips. `start()` checks again and refuses an unavailable filter with the same reason, so the sound never depends on the menu's state alone. A filter that passes the file check can still fail to start; the user then sees PipeWire's error in the status bar.

## When a device is plugged in or out

```mermaid
%%{init: {"theme": "base", "themeVariables": {"primaryTextColor": "#000000", "primaryBorderColor": "#000000", "textColor": "#000000", "titleColor": "#000000", "actorBkg": "#ffffff", "actorBorder": "#000000", "actorTextColor": "#000000", "actorLineColor": "#94a3b8", "signalColor": "#475569", "signalTextColor": "#000000", "noteBkgColor": "#fef9c3", "noteBorderColor": "#000000", "noteTextColor": "#000000", "fontSize": "14px"}, "sequence": {"actorFontWeight": "bold"}}}%%
sequenceDiagram
    box rgb(255,237,213) PipeWire
        participant Server as PipeWire server
    end
    box rgb(219,234,254) Programs
        participant Subscribe as pactl subscribe
    end
    box rgb(220,252,231) Linux adapters
        participant Watcher as LinuxAudioDeviceWatcher
        participant Provider as LinuxAudioDeviceProvider
    end
    box rgb(252,231,243) Form
        participant Window as MainWindow
    end

    Note over Server: a USB headset is plugged in
    Server-->>Subscribe: new sink, new source
    Subscribe->>Watcher: Event 'new' on sink ...
    Subscribe->>Watcher: Event 'new' on source ...
    Note over Watcher: every device line restarts the 300 ms settle timer
    Watcher->>Window: on_devices_changed(), once the events are quiet
    Window->>Provider: list_microphones() and list_speakers()
    Provider-->>Window: AudioDevice lists, without Mic2Speaker's own virtual devices
    Window->>Window: refill the dropdowns, keep the selection, leave the status bar alone
```

`LinuxAudioDeviceWatcher` keeps `pactl subscribe` running. That command prints a line for every change on the audio server, such as `Event 'new' on sink #57`. The watcher reacts to new or removed sinks (speakers) and sources (microphones), and to `change` events on the server, which is how a new system default device shows up. It ignores `change` events on sinks and sources, because those fire on every volume change and whenever a device starts playing, including for Mic2Speaker's own sound. It runs `pactl` with `LC_ALL=C` because pactl translates the line format.

Plugging in a USB headset produces several events in quick succession, so the watcher waits until the events have been quiet for 300 ms and then calls `MainWindow._handle_devices_changed` once. That method refills both dropdowns and leaves the status bar alone. Devices that are still connected stay selected, so sound that is playing goes on. If `pactl subscribe` exits, for example because PipeWire restarted, the watcher starts it again after two seconds and reports one change so that the lists are read again.

Devices > Redetect inputs and outputs (F5) calls `MainWindow.redetect_devices`, which refills the dropdowns the same way and also shows how many devices it found.

## When a device in use is unplugged

```mermaid
%%{init: {"theme": "base", "themeVariables": {"primaryTextColor": "#000000", "primaryBorderColor": "#000000", "textColor": "#000000", "titleColor": "#000000", "actorBkg": "#ffffff", "actorBorder": "#000000", "actorTextColor": "#000000", "actorLineColor": "#94a3b8", "signalColor": "#475569", "signalTextColor": "#000000", "noteBkgColor": "#fef9c3", "noteBorderColor": "#000000", "noteTextColor": "#000000", "fontSize": "14px"}, "sequence": {"actorFontWeight": "bold"}}}%%
sequenceDiagram
    box rgb(243,232,255) User
        actor User
    end
    box rgb(255,237,213) PipeWire
        participant Session as PipeWire and WirePlumber
    end
    box rgb(219,234,254) Programs
        participant Helper as pipewire -c filters.conf
        participant PwLoopback as pw-loopback
    end
    box rgb(220,252,231) Linux adapters
        participant Loopback as LinuxAudioLoopback
    end
    box rgb(252,231,243) Form
        participant Window as MainWindow
    end

    User->>Session: unplugs the USB microphone
    Session->>Helper: destroys the stream that read the microphone
    Note over Helper: the filter unloads itself and its virtual microphone disappears
    Session->>PwLoopback: destroys the stream that read the virtual microphone
    PwLoopback-->>Loopback: exits, QProcess.finished
    Loopback->>Helper: stop the filter process
    Loopback->>Window: on_stopped(the microphone or speaker is no longer available.)
    Window->>Window: toggle OFF, refill the dropdowns
    Window->>User: status bar: The sound stopped: ...
```

Every stream carries `node.dont-reconnect=true`: pw-loopback's two streams and, when filters run, the streams of the echo canceller and the filter chain. Without it, WirePlumber (PipeWire's session manager) would move the sound to another device, for example from unplugged USB speakers to the laptop speakers next to the microphone. With it, WirePlumber destroys the stream instead. A filter whose stream is destroyed unloads itself, its virtual microphone disappears, and that in turn ends pw-loopback's capture stream. Without filters, the unplugged device ends one of pw-loopback's streams directly. Either way, `pw-loopback` exits.

`LinuxAudioLoopback` notices the exit through `QProcess.finished`, ends the filter process (which keeps running even with nothing left in it), and calls the `on_stopped` callback. `MainWindow._handle_sound_stopped` then turns the toggle OFF, refills the device lists, and shows the reason in the status bar. When the app itself calls `stop()`, the adapter disconnects from `finished` first, so a requested stop is never reported as an unexpected one.

## When the app closes or crashes

```mermaid
%%{init: {"theme": "base", "themeVariables": {"lineColor": "#64748b", "primaryTextColor": "#000000", "primaryBorderColor": "#000000", "textColor": "#000000", "titleColor": "#000000", "edgeLabelBackground": "#ffffff", "fontSize": "14px"}}}%%
flowchart LR
    subgraph app_process ["<b>Mic2Speaker process</b>"]
        qt_application["<b>Qt event loop<br/>MainWindow and the adapters</b>"]
    end

    pw_loopback["<b>pw-loopback</b>"]
    pipewire_helper["<b>pipewire -c filters.conf</b>"]
    pactl_subscribe["<b>pactl subscribe</b>"]
    pipewire_server[("<b>PipeWire server</b>")]

    qt_application -->|"setpriv --pdeathsig TERM"| pw_loopback
    qt_application -->|"setpriv --pdeathsig TERM"| pipewire_helper
    qt_application -->|"setpriv --pdeathsig TERM"| pactl_subscribe
    pw_loopback & pipewire_helper & pactl_subscribe --> pipewire_server

    classDef app_part fill:#fce7f3,stroke:#000000,color:#000000
    classDef program_part fill:#dbeafe,stroke:#000000,color:#000000
    classDef pipewire_part fill:#ffedd5,stroke:#000000,color:#000000

    class qt_application app_part
    class pw_loopback,pipewire_helper,pactl_subscribe program_part
    class pipewire_server pipewire_part

    style app_process fill:#fdf2f8,stroke:#000000,color:#000000
```

`MainWindow.closeEvent` stops the device watcher and the sound before the window closes. For crashes, `pw-loopback`, `pipewire -c`, and `pactl subscribe` are all started through `command_that_ends_with_app()`, which puts `setpriv --pdeathsig TERM` in front of the command. setpriv asks the Linux kernel to send the program SIGTERM when its parent (the app) dies, so the microphone cannot keep playing without a window to switch it off. If `setpriv` is not installed, the programs are started directly and this protection is lost.

## Tests

`tests/fakes.py` has `FakeDeviceProvider`, `FakeAudioLoopback`, and `FakeDeviceWatcher`, which implement the three interfaces without making sound. `tests/simulated_user.py` has `SimulatedUser`, which clicks, picks, drags the slider, types a volume, and ticks menu items on the form the way a person would, finding the widgets with `findChild()` and their object names. With these, `tests/test_main_window.py` checks the form's behaviour on any operating system. `tests/test_linux_filter_config.py` checks the filter config for each combination of filters, with empty files standing in for the LADSPA plugins. `tests/test_linux_filter_support.py` builds pretend computers in a temporary directory, each missing a different file, and checks what the support check reports.

`tests/test_linux_audio_integration.py` checks the Linux adapters against the real PipeWire server, using temporary virtual devices made with `pactl load-module module-null-sink`. It checks how every filter is linked, that unplugging the microphone or the speaker ends everything, and that the watcher notices devices and ignores the app's own sound. For the filters' effect it plays test tones into a virtual microphone and measures what reaches a virtual speaker: the noise gate must block a -70 dBFS tone and pass a -20 dBFS one, and the frequency shifter must keep the level within 2 dB. Every filter that `filter_support()` reports as available must also start. Tests of filters this computer cannot run are skipped with the reason, and all integration tests are skipped while another Mic2Speaker plays sound, because its streams and devices have the same names.
