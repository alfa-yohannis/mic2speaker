"""Entry point for ``python -m mic2speaker``."""

import sys

from mic2speaker.app import main

exit_code = main()
sys.exit(exit_code)
