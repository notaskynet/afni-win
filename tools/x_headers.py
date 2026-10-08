"""Download the X11/Motif/OpenGL headers that compile SUMA without X.

Reads ``manifests/x-headers.txt`` (Ubuntu ``.deb`` URLs with SHA-512), checks
every download, and extracts ``usr/include/{X11,Xm,GL}`` into the output
directory, which is passed to the build as ``AFNI_WIN_X_HEADERS``. The GLw
headers are left out: SUMA compiles its own copy (``src/SUMA/GLw_local``).
The ``.deb`` data members are zstd-compressed; the ``zstd`` program unpacks
them (it is part of every MSYS2 installation).
"""

import argparse
import hashlib
import io
import logging
import shutil
import subprocess
import tarfile
import urllib.request
from pathlib import Path

from pydantic import BaseModel

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MANIFEST = REPO_ROOT / "manifests" / "x-headers.txt"
INCLUDE_DIRS = ("X11", "Xm", "GL")
EXCLUDED_PREFIX = "GL/GLw"


class HeadersConfig(BaseModel):
    """Inputs of the header download."""

    manifest: Path = DEFAULT_MANIFEST
    output_dir: Path
    cache_dir: Path | None = None


class Package(BaseModel):
    """One package of the manifest."""

    url: str
    sha512: str


def read_manifest(path: Path) -> list[Package]:
    """Read the package list.

    Args:
        path: Manifest file with ``<url> <sha512>`` lines; ``#`` starts a comment.

    Returns:
        Packages in file order.

    Raises:
        ValueError: If a line does not have exactly two fields.
    """
    packages: list[Package] = []
    for line in path.read_text().splitlines():
        fields = line.split("#", 1)[0].split()
        if not fields:
            continue
        if len(fields) != 2:
            raise ValueError(f"{path}: expected '<url> <sha512>': {line}")
        packages.append(Package(url=fields[0], sha512=fields[1].lower()))
    return packages


def ar_members(data: bytes) -> dict[str, bytes]:
    """Split a Unix ``ar`` archive (the container of a ``.deb``).

    Args:
        data: Archive bytes.

    Returns:
        Member contents by name.

    Raises:
        ValueError: If the data is not an ``ar`` archive.
    """
    if not data.startswith(b"!<arch>\n"):
        raise ValueError("not an ar archive")
    members: dict[str, bytes] = {}
    offset = 8
    while offset + 60 <= len(data):
        header = data[offset : offset + 60]
        name = header[:16].decode().strip().rstrip("/")
        size = int(header[48:58].decode().strip())
        start = offset + 60
        members[name] = data[start : start + size]
        offset = start + size + (size % 2)
    return members


def _download(package: Package, cache_dir: Path | None) -> bytes:
    """Fetch a package (from the cache when present) and check its hash.

    Args:
        package: Package to fetch.
        cache_dir: Directory for downloaded files, or None.

    Returns:
        Package bytes.

    Raises:
        ValueError: If the SHA-512 does not match.
    """
    cached = cache_dir / package.url.rsplit("/", 1)[-1] if cache_dir else None
    if cached is not None and cached.exists():
        data = cached.read_bytes()
    else:
        logger.info("Downloading %s", package.url)
        with urllib.request.urlopen(package.url, timeout=120) as response:
            data = response.read()
    digest = hashlib.sha512(data).hexdigest()
    if digest != package.sha512:
        raise ValueError(f"{package.url}: sha512 {digest} does not match the manifest")
    if cached is not None and not cached.exists():
        cached.parent.mkdir(parents=True, exist_ok=True)
        cached.write_bytes(data)
    return data


def _data_tar(deb: bytes) -> tarfile.TarFile:
    """Open the data member of a ``.deb``.

    Args:
        deb: Package bytes.

    Returns:
        Tar archive of the package files.

    Raises:
        ValueError: If the package has no supported data member.
    """
    members = ar_members(deb)
    if "data.tar.zst" in members:
        tar = subprocess.run(
            ["zstd", "-d", "-c"], input=members["data.tar.zst"], capture_output=True, check=True
        ).stdout
        return tarfile.open(fileobj=io.BytesIO(tar))
    for name in ("data.tar.xz", "data.tar.gz"):
        if name in members:
            return tarfile.open(fileobj=io.BytesIO(members[name]))
    raise ValueError(f"no data member in package: {sorted(members)}")


def wanted(path: str) -> str | None:
    """Map a package path to its place in the output directory.

    Args:
        path: Member name inside the data archive (``./usr/include/...``).

    Returns:
        Path relative to the output directory, or None to skip the member.
    """
    relative = path.removeprefix("./").removeprefix("usr/include/")
    if relative == path.removeprefix("./"):
        return None
    if relative.split("/", 1)[0] not in INCLUDE_DIRS or relative.startswith(EXCLUDED_PREFIX):
        return None
    return relative


def extract(config: HeadersConfig) -> int:
    """Download all packages and extract their headers.

    Args:
        config: Manifest, output and cache directories.

    Returns:
        Number of header files written.
    """
    if config.output_dir.exists():
        shutil.rmtree(config.output_dir)
    count = 0
    for package in read_manifest(config.manifest):
        with _data_tar(_download(package, config.cache_dir)) as tar:
            for member in tar.getmembers():
                target = wanted(member.name)
                if target is None or not member.isfile():
                    continue
                source = tar.extractfile(member)
                if source is None:
                    continue
                destination = config.output_dir / target
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(source.read())
                count += 1
    return count


def main() -> None:
    """Command line entry point."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--cache-dir", type=Path)
    config = HeadersConfig(**vars(parser.parse_args()))
    count = extract(config)
    logger.info("Wrote %d headers to %s", count, config.output_dir)


if __name__ == "__main__":
    main()
