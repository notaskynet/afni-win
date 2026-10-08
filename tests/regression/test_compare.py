"""Tests for tests.regression.compare."""

import numpy as np

from tests.regression.compare import (
    DEFAULT_TOLERANCE_FILE,
    Tolerance,
    ToleranceConfig,
    _compare_text,
    _values,
)


def test_last_printed_digit_is_tolerated() -> None:
    """Numbers that differ by one unit in the last printed digit agree."""
    result = _compare_text("x.1D", "text", b"12.3 4\n", b"12.4 4\n", 1e-6)
    assert result.status == "within"


def test_words_must_match() -> None:
    """Text around the numbers must be identical."""
    result = _compare_text("x.1D", "text", b"mean 1.0\n", b"max 1.0\n", 1e-3)
    assert result.status == "different"


def test_number_beyond_tolerance() -> None:
    """A relative difference above rtol and above one printed unit fails."""
    result = _compare_text("x.1D", "text", b"1.000000\n", b"1.010000\n", 1e-4)
    assert result.status == "different" and result.beyond == 1


def test_values_with_absolute_and_relative_tolerance() -> None:
    """Values pass if |a-b| <= atol_scale*max|ref| + rtol*max(|a|,|b|)."""
    ref = np.array([1000.0, 0.0, 5.0])
    tolerance = Tolerance(rtol=1e-5, atol_scale=1e-6)
    assert _values("d", "AFNI", ref, ref + [0.005, 0.0009, 0.0], tolerance).status == "within"
    assert _values("d", "AFNI", ref, ref + [0.0, 0.002, 0.0], tolerance).status == "different"
    assert _values("d", "AFNI", ref, ref.copy(), tolerance).status == "identical"


def test_overrides_select_by_pattern() -> None:
    """The tolerance file assigns registration outputs to the optimisation class."""
    config = ToleranceConfig.model_validate_json(DEFAULT_TOLERANCE_FILE.read_text())
    assert config.for_file("qwarp+orig.HEAD")[0].rtol == 1e-2
    assert config.for_file("tproject+orig.HEAD")[0].rtol == 1e-4
    assert config.for_file("c1+orig.HEAD")[0] == config.default
    assert config.for_file("logs/fwhmx.stdout")[2]


def test_blanks_between_numbers_do_not_matter() -> None:
    """Column alignment that changes with the printed width is not a difference."""
    result = _compare_text("x.1D", "text", b"  0.259739  1\n", b"   0.25974  1\n", 1e-4)
    assert result.status == "within"


def test_absolute_tolerance_for_near_zero_numbers() -> None:
    """Near-zero entries next to large ones pass with the absolute tolerance."""
    ref = b"1.000000 0.000012 15.5\n"
    cand = b"1.000000 -0.000003 15.5\n"
    assert _compare_text("m.1D", "text", ref, cand, 1e-2, 0.0).status == "different"
    assert _compare_text("m.1D", "text", ref, cand, 1e-2, 1e-2).status == "within"
