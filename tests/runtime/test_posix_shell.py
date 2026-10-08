"""Tests for runtime/python/afni_win_posix_shell.py."""

import importlib.util
import ntpath
import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

MODULE = Path(__file__).resolve().parents[2] / "runtime" / "python" / "afni_win_posix_shell.py"


def _load() -> ModuleType:
    """Load the module without importing it under its own name.

    Returns:
        The loaded module (its import-time ``activate()`` is a no-op off Windows).
    """
    spec = importlib.util.spec_from_file_location("posix_shell_under_test", MODULE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_default_shell_is_next_to_the_python_prefix() -> None:
    """The shell of the installation is <root>/msys/usr/bin/sh.exe."""
    module = _load()
    assert module.default_shell("C:/AFNI/python") == Path("C:/AFNI/msys/usr/bin/sh.exe")


def test_posix_shell_args() -> None:
    """Strings and sequences become one sh -c command line."""
    module = _load()
    assert module.posix_shell_args("ls '-1'", "sh") == ["sh", "-c", "ls '-1'"]
    assert module.posix_shell_args(["ls", "-1"], "sh") == ["sh", "-c", "ls -1"]


def test_activate_does_nothing_off_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    """On other platforms subprocess and os.system stay untouched."""
    module = _load()
    monkeypatch.setattr(sys, "platform", "linux")
    assert module.activate() is False


@pytest.mark.skipif(not Path("/bin/sh").exists(), reason="needs a POSIX sh")
def test_install_routes_shell_commands_through_sh(monkeypatch: pytest.MonkeyPatch) -> None:
    """shell=True, os.system and os.popen all run through the given sh."""
    module = _load()
    monkeypatch.setattr(subprocess, "Popen", subprocess.Popen)
    monkeypatch.setattr(os, "system", os.system)
    module.install("/bin/sh")
    result = subprocess.run("echo 'a b' | tr a-z A-Z", shell=True, capture_output=True, text=True)
    assert result.stdout == "A B\n"
    assert os.system("exit 3") == 3
    assert os.popen("printf %s ok").read() == "ok"  # ty: ignore[deprecated]


def test_activate_needs_an_existing_shell(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Without the shell file nothing is replaced."""
    module = _load()
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("AFNI_POSIX_SHELL", str(tmp_path / "missing-sh.exe"))
    assert module.activate() is False


def test_path_functions_return_forward_slashes(monkeypatch: pytest.MonkeyPatch) -> None:
    """Dataset paths built by afnipy keep '/' on Windows, as on Linux."""
    module = _load()
    for name in module.PATH_FUNCTIONS:
        monkeypatch.setattr(ntpath, name, getattr(ntpath, name))
    fake_os = SimpleNamespace(getcwd=lambda: "D:\\a\\work")
    module.install_forward_slash_paths(ntpath, fake_os)
    assert ntpath.join("D:\\a\\data", "sub-01.nii.gz") == "D:/a/data/sub-01.nii.gz"
    assert ntpath.normpath("D:/a/b/../c") == "D:/a/c"
    assert fake_os.getcwd() == "D:/a/work"
    assert module.forward_slashes(3) == 3
