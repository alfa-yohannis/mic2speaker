"""Runs the optional filters in a helper ``pipewire`` process on Linux."""

import json
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from mic2speaker.audio.audio_device import AudioDevice
from mic2speaker.audio.audio_filters import AudioFilters
from mic2speaker.audio.audio_loopback import AudioLoopbackError
from mic2speaker.audio.linux_child_process import command_that_ends_with_app
from mic2speaker.audio.linux_filter_config import LinuxFilterConfig, ladspa_directories
from mic2speaker.audio.linux_pactl import PactlError, read_pactl_list


class LinuxFilterProcess:
    """Starts and stops the ``pipewire -c <config>`` process that runs the filters.

    The config file lives in a temporary directory together with the
    process's log, and both are deleted again by stop().

    Every stream in the chain carries ``node.dont-reconnect=true``. If the
    microphone or the speaker is unplugged, PipeWire removes the chain piece
    by piece, the virtual microphone disappears, and pw-loopback exits. The
    helper process itself keeps running, so LinuxAudioLoopback calls stop().
    """

    PIPEWIRE_COMMAND = "pipewire"
    CONFIG_FILE_NAME = "filters.conf"
    LOG_FILE_NAME = "pipewire.log"
    START_TIMEOUT_SECONDS = 3.0
    POLL_INTERVAL_SECONDS = 0.05
    STOP_TIMEOUT_SECONDS = 2.0

    def __init__(self) -> None:
        self._process: subprocess.Popen | None = None
        self._work_directory: Path | None = None

    def start(self, microphone: AudioDevice, speaker: AudioDevice, filters: AudioFilters) -> str:
        """Start the filters and return the name of the virtual microphone they feed.

        Raises AudioLoopbackError if a filter is not installed or PipeWire
        does not bring the chain up in time.
        """
        self.stop()
        plugin_directories = ladspa_directories()
        filter_config = LinuxFilterConfig(microphone, speaker, filters, plugin_directories)
        config = filter_config.build()
        output_source_name = filter_config.output_source_name()

        self._work_directory = Path(tempfile.mkdtemp(prefix="mic2speaker-"))
        config_path = self._work_directory / self.CONFIG_FILE_NAME
        config_text = json.dumps(config, indent=2)
        config_path.write_text(config_text)
        self._start_process(config_path)

        source_is_ready = self._wait_for_source(output_source_name)
        if not source_is_ready:
            log_text = self._read_log()
            self.stop()
            raise AudioLoopbackError(f"the filters did not start. {log_text}")
        return output_source_name

    def stop(self) -> None:
        """End the helper process and delete its files. Safe to call at any time."""
        self._end_process()
        self._delete_work_directory()

    def _start_process(self, config_path: Path) -> None:
        """Run ``pipewire -c config_path``, writing its messages to the log file."""
        pipewire_command = [self.PIPEWIRE_COMMAND, "-c", str(config_path)]
        command = command_that_ends_with_app(pipewire_command)
        log_path = self._work_directory / self.LOG_FILE_NAME
        with open(log_path, "w") as log_file:
            self._process = subprocess.Popen(command, stdout=log_file, stderr=subprocess.STDOUT)

    def _wait_for_source(self, source_name: str) -> bool:
        """Wait until PipeWire lists ``source_name``; return False on timeout or if the process died."""
        deadline = time.monotonic() + self.START_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            process_has_exited = self._process.poll() is not None
            if process_has_exited:
                return False
            if self._source_exists(source_name):
                return True
            time.sleep(self.POLL_INTERVAL_SECONDS)
        return False

    @staticmethod
    def _source_exists(source_name: str) -> bool:
        """Return True if PipeWire currently lists a source called ``source_name``."""
        try:
            sources = read_pactl_list("sources")
        except PactlError:
            return False
        for source in sources:
            if source["name"] == source_name:
                return True
        return False

    def _read_log(self) -> str:
        """Return the last lines the helper process wrote, or an empty string."""
        if self._work_directory is None:
            return ""
        log_path = self._work_directory / self.LOG_FILE_NAME
        if not log_path.is_file():
            return ""
        log_text = log_path.read_text(errors="replace")
        log_lines = log_text.strip().splitlines()
        last_lines = log_lines[-3:]
        return " ".join(last_lines)

    def _end_process(self) -> None:
        """Ask the helper process to end, and kill it if it does not."""
        if self._process is None:
            return
        process = self._process
        self._process = None
        process.terminate()
        try:
            process.wait(timeout=self.STOP_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()

    def _delete_work_directory(self) -> None:
        """Delete the temporary config and log files."""
        if self._work_directory is None:
            return
        shutil.rmtree(self._work_directory, ignore_errors=True)
        self._work_directory = None
