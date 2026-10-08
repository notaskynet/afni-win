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


def test_runtime_tree_gets_the_dlls_its_files_import(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A DLL that no package dependency named is copied from the MSYS2 tree."""
    tree = tmp_path / "msys"
    bin_dir = tree / "usr" / "bin"
    source = tmp_path / "source"
    bin_dir.mkdir(parents=True)
    source.mkdir()
    (bin_dir / "sh.exe").write_bytes(b"")
    (bin_dir / "msys-ncursesw6.dll").write_bytes(b"")
    (source / "msys-2.0.dll").write_bytes(b"runtime")
    imports = {
        "sh.exe": ["msys-2.0.dll", "msys-ncursesw6.dll", "KERNEL32.dll"],
        "msys-ncursesw6.dll": ["msys-2.0.dll"],
        "msys-2.0.dll": [],
    }
    monkeypatch.setattr(package, "imported_dlls", lambda objdump, path: imports[path.name])
    added = package.complete_runtime_tree("objdump", tree, bin_dir, source)
    assert [p.name for p in added] == ["msys-2.0.dll"]
    assert (bin_dir / "msys-2.0.dll").read_bytes() == b"runtime"
