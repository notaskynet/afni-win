"""Report how the use of POSIX APIs changed between two upstream tags.

``scan`` records the textual call sites of every inventoried API in an
upstream checkout (the scanner of ``tools.inventory``) as JSON; the file is
attached to each release. ``diff`` compares two such files and writes a
Markdown report: call-site counts per API and the call sites that appeared
or disappeared. Line numbers are ignored when matching call sites, so code
that only moved is not reported.
"""

import argparse
import json
import logging
from collections import Counter
from pathlib import Path

from pydantic import BaseModel

from tools.inventory import API_GROUPS, scan_callsites

logger = logging.getLogger(__name__)


class CallSites(BaseModel):
    """Call sites of one upstream tag."""

    tag: str
    callsites: dict[str, list[str]]


def _by_file(sites: list[str]) -> Counter[str]:
    """Count call sites per file, ignoring line numbers.

    Args:
        sites: ``file:line`` locations.

    Returns:
        Number of call sites per file.
    """
    return Counter(site.rsplit(":", 1)[0] for site in sites)


def render_diff(previous: CallSites | None, current: CallSites) -> str:
    """Render the difference between two tags as Markdown.

    Args:
        previous: Call sites of the previous released tag, if any.
        current: Call sites of the tag being built.

    Returns:
        Markdown text.
    """
    if previous is None:
        return f"## POSIX API use\n\nNo previous release to compare {current.tag} with.\n"
    lines = [
        f"## POSIX API use: {previous.tag} -> {current.tag}",
        "",
        "| Group | API | Call sites before | Call sites now | Files with more | Files with fewer |",
        "|---|---|---|---|---|---|",
    ]
    changed = 0
    for group, names in API_GROUPS.items():
        for name in names:
            before = previous.callsites.get(name, [])
            now = current.callsites.get(name, [])
            more = _by_file(now) - _by_file(before)
            fewer = _by_file(before) - _by_file(now)
            if not more and not fewer:
                continue
            changed += 1
            lines.append(
                f"| {group} | {name} | {len(before)} | {len(now)} "
                f"| {', '.join(sorted(more))} | {', '.join(sorted(fewer))} |"
            )
    if changed == 0:
        lines = [lines[0], "", "No change in the use of inventoried APIs."]
    return "\n".join(lines) + "\n"


def _parse_args() -> argparse.Namespace:
    """Parse command line arguments.

    Returns:
        Parsed arguments.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    scan = sub.add_parser("scan")
    scan.add_argument("--tag", required=True)
    scan.add_argument("--source-dir", type=Path, required=True, help="upstream src directory")
    scan.add_argument("--output", type=Path, required=True)
    diff = sub.add_parser("diff")
    diff.add_argument("--previous", type=Path, help="call sites of the previous release")
    diff.add_argument("--current", type=Path, required=True)
    diff.add_argument("--report", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    """Run ``scan`` or ``diff``."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = _parse_args()
    if args.command == "scan":
        sites = CallSites(tag=args.tag, callsites=scan_callsites(args.source_dir))
        args.output.write_text(json.dumps(sites.model_dump(), indent=1, sort_keys=True))
        logger.info("%d APIs with call sites", len(sites.callsites))
        return
    previous = (
        CallSites.model_validate_json(args.previous.read_text())
        if args.previous is not None and args.previous.exists()
        else None
    )
    current = CallSites.model_validate_json(args.current.read_text())
    args.report.write_text(render_diff(previous, current))


if __name__ == "__main__":
    main()
