"""Tests for tools.posix_diff."""

from tools.posix_diff import CallSites, render_diff


def test_moved_code_is_not_reported() -> None:
    """Call sites that only changed line numbers are not a difference."""
    before = CallSites(tag="AFNI_26.2.08", callsites={"fork": ["a.c:10"]})
    after = CallSites(tag="AFNI_26.2.09", callsites={"fork": ["a.c:20"]})
    assert "No change" in render_diff(before, after)


def test_new_call_site_is_reported() -> None:
    """A call site in a new file appears in the table."""
    before = CallSites(tag="AFNI_26.2.08", callsites={"fork": ["a.c:10"]})
    after = CallSites(tag="AFNI_26.2.09", callsites={"fork": ["a.c:10", "b.c:5"]})
    report = render_diff(before, after)
    assert "| process | fork | 1 | 2 | b.c |  |" in report


def test_no_previous_release() -> None:
    """Without a previous release the report says so."""
    current = CallSites(tag="AFNI_26.2.09", callsites={})
    assert "No previous release" in render_diff(None, current)
