"""Run the shell commands of the bundled Python through the MSYS2 POSIX shell.

Part of the afni-win scripting runtime (docs/DECISIONS.md D38). ``afnipy``
starts commands with ``subprocess`` ``shell=True``, ``os.system`` and
``os.popen``; written for ``/bin/sh``, they contain single quotes, ``$var``,
backslash escapes and tcsh scripts that ``cmd.exe`` does not understand.
``afni_win_posix_shell.pth`` imports this module at interpreter start-up; on
Windows it sends those commands to ``sh -c``. The shell is ``AFNI_POSIX_SHELL``
or, by default, ``msys/usr/bin/sh.exe`` of the afni-win installation (the
Python prefix is ``<root>/python``). Elsewhere, or without a shell, nothing
changes.
"""

import os
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

_ORIGINAL_POPEN = subprocess.Popen


def default_shell(prefix: str) -> Path:
    """Locate the MSYS2 ``sh`` of the installation that ships this Python.

    Args:
        prefix: ``sys.prefix`` of the bundled Python (``<root>/python``).

    Returns:
        Path of ``<root>/msys/usr/bin/sh.exe``.
    """
    return Path(prefix).parent / "msys" / "usr" / "bin" / "sh.exe"


def posix_shell_args(args: str | Sequence[object], shell: str) -> list[str]:
    """Build the argument list that runs a shell command line with ``sh -c``.

    Args:
        args: Command line (string) or argument sequence given with ``shell=True``.
        shell: Path of the POSIX shell.

    Returns:
        Arguments for a direct process start.
    """
    command = args if isinstance(args, str) else " ".join(str(a) for a in args)
    return [shell, "-c", command]


def install(shell: str) -> None:
    """Replace ``subprocess.Popen`` and ``os.system`` with POSIX-shell versions.

    ``os.popen`` uses ``subprocess.Popen`` and is covered by the first.

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
                args = posix_shell_args(args, shell)
            super().__init__(args, *rest, **kwargs)  # ty: ignore[no-matching-overload]

    def _system(command: str) -> int:
        """Run a command line with the POSIX shell, like ``os.system``.

        Args:
            command: Command line.

        Returns:
            Exit code of the shell.
        """
        return subprocess.call(posix_shell_args(command, shell))

    setattr(subprocess, "Popen", _PosixShellPopen)  # noqa: B010
    setattr(os, "system", _system)  # noqa: B010


def activate() -> bool:
    """Install the POSIX shell commands on Windows when a shell is available.

    Returns:
        True if the replacement was installed.
    """
    if sys.platform != "win32":
        return False
    shell = os.environ.get("AFNI_POSIX_SHELL") or str(default_shell(sys.prefix))
    if not Path(shell).is_file():
        return False
    install(shell)
    return True


activate()
