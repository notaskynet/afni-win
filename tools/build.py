"""Fetch an upstream AFNI tag, apply afni-win patches and build it for Windows.

Runs natively in an MSYS2 UCRT64 shell or on Linux with the MinGW-w64 UCRT
cross toolchain; ``cmake/toolchain-mingw.cmake`` selects the compiler.
"""

import argparse
import json
import logging
import subprocess
import sys
from pathlib import Path

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_UPSTREAM = "https://github.com/afni/afni.git"


class BuildConfig(BaseModel):
    """Build configuration."""

    tag: str
    work_dir: Path
    upstream_url: str = DEFAULT_UPSTREAM
    source_dir: Path | None = None
    build_type: str = "Release"
    generator: str = "Ninja"
    jobs: int | None = None
    manifests: list[Path] = Field(
        default_factory=lambda: [REPO_ROOT / "manifests" / "programs-required.txt"]
    )
    extra_targets: list[str] = Field(default_factory=list)
    patches_dir: Path = REPO_ROOT / "patches"
    toolchain: Path = REPO_ROOT / "cmake" / "toolchain-mingw.cmake"
    skip_fetch: bool = False
    skip_patch: bool = False


class BuildResult(BaseModel):
    """Outcome of a build."""

    tag: str
    commit: str
    patches: list[str]
    built: list[str]
    missing: list[str]
    undefined: list[str]


class PatchError(RuntimeError):
    """A patch does not apply to the upstream tree."""


def _run(cmd: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    """Run a command, logging it, and fail on a non-zero exit code.

    Args:
        cmd: Command and arguments.
        cwd: Working directory.

    Returns:
        Completed process with captured text output.

    Raises:
        subprocess.CalledProcessError: If the command fails.
    """
    logger.info("$ %s", " ".join(cmd))
    return subprocess.run(cmd, cwd=cwd, check=True, text=True, capture_output=True)


def _source_dir(config: BuildConfig) -> Path:
    """Return the upstream checkout location.

    Args:
        config: Build configuration.

    Returns:
        Path of the upstream source tree.
    """
    return config.source_dir or config.work_dir / "upstream"


def fetch(config: BuildConfig) -> Path:
    """Clone the upstream tag (shallow) unless it is already present.

    Args:
        config: Build configuration.

    Returns:
        Path of the upstream source tree.
    """
    source = _source_dir(config)
    if source.exists():
        logger.info("Using existing upstream tree %s", source)
        return source
    source.parent.mkdir(parents=True, exist_ok=True)
    _run(["git", "clone", "--depth", "1", "--branch", config.tag, config.upstream_url, str(source)])
    return source


def apply_patches(config: BuildConfig, source: Path) -> list[str]:
    """Apply every patch in order with ``git apply --3way``.

    Args:
        config: Build configuration.
        source: Upstream source tree.

    Returns:
        Names of the applied patches.

    Raises:
        PatchError: If a patch does not apply; the message names the patch.
    """
    applied: list[str] = []
    for patch in sorted(config.patches_dir.glob("*.patch")):
        try:
            _run(["git", "apply", "--3way", str(patch)], cwd=source)
        except subprocess.CalledProcessError as error:
            raise PatchError(f"{patch.name} does not apply:\n{error.stderr}") from error
        applied.append(patch.name)
        logger.info("Applied %s", patch.name)
    return applied


def configure(config: BuildConfig, source: Path) -> Path:
    """Configure the upstream CMake project for Windows.

    Args:
        config: Build configuration.
        source: Upstream source tree.

    Returns:
        Build directory.
    """
    build = config.work_dir / "build"
    _run(
        [
            "cmake",
            "-S",
            str(source),
            "-B",
            str(build),
            "-G",
            config.generator,
            f"-DCMAKE_TOOLCHAIN_FILE={config.toolchain}",
            f"-DCMAKE_BUILD_TYPE={config.build_type}",
            "-DCOMP_GUI=OFF",
            "-DCOMP_PYTHON=OFF",
            "-DCOMP_TCSH=OFF",
            "-DREMOVE_BUILD_PARITY_CHECKS=ON",
            "-DUSE_OMP=ON",
            f"-DFETCHCONTENT_SOURCE_DIR_NIFTI_CLIB={source / 'src' / 'nifti'}",
            f"-DFETCHCONTENT_SOURCE_DIR_GIFTI_CLIB={REPO_ROOT / 'cmake' / 'gifti'}",
        ]
    )
    return build


def _targets(config: BuildConfig) -> list[str]:
    """Collect build targets from the manifests and extra targets.

    Args:
        config: Build configuration.

    Returns:
        Ordered list of unique target names.
    """
    names: list[str] = []
    for manifest in config.manifests:
        for line in manifest.read_text().splitlines():
            name = line.split("#", 1)[0].strip()
            if name and name not in names:
                names.append(name)
    for name in config.extra_targets:
        if name not in names:
            names.append(name)
    return names


def _defined_targets(build_dir: Path) -> set[str]:
    """List the targets defined in a Ninja build directory.

    Args:
        build_dir: CMake build directory generated for Ninja.

    Returns:
        Names of all targets known to Ninja.
    """
    result = _run(["cmake", "--build", str(build_dir), "--", "-t", "targets", "all"])
    return {line.split(":", 1)[0] for line in result.stdout.splitlines() if ":" in line}


def build(config: BuildConfig, build_dir: Path, targets: list[str]) -> tuple[list[str], list[str]]:
    """Build the given targets, continuing past failures.

    Args:
        config: Build configuration.
        build_dir: CMake build directory.
        targets: Targets to build; all of them must be defined.

    Returns:
        Built and missing program names.
    """
    cmd = ["cmake", "--build", str(build_dir), "--target", *targets]
    if config.jobs is not None:
        cmd += ["--parallel", str(config.jobs)]
    cmd += ["--", "-k", "0"]
    logger.info("$ %s", " ".join(cmd))
    result = subprocess.run(cmd, text=True, capture_output=True)
    (build_dir / "build.log").write_text(result.stdout + result.stderr)
    output = build_dir / "targets_built"
    built = [t for t in targets if (output / f"{t}.exe").exists()]
    missing = [t for t in targets if t not in built]
    return built, missing


def run(config: BuildConfig) -> BuildResult:
    """Run fetch, patch, configure and build.

    Args:
        config: Build configuration.

    Returns:
        Build result.
    """
    source = _source_dir(config) if config.skip_fetch else fetch(config)
    patches = [] if config.skip_patch else apply_patches(config, source)
    commit = _run(["git", "rev-parse", "HEAD"], cwd=source).stdout.strip()
    build_dir = configure(config, source)
    targets = _targets(config)
    defined = _defined_targets(build_dir)
    undefined = [t for t in targets if t not in defined]
    if undefined:
        logger.warning("Not defined by the upstream CMake configuration: %s", undefined)
    built, missing = build(config, build_dir, [t for t in targets if t in defined])
    return BuildResult(
        tag=config.tag,
        commit=commit,
        patches=patches,
        built=built,
        missing=missing,
        undefined=undefined,
    )


def _parse_args() -> BuildConfig:
    """Parse command line arguments.

    Returns:
        Build configuration.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--upstream-url", default=DEFAULT_UPSTREAM)
    parser.add_argument("--source-dir", type=Path)
    parser.add_argument("--jobs", type=int)
    parser.add_argument("--manifest", dest="manifests", type=Path, action="append")
    parser.add_argument("--target", dest="extra_targets", action="append", default=[])
    parser.add_argument("--skip-fetch", action="store_true")
    parser.add_argument("--skip-patch", action="store_true")
    args = vars(parser.parse_args())
    if args["manifests"] is None:
        del args["manifests"]
    return BuildConfig(**args)


def main() -> None:
    """Run the build from the command line and print a JSON summary to stdout."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    config = _parse_args()
    try:
        result = run(config)
    except PatchError as error:
        logger.error("%s", error)
        sys.exit(2)
    except subprocess.CalledProcessError as error:
        logger.error("%s failed:\n%s%s", " ".join(error.cmd), error.stdout, error.stderr)
        sys.exit(1)
    (config.work_dir / "build-result.json").write_text(result.model_dump_json(indent=2))
    logger.info(
        "Built %d, failed %d %s, undefined %d %s",
        len(result.built),
        len(result.missing),
        result.missing,
        len(result.undefined),
        result.undefined,
    )
    sys.stdout.write(json.dumps(result.model_dump(), indent=2) + "\n")
    if result.missing or result.undefined:
        sys.exit(3)


if __name__ == "__main__":
    main()
