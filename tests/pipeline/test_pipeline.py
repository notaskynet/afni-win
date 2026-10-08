"""Unit tests of the acceptance pipeline driver."""

from pathlib import Path

import pytest

from tests.pipeline.data import subject_urls, timing_line
from tests.pipeline.run import (
    Timing,
    afni_proc_args,
    command,
    environment,
    log_tail,
    output_patterns,
    probes,
    time_report,
)
from tests.regression.compare import CompareConfig, compare

EVENTS = (
    "onset\tduration\ttrial_type\tStimulus\n"
    "0.0\t2.0\tincongruent_correct\tincongruent\n"
    "10.0\t2.0\tcongruent_correct\tcongruent\n"
    "20.0\t2.0\tincongruent_correct\tincongruent\n"
)


def test_timing_line_selects_the_stimulus_column() -> None:
    """Onsets come from the Stimulus column, not from trial_type."""
    assert timing_line(EVENTS, "incongruent") == "0.0 20.0"
    assert timing_line(EVENTS, "congruent") == "10.0"


def test_timing_line_rejects_missing_column() -> None:
    """An events file without Stimulus is an error."""
    with pytest.raises(ValueError, match="Stimulus"):
        timing_line("onset\tduration\n0\t2\n", "congruent")


def test_subject_urls_cover_anatomy_runs_and_events() -> None:
    """One anatomy, two runs and two events files per subject."""
    names = [name for _, name in subject_urls("01")]
    assert names[0] == "sub-01_T1w.nii.gz"
    assert "sub-01_task-flanker_run-2_bold.nii.gz" in names
    assert len(names) == 5


def test_clustsim_only_for_the_reference_subject(tmp_path: Path) -> None:
    """3dClustSim runs for sub-08 only; paths use forward slashes."""
    args08 = afni_proc_args("08", tmp_path, tmp_path / "MNI_brain.nii.gz")
    args01 = afni_proc_args("01", tmp_path, tmp_path / "MNI_brain.nii.gz")
    assert args08[args08.index("-regress_run_clustsim") + 1] == "yes"
    assert args01[args01.index("-regress_run_clustsim") + 1] == "no"
    assert all("\\" not in a for a in args08)
    assert args08[args08.index("-html_review_style") + 1] == "none"


def test_windows_environment_is_isolated(tmp_path: Path) -> None:
    """Windows PATH holds the AFNI and system directories only."""
    base = {"PATH": "C:\\Other", "SystemRoot": "C:\\Windows", "PYTHONPATH": "x", "R_HOME": "y"}
    env = environment("windows", tmp_path, base)
    assert env["PATH"].split(";")[0] == str(tmp_path)
    assert "C:\\Other" not in env["PATH"]
    assert "PYTHONPATH" not in env and "R_HOME" not in env


def test_linux_environment_adds_afni_dir(tmp_path: Path) -> None:
    """Linux keeps PATH without the driver venv and adds the AFNI directory."""
    base = {"PATH": "/venv/bin:/usr/bin", "HOME": "/home/u", "VIRTUAL_ENV": "/venv"}
    base["R_LIBS_USER"] = "/r"
    env = environment("linux", tmp_path, base)
    assert env["PATH"] == f"{tmp_path}:/usr/bin"
    assert env["PYTHONPATH"] == str(tmp_path)
    assert env["HOME"] == "/home/u" and env["R_LIBS_USER"] == "/r"
    assert "VIRTUAL_ENV" not in env


def test_windows_commands_use_launchers(tmp_path: Path) -> None:
    """Scripts and tcsh start through .cmd launchers, programs as .exe."""
    (tmp_path / "afni_proc.py.cmd").write_text("")
    assert command("windows", tmp_path, "afni_proc.py").endswith("afni_proc.py.cmd")
    assert command("windows", tmp_path, "tcsh").endswith("tcsh.cmd")
    assert command("windows", tmp_path, "3dcalc").endswith("3dcalc.exe")
    assert command("linux", tmp_path, "tcsh") == "tcsh"


def test_output_patterns_use_the_subject_id() -> None:
    """Patterns name the afni_proc.py subject ID."""
    assert "stats.sub08+tlrc.*" in output_patterns("08")


def test_time_report_applies_the_limit() -> None:
    """The subjects' wall time ratio decides; the group is only reported."""
    linux = Timing(subjects_wall=100, subjects={"sub08": 90}, group=10)
    ok, report = time_report(linux, Timing(subjects_wall=140, group=100), 1.5)
    assert ok
    assert "| group | 10 | 100 | 10.00 |" in report
    assert not time_report(linux, Timing(subjects_wall=160), 1.5)[0]


def test_compare_without_logs_directory(tmp_path: Path) -> None:
    """Pipeline output directories have no logs/ subdirectory."""
    for side in ("ref", "cand"):
        (tmp_path / side).mkdir()
        (tmp_path / side / "out.gcor.1D").write_text("0.1234\n")
    config = CompareConfig(
        reference=tmp_path / "ref", candidate=tmp_path / "cand", report=tmp_path / "r.md"
    )
    assert [r.status for r in compare(config)] == ["identical"]


def test_log_tail_keeps_the_last_lines() -> None:
    """Only the end of a long log reaches the CI output."""
    raw = "".join(f"line {i}\n" for i in range(100)).encode()
    tail = log_tail(raw)
    assert tail.splitlines()[0] == "line 60" and tail.endswith("line 99")
    assert log_tail(b"\xff") == "\ufffd"


def test_probes_cover_every_start_path(tmp_path: Path) -> None:
    """Direct, sh, Python shell=True and tcsh, on the same dataset."""
    windows = probes("windows", tmp_path, tmp_path / "MNI_brain.nii.gz")
    assert [label for label, _ in windows] == ["direct", "sh -c", "python shell=True", "tcsh -c"]
    assert windows[1][1][0].endswith("sh.exe")
    assert windows[3][1][0].endswith("tcsh.cmd")
    assert "shell=True" in windows[2][1][2]
    assert probes("linux", tmp_path, tmp_path / "x.nii")[3][1][0] == "tcsh"
