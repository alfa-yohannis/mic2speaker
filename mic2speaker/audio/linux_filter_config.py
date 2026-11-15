"""Builds the PipeWire config file that runs the chosen filters on Linux.

The filters run in a helper process started with ``pipewire -c <config
file>``. Depending on the switched-on filters, the chain looks like this:

    microphone -> echo canceller -> noise gate -> frequency shifter -> virtual microphone

pw-loopback then plays the virtual microphone through the speaker.

PipeWire config files use SPA-JSON, which also accepts plain JSON, so the
config is built from Python dictionaries and saved with json.dump().
"""

import os
from dataclasses import dataclass, field
from pathlib import Path

from mic2speaker.audio.audio_device import AudioDevice
from mic2speaker.audio.audio_filters import AudioFilters
from mic2speaker.audio.audio_loopback import AudioLoopbackError
from mic2speaker.audio.linux_node_names import (
    ECHO_CANCEL_CAPTURE_NAME,
    ECHO_CANCEL_REFERENCE_NAME,
    ECHO_CANCEL_SOURCE_NAME,
    FILTERED_MICROPHONE_NAME,
    FILTERS_CAPTURE_NAME,
)

DEFAULT_LADSPA_DIRECTORIES = [
    "/usr/lib/ladspa",
    "/usr/lib/x86_64-linux-gnu/ladspa",
    "/usr/lib64/ladspa",
    "/usr/local/lib/ladspa",
]
SWH_PLUGINS_HINT = "Install the swh-plugins package (sudo apt install swh-plugins)."

# The modules every PipeWire client process needs, copied from PipeWire's
# own filter-chain.conf.
BASE_CONFIG = {
    "context.properties": {"log.level": 0},
    "context.spa-libs": {
        "audio.convert.*": "audioconvert/libspa-audioconvert",
        "support.*": "support/libspa-support",
    },
}
BASE_MODULES = [
    {"name": "libpipewire-module-rt", "args": {}, "flags": ["ifexists", "nofail"]},
    {"name": "libpipewire-module-protocol-native"},
    {"name": "libpipewire-module-client-node"},
    {"name": "libpipewire-module-adapter"},
]
MONO_AUDIO = {"audio.channels": 1, "audio.position": ["MONO"]}


@dataclass(frozen=True)
class FilterStage:
    """One plugin in the filter chain, with the settings Mic2Speaker uses.

    Attributes:
        name: Name of the node inside the filter graph.
        label: The plugin's label.
        input_port: Name of the plugin's audio input.
        output_port: Name of the plugin's audio output.
        controls: Values for the plugin's control ports.
        plugin_file: File name of a LADSPA plugin, searched in the LADSPA
            directories, or None for a plugin built into PipeWire.
    """

    name: str
    label: str
    input_port: str
    output_port: str
    controls: dict = field(default_factory=dict)
    plugin_file: str | None = None


# The gate opens when the voice is louder than the threshold, stays open
# between words for the hold time, and makes everything else quieter by the
# range when it is closed.
NOISE_GATE = FilterStage(
    name="noise_gate",
    plugin_file="gate_1410.so",
    label="gate",
    input_port="Input",
    output_port="Output",
    controls={
        "Threshold (dB)": -50,
        "Attack (ms)": 2,
        "Hold (ms)": 200,
        "Decay (ms)": 200,
        "Range (dB)": -70,
        "LF key filter (Hz)": 80,
        "HF key filter (Hz)": 8000,
        "Output select (-1 = key listen, 0 = gate, 1 = bypass)": 0,
    },
)

# Shifting every frequency up by a few hertz keeps a howl from building up
# on one room resonance, which buys a few dB of volume before feedback.
FREQUENCY_SHIFTER = FilterStage(
    name="frequency_shifter",
    plugin_file="bode_shifter_1431.so",
    label="bodeShifter",
    input_port="Input",
    output_port="Up out",
    controls={"Frequency shift": 5},
)

# The Bode shifter's output is half as loud as its input (-6 dB). PipeWire's
# built-in "linear" plugin doubles it again, so that ticking the shifter
# does not lower the volume.
SHIFTER_MAKEUP_GAIN = FilterStage(
    name="frequency_shifter_gain",
    label="linear",
    input_port="In",
    output_port="Out",
    controls={"Mult": 2.0, "Add": 0.0},
)


def find_ladspa_plugin(plugin_file: str, directories: list[str]) -> str | None:
    """Return the full path of ``plugin_file`` in the first directory that has it, or None."""
    for directory in directories:
        candidate = Path(directory) / plugin_file
        if candidate.is_file():
            return str(candidate)
    return None


def ladspa_directories() -> list[str]:
    """Return the directories to search for LADSPA plugins: LADSPA_PATH first, then the usual ones."""
    directories = []
    ladspa_path = os.environ.get("LADSPA_PATH", "")
    for directory in ladspa_path.split(":"):
        if directory:
            directories.append(directory)
    return directories + DEFAULT_LADSPA_DIRECTORIES


class LinuxFilterConfig:
    """The PipeWire config for one set of filters between one microphone and one speaker."""

    def __init__(
        self,
        microphone: AudioDevice,
        speaker: AudioDevice,
        filters: AudioFilters,
        plugin_directories: list[str],
    ) -> None:
        """Prepare the config.

        Args:
            microphone: The real microphone at the start of the chain.
            speaker: The real speaker; the echo canceller listens to its monitor.
            filters: Which filters to put in the chain.
            plugin_directories: Where to look for the LADSPA plugins.
        """
        self._microphone = microphone
        self._speaker = speaker
        self._filters = filters
        self._plugin_directories = plugin_directories

    def output_source_name(self) -> str:
        """Return the node that carries the filtered microphone, for pw-loopback to read."""
        if self._filter_stages():
            return FILTERED_MICROPHONE_NAME
        return ECHO_CANCEL_SOURCE_NAME

    def build(self) -> dict:
        """Return the whole config as a dictionary, ready for json.dump().

        Raises AudioLoopbackError if a LADSPA plugin is not installed.
        """
        modules = list(BASE_MODULES)
        chain_input_name = self._microphone.system_name
        if self._filters.echo_canceller:
            echo_canceller_module = self._echo_canceller_module()
            modules.append(echo_canceller_module)
            chain_input_name = ECHO_CANCEL_SOURCE_NAME

        filter_stages = self._filter_stages()
        if filter_stages:
            filter_chain_module = self._filter_chain_module(filter_stages, chain_input_name)
            modules.append(filter_chain_module)

        config = dict(BASE_CONFIG)
        config["context.modules"] = modules
        return config

    def _filter_stages(self) -> list[FilterStage]:
        """Return the stages of the switched-on gate and shifter, in the order the sound passes them."""
        chain = []
        if self._filters.noise_gate:
            chain.append(NOISE_GATE)
        if self._filters.frequency_shifter:
            chain.append(FREQUENCY_SHIFTER)
            chain.append(SHIFTER_MAKEUP_GAIN)
        return chain

    def _echo_canceller_module(self) -> dict:
        """Return PipeWire's WebRTC echo canceller, set up for a loopback.

        In monitor mode the canceller records what the speaker plays from the
        speaker's monitor and removes it from the microphone signal. Its
        output is a virtual microphone named ECHO_CANCEL_SOURCE_NAME.
        """
        arguments = {
            "library.name": "aec/libspa-aec-webrtc",
            "monitor.mode": True,
            "aec.args": {
                "webrtc.noise_suppression": True,
                "webrtc.high_pass_filter": True,
                # Automatic gain would raise the volume, and the feedback with it.
                "webrtc.gain_control": False,
            },
            "capture.props": {
                "node.name": ECHO_CANCEL_CAPTURE_NAME,
                "target.object": self._microphone.system_name,
                "node.dont-reconnect": True,
            },
            "sink.props": {
                "node.name": ECHO_CANCEL_REFERENCE_NAME,
                "target.object": self._speaker.system_name,
                "node.dont-reconnect": True,
            },
            "source.props": {
                "node.name": ECHO_CANCEL_SOURCE_NAME,
                "node.description": "Mic2Speaker echo-cancelled microphone",
            },
        }
        arguments.update(MONO_AUDIO)
        return {"name": "libpipewire-module-echo-cancel", "args": arguments}

    def _filter_chain_module(self, filter_stages: list[FilterStage], input_node_name: str) -> dict:
        """Return a filter chain that runs ``filter_stages`` one after another.

        It reads from ``input_node_name`` and offers the result as a virtual
        microphone named FILTERED_MICROPHONE_NAME.
        """
        graph = self._filter_graph(filter_stages)
        arguments = {
            "node.description": "Mic2Speaker filters",
            "media.name": "Mic2Speaker filters",
            "filter.graph": graph,
            "capture.props": {
                "node.name": FILTERS_CAPTURE_NAME,
                "target.object": input_node_name,
                "node.dont-reconnect": True,
            },
            "playback.props": {
                "node.name": FILTERED_MICROPHONE_NAME,
                "node.description": "Mic2Speaker filtered microphone",
                "media.class": "Audio/Source",
            },
        }
        arguments.update(MONO_AUDIO)
        return {"name": "libpipewire-module-filter-chain", "args": arguments}

    def _filter_graph(self, filter_stages: list[FilterStage]) -> dict:
        """Return the filter graph: the plugin nodes, the links between them, and the ends."""
        nodes = []
        for filter_stage in filter_stages:
            graph_node = self._graph_node(filter_stage)
            nodes.append(graph_node)

        links = []
        for index in range(1, len(filter_stages)):
            previous_stage = filter_stages[index - 1]
            next_stage = filter_stages[index]
            link = {
                "output": f"{previous_stage.name}:{previous_stage.output_port}",
                "input": f"{next_stage.name}:{next_stage.input_port}",
            }
            links.append(link)

        first_stage = filter_stages[0]
        last_stage = filter_stages[-1]
        return {
            "nodes": nodes,
            "links": links,
            "inputs": [f"{first_stage.name}:{first_stage.input_port}"],
            "outputs": [f"{last_stage.name}:{last_stage.output_port}"],
        }

    def _graph_node(self, filter_stage: FilterStage) -> dict:
        """Return the graph node for one stage, LADSPA or built into PipeWire.

        Raises AudioLoopbackError if a LADSPA plugin is not installed.
        """
        graph_node = {
            "type": "builtin",
            "name": filter_stage.name,
            "label": filter_stage.label,
            "control": filter_stage.controls,
        }
        if filter_stage.plugin_file is None:
            return graph_node

        plugin_path = find_ladspa_plugin(filter_stage.plugin_file, self._plugin_directories)
        if plugin_path is None:
            raise AudioLoopbackError(f"{filter_stage.plugin_file} was not found. {SWH_PLUGINS_HINT}")
        graph_node["type"] = "ladspa"
        graph_node["plugin"] = plugin_path
        return graph_node
