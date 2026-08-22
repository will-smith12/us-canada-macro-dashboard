"""Helpers for driving the legacy ~/Downloads scripts from the orchestrator."""
from __future__ import annotations

import io
import sys
from contextlib import redirect_stdout


class _LineForwarder(io.TextIOBase):
    """A writable stream that forwards completed lines to a callback."""

    def __init__(self, emit):
        self._emit = emit
        self._buf = ""

    def write(self, s):  # noqa: D401
        self._buf += s
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            self._emit(line)
        return len(s)

    def flush(self):
        if self._buf:
            self._emit(self._buf)
            self._buf = ""


def run_legacy_main(main_func, argv, log):
    """
    Call a legacy module's `main()` with a controlled argv and stdout routed
    line-by-line to `log`. Restores argv afterwards.
    """
    saved_argv = sys.argv
    sys.argv = list(argv)
    forwarder = _LineForwarder(log)
    try:
        with redirect_stdout(forwarder):
            main_func()
        forwarder.flush()
    finally:
        sys.argv = saved_argv
