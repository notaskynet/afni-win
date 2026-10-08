"""Tests for tools.r_runtime."""

from pathlib import Path

import pytest

from tools.r_runtime import DEFAULT_MANIFEST, install_script, r_vector, read_manifest


def test_shipped_manifest_is_complete() -> None:
    """The repository manifest pins version, installer, hash and snapshot."""
    manifest = read_manifest(DEFAULT_MANIFEST)
    assert manifest.installers[0].endswith(f"R-{manifest.version}-win.exe")
    assert len(manifest.sha256) == 64
    assert "/cran/20" in manifest.repository
    assert {"afex", "phia", "lme4", "lmerTest", "snow"} <= set(manifest.packages)


def test_read_manifest_rejects_unknown_and_missing_keys(tmp_path: Path) -> None:
    """Typos and missing keys are errors, not defaults."""
    manifest = tmp_path / "r.txt"
    manifest.write_text("version 1\ninstaler http://x\n")
    with pytest.raises(ValueError):
        read_manifest(manifest)
    manifest.write_text("version 1\ninstaller http://x\n")
    with pytest.raises(ValueError):
        read_manifest(manifest)


def test_install_script() -> None:
    """Packages are installed as binaries from the snapshot and then checked."""
    script = install_script("https://p/cran/2026-10-01", ["afex", "phia"], "C:/R/library")
    assert script.startswith('pkgs <- c("afex", "phia"); ')
    assert 'repos = "https://p/cran/2026-10-01", type = "binary"' in script
    assert 'stop("not installed: "' in script
    assert r_vector([]) == "c()"
