"""Checks which filters this Linux computer can run.

The check only looks for files: the pipewire program, PipeWire's modules and
plugins, and the LADSPA plugins. Nothing is started, so it is quick and has
no side effects. A filter that passes the check can still fail when it
starts; LinuxAudioLoopback then reports that error.
"""

import glob
import shutil
from pathlib import Path

from mic2speaker.audio.audio_filters import AVAILABLE, FilterAvailability, FilterSupport
from mic2speaker.audio.linux_filter_config import FREQUENCY_SHIFTER, NOISE_GATE, FilterStage, find_ladspa_plugin

PIPEWIRE_COMMAND = "pipewire"
ECHO_CANCEL_MODULE = "pipewire-0.3/libpipewire-module-echo-cancel.so"
FILTER_CHAIN_MODULE = "pipewire-0.3/libpipewire-module-filter-chain.so"
WEBRTC_PLUGIN = "spa-0.2/aec/libspa-aec-webrtc.so"

# Mic2Speaker runs the echo canceller in monitor mode. The option's name
# appears as text inside the module file only in PipeWire versions that
# support it.
MONITOR_MODE_OPTION = b"monitor.mode"

PIPEWIRE_MISSING_REASON = "Needs the pipewire program (Ubuntu package: pipewire-bin)."
ECHO_CANCEL_MODULE_MISSING_REASON = "Needs PipeWire's echo-cancel module (Ubuntu package: libpipewire-0.3-modules)."
MONITOR_MODE_MISSING_REASON = "Needs a newer PipeWire: this echo canceller has no monitor mode."
WEBRTC_PLUGIN_MISSING_REASON = "Needs PipeWire's WebRTC plugin (Ubuntu package: libspa-0.2-modules)."
FILTER_CHAIN_MODULE_MISSING_REASON = "Needs PipeWire's filter-chain module (Ubuntu package: libpipewire-0.3-modules)."


def default_library_directories() -> list[str]:
    """Return the directories that hold pipewire-0.3/ and spa-0.2/ on common Linux distributions."""
    multiarch_directories = sorted(glob.glob("/usr/lib/*-linux-gnu*"))
    return multiarch_directories + ["/usr/lib64", "/usr/lib", "/usr/local/lib64", "/usr/local/lib"]


def find_file(relative_path: str, directories: list[str]) -> Path | None:
    """Return ``relative_path`` inside the first of ``directories`` that has it, or None."""
    for directory in directories:
        candidate = Path(directory) / relative_path
        if candidate.is_file():
            return candidate
    return None


def file_contains(path: Path, text: bytes) -> bool:
    """Return True if the file at ``path`` contains ``text`` anywhere."""
    content = path.read_bytes()
    return text in content


class LinuxFilterSupportChecker:
    """Finds out which filters can run, by looking for the files each filter needs."""

    def __init__(self, library_directories: list[str], plugin_directories: list[str]) -> None:
        """Prepare the check.

        Args:
            library_directories: Where to look for pipewire-0.3/ and spa-0.2/.
            plugin_directories: Where to look for the LADSPA plugins.
        """
        self._library_directories = library_directories
        self._plugin_directories = plugin_directories

    def check(self) -> FilterSupport:
        """Return the availability of each filter."""
        pipewire_path = shutil.which(PIPEWIRE_COMMAND)
        if pipewire_path is None:
            pipewire_missing = FilterAvailability(is_available=False, reason=PIPEWIRE_MISSING_REASON)
            return FilterSupport(
                echo_canceller=pipewire_missing,
                frequency_shifter=pipewire_missing,
                noise_gate=pipewire_missing,
            )

        echo_canceller = self._check_echo_canceller()
        frequency_shifter = self._check_ladspa_filter(FREQUENCY_SHIFTER)
        noise_gate = self._check_ladspa_filter(NOISE_GATE)
        return FilterSupport(
            echo_canceller=echo_canceller,
            frequency_shifter=frequency_shifter,
            noise_gate=noise_gate,
        )

    def _check_echo_canceller(self) -> FilterAvailability:
        """Look for the echo-cancel module with monitor mode, and for the WebRTC plugin."""
        module_path = find_file(ECHO_CANCEL_MODULE, self._library_directories)
        if module_path is None:
            return FilterAvailability(is_available=False, reason=ECHO_CANCEL_MODULE_MISSING_REASON)
        if not file_contains(module_path, MONITOR_MODE_OPTION):
            return FilterAvailability(is_available=False, reason=MONITOR_MODE_MISSING_REASON)
        plugin_path = find_file(WEBRTC_PLUGIN, self._library_directories)
        if plugin_path is None:
            return FilterAvailability(is_available=False, reason=WEBRTC_PLUGIN_MISSING_REASON)
        return AVAILABLE

    def _check_ladspa_filter(self, filter_stage: FilterStage) -> FilterAvailability:
        """Look for the filter-chain module and for the LADSPA plugin of ``filter_stage``."""
        module_path = find_file(FILTER_CHAIN_MODULE, self._library_directories)
        if module_path is None:
            return FilterAvailability(is_available=False, reason=FILTER_CHAIN_MODULE_MISSING_REASON)
        plugin_path = find_ladspa_plugin(filter_stage.plugin_file, self._plugin_directories)
        if plugin_path is None:
            reason = f"Needs {filter_stage.plugin_file} from the swh-plugins package."
            return FilterAvailability(is_available=False, reason=reason)
        return AVAILABLE
