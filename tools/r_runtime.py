"""Install the R used by the AFNI R programs (docs/DECISIONS.md D39).

Reads ``manifests/r-runtime.txt``: downloads the CRAN R for Windows installer
(first URL that answers; checked against the pinned sha256), installs it
silently into the target directory, installs the listed CRAN packages as
Windows binaries from the pinned repository snapshot into its library, adds
the afni-win site profile (``runtime/r/Rprofile.site``) and writes
``r-runtime.json`` with the versions. Runs on Windows.

With ``--linux-codename`` it installs only the packages, into the library of
the ``Rscript`` on PATH, from the Linux binaries of the same snapshot; the
Linux reference of the acceptance pipeline uses that (D40). The R version
must be the one of the manifest.
"""

import argparse
import hashlib
import json
import logging
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

from pydantic import BaseModel

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MANIFEST = REPO_ROOT / "manifests" / "r-runtime.txt"
SITE_PROFILE = REPO_ROOT / "runtime" / "r" / "Rprofile.site"


class RManifest(BaseModel):
    """Contents of ``manifests/r-runtime.txt``."""

    version: str
    installers: list[str]
    sha256: str
    repository: str
    packages: list[str]


class RConfig(BaseModel):
    """Inputs of the R installation."""

    manifest: Path = DEFAULT_MANIFEST
    r_home: Path
    download_dir: Path


def read_manifest(path: Path) -> RManifest:
    """Parse the R runtime manifest.

    Args:
        path: Manifest with ``<key> <value...>`` lines; ``#`` starts a comment.

    Returns:
        Parsed manifest.

    Raises:
        ValueError: If a key is unknown or a required key is missing.
    """
    values: dict[str, list[str]] = {}
    for line in path.read_text().splitlines():
        fields = line.split("#", 1)[0].split()
        if not fields:
            continue
        key, rest = fields[0], fields[1:]
        if key not in ("version", "installer", "sha256", "repository", "packages"):
            raise ValueError(f"{path}: unknown key '{key}'")
        values.setdefault(key, []).extend(rest)
    missing = [k for k in ("version", "installer", "sha256", "repository") if k not in values]
    if missing:
        raise ValueError(f"{path}: missing {missing}")
    return RManifest(
        version=values["version"][0],
        installers=values["installer"],
        sha256=values["sha256"][0].lower(),
        repository=values["repository"][0],
        packages=values.get("packages", []),
    )


def r_vector(values: list[str]) -> str:
    """Write an R character vector.

    Args:
        values: Strings without quotes or backslashes.

    Returns:
        R expression ``c("a", "b")``.
    """
    return "c(" + ", ".join(f'"{v}"' for v in values) + ")"


def linux_repository(repository: str, codename: str) -> str:
    """Address of the Linux binaries of a Posit Package Manager snapshot.

    Args:
        repository: Snapshot URL such as ``https://host/cran/2026-10-01``.
        codename: Distribution codename such as ``noble``.

    Returns:
        URL such as ``https://host/cran/__linux__/noble/2026-10-01``.

    Raises:
        ValueError: If the URL has no ``/cran/`` part.
    """
    head, sep, snapshot = repository.partition("/cran/")
    if not sep:
        raise ValueError(f"not a Package Manager CRAN snapshot: {repository}")
    return f"{head}/cran/__linux__/{codename}/{snapshot}"


def install_script(
    repository: str, packages: list[str], library: str | None, binary: bool = True
) -> str:
    """Write the R code that installs the packages.

    Args:
        repository: CRAN-like repository URL (snapshot).
        packages: Package names.
        library: Library directory (forward slashes), or None for the first
            library of ``.libPaths()``.
        binary: Ask for Windows binaries (``type = "binary"``). Linux
            binaries of Package Manager are served as ``type = "source"`` to
            an R that sends its version in the HTTP user agent.

    Returns:
        R expression for ``Rscript -e``; it fails if any package is missing
        afterwards.
    """
    lib = f'"{library}"' if library is not None else ".libPaths()[1]"
    if binary:
        prefix, kind = "", ', type = "binary"'
    else:
        prefix = (
            'options(HTTPUserAgent = sprintf("R/%s R (%s)", getRversion(), '
            'paste(getRversion(), R.version["platform"], R.version["arch"], R.version["os"]))); '
        )
        kind = ""
    return (
        f"{prefix}pkgs <- {r_vector(packages)}; lib <- {lib}; "
        f'install.packages(pkgs, lib = lib, repos = "{repository}"{kind}); '
        "missing <- pkgs[!vapply(pkgs, requireNamespace, logical(1), lib.loc = lib, "
        "quietly = TRUE)]; "
        'if (length(missing)) stop("not installed: ", paste(missing, collapse = " "))'
    )


def version_query(packages: list[str]) -> str:
    """Write the R code that prints R's and the packages' versions.

    Args:
        packages: Package names.

    Returns:
        R expression printing ``<name> <version>`` lines, R first.
    """
    return (
        f"pkgs <- {r_vector(packages)}; "
        'v <- vapply(pkgs, function(p) as.character(packageVersion(p)), ""); '
        'cat(paste("R", getRversion()), paste(pkgs, v), sep = "\\n")'
    )


def _versions(rscript: str, packages: list[str]) -> dict[str, str]:
    """Ask an R installation for its versions.

    Args:
        rscript: ``Rscript`` executable.
        packages: Package names.

    Returns:
        Versions of R and of each package.
    """
    output = subprocess.run(
        [rscript, "-e", version_query(packages)], check=True, capture_output=True, text=True
    ).stdout
    versions: dict[str, str] = {}
    for line in output.splitlines():
        name, _, version = line.partition(" ")
        if version:
            versions[name] = version
    return versions


def install_linux_packages(manifest_path: Path, codename: str) -> dict[str, str]:
    """Install the manifest packages into the R on PATH (Linux reference).

    Args:
        manifest_path: R runtime manifest.
        codename: Distribution codename of the Package Manager binaries.

    Returns:
        Versions of R and of each package.

    Raises:
        ValueError: If the R on PATH is not the manifest version.
    """
    manifest = read_manifest(manifest_path)
    found = _versions("Rscript", [])["R"]
    if found != manifest.version:
        raise ValueError(f"R {found} on PATH, manifest pins {manifest.version}")
    repository = linux_repository(manifest.repository, codename)
    script = install_script(repository, manifest.packages, None, binary=False)
    subprocess.run(["Rscript", "-e", script], check=True)
    return _versions("Rscript", manifest.packages)


def _download(manifest: RManifest, directory: Path) -> Path:
    """Fetch the R installer and check its hash.

    Args:
        manifest: R runtime manifest.
        directory: Download directory.

    Returns:
        Path of the installer.

    Raises:
        ValueError: If the sha256 does not match.
        urllib.error.URLError: If no URL answers.
    """
    target = directory / manifest.installers[0].rsplit("/", 1)[-1]
    if not target.exists():
        directory.mkdir(parents=True, exist_ok=True)
        error: urllib.error.URLError | None = None
        for url in manifest.installers:
            try:
                logger.info("Downloading %s", url)
                with urllib.request.urlopen(url, timeout=300) as response:
                    target.write_bytes(response.read())
                break
            except urllib.error.URLError as exc:
                error = exc
        else:
            assert error is not None
            raise error
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    if digest != manifest.sha256:
        raise ValueError(f"{target.name}: sha256 {digest} does not match {manifest.sha256}")
    return target


def install(config: RConfig) -> dict[str, str]:
    """Install R and the packages.

    Args:
        config: Manifest, target and download directories.

    Returns:
        Installed versions (R and each package).
    """
    manifest = read_manifest(config.manifest)
    installer = _download(manifest, config.download_dir)
    subprocess.run(
        [
            str(installer),
            "/VERYSILENT",
            "/SUPPRESSMSGBOXES",
            "/NORESTART",
            "/CURRENTUSER",
            "/NOICONS",
            "/COMPONENTS=main,x64",
            f"/DIR={config.r_home}",
        ],
        check=True,
    )
    rscript = config.r_home / "bin" / "Rscript.exe"
    library = (config.r_home / "library").as_posix()
    subprocess.run(
        [str(rscript), "-e", install_script(manifest.repository, manifest.packages, library)],
        check=True,
    )
    profile = config.r_home / "etc" / "Rprofile.site"
    profile.write_text(profile.read_text() + "\n" + SITE_PROFILE.read_text())
    return _versions(str(rscript), manifest.packages)


def main() -> None:
    """Command line entry point; writes ``r-runtime.json`` into the download directory."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--r-home", type=Path)
    parser.add_argument("--download-dir", type=Path, required=True)
    parser.add_argument("--linux-codename")
    args = parser.parse_args()
    try:
        if args.linux_codename:
            versions = install_linux_packages(args.manifest, args.linux_codename)
        else:
            if args.r_home is None:
                parser.error("--r-home is required unless --linux-codename is given")
            config = RConfig(
                manifest=args.manifest, r_home=args.r_home, download_dir=args.download_dir
            )
            versions = install(config)
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        logger.error("%s", error)
        sys.exit(1)
    args.download_dir.mkdir(parents=True, exist_ok=True)
    (args.download_dir / "r-runtime.json").write_text(json.dumps(versions, indent=2))
    logger.info("R %s with %d packages", versions["R"], len(versions) - 1)


if __name__ == "__main__":
    main()
