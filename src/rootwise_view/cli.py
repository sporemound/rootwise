"""Compatibility module for :mod:`rootwise.viewer.cli`."""

from rootwise.viewer.cli import main, parser

__all__ = ["main", "parser"]


if __name__ == "__main__":
    raise SystemExit(main())
