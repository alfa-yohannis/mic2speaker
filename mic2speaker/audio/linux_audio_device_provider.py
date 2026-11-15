"""Linux adapter that reads the audio devices with the ``pactl`` command.

``pactl`` is the PulseAudio command-line tool. PipeWire, the default audio
system on current Linux desktops, answers it as well, so this adapter works
with both.
"""

from mic2speaker.audio.audio_device import AudioDevice
from mic2speaker.audio.audio_device_provider import AudioDeviceError, AudioDeviceProvider
from mic2speaker.audio.linux_node_names import OWN_DEVICE_PREFIX
from mic2speaker.audio.linux_pactl import PactlError, read_pactl_list, run_pactl


class LinuxAudioDeviceProvider(AudioDeviceProvider):
    """Lists microphones and speakers by running ``pactl``.

    PulseAudio calls a microphone a "source" and a speaker a "sink". Every
    sink also has a "Monitor of ..." source that records what the speaker
    plays. Those monitors are left out of the microphone list, and so are the
    virtual devices that Mic2Speaker's own filters create.
    """

    MONITOR_DEVICE_CLASS = "monitor"

    def list_microphones(self) -> list[AudioDevice]:
        """Return the real microphones, that is, every source except the monitors."""
        sources = self._read_devices("sources")
        default_source_name = self._read_default("get-default-source")

        microphones = []
        for source in sources:
            if self._is_monitor(source):
                continue
            microphone = self._to_audio_device(source, default_source_name)
            microphones.append(microphone)
        return microphones

    def list_speakers(self) -> list[AudioDevice]:
        """Return every sink as a speaker."""
        sinks = self._read_devices("sinks")
        default_sink_name = self._read_default("get-default-sink")

        speakers = []
        for sink in sinks:
            speaker = self._to_audio_device(sink, default_sink_name)
            speakers.append(speaker)
        return speakers

    def _read_devices(self, kind: str) -> list[dict]:
        """Return the sinks or sources from pactl, leaving out Mic2Speaker's own virtual devices."""
        try:
            entries = read_pactl_list(kind)
        except PactlError as error:
            error_text = str(error)
            raise AudioDeviceError(error_text) from error

        devices = []
        for entry in entries:
            device_name = entry["name"]
            if device_name.startswith(OWN_DEVICE_PREFIX):
                continue
            devices.append(entry)
        return devices

    @staticmethod
    def _read_default(pactl_command: str) -> str:
        """Return the name of the default sink or source, for example via "get-default-sink"."""
        try:
            return run_pactl([pactl_command])
        except PactlError as error:
            error_text = str(error)
            raise AudioDeviceError(error_text) from error

    def _is_monitor(self, source: dict) -> bool:
        """Tell whether ``source`` is a "Monitor of ..." source rather than a microphone."""
        properties = source.get("properties", {})
        device_class = properties.get("device.class")
        return device_class == self.MONITOR_DEVICE_CLASS

    @staticmethod
    def _to_audio_device(pactl_entry: dict, default_system_name: str) -> AudioDevice:
        """Turn one entry of ``pactl --format=json list ...`` into an AudioDevice."""
        system_name = pactl_entry["name"]
        is_default = system_name == default_system_name
        return AudioDevice(
            system_name=system_name,
            display_name=pactl_entry["description"],
            is_default=is_default,
        )
