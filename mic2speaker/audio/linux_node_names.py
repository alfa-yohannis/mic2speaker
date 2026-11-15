"""Names of the PipeWire nodes that Mic2Speaker creates on Linux.

The virtual devices all start with OWN_DEVICE_PREFIX, which lets the device
list leave them out.
"""

OWN_DEVICE_PREFIX = "mic2speaker"

# pw-loopback --name LOOPBACK_NAME creates the two streams below.
LOOPBACK_NAME = "mic2speaker"
CAPTURE_STREAM_NAME = "input.mic2speaker"
PLAYBACK_STREAM_NAME = "output.mic2speaker"

# Nodes of the echo canceller.
ECHO_CANCEL_CAPTURE_NAME = "mic2speaker_echo_cancel_capture"
ECHO_CANCEL_REFERENCE_NAME = "mic2speaker_echo_cancel_reference"
ECHO_CANCEL_SOURCE_NAME = "mic2speaker_echo_cancel_source"

# Nodes of the LADSPA filter chain (noise gate and frequency shifter).
FILTERS_CAPTURE_NAME = "mic2speaker_filters_capture"
FILTERED_MICROPHONE_NAME = "mic2speaker_filtered_microphone"
