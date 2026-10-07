"""Compare the outputs of the smoke scenario between two platforms.

Datasets are compared by value: AFNI ``.HEAD``/``.BRIK`` pairs and NIfTI-1
files (optionally gzipped). Header attributes that differ on every run
(identifiers, dates, history) are ignored; everything else must match.
Program logs are compared after removing paths, identifiers and dates.
There is no tolerance: any difference is reported with its magnitude and
makes the comparison fail.
"""

import argparse
import gzip
import logging
import re
import struct
import sys
from pathlib import Path

import numpy as np
from pydantic import BaseModel

logger = logging.getLogger(__name__)

VOLATILE_ATTRIBUTES: frozenset[str] = frozenset({"IDCODE_STRING", "IDCODE_DATE", "HISTORY_NOTE"})
BRICK_DTYPES: dict[int, str] = {0: "u1", 1: "i2", 3: "f4", 5: "c8"}
NIFTI_DTYPES: dict[int, str] = {
    2: "u1",
    4: "i2",
    8: "i4",
    16: "f4",
    32: "c8",
    64: "f8",
    256: "i1",
    512: "u2",
    768: "u4",
}
INPUT_NAMES: frozenset[str] = frozenset(
    {"rnd+orig.HEAD", "rnd+orig.BRIK", "rnd.nii.gz", "rnd_short.nii"}
)
LOG_NORMALIZATION: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\r\n"), "\n"),
    (re.compile(r"(?:[A-Za-z]:)?[/\\][^\s'\"]*[/\\]"), "<DIR>/"),
    (re.compile(r"XYZ_[A-Za-z0-9_-]{22}"), "<IDCODE>"),
    (re.compile(r"3dcalc_<IDCODE>"), "3dcalc_<TMP>"),
    (re.compile(r"[A-Z][a-z]{2} [A-Z][a-z]{2} [ 0-9]\d \d\d:\d\d:\d\d \d{4}"), "<DATE>"),
    (re.compile(r"\([A-Z][a-z]{2} [ 0-9]\d \d{4}\)"), "(<DATE>)"),
    (re.compile(r"compile date = .*"), "compile date = <DATE>"),
    (re.compile(r"\[[^\]@\s]+@[^\]:\s]+:"), "[<USER>@<HOST>:"),
    (re.compile(r"\{AFNI_[^}]*\}"), "{<VERSION>}"),
]


class Comparison(BaseModel):
    """Result for one compared file."""

    name: str
    kind: str
    identical: bool
    values: int = 0
    different: int = 0
    max_abs_diff: float = 0.0
    max_rel_diff: float = 0.0
    notes: list[str] = []


class CompareConfig(BaseModel):
    """Inputs and output of the comparison."""

    reference: Path
    candidate: Path
    report: Path


def _parse_head(path: Path) -> dict[str, str]:
    """Parse an AFNI ``.HEAD`` file into raw attribute values.

    Args:
        path: ``.HEAD`` file.

    Returns:
        Mapping from attribute name to its value text.
    """
    text = path.read_bytes().decode("latin-1")
    pattern = re.compile(
        r"type\s*=\s*\S+\s*\nname\s*=\s*(\S+)\s*\ncount\s*=\s*\d+\s*\n(.*?)(?=\n\s*type\s*=|\Z)",
        re.DOTALL,
    )
    return {m.group(1): m.group(2).strip() for m in pattern.finditer(text)}


def _value_difference(name: str, kind: str, ref: np.ndarray, cand: np.ndarray) -> Comparison:
    """Compare two arrays element by element without tolerance.

    Args:
        name: File name for the report.
        kind: File kind for the report.
        ref: Reference values.
        cand: Candidate values.

    Returns:
        Comparison result with difference statistics.
    """
    if ref.shape != cand.shape or ref.dtype != cand.dtype:
        return Comparison(
            name=name,
            kind=kind,
            identical=False,
            notes=[f"shape/type {ref.shape} {ref.dtype} vs {cand.shape} {cand.dtype}"],
        )
    same = ref.tobytes() == cand.tobytes()
    if same:
        return Comparison(name=name, kind=kind, identical=True, values=int(ref.size))
    r = ref.astype(np.complex128 if np.iscomplexobj(ref) else np.float64)
    c = cand.astype(r.dtype)
    diff = np.abs(r - c)
    scale = np.maximum(np.abs(r), np.abs(c))
    rel = np.divide(diff, scale, out=np.zeros_like(diff, dtype=np.float64), where=scale > 0)
    return Comparison(
        name=name,
        kind=kind,
        identical=False,
        values=int(ref.size),
        different=int(np.count_nonzero(ref != cand)),
        max_abs_diff=float(np.nanmax(diff)),
        max_rel_diff=float(np.nanmax(rel)),
    )


def _read_brik(head: dict[str, str], brik: Path) -> np.ndarray:
    """Read all sub-bricks of an uncompressed ``.BRIK`` file.

    Args:
        head: Parsed attributes of the matching ``.HEAD``.
        brik: ``.BRIK`` file.

    Returns:
        Array of shape (nvals, nz, ny, nx); all sub-bricks must share one type.

    Raises:
        ValueError: If sub-bricks have different types.
    """
    dims = [int(v) for v in head["DATASET_DIMENSIONS"].split()[:3]]
    types = {int(v) for v in head["BRICK_TYPES"].split()}
    if len(types) != 1:
        raise ValueError(f"mixed brick types {types}")
    nvals = len(head["BRICK_TYPES"].split())
    order = "<" if "LSB" in head.get("BYTEORDER_STRING", "LSB") else ">"
    dtype = np.dtype(order + BRICK_DTYPES[types.pop()])
    data = np.frombuffer(brik.read_bytes(), dtype=dtype)
    return data.reshape(nvals, dims[2], dims[1], dims[0])


def _compare_afni(name: str, ref_dir: Path, cand_dir: Path) -> Comparison:
    """Compare an AFNI dataset (``.HEAD`` and ``.BRIK``).

    Args:
        name: ``.HEAD`` file name.
        ref_dir: Reference directory.
        cand_dir: Candidate directory.

    Returns:
        Comparison result.
    """
    ref_head = _parse_head(ref_dir / name)
    cand_head = _parse_head(cand_dir / name)
    notes = [
        f"attribute {key} differs"
        for key in sorted(set(ref_head) | set(cand_head))
        if key not in VOLATILE_ATTRIBUTES and ref_head.get(key) != cand_head.get(key)
    ]
    brik = name.removesuffix(".HEAD") + ".BRIK"
    result = _value_difference(
        name.removesuffix(".HEAD"),
        "AFNI",
        _read_brik(ref_head, ref_dir / brik),
        _read_brik(cand_head, cand_dir / brik),
    )
    result.notes += notes
    result.identical = result.identical and not notes
    return result


def _read_nifti(path: Path) -> tuple[bytes, np.ndarray]:
    """Read a NIfTI-1 file.

    Args:
        path: ``.nii`` or ``.nii.gz`` file.

    Returns:
        The 348-byte header and the voxel data as a flat array.

    Raises:
        ValueError: If the file is not NIfTI-1.
    """
    raw = path.read_bytes()
    if path.name.endswith(".gz"):
        raw = gzip.decompress(raw)
    if struct.unpack("<i", raw[:4])[0] != 348:
        raise ValueError(f"{path.name} is not a little-endian NIfTI-1 file")
    header = raw[:348]
    dims = struct.unpack("<8h", header[40:56])
    datatype = struct.unpack("<h", header[70:72])[0]
    offset = int(struct.unpack("<f", header[108:112])[0])
    count = int(np.prod(dims[1 : dims[0] + 1]))
    data = np.frombuffer(
        raw, dtype=np.dtype("<" + NIFTI_DTYPES[datatype]), count=count, offset=offset
    )
    return header, data


def _without_vox_offset(header: bytes) -> bytes:
    """Blank out ``vox_offset``, which depends on the size of the AFNI extension.

    Args:
        header: 348-byte NIfTI-1 header.

    Returns:
        Header with bytes 108-111 zeroed.
    """
    return header[:108] + bytes(4) + header[112:]


def _compare_nifti(name: str, ref_dir: Path, cand_dir: Path) -> Comparison:
    """Compare a NIfTI-1 dataset; the AFNI header extension and its size are not compared.

    Args:
        name: File name.
        ref_dir: Reference directory.
        cand_dir: Candidate directory.

    Returns:
        Comparison result.
    """
    ref_header, ref_data = _read_nifti(ref_dir / name)
    cand_header, cand_data = _read_nifti(cand_dir / name)
    result = _value_difference(name, "NIfTI", ref_data, cand_data)
    if _without_vox_offset(ref_header) != _without_vox_offset(cand_header):
        result.notes.append("348-byte header differs")
        result.identical = False
    if ref_header[108:112] != cand_header[108:112]:
        ref_offset = struct.unpack("<f", ref_header[108:112])[0]
        cand_offset = struct.unpack("<f", cand_header[108:112])[0]
        result.notes.append(
            f"extension size differs (vox_offset {ref_offset:g} vs {cand_offset:g})"
        )
    return result


def _normalize_log(raw: bytes) -> str:
    """Remove run-specific parts of a program log.

    Args:
        raw: Log contents.

    Returns:
        Normalized text.
    """
    text = raw.decode("utf-8", errors="replace")
    for pattern, replacement in LOG_NORMALIZATION:
        text = pattern.sub(replacement, text)
    return text


def _compare_log(name: str, ref_dir: Path, cand_dir: Path) -> Comparison:
    """Compare one normalized log file.

    Args:
        name: Path relative to the output directory.
        ref_dir: Reference directory.
        cand_dir: Candidate directory.

    Returns:
        Comparison result; notes hold the first differing lines.
    """
    ref = _normalize_log((ref_dir / name).read_bytes()).splitlines()
    cand = _normalize_log((cand_dir / name).read_bytes()).splitlines()
    if ref == cand:
        return Comparison(name=name, kind="log", identical=True, values=len(ref))
    notes = [
        f"line {i + 1}: {a!r} != {b!r}"
        for i, (a, b) in enumerate(zip(ref, cand, strict=False))
        if a != b
    ][:3]
    if len(ref) != len(cand):
        notes.append(f"{len(ref)} vs {len(cand)} lines")
    return Comparison(name=name, kind="log", identical=False, values=len(ref), notes=notes)


def compare(config: CompareConfig) -> list[Comparison]:
    """Compare every output of the reference directory with the candidate.

    Args:
        config: Directories and report path.

    Returns:
        One result per compared file.
    """
    results: list[Comparison] = []
    ref_dir, cand_dir = config.reference, config.candidate
    for path in sorted(ref_dir.iterdir()):
        name = path.name
        if name in INPUT_NAMES or not path.is_file():
            continue
        if not (cand_dir / name).exists() and not name.endswith(".BRIK"):
            results.append(Comparison(name=name, kind="missing", identical=False))
            continue
        if name.endswith(".HEAD"):
            results.append(_compare_afni(name, ref_dir, cand_dir))
        elif name.endswith((".nii", ".nii.gz")):
            results.append(_compare_nifti(name, ref_dir, cand_dir))
    for path in sorted((ref_dir / "logs").iterdir()):
        name = f"logs/{path.name}"
        if not (cand_dir / name).exists():
            results.append(Comparison(name=name, kind="missing", identical=False))
            continue
        results.append(_compare_log(name, ref_dir, cand_dir))
    return results


def render_report(results: list[Comparison]) -> str:
    """Render the comparison as Markdown.

    Args:
        results: Comparison results.

    Returns:
        Markdown text.
    """
    failed = [r for r in results if not r.identical]
    lines = [
        "## Linux vs Windows comparison",
        "",
        f"{len(results) - len(failed)} of {len(results)} files identical.",
        "",
        "| File | Kind | Identical | Values | Different | Max abs diff | Max rel diff | Notes |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in results:
        lines.append(
            f"| {r.name} | {r.kind} | {'yes' if r.identical else '**no**'} | {r.values} "
            f"| {r.different} | {r.max_abs_diff:.3g} | {r.max_rel_diff:.3g} "
            f"| {'; '.join(r.notes).replace('|', '/')} |"
        )
    return "\n".join(lines) + "\n"


def _parse_args() -> CompareConfig:
    """Parse command line arguments.

    Returns:
        Comparison configuration.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    return CompareConfig(**vars(parser.parse_args()))


def main() -> None:
    """Run the comparison and exit non-zero if anything differs."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    config = _parse_args()
    results = compare(config)
    config.report.write_text(render_report(results))
    failed = [r.name for r in results if not r.identical]
    logger.info("%d compared, %d different: %s", len(results), len(failed), failed)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
