#!/usr/bin/env python3
"""Executable launcher for the Cody Coordinator package."""

import sys

sys.dont_write_bytecode = True

from coordinator_standard.cli import main


if __name__ == "__main__":
    raise SystemExit(main())
