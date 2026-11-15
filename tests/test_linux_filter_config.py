"""Tests for the PipeWire config that runs the filters on Linux."""

import json

import pytest

from mic2speaker.audio.audio_device import AudioDevice
from mic2speaker.audio.audio_filters import AudioFilters
from mic2speaker.audio.audio_loopback import AudioLoopbackError
from mic2speaker.audio.linux_filter_config import LinuxFilterConfig
from mic2speaker.audio.linux_node_names import ECHO_CANCEL_SOURCE_NAME, FILTERED_MICROPHONE_NAME

MICROPHONE = AudioDevice("alsa_input.usb", "USB Microphone")
SPEAKER = AudioDevice("alsa_output.usb", "USB Speaker")
ECHO_CANCEL_MODULE = "libpipewire-module-echo-cancel"
FILTER_CHAIN_MODULE = "libpipewire-module-filter-chain"


@pytest.fixture
def plugin_directory(tmp_path) -> str:
    """A directory with empty stand-ins for the two LADSPA plugin files."""
    gate_plugin = tmp_path / "gate_1410.so"
    shifter_plugin = tmp_path / "bode_shifter_1431.so"
    gate_plugin.touch()
    shifter_plugin.touch()
    return str(tmp_path)


def build_config(filters: AudioFilters, plugin_directory: str) -> tuple[dict, LinuxFilterConfig]:
    """Build the config for ``filters`` and return it together with its builder."""
    filter_config = LinuxFilterConfig(MICROPHONE, SPEAKER, filters, [plugin_directory])
    config = filter_config.build()
    return config, filter_config


def module_arguments(config: dict, module_name: str) -> dict | None:
    """Return the arguments of the module called ``module_name``, or None if it is not loaded."""
    for module in config["context.modules"]:
        if module["name"] == module_name:
            return module["args"]
    return None


def test_echo_canceller_alone_reads_the_microphone_and_listens_to_the_speaker(plugin_directory):
    config, filter_config = build_config(AudioFilters(echo_canceller=True), plugin_directory)

    echo_cancel = module_arguments(config, ECHO_CANCEL_MODULE)
    assert echo_cancel["capture.props"]["target.object"] == MICROPHONE.system_name
    assert echo_cancel["sink.props"]["target.object"] == SPEAKER.system_name
    assert echo_cancel["monitor.mode"] is True
    assert module_arguments(config, FILTER_CHAIN_MODULE) is None
    assert filter_config.output_source_name() == ECHO_CANCEL_SOURCE_NAME


def test_noise_gate_runs_before_the_frequency_shifter_and_its_makeup_gain(plugin_directory):
    filters = AudioFilters(noise_gate=True, frequency_shifter=True)

    config, filter_config = build_config(filters, plugin_directory)

    filter_chain = module_arguments(config, FILTER_CHAIN_MODULE)
    graph = filter_chain["filter.graph"]
    node_names = [node["name"] for node in graph["nodes"]]
    assert node_names == ["noise_gate", "frequency_shifter", "frequency_shifter_gain"]
    assert graph["links"] == [
        {"output": "noise_gate:Output", "input": "frequency_shifter:Input"},
        {"output": "frequency_shifter:Up out", "input": "frequency_shifter_gain:In"},
    ]
    assert graph["inputs"] == ["noise_gate:Input"]
    assert graph["outputs"] == ["frequency_shifter_gain:Out"]
    assert filter_chain["capture.props"]["target.object"] == MICROPHONE.system_name
    assert module_arguments(config, ECHO_CANCEL_MODULE) is None
    assert filter_config.output_source_name() == FILTERED_MICROPHONE_NAME


def test_with_the_echo_canceller_the_filter_chain_reads_the_cleaned_microphone(plugin_directory):
    filters = AudioFilters(echo_canceller=True, frequency_shifter=True, noise_gate=True)

    config, filter_config = build_config(filters, plugin_directory)

    filter_chain = module_arguments(config, FILTER_CHAIN_MODULE)
    assert filter_chain["capture.props"]["target.object"] == ECHO_CANCEL_SOURCE_NAME
    assert filter_config.output_source_name() == FILTERED_MICROPHONE_NAME


def test_every_stream_is_pinned_to_its_device(plugin_directory):
    filters = AudioFilters(echo_canceller=True, noise_gate=True)

    config, _ = build_config(filters, plugin_directory)

    echo_cancel = module_arguments(config, ECHO_CANCEL_MODULE)
    filter_chain = module_arguments(config, FILTER_CHAIN_MODULE)
    assert echo_cancel["capture.props"]["node.dont-reconnect"] is True
    assert echo_cancel["sink.props"]["node.dont-reconnect"] is True
    assert filter_chain["capture.props"]["node.dont-reconnect"] is True


def test_plugin_paths_point_into_the_plugin_directory(plugin_directory):
    config, _ = build_config(AudioFilters(noise_gate=True), plugin_directory)

    filter_chain = module_arguments(config, FILTER_CHAIN_MODULE)
    gate_node = filter_chain["filter.graph"]["nodes"][0]
    assert gate_node["type"] == "ladspa"
    assert gate_node["plugin"] == f"{plugin_directory}/gate_1410.so"
    assert gate_node["label"] == "gate"


def test_makeup_gain_uses_pipewires_builtin_linear_plugin(plugin_directory):
    config, _ = build_config(AudioFilters(frequency_shifter=True), plugin_directory)

    filter_chain = module_arguments(config, FILTER_CHAIN_MODULE)
    gain_node = filter_chain["filter.graph"]["nodes"][1]
    assert gain_node["type"] == "builtin"
    assert gain_node["label"] == "linear"
    assert gain_node["control"]["Mult"] == 2.0
    assert "plugin" not in gain_node


def test_missing_plugin_names_the_package_to_install(tmp_path):
    empty_directory = str(tmp_path)

    with pytest.raises(AudioLoopbackError, match="swh-plugins"):
        build_config(AudioFilters(noise_gate=True), empty_directory)


def test_config_can_be_saved_as_json(plugin_directory):
    filters = AudioFilters(echo_canceller=True, frequency_shifter=True, noise_gate=True)
    config, _ = build_config(filters, plugin_directory)

    config_text = json.dumps(config)

    assert json.loads(config_text) == config
