"""Tests for tools.upstream_tags."""

import pytest

from tools.upstream_tags import failed_tags, previous_release, released_tags, select_tags

TAGS = ["AFNI_26.2.08", "AFNI_26.2.09", "AFNI_26.2.10", "AFNI_26.3.01", "AFNI_legacy_11.3.82"]


def test_select_skips_old_released_failed_and_other_tags() -> None:
    """Only tags not older than the baseline, not released and not failed are chosen."""
    chosen = select_tags(TAGS, "AFNI_26.2.09", {"AFNI_26.2.09"}, {"AFNI_26.2.10"}, 3)
    assert chosen == ["AFNI_26.3.01"]


def test_select_keeps_the_newest_in_version_order() -> None:
    """Versions are compared numerically and the newest ones are kept."""
    tags = ["AFNI_26.10.01", "AFNI_26.9.12", "AFNI_26.2.09"]
    assert select_tags(tags, "AFNI_26.2.09", set(), set(), 2) == ["AFNI_26.9.12", "AFNI_26.10.01"]


def test_select_rejects_a_bad_baseline() -> None:
    """A baseline that is not a release tag is an error."""
    with pytest.raises(ValueError):
        select_tags(TAGS, "main", set(), set(), 3)


def test_released_and_failed_tags_are_parsed() -> None:
    """Release names and failure issue titles map back to upstream tags."""
    assert released_tags([{"tagName": "AFNI_26.2.09-win"}, {"tagName": "v1"}]) == {"AFNI_26.2.09"}
    issues = [{"title": "Build failed: AFNI_26.2.10"}, {"title": "Other"}]
    assert failed_tags(issues) == {"AFNI_26.2.10"}


def test_previous_release_is_the_newest_older_one() -> None:
    """The previous release is the newest released tag older than the current one."""
    releases = [{"tagName": f"{t}-win"} for t in ("AFNI_26.2.08", "AFNI_26.2.10", "AFNI_26.3.01")]
    assert previous_release("AFNI_26.3.01", releases) == "AFNI_26.2.10"
    assert previous_release("AFNI_26.2.08", releases) == ""
