"""Select upstream AFNI tags to build, and find the previous released tag.

``select`` lists the tags of the upstream repository (``git ls-remote``),
keeps release tags (``AFNI_YY.M.NN``) not older than the baseline, drops tags
that already have a ``<tag>-win`` release or are marked as failed, and prints
the newest ones as a JSON list. ``previous`` prints the newest released tag
older than a given tag (empty if there is none).
"""

import argparse
import json
import logging
import re
import subprocess
import sys
from pathlib import Path

from pydantic import BaseModel

logger = logging.getLogger(__name__)

TAG = re.compile(r"^AFNI_(\d+)\.(\d+)\.(\d+)$")
RELEASE_SUFFIX = "-win"
FAILED_TITLE = re.compile(r"^Build failed: (AFNI_\d+\.\d+\.\d+)$")


class SelectConfig(BaseModel):
    """Inputs of ``select``."""

    upstream_url: str
    baseline: str
    released: Path
    failed: Path
    max_tags: int


def tag_version(tag: str) -> tuple[int, int, int] | None:
    """Parse an upstream release tag.

    Args:
        tag: Tag name, e.g. ``AFNI_26.2.09``.

    Returns:
        Version tuple, or None if the name is not a release tag.
    """
    match = TAG.match(tag)
    if match is None:
        return None
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


def remote_tags(upstream_url: str) -> list[str]:
    """List the tags of a remote repository.

    Args:
        upstream_url: Repository URL.

    Returns:
        Tag names.

    Raises:
        subprocess.CalledProcessError: If ``git ls-remote`` fails.
    """
    result = subprocess.run(
        ["git", "ls-remote", "--tags", "--refs", upstream_url],
        check=True,
        capture_output=True,
        text=True,
    )
    return [line.split("refs/tags/", 1)[1] for line in result.stdout.splitlines() if line]


def released_tags(releases: list[dict[str, str]]) -> set[str]:
    """Upstream tags that already have a release.

    Args:
        releases: ``gh release list --json tagName`` output.

    Returns:
        Upstream tag names.
    """
    return {
        r["tagName"].removesuffix(RELEASE_SUFFIX)
        for r in releases
        if r["tagName"].endswith(RELEASE_SUFFIX)
    }


def failed_tags(issues: list[dict[str, str]]) -> set[str]:
    """Upstream tags marked as failed by an issue.

    Args:
        issues: ``gh issue list --json title`` output.

    Returns:
        Upstream tag names.
    """
    tags = set()
    for issue in issues:
        match = FAILED_TITLE.match(issue["title"])
        if match is not None:
            tags.add(match.group(1))
    return tags


def select_tags(
    tags: list[str], baseline: str, released: set[str], failed: set[str], max_tags: int
) -> list[str]:
    """Choose the tags to build.

    Args:
        tags: Upstream tag names.
        baseline: Oldest tag to consider.
        released: Tags that already have a release.
        failed: Tags marked as failed.
        max_tags: Maximum number of tags to return.

    Returns:
        Newest eligible tags, oldest first.

    Raises:
        ValueError: If the baseline is not a release tag.
    """
    floor = tag_version(baseline)
    if floor is None:
        raise ValueError(f"baseline {baseline!r} is not an AFNI release tag")
    eligible = [
        t
        for t in tags
        if (v := tag_version(t)) is not None and v >= floor and t not in released | failed
    ]
    eligible.sort(key=lambda t: tag_version(t) or (0, 0, 0))
    return eligible[-max_tags:] if max_tags > 0 else []


def previous_release(tag: str, releases: list[dict[str, str]]) -> str:
    """Find the newest released upstream tag older than ``tag``.

    Args:
        tag: Current upstream tag.
        releases: ``gh release list --json tagName`` output.

    Returns:
        Upstream tag name, or an empty string.
    """
    current = tag_version(tag)
    older = [
        t
        for t in released_tags(releases)
        if (v := tag_version(t)) is not None and current is not None and v < current
    ]
    return max(older, key=lambda t: tag_version(t) or (0, 0, 0), default="")


def _parse_args() -> argparse.Namespace:
    """Parse command line arguments.

    Returns:
        Parsed arguments.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    select = sub.add_parser("select")
    select.add_argument("--upstream-url", required=True)
    select.add_argument("--baseline-file", type=Path, required=True)
    select.add_argument("--released", type=Path, required=True)
    select.add_argument("--failed", type=Path, required=True)
    select.add_argument("--max-tags", type=int, default=3)
    previous = sub.add_parser("previous")
    previous.add_argument("--tag", required=True)
    previous.add_argument("--released", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    """Print the selected tags (JSON list) or the previous released tag."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = _parse_args()
    releases = json.loads(args.released.read_text())
    if args.command == "previous":
        sys.stdout.write(previous_release(args.tag, releases) + "\n")
        return
    config = SelectConfig(
        upstream_url=args.upstream_url,
        baseline=args.baseline_file.read_text().strip(),
        released=args.released,
        failed=args.failed,
        max_tags=args.max_tags,
    )
    chosen = select_tags(
        remote_tags(config.upstream_url),
        config.baseline,
        released_tags(releases),
        failed_tags(json.loads(config.failed.read_text())),
        config.max_tags,
    )
    logger.info("Tags to build: %s", chosen)
    sys.stdout.write(json.dumps(chosen) + "\n")


if __name__ == "__main__":
    main()
