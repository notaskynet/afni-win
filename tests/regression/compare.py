"""Compare the outputs of the regression scenario between two platforms.

Datasets (AFNI ``.HEAD``/``.BRIK[.gz]`` and NIfTI-1 ``.nii[.gz]``) are compared
by value after applying their scale factors. Text outputs (``.1D``, ``.niml``,
program stdout) are compared token by token: the text must be equal and the
numbers equal within tolerance. Exit codes must be equal and zero. stderr is
compared after normalization but only reported, because it holds timings,
thread counts and similar run-specific text.

Tolerances are fixed in ``tolerance.json`` before looking at the results; a
value is within tolerance if ``|a - b| <= atol + rtol * max(|a|, |b|)``, where
``atol = atol_scale * max|reference|`` of the whole file. A printed number
also passes if it differs by at most one unit in its last printed digit.
"""

import argparse
import fnmatch
import gzip
import json
import logging
import re
import struct
import sys
from pathlib import Path
from typing import Literal

import numpy as np
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

DEFAULT_TOLERANCE_FILE = Path(__file__).resolve().parent / "tolerance.json"
INPUTS_LIST = "inputs.txt"

Status = Literal["identical", "within", "different", "missing", "informational"]
FAILING: frozenset[str] = frozenset({"different", "missing"})

VOLATILE_ATTRIBUTE = re.compile(r"^(IDCODE_.*|HISTORY_NOTE|NOTE_DATE_\d+)$")
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
NIFTI_FLOAT_FIELDS: tuple[tuple[int, int], ...] = (
    (56, 3),
    (76, 8),
    (112, 2),
    (124, 4),
    (256, 6),
    (280, 12),
)
TEXT_SUFFIXES: tuple[str, ...] = (".1D", ".1D.txt", ".niml", ".txt", ".cmd", ".stdout")
NUMBER = re.compile(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?|[-+]?(?:nan|inf)\b", re.I)
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
    (re.compile(r"\.exe\b"), ""),
    (re.compile(r"\b(?:Linux|Windows)_cmake\b"), "<PACKAGE>"),
]


class Tolerance(BaseModel):
    """Numeric tolerance for dataset values.

    ``max_fraction_beyond`` lets that fraction of the values of a dataset lie
    beyond ``rtol``/``atol_scale`` (whole pipelines: voxels at the brain edge
    move when a registration stops at a slightly different point).
    """

    rtol: float
    atol_scale: float
    max_fraction_beyond: float = 0.0


class TextTolerance(BaseModel):
    """Numeric tolerance for numbers in text."""

    rtol: float


class Override(BaseModel):
    """Tolerance for files whose relative path matches one of ``pattern`` (``|``-separated)."""

    pattern: str
    reason: str
    tolerance: Tolerance
    text_rtol: float
    informational: bool = False
    informational_attributes: list[str] = Field(default_factory=list)


class ToleranceConfig(BaseModel):
    """All tolerances."""

    default: Tolerance
    text: TextTolerance
    overrides: list[Override] = Field(default_factory=list)

    def for_file(self, name: str) -> tuple[Tolerance, float, bool]:
        """Select the tolerance for a file.

        Args:
            name: Path relative to the output directory.

        Returns:
            Dataset tolerance, relative tolerance for text numbers, and whether
            differences are only reported.
        """
        override = self._override(name)
        if override is not None:
            return override.tolerance, override.text_rtol, override.informational
        return self.default, self.text.rtol, False

    def informational_attributes(self, name: str) -> list[str]:
        """Dataset attributes of a file whose differences are only reported.

        Args:
            name: Path relative to the output directory.

        Returns:
            Regular expressions matched against whole attribute names.
        """
        override = self._override(name)
        return override.informational_attributes if override is not None else []

    def _override(self, name: str) -> Override | None:
        """Find the first override whose pattern matches a file.

        Args:
            name: Path relative to the output directory.

        Returns:
            The override, or None.
        """
        for override in self.overrides:
            if any(fnmatch.fnmatch(name, p) for p in override.pattern.split("|")):
                return override
        return None


class Comparison(BaseModel):
    """Result for one compared file."""

    name: str
    kind: str
    status: Status
    values: int = 0
    different: int = 0
    beyond: int = 0
    max_abs_diff: float = 0.0
    max_rel_diff: float = 0.0
    notes: list[str] = Field(default_factory=list)


class CompareConfig(BaseModel):
    """Inputs and outputs of the comparison."""

    reference: Path
    candidate: Path
    report: Path
    json_report: Path | None = None
    tolerance: Path = DEFAULT_TOLERANCE_FILE


def _values(
    name: str, kind: str, ref: np.ndarray, cand: np.ndarray, tolerance: Tolerance
) -> Comparison:
    """Compare two arrays of values with a tolerance.

    Args:
        name: File name for the report.
        kind: File kind for the report.
        ref: Reference values.
        cand: Candidate values.
        tolerance: Allowed difference.

    Returns:
        Comparison result with difference statistics.
    """
    if ref.shape != cand.shape:
        return Comparison(
            name=name, kind=kind, status="different", notes=[f"shape {ref.shape} vs {cand.shape}"]
        )
    if ref.tobytes() == cand.tobytes():
        return Comparison(name=name, kind=kind, status="identical", values=int(ref.size))
    dtype = np.complex128 if np.iscomplexobj(ref) or np.iscomplexobj(cand) else np.float64
    r = ref.astype(dtype)
    c = cand.astype(dtype)
    both_nan = np.isnan(r) & np.isnan(c)
    diff = np.where(both_nan, 0.0, np.abs(r - c))
    scale = np.maximum(np.abs(r), np.abs(c))
    finite = np.abs(r[np.isfinite(r)])
    atol = tolerance.atol_scale * (float(finite.max()) if finite.size else 0.0)
    allowed = atol + tolerance.rtol * scale
    beyond = int(np.count_nonzero(~(diff <= allowed)))
    rel = np.divide(diff, scale, out=np.zeros_like(diff, dtype=np.float64), where=scale > 0)
    notes = []
    if 0 < beyond <= tolerance.max_fraction_beyond * ref.size:
        notes.append(f"{beyond / ref.size:.3%} beyond, allowed {tolerance.max_fraction_beyond:.3%}")
    return Comparison(
        name=name,
        kind=kind,
        status="within" if beyond == 0 or notes else "different",
        notes=notes,
        values=int(ref.size),
        different=int(np.count_nonzero(diff > 0)),
        beyond=beyond,
        max_abs_diff=float(np.nanmax(diff)),
        max_rel_diff=float(np.nanmax(rel)),
    )


def _merge(first: Comparison, second: Comparison) -> Comparison:
    """Combine the results of two parts of the same file (e.g. header and data).

    Args:
        first: Result that gives the name and kind.
        second: Result for the other part.

    Returns:
        Combined result.
    """
    order = ["identical", "within", "different"]
    status = max(first.status, second.status, key=order.index)
    return first.model_copy(
        update={
            "status": status,
            "values": first.values + second.values,
            "different": first.different + second.different,
            "beyond": first.beyond + second.beyond,
            "max_abs_diff": max(first.max_abs_diff, second.max_abs_diff),
            "max_rel_diff": max(first.max_rel_diff, second.max_rel_diff),
            "notes": first.notes + second.notes,
        }
    )


def _parse_head(path: Path) -> dict[str, tuple[str, str]]:
    """Parse an AFNI ``.HEAD`` file.

    Args:
        path: ``.HEAD`` file.

    Returns:
        Mapping from attribute name to (type, value text).
    """
    text = path.read_bytes().decode("latin-1")
    pattern = re.compile(
        r"type\s*=\s*(\S+)\s*\nname\s*=\s*(\S+)\s*\ncount\s*=\s*\d+\s*\n(.*?)(?=\n\s*type\s*=|\Z)",
        re.DOTALL,
    )
    return {m.group(2): (m.group(1), m.group(3).strip()) for m in pattern.finditer(text)}


def _brik_path(directory: Path, prefix: str) -> Path:
    """Locate the ``.BRIK`` file of a dataset, compressed or not.

    Args:
        directory: Directory of the dataset.
        prefix: Dataset name without ``.HEAD``.

    Returns:
        Path of the ``.BRIK`` or ``.BRIK.gz`` file.
    """
    plain = directory / f"{prefix}.BRIK"
    return plain if plain.exists() else directory / f"{prefix}.BRIK.gz"


def _read_brik(head: dict[str, tuple[str, str]], brik: Path) -> np.ndarray:
    """Read all sub-bricks and apply ``BRICK_FLOAT_FACS``.

    Args:
        head: Parsed attributes of the matching ``.HEAD``.
        brik: ``.BRIK`` or ``.BRIK.gz`` file.

    Returns:
        All values, sub-brick after sub-brick, as one flat array.
    """
    dims = [int(v) for v in head["DATASET_DIMENSIONS"][1].split()[:3]]
    types = [int(v) for v in head["BRICK_TYPES"][1].split()]
    facs = [float(v) for v in head.get("BRICK_FLOAT_FACS", ("", ""))[1].split()]
    order = "<" if "LSB" in head.get("BYTEORDER_STRING", ("", "LSB"))[1] else ">"
    raw = brik.read_bytes()
    if brik.name.endswith(".gz"):
        raw = gzip.decompress(raw)
    count = dims[0] * dims[1] * dims[2]
    parts: list[np.ndarray] = []
    offset = 0
    for index, code in enumerate(types):
        dtype = np.dtype(order + BRICK_DTYPES[code])
        part = np.frombuffer(raw, dtype=dtype, count=count, offset=offset)
        offset += count * dtype.itemsize
        fac = facs[index] if index < len(facs) else 0.0
        parts.append(part.astype(np.complex128 if code == 5 else np.float64) * (fac or 1.0))
    return np.concatenate(parts)


def _numbers(text: str) -> np.ndarray:
    """Parse whitespace-separated numbers.

    Args:
        text: Attribute value.

    Returns:
        The numbers.
    """
    return np.array([float(v) for v in text.split()], dtype=np.float64)


def _compare_afni(
    name: str,
    ref_dir: Path,
    cand_dir: Path,
    tolerance: Tolerance,
    informational_attributes: list[str] | None = None,
) -> Comparison:
    """Compare an AFNI dataset: attributes and values.

    Args:
        name: ``.HEAD`` file name.
        ref_dir: Reference directory.
        cand_dir: Candidate directory.
        tolerance: Allowed difference.
        informational_attributes: Attribute name patterns whose differences
            are only noted.

    Returns:
        Comparison result.
    """
    prefix = name.removesuffix(".HEAD")
    ref_head = _parse_head(ref_dir / name)
    cand_head = _parse_head(cand_dir / name)
    notes: list[str] = []
    float_ref: list[np.ndarray] = []
    float_cand: list[np.ndarray] = []
    reported = [re.compile(p) for p in informational_attributes or []]
    informational: list[str] = []
    for key in sorted(set(ref_head) | set(cand_head)):
        if VOLATILE_ATTRIBUTE.match(key):
            continue
        if any(p.fullmatch(key) for p in reported):
            if ref_head.get(key) != cand_head.get(key):
                informational.append(key)
            continue
        ref_attr = ref_head.get(key)
        cand_attr = cand_head.get(key)
        if ref_attr is None or cand_attr is None:
            notes.append(f"attribute {key} only on one side")
        elif ref_attr[0] == "float-attribute" and cand_attr[0] == "float-attribute":
            r, c = _numbers(ref_attr[1]), _numbers(cand_attr[1])
            if r.shape != c.shape:
                notes.append(f"attribute {key} has a different length")
            else:
                float_ref.append(r)
                float_cand.append(c)
        elif ref_attr != cand_attr:
            notes.append(f"attribute {key} differs")
    data = _values(
        prefix,
        "AFNI",
        _read_brik(ref_head, _brik_path(ref_dir, prefix)),
        _read_brik(cand_head, _brik_path(cand_dir, prefix)),
        tolerance,
    )
    if float_ref:
        attributes = _values(
            prefix, "AFNI", np.concatenate(float_ref), np.concatenate(float_cand), tolerance
        )
        if attributes.status == "different":
            attributes.notes.append("float attributes beyond tolerance")
        data = _merge(data, attributes.model_copy(update={"values": 0}))
    if informational:
        notes_text = f"attributes differ (reported only): {' '.join(informational)}"
        data = data.model_copy(update={"notes": [*data.notes, notes_text]})
    if notes:
        data = data.model_copy(update={"status": "different", "notes": data.notes + notes})
    return data


def _read_nifti(path: Path) -> tuple[bytes, np.ndarray]:
    """Read a NIfTI-1 file and apply ``scl_slope``/``scl_inter``.

    Args:
        path: ``.nii`` or ``.nii.gz`` file.

    Returns:
        The 348-byte header and the scaled voxel values as a flat array.

    Raises:
        ValueError: If the file is not little-endian NIfTI-1.
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
    slope, inter = struct.unpack("<2f", header[112:120])
    count = int(np.prod(dims[1 : dims[0] + 1]))
    dtype = np.dtype("<" + NIFTI_DTYPES[datatype])
    data = np.frombuffer(raw, dtype=dtype, count=count, offset=offset)
    values = data.astype(np.complex128 if datatype == 32 else np.float64)
    if slope not in (0.0, 1.0) or inter != 0.0:
        values = values * (slope or 1.0) + inter
    return header, values


def _header_parts(header: bytes) -> tuple[bytes, np.ndarray]:
    """Split a NIfTI-1 header into exact bytes and float fields.

    ``vox_offset`` (bytes 108-111) is left out: it depends on the size of the
    AFNI header extension (history, paths).

    Args:
        header: 348-byte header.

    Returns:
        Bytes compared exactly and float fields compared with tolerance.
    """
    exact = bytearray(header)
    floats: list[float] = []
    for start, n in NIFTI_FLOAT_FIELDS:
        floats.extend(struct.unpack(f"<{n}f", header[start : start + 4 * n]))
        exact[start : start + 4 * n] = bytes(4 * n)
    exact[108:112] = bytes(4)
    return bytes(exact), np.array(floats, dtype=np.float64)


def _compare_nifti(name: str, ref_dir: Path, cand_dir: Path, tolerance: Tolerance) -> Comparison:
    """Compare a NIfTI-1 dataset; the AFNI header extension is not compared.

    Args:
        name: File name.
        ref_dir: Reference directory.
        cand_dir: Candidate directory.
        tolerance: Allowed difference.

    Returns:
        Comparison result.
    """
    ref_header, ref_data = _read_nifti(ref_dir / name)
    cand_header, cand_data = _read_nifti(cand_dir / name)
    result = _values(name, "NIfTI", ref_data, cand_data, tolerance)
    ref_exact, ref_floats = _header_parts(ref_header)
    cand_exact, cand_floats = _header_parts(cand_header)
    if ref_exact != cand_exact:
        result = result.model_copy(
            update={"status": "different", "notes": [*result.notes, "header fields differ"]}
        )
    floats = _values(name, "NIfTI", ref_floats, cand_floats, tolerance)
    return _merge(result, floats.model_copy(update={"values": 0}))


def _normalize(raw: bytes) -> str:
    """Remove run-specific parts of program output.

    Args:
        raw: File contents.

    Returns:
        Normalized text.
    """
    text = raw.decode("utf-8", errors="replace")
    for pattern, replacement in LOG_NORMALIZATION:
        text = pattern.sub(replacement, text)
    return text


def _words(line: str) -> str:
    """Reduce a line to its words, with numbers and runs of blanks replaced.

    Args:
        line: Text line.

    Returns:
        The line with every number as ``#`` and single spaces.
    """
    return " ".join(NUMBER.sub("#", line).split())


def _last_digit_unit(token: str) -> float:
    """Value of one unit in the last printed digit of a number.

    Args:
        token: Number as printed.

    Returns:
        The unit, e.g. 0.01 for ``"3.14"`` or 100 for ``"1.2e3"``.
    """
    mantissa, _, exponent = token.lower().partition("e")
    decimals = len(mantissa.split(".", 1)[1]) if "." in mantissa else 0
    return 10.0 ** (int(exponent or 0) - decimals)


def _numbers_close(a: str, b: str, rtol: float, atol: float) -> tuple[bool, float, float]:
    """Compare two printed numbers.

    Args:
        a: Reference token.
        b: Candidate token.
        rtol: Relative tolerance.
        atol: Absolute tolerance.

    Returns:
        Whether they agree, absolute and relative difference.
    """
    x, y = float(a), float(b)
    if (np.isnan(x) and np.isnan(y)) or x == y:
        return True, 0.0, 0.0
    diff = abs(x - y)
    scale = max(abs(x), abs(y))
    rel = diff / scale if scale > 0 else 0.0
    unit = max(_last_digit_unit(a), _last_digit_unit(b))
    return diff <= atol + rtol * scale or diff <= unit * (1 + 1e-9), diff, rel


def _compare_text(
    name: str, kind: str, ref_raw: bytes, cand_raw: bytes, rtol: float, atol_scale: float = 0.0
) -> Comparison:
    """Compare two texts: words exactly, numbers within tolerance.

    As for datasets, the absolute tolerance is ``atol_scale`` times the
    largest finite magnitude among the reference numbers.

    Args:
        name: Path relative to the output directory.
        kind: Kind for the report.
        ref_raw: Reference contents.
        cand_raw: Candidate contents.
        rtol: Relative tolerance for numbers.
        atol_scale: Absolute tolerance relative to the largest reference number.

    Returns:
        Comparison result; notes hold the first differing lines.
    """
    ref_lines = _normalize(ref_raw).splitlines()
    cand_lines = _normalize(cand_raw).splitlines()
    if ref_lines == cand_lines:
        return Comparison(name=name, kind=kind, status="identical", values=len(ref_lines))
    result = Comparison(name=name, kind=kind, status="within", values=len(ref_lines))
    magnitudes = [abs(float(t)) for line in ref_lines for t in NUMBER.findall(line)]
    finite = [m for m in magnitudes if np.isfinite(m)]
    atol = atol_scale * (max(finite) if finite else 0.0)
    if len(ref_lines) != len(cand_lines):
        result.status = "different"
        result.notes.append(f"{len(ref_lines)} vs {len(cand_lines)} lines")
    for number, (a, b) in enumerate(zip(ref_lines, cand_lines, strict=False), start=1):
        if a == b:
            continue
        ref_tokens, cand_tokens = NUMBER.findall(a), NUMBER.findall(b)
        same_words = _words(a) == _words(b)
        if not same_words or len(ref_tokens) != len(cand_tokens):
            result.status = "different"
            if len(result.notes) < 3:
                result.notes.append(f"line {number}: {a!r} != {b!r}")
            continue
        for x, y in zip(ref_tokens, cand_tokens, strict=True):
            ok, diff, rel = _numbers_close(x, y, rtol, atol)
            if diff > 0:
                result.different += 1
                result.max_abs_diff = max(result.max_abs_diff, diff)
                result.max_rel_diff = max(result.max_rel_diff, rel)
            if not ok:
                result.beyond += 1
                result.status = "different"
                if len(result.notes) < 3:
                    result.notes.append(f"line {number}: {x} vs {y}")
    return result


def _compare_rc(name: str, ref_dir: Path, cand_dir: Path) -> Comparison:
    """Compare exit codes; both must be zero.

    Args:
        name: Path of the ``.rc`` file relative to the output directory.
        ref_dir: Reference directory.
        cand_dir: Candidate directory.

    Returns:
        Comparison result.
    """
    ref = (ref_dir / name).read_text().strip()
    cand = (cand_dir / name).read_text().strip()
    ok = ref == cand == "0"
    notes = [] if ok else [f"exit code {ref} vs {cand}"]
    return Comparison(
        name=name, kind="exit code", status="identical" if ok else "different", notes=notes
    )


def _is_text(name: str) -> bool:
    """Tell whether an output file is compared as text.

    Args:
        name: File name.

    Returns:
        True for text outputs.
    """
    return name.endswith(TEXT_SUFFIXES)


def _compare_file(
    name: str, ref_dir: Path, cand_dir: Path, tolerances: ToleranceConfig
) -> Comparison | None:
    """Compare one reference output with the candidate.

    Args:
        name: Path relative to the output directory.
        ref_dir: Reference directory.
        cand_dir: Candidate directory.
        tolerances: Tolerance configuration.

    Returns:
        Comparison result, or None for files compared as part of another one.
    """
    if name.endswith((".BRIK", ".BRIK.gz")):
        return None
    if not (cand_dir / name).exists():
        return Comparison(name=name, kind="missing", status="missing")
    tolerance, text_rtol, informational = tolerances.for_file(name)
    result = _compare_present(
        name, ref_dir, cand_dir, tolerance, text_rtol, tolerances.informational_attributes(name)
    )
    if informational and result.status == "different" and not name.endswith(".rc"):
        result.status = "informational"
    return result


def _compare_present(
    name: str,
    ref_dir: Path,
    cand_dir: Path,
    tolerance: Tolerance,
    text_rtol: float,
    informational_attributes: list[str] | None = None,
) -> Comparison:
    """Compare a file that exists on both sides.

    Args:
        name: Path relative to the output directory.
        ref_dir: Reference directory.
        cand_dir: Candidate directory.
        tolerance: Dataset tolerance.
        text_rtol: Relative tolerance for numbers in text.
        informational_attributes: AFNI attribute name patterns that are only reported.

    Returns:
        Comparison result.
    """
    if name.endswith(".HEAD"):
        return _compare_afni(name, ref_dir, cand_dir, tolerance, informational_attributes)
    if name.endswith((".nii", ".nii.gz")):
        return _compare_nifti(name, ref_dir, cand_dir, tolerance)
    if name.endswith(".rc"):
        return _compare_rc(name, ref_dir, cand_dir)
    ref_raw = (ref_dir / name).read_bytes()
    cand_raw = (cand_dir / name).read_bytes()
    if name.endswith(".stderr"):
        result = _compare_text(name, "stderr", ref_raw, cand_raw, text_rtol, tolerance.atol_scale)
        if result.status in FAILING:
            result.status = "informational"
        return result
    if _is_text(name):
        return _compare_text(name, "text", ref_raw, cand_raw, text_rtol, tolerance.atol_scale)
    same = ref_raw == cand_raw
    return Comparison(name=name, kind="binary", status="identical" if same else "different")


def compare(config: CompareConfig) -> list[Comparison]:
    """Compare every output of the reference directory with the candidate.

    Args:
        config: Directories, report paths and tolerance file.

    Returns:
        One result per compared file.
    """
    tolerances = ToleranceConfig.model_validate_json(config.tolerance.read_text())
    ref_dir, cand_dir = config.reference, config.candidate
    inputs_file = ref_dir / INPUTS_LIST
    inputs = set(inputs_file.read_text().split()) if inputs_file.exists() else set()
    names = sorted(
        p.name for p in ref_dir.iterdir() if p.is_file() and p.name not in inputs | {INPUTS_LIST}
    )
    if (ref_dir / "logs").is_dir():
        names += sorted(f"logs/{p.name}" for p in (ref_dir / "logs").iterdir() if p.is_file())
    results = [_compare_file(name, ref_dir, cand_dir, tolerances) for name in names]
    return [r for r in results if r is not None]


def render_report(results: list[Comparison]) -> str:
    """Render the comparison as Markdown.

    Args:
        results: Comparison results.

    Returns:
        Markdown text.
    """
    counts = {s: sum(1 for r in results if r.status == s) for s in Status.__args__}
    failed = [r for r in results if r.status in FAILING]
    lines = [
        "## Linux vs Windows comparison",
        "",
        f"{len(results)} files: "
        + ", ".join(f"{n} {s}" for s, n in counts.items() if n)
        + f". Result: **{'FAILED' if failed else 'passed'}**.",
        "",
        "| File | Kind | Status | Values | Different | Beyond tolerance | Max abs diff "
        "| Max rel diff | Notes |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in sorted(results, key=lambda r: (r.status not in FAILING, r.status == "identical")):
        status = f"**{r.status}**" if r.status in FAILING else r.status
        lines.append(
            f"| {r.name} | {r.kind} | {status} | {r.values} | {r.different} | {r.beyond} "
            f"| {r.max_abs_diff:.3g} | {r.max_rel_diff:.3g} "
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
    parser.add_argument("--json-report", type=Path)
    parser.add_argument("--tolerance", type=Path, default=DEFAULT_TOLERANCE_FILE)
    return CompareConfig(**vars(parser.parse_args()))


def main() -> None:
    """Run the comparison and exit non-zero if anything is beyond tolerance."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    config = _parse_args()
    results = compare(config)
    config.report.write_text(render_report(results))
    if config.json_report is not None:
        config.json_report.write_text(json.dumps([r.model_dump() for r in results], indent=2))
    failed = [r for r in results if r.status in FAILING]
    for r in failed:
        logger.error(
            "%s (%s): %s, max abs %.3g, max rel %.3g; %s",
            r.name,
            r.kind,
            r.status,
            r.max_abs_diff,
            r.max_rel_diff,
            "; ".join(r.notes),
        )
    logger.info("%d compared, %d failed: %s", len(results), len(failed), [r.name for r in failed])
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
