"""Add the scripting runtime to a package directory (docs/DECISIONS.md D38).

Runs inside MSYS2 after ``tools.package`` has assembled the programs. It adds:

- ``scripts/``: the upstream tcsh, Python, perl and R launcher scripts;
- ``msys/``: the MSYS2 userland of ``manifests/scripting-runtime.txt``
  (``tcsh``, ``sh``, coreutils, ...) with a mount table that maps ``/tmp`` to
  the user's temporary directory;
- ``python/``: the UCRT64 Python with numpy and matplotlib, ``afnipy`` and the
  shell shim ``afni_win_posix_shell`` in its ``site-packages``;
- ``R/``: the R installed by ``tools.r_runtime`` (with its CRAN packages), and
  ``scripts/R_io.so`` for ``AFNIio.R``;
- ``afni-env.cmd``, ``afni-tcsh.cmd``, ``tcsh.cmd`` and one ``<script>.cmd``
  launcher per script, so that scripts also start from ``cmd.exe``.

Package files come from ``pacman -Qlq``; dependencies from ``pactree -lu``.
"""

import argparse
import json
import logging
import re
import shutil
import subprocess
import sys
from pathlib import Path, PurePosixPath

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MANIFEST = REPO_ROOT / "manifests" / "scripting-runtime.txt"
SHIM_DIR = REPO_ROOT / "runtime" / "python"
TREES: dict[str, tuple[str, str]] = {"msys": ("/", "msys"), "python": ("/ucrt64/", "python")}
EXCLUDED = re.compile(
    r"(^|/)(include|share/(doc|man|info|locale|gtk-doc|bash-completion)|lib/pkgconfig|lib/cmake)(/|$)"
    r"|\.(a|la|h|hpp)$"
    r"|(^|/)lib/python3\.\d+/test/"
)
SCRIPT_DIRS: tuple[str, ...] = (
    "src/scripts_install",
    "src/python_scripts/scripts",
    "src/scripts_for_r",
    "src/R_scripts",
)
FSTAB = (
    "# afni-win: MSYS2 mount table of the AFNI scripting runtime\n"
    "none / cygdrive binary,posix=0,noacl,user 0 0\n"
    "none /tmp usertemp binary,posix=0,noacl 0 0\n"
)
ENV_CMD = r"""@echo off
rem afni-win: environment of the AFNI scripts (docs/DECISIONS.md D38).
rem Called by the AFNI shells and the script launchers; sets the variables
rem for the caller. Fails when the AFNI directory or the current directory
rem contains a space: AFNI does not support such paths (D34).
set "AFNI_ROOT=%~dp0"
set "AFNI_ROOT=%AFNI_ROOT:~0,-1%"
if not "%AFNI_ROOT%"=="%AFNI_ROOT: =%" (
  echo ** AFNI: the AFNI directory "%AFNI_ROOT%" contains a space. 1>&2
  echo    AFNI does not support paths with spaces; reinstall into a folder such as C:\AFNI. 1>&2
  exit /b 1
)
if not "%CD%"=="%CD: =%" (
  echo ** AFNI: the current directory "%CD%" contains a space. 1>&2
  echo    AFNI does not support paths with spaces; use a folder such as C:\data. 1>&2
  exit /b 1
)
set "AFNI_ROOT_SLASH=%AFNI_ROOT:\=/%"
set "AFNI_PATH=%AFNI_ROOT%;%AFNI_ROOT%\scripts;%AFNI_ROOT%\msys\usr\bin"
set "PATH=%AFNI_PATH%;%AFNI_ROOT%\python\bin;%AFNI_ROOT%\R\bin;%PATH%"
if not defined HOME set "HOME=%USERPROFILE%"
set "AFNI_ALLOW_ARBITRARY_FILENAMES=YES"
set "LANG=C.UTF-8"
set "MPLBACKEND=Agg"
exit /b 0
"""
TCSH_CMD = r"""@echo off
rem afni-win: tcsh of the AFNI scripting runtime, e.g. "tcsh -xef proc.subj".
setlocal
call "%~dp0afni-env.cmd" || exit /b 1
"%AFNI_ROOT%\msys\usr\bin\tcsh.exe" %*
"""
SHELL_CMD = r"""@echo off
rem afni-win: interactive AFNI shell (tcsh) with the AFNI environment.
setlocal
call "%~dp0afni-env.cmd" || (pause & exit /b 1)
echo AFNI shell (tcsh). AFNI programs and scripts are on the PATH; type "exit" to leave.
"%AFNI_ROOT%\msys\usr\bin\tcsh.exe"
"""


class ScriptingConfig(BaseModel):
    """Inputs of the runtime assembly."""

    package_dir: Path
    source_dir: Path
    msys_root: Path
    manifest: Path = DEFAULT_MANIFEST
    r_home: Path | None = None
    r_io: Path | None = None


class ScriptingResult(BaseModel):
    """What the runtime added to the package."""

    packages: dict[str, str] = Field(default_factory=dict)
    scripts: int = 0
    launchers: int = 0
    python_version: str = ""


def read_manifest(path: Path) -> list[tuple[str, str]]:
    """Read the runtime package list.

    Args:
        path: Manifest with ``<tree> <package>`` lines; ``#`` starts a comment.

    Returns:
        (tree, package) pairs in file order.

    Raises:
        ValueError: If a line is malformed or names an unknown tree.
    """
    entries: list[tuple[str, str]] = []
    for line in path.read_text().splitlines():
        fields = line.split("#", 1)[0].split()
        if not fields:
            continue
        if len(fields) != 2 or fields[0] not in TREES:
            raise ValueError(f"{path}: expected '<msys|python> <package>': {line}")
        entries.append((fields[0], fields[1]))
    return entries


def keep_file(path: str) -> bool:
    """Tell whether a package file belongs in the runtime.

    Args:
        path: File path as listed by ``pacman -Qlq`` (absolute, POSIX).

    Returns:
        False for documentation, headers, static libraries, the Python test
        suite and directories.
    """
    return not path.endswith("/") and EXCLUDED.search(path) is None


def target_path(tree: str, path: str) -> PurePosixPath | None:
    """Map a package file to its place in the package directory.

    Args:
        tree: ``msys`` or ``python``.
        path: File path as listed by ``pacman -Qlq``.

    Returns:
        Path relative to the package directory, or None if the file is
        outside the tree's prefix.
    """
    prefix, destination = TREES[tree]
    if not path.startswith(prefix):
        return None
    return PurePosixPath(destination) / path.removeprefix(prefix)


def script_interpreter(first_line: str) -> str | None:
    """Classify a script by its ``#!`` line.

    Args:
        first_line: First line of the file.

    Returns:
        ``tcsh``, ``python``, ``perl`` or ``sh``, or None if it is not a script
        that a launcher can start.
    """
    if not first_line.startswith("#!"):
        return None
    words = first_line[2:].split()
    if not words:
        return None
    name = PurePosixPath(words[0]).name
    if name == "env" and len(words) > 1:
        name = words[1]
    if name in ("tcsh", "csh"):
        return "tcsh"
    if name.startswith("python"):
        return "python"
    if name == "perl":
        return "perl"
    if name in ("sh", "bash"):
        return "sh"
    return None


def launcher(script: str, interpreter: str, flags: list[str]) -> str:
    """Write the ``.cmd`` launcher that runs a script from ``cmd.exe``.

    Args:
        script: Script file name in ``scripts/``.
        interpreter: Result of :func:`script_interpreter`.
        flags: Interpreter options from the ``#!`` line (e.g. ``-f``).

    Returns:
        Text of ``<script>.cmd`` (CRLF line ends).
    """
    programs = {
        "tcsh": r"%AFNI_ROOT%\msys\usr\bin\tcsh.exe",
        "perl": r"%AFNI_ROOT%\msys\usr\bin\perl.exe",
        "sh": r"%AFNI_ROOT%\msys\usr\bin\bash.exe",
        "python": r"%AFNI_ROOT%\python\bin\python.exe",
    }
    options = "".join(f" {flag}" for flag in flags)
    lines = [
        "@echo off",
        f"rem afni-win launcher for scripts/{script} (tools/scripting.py)",
        "setlocal",
        'call "%~dp0afni-env.cmd" || exit /b 1',
        f'"{programs[interpreter]}"{options} "%AFNI_ROOT_SLASH%/scripts/{script}" %*',
    ]
    return "\r\n".join(lines) + "\r\n"


def shebang_flags(first_line: str, interpreter: str) -> list[str]:
    """Interpreter options of a ``#!`` line that the launcher passes on.

    Args:
        first_line: First line of the script.
        interpreter: Result of :func:`script_interpreter`.

    Returns:
        Options such as ``-f`` (tcsh), or an empty list.
    """
    words = first_line[2:].split()
    if PurePosixPath(words[0]).name == "env":
        words = words[1:]
    return [w for w in words[1:] if w.startswith("-")] if interpreter == "tcsh" else []


def _pacman(*args: str) -> str:
    """Run pacman (or pactree) and return its output.

    Args:
        *args: Program and arguments.

    Returns:
        Standard output.
    """
    return subprocess.run(list(args), check=True, capture_output=True, text=True).stdout


def _closure(packages: list[str]) -> list[str]:
    """Collect packages and their dependencies.

    Args:
        packages: Package names.

    Returns:
        Unique package names, the given ones first.
    """
    names: list[str] = []
    for package in packages:
        for name in _pacman("pactree", "-lu", package).split():
            if name not in names:
                names.append(name)
    return names


def _version(package: str) -> str:
    """Return the installed version of a package.

    Args:
        package: Package name.

    Returns:
        Version string.
    """
    return _pacman("pacman", "-Q", package).split()[1]


def _copy_packages(config: ScriptingConfig, result: ScriptingResult) -> None:
    """Copy the runtime packages and their dependencies into the package.

    Args:
        config: Runtime configuration.
        result: Updated with package versions.
    """
    entries = read_manifest(config.manifest)
    for tree in TREES:
        wanted = [p for t, p in entries if t == tree]
        for package in _closure(wanted):
            files = _pacman("pacman", "-Qlq", package).splitlines()
            copied = 0
            for path in files:
                target = target_path(tree, path)
                if target is None or not keep_file(path):
                    continue
                source = config.msys_root / path.lstrip("/")
                if not source.is_file():
                    continue
                destination = config.package_dir / Path(target)
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)
                copied += 1
            if copied:
                result.packages[package] = _version(package)


def _install_python_extras(config: ScriptingConfig, result: ScriptingResult) -> None:
    """Put afnipy and the shell shim into the bundled Python's site-packages.

    Args:
        config: Runtime configuration.
        result: Updated with the Python version directory.

    Raises:
        FileNotFoundError: If the bundled Python has no site-packages.
    """
    candidates = sorted((config.package_dir / "python" / "lib").glob("python3.*/site-packages"))
    if not candidates:
        raise FileNotFoundError("python/lib/python3.*/site-packages not found in the package")
    site = candidates[-1]
    result.python_version = site.parent.name
    shutil.copytree(
        config.source_dir / "src" / "python_scripts" / "afnipy",
        site / "afnipy",
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    for name in ("afni_win_posix_shell.py", "afni_win_posix_shell.pth"):
        shutil.copy2(SHIM_DIR / name, site / name)


def _install_scripts(config: ScriptingConfig, result: ScriptingResult) -> None:
    """Copy the upstream scripts and write a launcher for each.

    Args:
        config: Runtime configuration.
        result: Updated with the number of scripts and launchers.
    """
    scripts = config.package_dir / "scripts"
    scripts.mkdir(exist_ok=True)
    for directory in SCRIPT_DIRS:
        for path in sorted((config.source_dir / directory).iterdir()):
            if not path.is_file() or path.name == "CMakeLists.txt":
                continue
            shutil.copy2(path, scripts / path.name)
            result.scripts += 1
            with path.open("rb") as handle:
                first_line = handle.readline().decode("utf-8", "replace").strip()
            interpreter = script_interpreter(first_line)
            if interpreter is None:
                continue
            text = launcher(path.name, interpreter, shebang_flags(first_line, interpreter))
            (config.package_dir / f"{path.name}.cmd").write_bytes(text.encode())
            result.launchers += 1


def assemble(config: ScriptingConfig) -> ScriptingResult:
    """Add the scripting runtime to the package directory.

    Args:
        config: Runtime configuration.

    Returns:
        What was added.
    """
    result = ScriptingResult()
    _copy_packages(config, result)
    _install_python_extras(config, result)
    _install_scripts(config, result)
    if config.r_home is not None:
        shutil.copytree(config.r_home, config.package_dir / "R")
    if config.r_io is not None:
        shutil.copy2(config.r_io, config.package_dir / "scripts" / config.r_io.name)
    etc = config.package_dir / "msys" / "etc"
    etc.mkdir(parents=True, exist_ok=True)
    (etc / "fstab").write_text(FSTAB)
    for name, text in (
        ("afni-env.cmd", ENV_CMD),
        ("tcsh.cmd", TCSH_CMD),
        ("afni-tcsh.cmd", SHELL_CMD),
    ):
        (config.package_dir / name).write_bytes(text.replace("\n", "\r\n").encode())
    return result


def main() -> None:
    """Command line entry point; writes ``scripting.json`` next to the package."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package-dir", type=Path, required=True)
    parser.add_argument("--source-dir", type=Path, required=True, help="upstream checkout")
    parser.add_argument("--msys-root", type=Path, required=True, help="Windows path of MSYS2 /")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    config = ScriptingConfig(**vars(parser.parse_args()))
    try:
        result = assemble(config)
    except (FileNotFoundError, ValueError, subprocess.CalledProcessError) as error:
        logger.error("%s", error)
        sys.exit(1)
    (config.package_dir.parent / "scripting.json").write_text(
        json.dumps(result.model_dump(), indent=2)
    )
    logger.info(
        "Runtime: %d packages, %d scripts, %d launchers, %s",
        len(result.packages),
        result.scripts,
        result.launchers,
        result.python_version,
    )


if __name__ == "__main__":
    main()
