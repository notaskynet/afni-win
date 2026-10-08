"""Link-level inventory of POSIX APIs used by an AFNI build.

The inventory is computed from a Linux build of upstream AFNI in which every
executable was linked with ``-Wl,-Map=<build>/maps/<program>.map``. For each
program the linker map gives the exact set of objects pulled in; ``nm`` gives
the undefined symbols of every object.
"""

import argparse
import logging
import re
import subprocess
from collections import defaultdict
from pathlib import Path

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

API_GROUPS: dict[str, list[str]] = {
    "process": [
        "fork",
        "vfork",
        "execvp",
        "execv",
        "execl",
        "execlp",
        "execle",
        "execve",
        "wait",
        "waitpid",
        "kill",
        "getppid",
        "nice",
        "setsid",
    ],
    "popen/system": ["popen", "pclose", "system"],
    "shm": ["shmget", "shmat", "shmdt", "shmctl"],
    "mmap": ["mmap", "munmap"],
    "dl": ["dlopen", "dlsym", "dlclose", "dlerror"],
    "signals/timers": ["signal", "sigaction", "alarm", "setitimer", "pause"],
    "sockets": [
        "socket",
        "bind",
        "listen",
        "accept",
        "connect",
        "select",
        "send",
        "recv",
        "setsockopt",
        "getsockopt",
        "shutdown",
        "gethostbyname",
        "gethostbyaddr",
        "gethostname",
        "inet_ntoa",
        "inet_addr",
        "getaddrinfo",
    ],
    "users": ["getpwuid", "getpwnam", "getuid", "geteuid"],
    "links/fs": [
        "symlink",
        "readlink",
        "lstat",
        "realpath",
        "statfs",
        "fsync",
        "sync",
        "flock",
        "lockf",
        "fcntl",
        "mkdir",
        "chmod",
    ],
    "sysinfo": ["uname", "sysconf", "times"],
    "rand48": ["drand48", "erand48", "jrand48", "lrand48", "nrand48", "srand48"],
    "gnu-strings": ["memmem", "stpcpy", "strcasestr"],
    "tty": ["tcgetattr", "tcsetattr", "cfsetispeed", "cfsetospeed"],
    "glibc-malloc": ["malloc_stats", "mallopt"],
    "file-offsets": ["ftell", "fseek", "fseeko", "ftello", "lseek", "stat", "fstat"],
}

SYMBOL_NORMALIZATION: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"^__isoc23_"), ""),
    (re.compile(r"^__(\w+)_chk$"), r"\1"),
    (re.compile(r"^(fopen|freopen|fseeko|ftello|stat|fstat|lseek|open)64$"), r"\1"),
]

THIRD_PARTY_PREFIXES: tuple[str, ...] = (
    "XmHTML/",
    "SUMA/",
    "f2c/",
    "qhulldir/",
    "crorden/",
    "jpeg-6b/",
    "volpack/",
    "mpeg_encodedir/",
    "Audio/",
    "3DEdge/",
    "eispack/",
    "svm/",
    "avovk/",
    "ptaylor/",
    "coxplot/",
    "gifti/",
    "nifti/",
    "pkundu/",
    "faces/",
    "poems/",
    "python_scripts/",
    "R_scripts/",
    "scripts_install/",
    "other_builds/",
)

COMPILER_ARTIFACTS: frozenset[str] = frozenset({"stpcpy"})


class InventoryConfig(BaseModel):
    """Inventory input and output locations."""

    build_dir: Path
    source_dir: Path
    output_json: Path
    output_markdown: Path | None = None
    missing_symbols: Path | None = Field(
        default=None,
        description="File with one symbol per line that is unresolved on the Windows toolchain.",
    )


class Inventory(BaseModel):
    """Inventory result."""

    programs: dict[str, dict[str, list[str]]]
    objects: dict[str, list[str]]
    callsites: dict[str, list[str]]
    groups: dict[str, list[str]]


def _symbol_to_group() -> dict[str, str]:
    """Build the reverse mapping from API symbol to its group.

    Returns:
        Mapping from symbol name to group name.
    """
    return {sym: group for group, syms in API_GROUPS.items() for sym in syms}


def _normalize(symbol: str) -> str:
    """Normalize a glibc-specific symbol name to the POSIX name.

    Args:
        symbol: Raw symbol name from ``nm``.

    Returns:
        Normalized symbol name.
    """
    for pattern, replacement in SYMBOL_NORMALIZATION:
        symbol = pattern.sub(replacement, symbol)
    return symbol


def _undefined_symbols(path: Path) -> dict[str, set[str]]:
    """Return undefined symbols of every object in an object file or archive.

    Args:
        path: Object file or static archive.

    Returns:
        Mapping from object (archive member) name to normalized undefined symbols.

    Raises:
        subprocess.CalledProcessError: If ``nm`` fails.
    """
    result = subprocess.run(
        ["nm", "-A", "-u", "--format=posix", str(path)],
        capture_output=True,
        text=True,
        check=True,
    )
    symbols: dict[str, set[str]] = defaultdict(set)
    for line in result.stdout.splitlines():
        head, _, rest = line.rpartition(": ")
        parts = rest.split()
        if len(parts) < 2 or parts[1] != "U":
            continue
        member = re.match(r".*\[(.+)\]$", head)
        name = member.group(1) if member else Path(head).name
        symbols[name].add(_normalize(parts[0]))
    return symbols


def _source_name(object_name: str) -> str:
    """Convert an object name to the source file name it was compiled from.

    Args:
        object_name: Object name such as ``foo.c.o``.

    Returns:
        Source file name such as ``foo.c``.
    """
    return object_name.removesuffix(".o")


def _program_objects(
    map_file: Path, build_dir: Path, archives: dict[str, dict[str, set[str]]]
) -> list[tuple[str, set[str]]]:
    """Collect the objects linked into one program and their undefined symbols.

    Args:
        map_file: Linker map of the program.
        build_dir: Root of the Linux build tree.
        archives: Undefined symbols per archive and member.

    Returns:
        List of (object label, undefined symbols) pairs.
    """
    text = map_file.read_text(errors="replace")
    head, _, tail = text.partition("Linker script and memory map")
    objects: list[tuple[str, set[str]]] = []
    for match in re.finditer(r"^(\S+\.a)\((\S+?\.o)\)", head, re.MULTILINE):
        archive = Path(match.group(1)).name
        member = match.group(2)
        objects.append((f"{archive}:{member}", archives.get(archive, {}).get(member, set())))
    for match in re.finditer(r"^LOAD (\S*CMakeFiles/\S+\.o)$", tail, re.MULTILINE):
        relative = match.group(1).split("CMakeFiles/", 1)[1]
        candidates = sorted(build_dir.rglob(f"CMakeFiles/{relative}"))
        undefined: set[str] = set()
        for candidate in candidates[:1]:
            for symbols in _undefined_symbols(candidate).values():
                undefined |= symbols
        objects.append((f"own:{Path(relative).name}", undefined))
    return objects


def _scan_programs(
    build_dir: Path, archives: dict[str, dict[str, set[str]]]
) -> dict[str, dict[str, list[str]]]:
    """Compute problematic symbols per program from linker maps.

    Args:
        build_dir: Root of the Linux build tree containing ``maps/``.
        archives: Undefined symbols per archive and member.

    Returns:
        Mapping program -> symbol -> list of source objects referencing it.
    """
    groups = _symbol_to_group()
    programs: dict[str, dict[str, list[str]]] = {}
    for map_file in sorted((build_dir / "maps").glob("*.map")):
        hits: dict[str, set[str]] = defaultdict(set)
        for label, undefined in _program_objects(map_file, build_dir, archives):
            for symbol in undefined:
                if symbol in groups:
                    hits[symbol].add(_source_name(label))
        programs[map_file.stem] = {sym: sorted(objs) for sym, objs in sorted(hits.items())}
        logger.debug("Scanned %s: %d symbols", map_file.stem, len(hits))
    return programs


def scan_callsites(source_dir: Path) -> dict[str, list[str]]:
    """Find textual call sites of inventoried APIs in first-party C sources.

    Args:
        source_dir: Upstream ``src`` directory.

    Returns:
        Mapping symbol -> list of ``file:line`` locations.
    """
    names = "|".join(sorted(_symbol_to_group(), key=len, reverse=True))
    call = re.compile(rf"(?<![\w.>])({names})\s*\(")
    declaration = re.compile(
        r"\b(int|void|char|pid_t|FILE|static|extern|unsigned|long|double|float)\s*\**$"
    )
    noise = re.compile(r"/\*.*?\*/|//[^\n]*|\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*'", re.DOTALL)
    callsites: dict[str, list[str]] = defaultdict(list)
    for path in sorted(source_dir.rglob("*.c")):
        relative = path.relative_to(source_dir).as_posix()
        if relative.startswith(THIRD_PARTY_PREFIXES):
            continue
        code = noise.sub(
            lambda m: re.sub(r"[^\n]", " ", m.group(0)), path.read_text(errors="replace")
        )
        for number, line in enumerate(code.splitlines(), 1):
            for match in call.finditer(line):
                if declaration.search(line[: match.start()].rstrip()):
                    continue
                callsites[match.group(1)].append(f"{relative}:{number}")
    return dict(callsites)


def build_inventory(config: InventoryConfig) -> Inventory:
    """Build the full inventory.

    Args:
        config: Input and output locations.

    Returns:
        Computed inventory.
    """
    archives = {path.name: _undefined_symbols(path) for path in config.build_dir.rglob("*.a")}
    logger.info("Read %d archives", len(archives))
    groups = _symbol_to_group()
    objects = {
        f"{archive}:{_source_name(member)}": sorted(s for s in undefined if s in groups)
        for archive, members in archives.items()
        for member, undefined in members.items()
        if any(s in groups for s in undefined)
    }
    programs = _scan_programs(config.build_dir, archives)
    logger.info("Scanned %d programs", len(programs))
    callsites = scan_callsites(config.source_dir)
    return Inventory(programs=programs, objects=objects, callsites=callsites, groups=API_GROUPS)


def _render_api_table(inventory: Inventory, missing: set[str]) -> list[str]:
    """Render the per-API table.

    Args:
        inventory: Computed inventory.
        missing: Symbols unresolved on the Windows toolchain.

    Returns:
        Markdown lines.
    """
    lines = [
        "| Group | API | Missing in UCRT64 | Textual call sites "
        "| Objects referencing it (link-level) | Programs linking it |",
        "|---|---|---|---|---|---|",
    ]
    for group, symbols in inventory.groups.items():
        for symbol in symbols:
            if symbol in COMPILER_ARTIFACTS:
                continue
            programs = [p for p, hits in inventory.programs.items() if symbol in hits]
            calls = len(inventory.callsites.get(symbol, []))
            if not programs and not calls:
                continue
            objects = sorted(
                {o for hits in inventory.programs.values() for o in hits.get(symbol, [])}
            )
            shown = ", ".join(f"`{o}`" for o in objects[:8])
            if len(objects) > 8:
                shown += f" (+{len(objects) - 8})"
            if symbol in missing:
                status = "yes"
            elif group == "sockets":
                status = "ws2_32 only"
            else:
                status = "no"
            lines.append(
                f"| {group} | `{symbol}` | {status} | {calls} | {shown or '—'} | {len(programs)} |"
            )
    return lines


def render_markdown(inventory: Inventory, missing: set[str]) -> str:
    """Render the inventory tables as Markdown.

    Args:
        inventory: Computed inventory.
        missing: Symbols unresolved on the Windows toolchain.

    Returns:
        Markdown text.
    """
    groups = _symbol_to_group()
    lines = ["### Per-API link-level inventory", "", *_render_api_table(inventory, missing), ""]
    lines += [
        "### Programs whose own sources use problematic APIs",
        "",
        "| Program | APIs (own objects only) |",
        "|---|---|",
    ]
    for program, hits in sorted(inventory.programs.items()):
        own = sorted(
            symbol
            for symbol, objects in hits.items()
            if symbol not in COMPILER_ARTIFACTS
            and symbol != "signal"
            and groups[symbol] != "file-offsets"
            and any(o.startswith("own:") for o in objects)
        )
        if own:
            lines.append(f"| {program} | {', '.join(f'`{s}`' for s in own)} |")
    clean = sorted(
        program
        for program, hits in inventory.programs.items()
        if not any(groups[s] != "file-offsets" and s not in COMPILER_ARTIFACTS for s in hits)
    )
    lines += ["", "### Programs without problematic APIs", "", ", ".join(f"`{p}`" for p in clean)]
    return "\n".join(lines) + "\n"


def _parse_args() -> InventoryConfig:
    """Parse command line arguments.

    Returns:
        Inventory configuration.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-dir", type=Path, required=True)
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-markdown", type=Path)
    parser.add_argument("--missing-symbols", type=Path)
    args = parser.parse_args()
    return InventoryConfig(**vars(args))


def main() -> None:
    """Run the inventory from the command line."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    config = _parse_args()
    inventory = build_inventory(config)
    config.output_json.write_text(inventory.model_dump_json(indent=1))
    logger.info("Wrote %s", config.output_json)
    if config.output_markdown is not None:
        missing: set[str] = set()
        if config.missing_symbols is not None:
            missing = set(config.missing_symbols.read_text().split())
        config.output_markdown.write_text(render_markdown(inventory, missing))
        logger.info("Wrote %s", config.output_markdown)


if __name__ == "__main__":
    main()
