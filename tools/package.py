"""Assemble the release directory and zip archive of a Windows build.

The archive holds the programs that were built, the DLLs of the build, the
MSYS2 runtime DLLs they import (found recursively with ``objdump -p``), the
helper programs listed in ``manifests/runtime-deps.txt`` and a README that
names the upstream tag, commit and patches.
"""

import argparse
import hashlib
import logging
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

from pydantic import BaseModel, Field

from tools.build import BuildResult
from tools.scripting import ScriptingConfig, ScriptingResult, assemble

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent
DLL_NAME = re.compile(r"DLL Name:\s*(\S+)", re.IGNORECASE)
BUSYBOX_APPLETS: tuple[str, ...] = ("gzip.exe", "bzip2.exe")
BUSYBOX_NOTICE = (
    "busybox.exe, gzip.exe and bzip2.exe are busybox-w32 by Ron Yorston, licensed under\r\n"
    "GPL-2.0-only. Version and checksum: see runtime-deps.txt. Source code:\r\n"
    "https://github.com/rmyorston/busybox-w32 (the tag named by the FRP version).\r\n"
)


class PackageConfig(BaseModel):
    """Inputs and outputs of packaging."""

    build_dir: Path
    source_dir: Path
    runtime_dir: Path
    busybox: Path
    output_dir: Path
    helpers: list[str] = Field(default_factory=lambda: ["qhull.exe", "cjpeg.exe", "djpeg.exe"])
    objdump: str = "objdump"
    msys_root: Path | None = None


class PackageResult(BaseModel):
    """What went into the package."""

    tag: str
    commit: str
    patches: list[str]
    programs: list[str]
    optional_programs: list[str]
    build_dlls: list[str]
    runtime_dlls: list[str]
    helpers: list[str]
    archive: str
    sha256: str
    scripting: ScriptingResult | None = None


def imported_dlls(objdump: str, path: Path) -> list[str]:
    """List the DLLs a PE file imports.

    Args:
        objdump: ``objdump`` executable.
        path: Executable or DLL.

    Returns:
        Imported DLL names as written in the import table.

    Raises:
        subprocess.CalledProcessError: If ``objdump`` fails.
    """
    result = subprocess.run([objdump, "-p", str(path)], check=True, capture_output=True, text=True)
    return DLL_NAME.findall(result.stdout)


def resolve_runtime(
    objdump: str, roots: list[Path], local_dir: Path, runtime_dir: Path
) -> list[Path]:
    """Find the runtime DLLs needed by a set of files, recursively.

    DLLs present in ``local_dir`` (the build) are not runtime DLLs; DLLs found
    in neither directory are system DLLs and are not shipped.

    Args:
        objdump: ``objdump`` executable.
        roots: Executables and DLLs to start from.
        local_dir: Directory with the DLLs of the build.
        runtime_dir: Directory with the MSYS2 runtime DLLs.

    Returns:
        Runtime DLL paths, sorted by name.
    """
    local = {p.name.lower() for p in local_dir.glob("*.dll")}
    available = {p.name.lower(): p for p in runtime_dir.glob("*.dll")}
    found: dict[str, Path] = {}
    queue = list(roots)
    seen: set[str] = set()
    while queue:
        path = queue.pop()
        if path.name.lower() in seen:
            continue
        seen.add(path.name.lower())
        for name in imported_dlls(objdump, path):
            key = name.lower()
            if key in local:
                queue.append(local_dir / name)
            elif key in available and key not in found:
                found[key] = available[key]
                queue.append(available[key])
    return sorted(found.values(), key=lambda p: p.name.lower())


def _readme(result: BuildResult, programs: list[str], helpers: list[str]) -> str:
    """Write the README of the archive.

    Args:
        result: Build result.
        programs: Programs in the archive.
        helpers: Helper programs in the archive.

    Returns:
        README text.
    """
    lines = [
        f"AFNI {result.tag} for Windows (x86-64), built by afni-win",
        "",
        f"Upstream: https://github.com/afni/afni tag {result.tag}, commit {result.commit}",
        "Patches applied (sources in the afni-win repository, directory patches/):",
        *[f"  {name}" for name in result.patches],
        "",
        "Put this directory on PATH. Programs that run other programs (3dttest++",
        "-Clustsim, compressed .BRIK files through gzip/bzip2) find them through PATH.",
        "busybox.exe provides sh for popen()/system(); gzip.exe and bzip2.exe are",
        "copies of it (busybox-w32 selects the applet from the file name).",
        "Use forward slashes in file names (C:/data/anat+orig).",
        "",
        f"Programs ({len(programs)}): " + " ".join(programs),
        "Helpers: " + " ".join(["busybox.exe", *BUSYBOX_APPLETS, *helpers]),
        "",
        "Licences: see licenses/ and manifests/runtime-deps.txt of afni-win.",
        "",
    ]
    return "\r\n".join(lines)


def package(config: PackageConfig) -> PackageResult:
    """Assemble the package directory and archive.

    Args:
        config: Locations.

    Returns:
        Description of the package.

    Raises:
        FileNotFoundError: If a helper program or a runtime file is missing.
    """
    result = BuildResult.model_validate_json((config.build_dir / "build-result.json").read_text())
    targets = config.build_dir / "build" / "targets_built"
    name = f"afni-{result.tag}-win64"
    root = config.output_dir / name
    if root.exists():
        shutil.rmtree(root)
    (root / "licenses").mkdir(parents=True)

    programs = [
        p for p in [*result.built, *result.optional_built] if (targets / f"{p}.exe").exists()
    ]
    exes = [targets / f"{p}.exe" for p in programs]
    build_dlls = sorted(targets.glob("*.dll"), key=lambda p: p.name.lower())
    helpers: list[Path] = []
    for helper in config.helpers:
        path = config.runtime_dir / helper
        if not path.is_file():
            raise FileNotFoundError(f"helper {helper} not found in {config.runtime_dir}")
        helpers.append(path)
    runtime = resolve_runtime(
        config.objdump, [*exes, *build_dlls, *helpers], targets, config.runtime_dir
    )
    for path in [*exes, *build_dlls, *helpers, *runtime]:
        shutil.copy2(path, root / path.name)
    shutil.copy2(config.busybox, root / "busybox.exe")
    for applet in BUSYBOX_APPLETS:
        shutil.copy2(config.busybox, root / applet)
    shutil.copy2(config.source_dir / "src" / "AFNI_atlas_spaces.niml", root)
    shutil.copy2(config.source_dir / "LICENSE.txt", root / "licenses" / "AFNI-LICENSE.txt")
    shutil.copy2(REPO_ROOT / "LICENSE", root / "licenses" / "afni-win-LICENSE.txt")
    shutil.copy2(REPO_ROOT / "manifests" / "runtime-deps.txt", root / "licenses")
    (root / "licenses" / "busybox-w32.txt").write_text(BUSYBOX_NOTICE)
    (root / "README.txt").write_text(_readme(result, programs, [h.name for h in helpers]))
    scripting = None
    if config.msys_root is not None:
        scripting = assemble(
            ScriptingConfig(
                package_dir=root, source_dir=config.source_dir, msys_root=config.msys_root
            )
        )

    archive = config.output_dir / f"{name}.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(root.rglob("*")):
            if path.is_file():
                zf.write(path, path.relative_to(config.output_dir).as_posix())
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    return PackageResult(
        tag=result.tag,
        commit=result.commit,
        patches=result.patches,
        programs=result.built,
        optional_programs=result.optional_built,
        build_dlls=[p.name for p in build_dlls],
        runtime_dlls=[p.name for p in runtime],
        helpers=["busybox.exe", *BUSYBOX_APPLETS, *(h.name for h in helpers)],
        archive=archive.name,
        sha256=digest,
        scripting=scripting,
    )


def _parse_args() -> PackageConfig:
    """Parse command line arguments.

    Returns:
        Packaging configuration.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-dir", type=Path, required=True, help="tools.build --work-dir")
    parser.add_argument("--source-dir", type=Path, required=True, help="upstream checkout")
    parser.add_argument("--runtime-dir", type=Path, required=True, help="MSYS2 ucrt64/bin")
    parser.add_argument("--busybox", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--objdump", default="objdump")
    parser.add_argument(
        "--msys-root", type=Path, help="Windows path of MSYS2 /: add the scripting runtime"
    )
    return PackageConfig(**vars(parser.parse_args()))


def main() -> None:
    """Build the package and write ``package.json`` next to the archive."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    config = _parse_args()
    try:
        result = package(config)
    except (FileNotFoundError, ValueError, subprocess.CalledProcessError) as error:
        logger.error("%s", error)
        sys.exit(1)
    (config.output_dir / "package.json").write_text(result.model_dump_json(indent=2))
    logger.info(
        "%s: %d programs, %d optional, %d runtime DLLs, sha256 %s",
        result.archive,
        len(result.programs),
        len(result.optional_programs),
        len(result.runtime_dlls),
        result.sha256,
    )


if __name__ == "__main__":
    main()
