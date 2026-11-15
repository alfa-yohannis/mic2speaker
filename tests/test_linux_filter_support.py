"""Tests for the check of which filters a Linux computer can run.

Each test builds a pretend computer in a temporary directory, with only the
files the test wants, so the results do not depend on the real machine.
"""

import shutil
from pathlib import Path

import pytest

from mic2speaker.audio.audio_device import AudioDevice
from mic2speaker.audio.audio_filters import AudioFilters, FilterAvailability, FilterSupport
from mic2speaker.audio.audio_loopback import AudioLoopbackError
from mic2speaker.audio.linux_audio_loopback import LinuxAudioLoopback
from mic2speaker.audio.linux_filter_support import (
    ECHO_CANCEL_MODULE,
    FILTER_CHAIN_MODULE,
    WEBRTC_PLUGIN,
    LinuxFilterSupportChecker,
)

# Module files only need to contain the option names the check looks for.
NEW_ECHO_CANCEL_MODULE_CONTENT = b"library.name ... monitor.mode ... aec.args"
OLD_ECHO_CANCEL_MODULE_CONTENT = b"library.name ... aec.args"


def pretend_every_program_is_installed(command: str) -> str:
    """Stand in for shutil.which on a computer that has every program."""
    return f"/usr/bin/{command}"


def pretend_no_program_is_installed(command: str) -> None:
    """Stand in for shutil.which on a computer that has none of the programs."""
    return None


class PretendComputer:
    """A library directory and a LADSPA directory that hold only the files a test adds."""

    def __init__(self, root: Path) -> None:
        self._library_directory = root / "lib"
        self._plugin_directory = root / "ladspa"
        self._library_directory.mkdir()
        self._plugin_directory.mkdir()

    def add_echo_canceller(self, module_content: bytes = NEW_ECHO_CANCEL_MODULE_CONTENT) -> None:
        """Add the echo-cancel module and the WebRTC plugin."""
        self.add_echo_cancel_module(module_content)
        self._add_library_file(WEBRTC_PLUGIN, b"")

    def add_echo_cancel_module(self, module_content: bytes = NEW_ECHO_CANCEL_MODULE_CONTENT) -> None:
        """Add the echo-cancel module only."""
        self._add_library_file(ECHO_CANCEL_MODULE, module_content)

    def add_filter_chain_module(self) -> None:
        """Add PipeWire's filter-chain module."""
        self._add_library_file(FILTER_CHAIN_MODULE, b"")

    def add_swh_plugins(self) -> None:
        """Add the two LADSPA plugins from swh-plugins."""
        for plugin_file in ("gate_1410.so", "bode_shifter_1431.so"):
            plugin_path = self._plugin_directory / plugin_file
            plugin_path.write_bytes(b"")

    def check(self) -> FilterSupport:
        """Run the filter check on this pretend computer."""
        library_directories = [str(self._library_directory)]
        plugin_directories = [str(self._plugin_directory)]
        checker = LinuxFilterSupportChecker(library_directories, plugin_directories)
        return checker.check()

    def _add_library_file(self, relative_path: str, content: bytes) -> None:
        """Create ``relative_path`` inside the library directory."""
        path = self._library_directory / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)


@pytest.fixture
def computer(tmp_path, monkeypatch) -> PretendComputer:
    """A pretend computer with the pipewire program but no modules or plugins yet."""
    monkeypatch.setattr(shutil, "which", pretend_every_program_is_installed)
    return PretendComputer(tmp_path)


def test_every_filter_is_available_when_all_files_are_there(computer):
    computer.add_echo_canceller()
    computer.add_filter_chain_module()
    computer.add_swh_plugins()

    support = computer.check()

    assert support == FilterSupport()


def test_without_swh_plugins_the_gate_and_the_shifter_are_not_available(computer):
    computer.add_echo_canceller()
    computer.add_filter_chain_module()

    support = computer.check()

    assert support.echo_canceller.is_available
    assert not support.noise_gate.is_available
    assert "gate_1410.so from the swh-plugins package" in support.noise_gate.reason
    assert not support.frequency_shifter.is_available
    assert "bode_shifter_1431.so from the swh-plugins package" in support.frequency_shifter.reason


def test_without_the_filter_chain_module_the_gate_and_the_shifter_are_not_available(computer):
    computer.add_echo_canceller()
    computer.add_swh_plugins()

    support = computer.check()

    assert not support.noise_gate.is_available
    assert "filter-chain module" in support.noise_gate.reason
    assert not support.frequency_shifter.is_available


def test_without_the_webrtc_plugin_the_echo_canceller_is_not_available(computer):
    computer.add_echo_cancel_module()

    support = computer.check()

    assert not support.echo_canceller.is_available
    assert "libspa-0.2-modules" in support.echo_canceller.reason


def test_old_pipewire_without_monitor_mode_cannot_run_the_echo_canceller(computer):
    computer.add_echo_canceller(module_content=OLD_ECHO_CANCEL_MODULE_CONTENT)

    support = computer.check()

    assert not support.echo_canceller.is_available
    assert "monitor mode" in support.echo_canceller.reason


def test_without_the_pipewire_program_no_filter_is_available(tmp_path, monkeypatch):
    monkeypatch.setattr(shutil, "which", pretend_no_program_is_installed)
    computer = PretendComputer(tmp_path)
    computer.add_echo_canceller()
    computer.add_filter_chain_module()
    computer.add_swh_plugins()

    support = computer.check()

    assert not support.echo_canceller.is_available
    assert not support.frequency_shifter.is_available
    assert not support.noise_gate.is_available
    assert "pipewire-bin" in support.noise_gate.reason


def support_without_the_noise_gate(loopback: LinuxAudioLoopback) -> FilterSupport:
    """Stand in for LinuxAudioLoopback.filter_support on a computer without swh-plugins."""
    missing_gate = FilterAvailability(is_available=False, reason="Needs gate_1410.so from the swh-plugins package.")
    return FilterSupport(noise_gate=missing_gate)


def test_loopback_refuses_a_filter_this_computer_cannot_run(monkeypatch):
    monkeypatch.setattr(LinuxAudioLoopback, "filter_support", support_without_the_noise_gate)
    loopback = LinuxAudioLoopback()
    microphone = AudioDevice("alsa_input.usb", "USB Microphone")
    speaker = AudioDevice("alsa_output.usb", "USB Speaker")
    filters = AudioFilters(noise_gate=True)

    with pytest.raises(AudioLoopbackError, match="The noise gate is not available"):
        loopback.start(microphone, speaker, filters, on_stopped=print)
