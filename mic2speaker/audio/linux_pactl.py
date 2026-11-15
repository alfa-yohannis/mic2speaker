"""Small helpers around the ``pactl`` command, shared by the Linux adapters.

``pactl`` is the PulseAudio command-line tool. PipeWire answers it as well.
"""

import json
import subprocess

PACTL_COMMAND = "pactl"
PACTL_TIMEOUT_SECONDS = 5


class PactlError(Exception):
    """Raised when pactl is missing, fails, or prints something unexpected."""


def run_pactl(pactl_arguments: list[str]) -> str:
    """Run pactl with ``pactl_arguments`` and return what it printed, without the trailing newline.

    Raises PactlError if pactl is missing, fails, or does not answer.
    """
    command = [PACTL_COMMAND] + pactl_arguments
    try:
        completed_process = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=PACTL_TIMEOUT_SECONDS,
            check=True,
        )
    except FileNotFoundError as error:
        raise PactlError("The pactl command is not installed.") from error
    except subprocess.TimeoutExpired as error:
        raise PactlError("pactl did not answer in time.") from error
    except subprocess.CalledProcessError as error:
        error_text = error.stderr.strip()
        raise PactlError(f"pactl failed: {error_text}") from error
    output = completed_process.stdout
    return output.strip()


def read_pactl_list(kind: str) -> list[dict]:
    """Return ``pactl list <kind>`` as parsed JSON, for example kind="sinks".

    Raises PactlError if pactl fails or does not print JSON.
    """
    output = run_pactl(["--format=json", "list", kind])
    try:
        return json.loads(output)
    except json.JSONDecodeError as error:
        raise PactlError(f"pactl printed something that is not JSON: {error}") from error
