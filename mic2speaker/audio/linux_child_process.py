"""Helper for Linux helper programs that must not outlive the app."""

import shutil

SETPRIV_COMMAND = "setpriv"
SETPRIV_ARGUMENTS = ["--pdeathsig", "TERM", "--"]


def command_that_ends_with_app(command: list[str]) -> list[str]:
    """Return ``command`` wrapped so that the program ends when this app dies.

    setpriv asks the kernel to send the program SIGTERM when its parent (the
    app) dies, even after a crash. Without setpriv the command is returned
    unchanged and loses that protection.
    """
    setpriv_path = shutil.which(SETPRIV_COMMAND)
    if setpriv_path is None:
        return command
    return [SETPRIV_COMMAND] + SETPRIV_ARGUMENTS + command
