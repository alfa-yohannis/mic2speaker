#!/usr/bin/env bash
# Launcher for Mic2Speaker.
#
# Runs the app with the Python of the project's own virtual environment
# (.venv). On the first run it creates .venv and installs requirements.txt.
# Extra command line arguments are passed on to the app.

set -euo pipefail

SCRIPT_PATH="$(realpath "${BASH_SOURCE[0]}")"
PROJECT_DIR="$(dirname "$SCRIPT_PATH")"
VENV_DIR="$PROJECT_DIR/.venv"
VENV_PYTHON="$VENV_DIR/bin/python"
REQUIREMENTS_FILE="$PROJECT_DIR/requirements.txt"

if [[ ! -x "$VENV_PYTHON" ]]; then
    echo "Creating the virtual environment in $VENV_DIR ..."
    python3 -m venv "$VENV_DIR"
    "$VENV_PYTHON" -m pip install --requirement "$REQUIREMENTS_FILE"
fi

cd "$PROJECT_DIR"
exec "$VENV_PYTHON" -m mic2speaker "$@"
