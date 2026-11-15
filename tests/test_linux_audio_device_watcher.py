"""Tests for reading the lines that ``pactl subscribe`` prints."""

import pytest

from mic2speaker.audio.linux_audio_device_watcher import is_device_change_line


@pytest.mark.parametrize(
    "line",
    [
        "Event 'new' on sink #57",
        "Event 'remove' on sink #57",
        "Event 'new' on source #12",
        "Event 'remove' on source #12",
        "Event 'change' on server #-1",
        "Event 'new' on sink #57\n",
    ],
)
def test_device_and_default_changes_count(line):
    assert is_device_change_line(line)


@pytest.mark.parametrize(
    "line",
    [
        "Event 'change' on sink #57",
        "Event 'change' on source #12",
        "Event 'new' on sink-input #90",
        "Event 'remove' on source-output #91",
        "Event 'new' on client #300",
        "",
        "Connection failure: Connection refused",
    ],
)
def test_other_lines_are_ignored(line):
    assert not is_device_change_line(line)
