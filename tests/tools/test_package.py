"""Tests for tools.package."""

from pathlib import Path

import pytest

from tools import package


def test_runtime_dlls_are_found_recursively(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Imports of build DLLs and of runtime DLLs are followed; system DLLs are skipped."""
    build = tmp_path / "build"
    runtime = tmp_path / "runtime"
    build.mkdir()
    runtime.mkdir()
    for path in (build / "prog.exe", build / "libmri.dll", runtime / "libgomp-1.dll"):
        path.write_bytes(b"")
    (runtime / "libwinpthread-1.dll").write_bytes(b"")
    (runtime / "unused.dll").write_bytes(b"")
    imports = {
        "prog.exe": ["libmri.dll", "KERNEL32.dll"],
        "libmri.dll": ["libgomp-1.dll", "api-ms-win-crt-heap-l1-1-0.dll"],
        "libgomp-1.dll": ["libwinpthread-1.dll"],
        "libwinpthread-1.dll": [],
    }
    monkeypatch.setattr(package, "imported_dlls", lambda objdump, path: imports[path.name])
    found = package.resolve_runtime("objdump", [build / "prog.exe"], build, runtime)
    assert [p.name for p in found] == ["libgomp-1.dll", "libwinpthread-1.dll"]
