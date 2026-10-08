"""Tests for tools.scripting."""

from pathlib import Path, PurePosixPath

import pytest

from tools.scripting import (
    ScriptingConfig,
    ScriptingResult,
    _install_scripts,
    keep_file,
    launcher,
    read_manifest,
    script_interpreter,
    shebang_flags,
    sources_text,
    target_path,
)


def test_read_manifest(tmp_path: Path) -> None:
    """Known trees are accepted, anything else is refused."""
    manifest = tmp_path / "m.txt"
    manifest.write_text("# c\nmsys tcsh\npython mingw-w64-ucrt-x86_64-python  # comment\n")
    assert read_manifest(manifest) == [("msys", "tcsh"), ("python", "mingw-w64-ucrt-x86_64-python")]
    manifest.write_text("clang64 foo\n")
    with pytest.raises(ValueError):
        read_manifest(manifest)


@pytest.mark.parametrize(
    ("path", "kept"),
    [
        ("/usr/bin/tcsh.exe", True),
        ("/usr/bin/", False),
        ("/usr/share/man/man1/tcsh.1.gz", False),
        ("/usr/share/doc/perl/README", False),
        ("/usr/include/stdio.h", False),
        ("/ucrt64/lib/libpython3.14.dll.a", False),
        ("/ucrt64/lib/python3.14/test/test_os.py", False),
        ("/ucrt64/lib/python3.14/os.py", True),
        ("/usr/share/perl5/core_perl/POSIX.pm", True),
        ("/usr/share/licenses/tcsh/LICENSE", True),
    ],
)
def test_keep_file(path: str, kept: bool) -> None:
    """Documentation, headers, static libraries and the test suite are left out."""
    assert keep_file(path) is kept


def test_target_path() -> None:
    """MSYS2 files go to msys/, UCRT64 files to python/."""
    assert target_path("msys", "/usr/bin/sed.exe") == PurePosixPath("msys/usr/bin/sed.exe")
    assert target_path("python", "/ucrt64/bin/python.exe") == PurePosixPath("python/bin/python.exe")
    assert target_path("python", "/usr/bin/sed.exe") is None


@pytest.mark.parametrize(
    ("line", "interpreter"),
    [
        ("#!/usr/bin/env tcsh", "tcsh"),
        ("#!/bin/tcsh -f", "tcsh"),
        ("#!/bin/csh", "tcsh"),
        ("#!/usr/bin/env python", "python"),
        ("#!/usr/bin/env python3", "python"),
        ("#!/usr/bin/perl", "perl"),
        ("#!/bin/bash", "sh"),
        ("#!/usr/bin/env AFNI_Batch_R", None),
        ("print('x')", None),
        ("#!", None),
    ],
)
def test_script_interpreter(line: str, interpreter: str | None) -> None:
    """The #! line decides which interpreter the launcher starts."""
    assert script_interpreter(line) == interpreter


def test_shebang_flags() -> None:
    """Options of a tcsh #! line are passed on, others are not."""
    assert shebang_flags("#!/bin/tcsh -f", "tcsh") == ["-f"]
    assert shebang_flags("#!/usr/bin/env tcsh", "tcsh") == []
    assert shebang_flags("#!/usr/bin/env python -u", "python") == []


def test_launcher_runs_the_script_with_its_interpreter() -> None:
    """The launcher sets the environment, then starts the interpreter with the script."""
    text = launcher("@SSwarper", "tcsh", ["-f"])
    assert text.endswith("\r\n")
    assert 'call "%~dp0afni-env.cmd" || exit /b 1' in text
    assert (
        r'"%AFNI_ROOT%\msys\usr\bin\tcsh.exe" -f "%AFNI_ROOT_SLASH%/scripts/@SSwarper" %*' in text
    )
    assert r"%AFNI_ROOT%\python\bin\python.exe" in launcher("afni_proc.py", "python", [])


def test_install_scripts_writes_launchers(tmp_path: Path) -> None:
    """Every upstream script is copied; scripts with a known #! line get a launcher."""
    source = tmp_path / "upstream"
    tcsh_dir = source / "src" / "scripts_install"
    python_dir = source / "src" / "python_scripts" / "scripts"
    tcsh_dir.mkdir(parents=True)
    python_dir.mkdir(parents=True)
    (source / "src" / "scripts_for_r").mkdir()
    (source / "src" / "R_scripts").mkdir()
    (source / "src" / "scripts_for_r" / "3dMVM").write_text("#!/bin/tcsh -f\n")
    (source / "src" / "R_scripts" / "3dMVM.R").write_text("#!/usr/bin/env AFNI_Batch_R\n")
    (tcsh_dir / "@GetAfniView").write_text("#!/usr/bin/env tcsh\necho\n")
    (tcsh_dir / "CMakeLists.txt").write_text("project(x)\n")
    (tcsh_dir / "notes.txt").write_text("plain text\n")
    (python_dir / "afni_proc.py").write_text("#!/usr/bin/env python\n")
    package = tmp_path / "package"
    package.mkdir()
    config = ScriptingConfig(package_dir=package, source_dir=source, msys_root=tmp_path)
    result = ScriptingResult()
    _install_scripts(config, result)
    assert sorted(p.name for p in (package / "scripts").iterdir()) == [
        "3dMVM",
        "3dMVM.R",
        "@GetAfniView",
        "afni_proc.py",
        "notes.txt",
    ]
    assert sorted(p.name for p in package.glob("*.cmd")) == [
        "3dMVM.cmd",
        "@GetAfniView.cmd",
        "afni_proc.py.cmd",
    ]
    assert (result.scripts, result.launchers) == (5, 3)
    assert " -f " in (package / "3dMVM.cmd").read_text()


def test_sources_text_lists_packages_and_r() -> None:
    """Every bundled package version and the R source are named, CRLF ends."""
    text = sources_text({"tcsh": "6.24.16-1", "bash": "5.2-1"}, "4.6.1", "https://p/cran/d")
    assert "  bash 5.2-1\r\n  tcsh 6.24.16-1\r\n" in text
    assert "https://cran.r-project.org/src/base/R-4/R-4.6.1.tar.gz" in text
    assert "\n" not in text.replace("\r\n", "")
    assert "R/ is R" not in sources_text({}, None, None)
