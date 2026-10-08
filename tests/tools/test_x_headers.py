"""Tests for tools.x_headers."""

from pathlib import Path

import pytest

from tools.x_headers import ar_members, read_manifest, wanted


def _ar(members: dict[str, bytes]) -> bytes:
    """Build a Unix ar archive.

    Args:
        members: Member contents by name.

    Returns:
        Archive bytes.
    """
    data = b"!<arch>\n"
    for name, content in members.items():
        header = f"{name + '/':<16}{0:<12}{0:<6}{0:<6}{644:<8}{len(content):<10}`\n"
        data += header.encode() + content + (b"\n" if len(content) % 2 else b"")
    return data


def test_ar_members_splits_odd_and_even_sizes() -> None:
    """Members come back unchanged, including after odd-sized padding."""
    archive = _ar({"debian-binary": b"2.0\n", "a": b"odd", "data.tar.zst": b"payload"})
    assert ar_members(archive) == {
        "debian-binary": b"2.0\n",
        "a": b"odd",
        "data.tar.zst": b"payload",
    }


def test_ar_members_rejects_other_data() -> None:
    """Anything without the ar magic is refused."""
    with pytest.raises(ValueError):
        ar_members(b"PK\x03\x04")


@pytest.mark.parametrize(
    ("member", "expected"),
    [
        ("./usr/include/X11/Xlib.h", "X11/Xlib.h"),
        ("./usr/include/Xm/Xm.h", "Xm/Xm.h"),
        ("./usr/include/GL/glx.h", "GL/glx.h"),
        ("./usr/include/GL/GLwDrawA.h", None),
        ("./usr/include/KHR/khrplatform.h", None),
        ("./usr/share/doc/libx11-dev/copyright", None),
    ],
)
def test_wanted_keeps_x_motif_and_gl_headers(member: str, expected: str | None) -> None:
    """Only X11/, Xm/ and GL/ headers are extracted, GLw is left to SUMA."""
    assert wanted(member) == expected


def test_read_manifest(tmp_path: Path) -> None:
    """Comments and blank lines are skipped, hashes are lower-cased."""
    manifest = tmp_path / "m.txt"
    manifest.write_text("# comment\n\nhttp://x/a.deb ABCDEF\n")
    packages = read_manifest(manifest)
    assert [(p.url, p.sha512) for p in packages] == [("http://x/a.deb", "abcdef")]
    manifest.write_text("http://x/a.deb\n")
    with pytest.raises(ValueError):
        read_manifest(manifest)
