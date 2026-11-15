"""Linux adapter that reads the audio devices with the ``pactl`` command.

``pactl`` is the PulseAudio command-line tool. PipeWire, the default audio
system on current Linux desktops, answers it as well, so this adapter works
with both.
"""

import json
import subprocess

from mic2speaker.audio.audio_device import AudioDevice
from mic2speaker.audio.audio_device_provider import AudioDeviceError, AudioDeviceProvider


class LinuxAudioDeviceProvider(AudioDeviceProvider):
    """Lists microphones and speakers by running ``pactl``.

    PulseAudio calls a microphone a "source" and a speaker a "sink". Every
    sink also has a "Monitor of ..." source that records what the speaker
    plays. Those monitors are left out of the microphone list.
    """

    PACTL_COMMAND = "pactl"
    PACTL_TIMEOUT_SECONDS = 5
    MONITOR_DEVICE_CLASS = "monitor"

    def list_microphones(self) -> list[AudioDevice]:
        """Return the real microphones, that is, every source except the monitors."""
        sources = self._run_pactl_json(["list", "sources"])
        default_source_name = self._run_pactl_text(["get-default-source"])

        microphones = []
        for source in sources:
            if self._is_monitor(source):
                continue
            microphone = self._to_audio_device(source, default_source_name)
            microphones.append(microphone)
        return microphones

    def list_speakers(self) -> list[AudioDevice]:
        """Return every sink as a speaker."""
        sinks = self._run_pactl_json(["list", "sinks"])
        default_sink_name = self._run_pactl_text(["get-default-sink"])

        speakers = []
        for sink in sinks:
            speaker = self._to_audio_device(sink, default_sink_name)
            speakers.append(speaker)
        return speakers

    def _is_monitor(self, source: dict) -> bool:
        """Tell whether ``source`` is a "Monitor of ..." source rather than a microphone."""
        properties = source.get("properties", {})
        device_class = properties.get("device.class")
        return device_class == self.MONITOR_DEVICE_CLASS

    def _to_audio_device(self, pactl_entry: dict, default_system_name: str) -> AudioDevice:
        """Turn one entry of ``pactl --format=json list ...`` into an AudioDevice."""
        system_name = pactl_entry["name"]
        is_default = system_name == default_system_name
        return AudioDevice(
            system_name=system_name,
            display_name=pactl_entry["description"],
            is_default=is_default,
        )

    def _run_pactl_json(self, pactl_arguments: list[str]) -> list[dict]:
        """Run pactl with JSON output and return the parsed list."""
        json_arguments = ["--format=json"] + pactl_arguments
        output = self._run_pactl(json_arguments)
        try:
            return json.loads(output)
        except json.JSONDecodeError as error:
            raise AudioDeviceError(f"pactl printed something that is not JSON: {error}") from error

    def _run_pactl_text(self, pactl_arguments: list[str]) -> str:
        """Run pactl and return its output without the trailing newline."""
        output = self._run_pactl(pactl_arguments)
        return output.strip()

    def _run_pactl(self, pactl_arguments: list[str]) -> str:
        """Run pactl with ``pactl_arguments`` and return what it printed.

        Raises AudioDeviceError if pactl is missing, fails, or does not answer.
        """
        command = [self.PACTL_COMMAND] + pactl_arguments
        try:
            completed_process = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=self.PACTL_TIMEOUT_SECONDS,
                check=True,
            )
        except FileNotFoundError as error:
            raise AudioDeviceError("The pactl command is not installed.") from error
        except subprocess.TimeoutExpired as error:
            raise AudioDeviceError("pactl did not answer in time.") from error
        except subprocess.CalledProcessError as error:
            error_text = error.stderr.strip()
            raise AudioDeviceError(f"pactl failed: {error_text}") from error
        return completed_process.stdout
