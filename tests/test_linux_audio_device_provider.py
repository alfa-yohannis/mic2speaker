"""Tests for the Linux device adapter, with pactl's answers faked."""

import json
import subprocess

import pytest

from mic2speaker.audio.audio_device import AudioDevice
from mic2speaker.audio.audio_device_provider import AudioDeviceError
from mic2speaker.audio.linux_audio_device_provider import LinuxAudioDeviceProvider

SOURCES = [
    {"name": "alsa_output.usb.monitor", "description": "Monitor of USB Speaker", "properties": {"device.class": "monitor"}},
    {"name": "alsa_input.builtin", "description": "Built-in Microphone", "properties": {"device.class": "sound"}},
    {"name": "alsa_input.usb", "description": "USB Microphone", "properties": {"device.class": "sound"}},
]
SINKS = [
    {"name": "alsa_output.builtin", "description": "Built-in Speaker", "properties": {"device.class": "sound"}},
    {"name": "alsa_output.usb", "description": "USB Speaker", "properties": {"device.class": "sound"}},
]
SOURCES_JSON = json.dumps(SOURCES)
SINKS_JSON = json.dumps(SINKS)

PACTL_ANSWERS = {
    ("--format=json", "list", "sources"): SOURCES_JSON,
    ("--format=json", "list", "sinks"): SINKS_JSON,
    ("get-default-source",): "alsa_input.usb\n",
    ("get-default-sink",): "alsa_output.usb\n",
}


class FakePactl:
    """Stands in for subprocess.run and answers pactl commands from a table."""

    def __init__(self, answers: dict[tuple[str, ...], str]) -> None:
        self._answers = answers

    def run(self, command: list[str], **_options) -> subprocess.CompletedProcess:
        """Return the prepared answer for ``command`` as if pactl had printed it."""
        pactl_arguments = tuple(command[1:])
        answer = self._answers[pactl_arguments]
        return subprocess.CompletedProcess(command, returncode=0, stdout=answer, stderr="")


def run_without_pactl(command: list[str], **_options) -> subprocess.CompletedProcess:
    """Behave like subprocess.run when pactl is not installed."""
    raise FileNotFoundError(command[0])


def run_failing_pactl(command: list[str], **_options) -> subprocess.CompletedProcess:
    """Behave like subprocess.run when pactl cannot reach the audio server."""
    raise subprocess.CalledProcessError(1, command, stderr="Connection failure: Connection refused\n")


@pytest.fixture
def provider(monkeypatch) -> LinuxAudioDeviceProvider:
    """A provider whose pactl calls are answered by FakePactl."""
    fake_pactl = FakePactl(PACTL_ANSWERS)
    monkeypatch.setattr(subprocess, "run", fake_pactl.run)
    return LinuxAudioDeviceProvider()


def test_microphones_leave_out_the_monitor_sources(provider):
    microphones = provider.list_microphones()

    assert microphones == [
        AudioDevice("alsa_input.builtin", "Built-in Microphone", is_default=False),
        AudioDevice("alsa_input.usb", "USB Microphone", is_default=True),
    ]


def test_speakers_mark_the_system_default(provider):
    speakers = provider.list_speakers()

    assert speakers == [
        AudioDevice("alsa_output.builtin", "Built-in Speaker", is_default=False),
        AudioDevice("alsa_output.usb", "USB Speaker", is_default=True),
    ]


def test_missing_pactl_is_reported_as_audio_device_error(monkeypatch):
    monkeypatch.setattr(subprocess, "run", run_without_pactl)
    provider = LinuxAudioDeviceProvider()

    with pytest.raises(AudioDeviceError, match="not installed"):
        provider.list_microphones()


def test_pactl_failure_message_is_passed_on(monkeypatch):
    monkeypatch.setattr(subprocess, "run", run_failing_pactl)
    provider = LinuxAudioDeviceProvider()

    with pytest.raises(AudioDeviceError, match="Connection refused"):
        provider.list_speakers()


def test_output_that_is_not_json_is_reported_as_audio_device_error(monkeypatch):
    answers_with_bad_json = dict(PACTL_ANSWERS)
    answers_with_bad_json[("--format=json", "list", "sinks")] = "this is not JSON"
    fake_pactl = FakePactl(answers_with_bad_json)
    monkeypatch.setattr(subprocess, "run", fake_pactl.run)
    provider = LinuxAudioDeviceProvider()

    with pytest.raises(AudioDeviceError, match="not JSON"):
        provider.list_speakers()
