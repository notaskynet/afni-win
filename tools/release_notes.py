"""Compose the build report used as the body of a GitHub release.

The report names the upstream tag, commit and patches (required by the
spec), lists what was packaged, the optional programs that did not build,
the result of the Linux comparison, the POSIX API changes since the previous
release and the versions of the MSYS2 packages that were shipped.
"""

import argparse
import hashlib
import logging
from pathlib import Path

from pydantic import BaseModel

from tools.build import BuildResult
from tools.package import PackageResult

logger = logging.getLogger(__name__)

REPOSITORY_URL = "https://github.com/notaskynet/afni-win"


class NotesConfig(BaseModel):
    """Inputs and output of the report."""

    build_result: Path
    package: Path
    comparison: Path
    posix_diff: Path
    packages: Path
    commit: str
    output: Path
    installer: Path | None = None


def render_notes(
    build: BuildResult,
    package: PackageResult,
    comparison: str,
    posix_diff: str,
    packages: str,
    commit: str,
    installer: tuple[str, str] | None = None,
) -> str:
    """Render the release body.

    Args:
        build: Result of tools.build.
        package: Result of tools.package.
        comparison: Markdown report of tests.regression.compare.
        posix_diff: Markdown report of tools.posix_diff.
        packages: ``pacman -Q`` output for the shipped MSYS2 packages.
        commit: afni-win commit that produced the build.
        installer: File name and sha256 of the Windows installer, if built.

    Returns:
        Markdown text.
    """
    summary = next((line for line in comparison.splitlines() if "Result:" in line), "")
    not_built = build.optional_missing + build.optional_undefined
    lines = [
        f"AFNI `{build.tag}` (upstream commit `{build.commit}`) for Windows x86-64, "
        f"built by afni-win `{commit}` ({REPOSITORY_URL}/tree/{commit}).",
        "",
        "### Patches",
        "",
        *[f"- [`{p}`]({REPOSITORY_URL}/blob/{commit}/patches/{p})" for p in build.patches],
        "",
        "### Download",
        "",
        *(
            [
                f"- **`{installer[0]}`**: installer, recommended. Run it and follow the wizard;",
                "  afterwards open *AFNI Command Prompt* from the Start menu.",
                f"  sha256 `{installer[1]}`",
            ]
            if installer is not None
            else []
        ),
        f"- `{package.archive}`: the same programs as a zip archive, sha256 `{package.sha256}`",
        "",
        "### Contents",
        "",
        f"- required programs: {len(package.programs)} (all of them)",
        f"- optional programs: {len(package.optional_programs)} built, "
        f"{len(not_built)} not built" + (f": {' '.join(not_built)}" if not_built else ""),
        f"- runtime DLLs: {' '.join(package.runtime_dlls)}",
        f"- helpers: {' '.join(package.helpers)}",
        "",
        "### Comparison with the Linux build of the same tag",
        "",
        summary or "No comparison report.",
        "",
        "The full table is attached as `comparison.md`.",
        "",
        posix_diff.replace("## ", "### ", 1).rstrip(),
        "",
        "### MSYS2 packages",
        "",
        "```",
        packages.strip(),
        "```",
        "",
    ]
    return "\n".join(lines)


def _parse_args() -> NotesConfig:
    """Parse command line arguments.

    Returns:
        Report configuration.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-result", type=Path, required=True)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--comparison", type=Path, required=True)
    parser.add_argument("--posix-diff", type=Path, required=True)
    parser.add_argument("--packages", type=Path, required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--installer", type=Path)
    return NotesConfig(**vars(parser.parse_args()))


def main() -> None:
    """Write the release body."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    config = _parse_args()
    text = render_notes(
        BuildResult.model_validate_json(config.build_result.read_text()),
        PackageResult.model_validate_json(config.package.read_text()),
        config.comparison.read_text(),
        config.posix_diff.read_text(),
        config.packages.read_text(),
        config.commit,
        (
            (config.installer.name, hashlib.sha256(config.installer.read_bytes()).hexdigest())
            if config.installer is not None
            else None
        ),
    )
    config.output.write_text(text)
    logger.info("Wrote %s", config.output)


if __name__ == "__main__":
    main()
