"""Run shell commands of native Windows Python through a POSIX shell.

Prototype for the scripting research (docs/inventory/scripts-REPORT.md).
afnipy starts commands with ``shell=True``, ``os.system`` and ``os.popen``,
which on Windows go to ``cmd.exe``. When ``AFNI_POSIX_SHELL`` names a POSIX
``sh`` (MSYS2), this module, loaded by Python at startup from ``PYTHONPATH``,
sends those commands to ``sh -c`` instead. Without the variable, or on other
platforms, it changes nothing.
"""

import os
import subprocess
import sys
from collections.abc import Sequence

_ORIGINAL_POPEN = subprocess.Popen


def _posix_shell_args(args: str | Sequence[object], shell: str) -> list[str]:
    """Build the argument list that runs a shell command line with ``sh -c``.

    Args:
        args: Command line (string) or argument sequence given with ``shell=True``.
        shell: Path of the POSIX shell.

    Returns:
        Arguments for a direct process start.
    """
    command = args if isinstance(args, str) else " ".join(str(a) for a in args)
    return [shell, "-c", command]


def _install(shell: str) -> None:
    """Replace ``subprocess.Popen`` and ``os.system`` with POSIX-shell versions.

    Args:
        shell: Path of the POSIX shell.
    """

    class _PosixShellPopen(_ORIGINAL_POPEN):
        """``subprocess.Popen`` that runs ``shell=True`` commands with ``sh -c``."""

        def __init__(self, args: str | Sequence[object], *rest: object, **kwargs: object) -> None:
            """Start the process, rewriting shell command lines.

            Args:
                args: Command line or argument sequence.
                *rest: Other positional ``Popen`` arguments.
                **kwargs: Other keyword ``Popen`` arguments.
            """
            if kwargs.get("shell"):
                kwargs["shell"] = False
                args = _posix_shell_args(args, shell)
            super().__init__(args, *rest, **kwargs)  # ty: ignore[no-matching-overload]

    def _system(command: str) -> int:
        """Run a command line with the POSIX shell, like ``os.system``.

        Args:
            command: Command line.

        Returns:
            Exit code of the shell.
        """
        return subprocess.call(_posix_shell_args(command, shell))

    setattr(subprocess, "Popen", _PosixShellPopen)  # noqa: B010
    setattr(os, "system", _system)  # noqa: B010


if sys.platform == "win32" and os.environ.get("AFNI_POSIX_SHELL"):
    _install(os.environ["AFNI_POSIX_SHELL"])
