"""Run the acceptance pipeline on one platform (docs/DECISIONS.md D40).

``prepare`` makes the skull-stripped MNI template. ``subjects`` writes and runs
the ``afni_proc.py`` pipeline of every subject, all subjects at once, and
copies the compared outputs to ``<results>/outputs/<subject>/``. ``group``
runs ``group.tcsh`` (``3dttest++`` and ``3dMVM``) on the subject results.
``time`` checks the wall time of the subjects against the Linux run.
``check`` starts ``3dinfo`` on the template in each way the pipeline starts
programs (directly, ``sh -c``, Python ``shell=True``, tcsh) and logs what each
printed, so that a broken link of the runtime shows up by name.

On Windows everything starts through the installed package: ``afni_proc.py``
through its ``.cmd`` launcher, the proc script through ``tcsh.cmd``, and the
group script inside the AFNI shell ``afni-tcsh.cmd``, all with a PATH that
holds only the AFNI directory and the Windows system directories. On Linux
the programs and scripts come from one directory, as in an upstream
installation.
"""

import argparse
import io
import logging
import os
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from tests.pipeline.data import (
    CONDITIONS,
    RUNS,
    SUBJECTS,
    TEMPLATE_MASK,
    TEMPLATE_T1,
    anat_name,
    bold_name,
    timing_name,
)

logger = logging.getLogger(__name__)

Platform = Literal["linux", "windows"]

HERE = Path(__file__).resolve().parent
GROUP_SCRIPT = HERE / "group.tcsh"
TEMPLATE = "MNI_brain.nii.gz"
CLUSTSIM_SUBJECTS: frozenset[str] = frozenset({"08"})
TIMING_FILE = "timing.json"
LOG_TAIL_LINES = 300
PYTHON_VARIABLES: frozenset[str] = frozenset({"PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV"})
WINDOWS_DROPPED_VARIABLES: frozenset[str] = PYTHON_VARIABLES | {
    "HOME",
    "TMPDIR",
    "MSYSTEM",
    "CHERE_INVOKING",
    "R_HOME",
    "R_LIBS",
    "R_LIBS_SITE",
    "R_LIBS_USER",
}
OUTPUTS: tuple[str, ...] = (
    "stats.{s}+tlrc.*",
    "X.xmat.1D",
    "dfile_rall.1D",
    "motion_{s}_enorm.1D",
    "censor_{s}_combined_2.1D",
    "out.ss_review.{s}.txt",
    "blur_est.{s}.1D",
    "mask_epi_anat.{s}+tlrc.*",
    "anat_final.{s}+tlrc.*",
    "final_epi_vr_base_min_outlier+tlrc.*",
    "mat.basewarp.aff12.1D",
    "out.gcor.1D",
    "TSNR.{s}+tlrc.*",
)
GROUP_OUTPUTS: tuple[str, ...] = ("group_mask+tlrc.*", "ttest.inc-con+tlrc.*", "MVM+tlrc.*")


class PipelineConfig(BaseModel):
    """Locations and platform of one run."""

    platform: Platform
    afni_dir: Path
    data_dir: Path
    work_dir: Path
    results_dir: Path
    subjects: list[str] = list(SUBJECTS)
    jobs: int = 4


class SubjectResult(BaseModel):
    """Outcome of one subject."""

    subject: str
    afni_proc_status: int
    proc_status: int
    seconds: float


class Timing(BaseModel):
    """Wall times of a run, in seconds."""

    subjects_wall: float = 0.0
    subjects: dict[str, float] = {}
    group: float = 0.0


class TimeConfig(BaseModel):
    """Inputs of the time check."""

    reference: Path
    candidate: Path
    limit: float
    report: Path


def subject_id(subject: str) -> str:
    """Subject ID used by ``afni_proc.py``.

    Args:
        subject: Subject number such as ``08``.

    Returns:
        ID such as ``sub08``.
    """
    return f"sub{subject}"


def _path(path: Path) -> str:
    """Write a path for AFNI scripts: absolute, with forward slashes.

    Args:
        path: Any path.

    Returns:
        Absolute path with ``/`` separators (``D:/...`` on Windows), which
        native programs and the MSYS2 tcsh both accept.
    """
    return path.resolve().as_posix()


def afni_proc_args(subject: str, data_dir: Path, template: Path) -> list[str]:
    """Options of ``afni_proc.py`` for one subject.

    The anatomy keeps its skull (``3dSkullStrip`` runs inside the pipeline);
    the QC report is off (D34, U6); ``3dClustSim`` runs for the subjects of
    :data:`CLUSTSIM_SUBJECTS` only, to keep the run short.

    Args:
        subject: Subject number.
        data_dir: Directory of :mod:`tests.pipeline.data`.
        template: Skull-stripped template written by ``prepare``.

    Returns:
        Arguments after the program name.
    """
    sid = subject_id(subject)
    return [
        "-subj_id",
        sid,
        "-script",
        f"proc.{sid}",
        "-scr_overwrite",
        "-dsets",
        *[_path(data_dir / bold_name(subject, run)) for run in RUNS],
        "-copy_anat",
        _path(data_dir / anat_name(subject)),
        "-blocks",
        "tshift",
        "align",
        "tlrc",
        "volreg",
        "blur",
        "mask",
        "scale",
        "regress",
        "-align_opts_aea",
        "-cost",
        "lpc+ZZ",
        "-giant_move",
        "-tlrc_base",
        _path(template),
        "-volreg_align_to",
        "MIN_OUTLIER",
        "-volreg_align_e2a",
        "-volreg_tlrc_warp",
        "-blur_size",
        "4.0",
        "-regress_stim_times",
        *[_path(data_dir / timing_name(subject, c)) for c in CONDITIONS],
        "-regress_stim_labels",
        *CONDITIONS,
        "-regress_basis",
        "BLOCK(2,1)",
        "-regress_censor_motion",
        "0.3",
        "-regress_censor_outliers",
        "0.05",
        "-regress_motion_per_run",
        "-regress_opts_3dD",
        "-jobs",
        "1",
        "-gltsym",
        "SYM: incongruent -congruent",
        "-glt_label",
        "1",
        "inc-con",
        "-regress_make_ideal_sum",
        "sum_ideal.1D",
        "-regress_est_blur_epits",
        "-regress_est_blur_errts",
        "-regress_run_clustsim",
        "yes" if subject in CLUSTSIM_SUBJECTS else "no",
        "-html_review_style",
        "none",
    ]


def environment(platform: Platform, afni_dir: Path, base: dict[str, str]) -> dict[str, str]:
    """Environment of the AFNI commands.

    Args:
        platform: ``linux`` or ``windows``.
        afni_dir: AFNI directory (Linux: programs, scripts and ``afnipy``;
            Windows: the installed package).
        base: Environment of the caller.

    Returns:
        Windows: the caller's environment without variables that would point
        AFNI at other installations, with PATH limited to the AFNI directory
        and the system directories (the launchers add the rest). Linux: the
        AFNI directory first on PATH and on PYTHONPATH, without the virtual
        environment of the driver, so that scripts get the system Python.
    """
    if platform == "windows":
        env = {k: v for k, v in base.items() if k.upper() not in WINDOWS_DROPPED_VARIABLES}
        system_root = base.get("SystemRoot", "C:\\Windows")
        env["PATH"] = ";".join(
            [
                str(afni_dir),
                f"{system_root}\\System32",
                system_root,
                f"{system_root}\\System32\\Wbem",
            ]
        )
    else:
        env = {k: v for k, v in base.items() if k not in PYTHON_VARIABLES}
        venv = base.get("VIRTUAL_ENV")
        path = [
            p for p in base.get("PATH", "").split(os.pathsep) if not (venv and p.startswith(venv))
        ]
        env["PATH"] = os.pathsep.join([str(afni_dir), *path])
        env["PYTHONPATH"] = str(afni_dir)
    return env


def command(platform: Platform, afni_dir: Path, name: str) -> str:
    """Executable that starts an AFNI program, script or tcsh.

    Args:
        platform: ``linux`` or ``windows``.
        afni_dir: AFNI directory.
        name: ``tcsh``, ``afni-tcsh``, a script name or a program name.

    Returns:
        Path to run. Windows: the ``.cmd`` launcher of a script or of tcsh,
        or the ``.exe`` of a program. Linux: the file in the AFNI directory,
        or ``tcsh`` from the system.
    """
    if platform == "linux":
        return "tcsh" if name == "tcsh" else str(afni_dir / name)
    if name in ("tcsh", "afni-tcsh") or (afni_dir / f"{name}.cmd").exists():
        return str(afni_dir / f"{name}.cmd")
    return str(afni_dir / f"{name}.exe")


def output_patterns(subject: str) -> list[str]:
    """File patterns copied from a subject's results directory.

    Args:
        subject: Subject number.

    Returns:
        Glob patterns.
    """
    return [p.format(s=subject_id(subject)) for p in OUTPUTS]


def _run(
    cmd: list[str], cwd: Path, env: dict[str, str], log: Path, stdin_text: str | None = None
) -> int:
    """Run a command with stdout and stderr in a log file.

    Args:
        cmd: Command line.
        cwd: Working directory.
        env: Environment.
        log: Log file.
        stdin_text: Text for stdin, or None for no input.

    Returns:
        Exit status.
    """
    logger.info("%s: %s", cwd.name, " ".join(cmd[:3]))
    with log.open("wb") as out:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            env=env,
            input=stdin_text.encode() if stdin_text is not None else None,
            stdin=None if stdin_text is not None else subprocess.DEVNULL,
            stdout=out,
            stderr=subprocess.STDOUT,
        )
    if result.returncode != 0:
        logger.error(
            "%s: exit status %d; end of %s:\n%s",
            cwd.name,
            result.returncode,
            log.name,
            log_tail(log.read_bytes()),
        )
    return result.returncode


def log_tail(raw: bytes) -> str:
    """Last lines of a log, for the CI output.

    Args:
        raw: Log contents.

    Returns:
        The last :data:`LOG_TAIL_LINES` lines, decoded leniently.
    """
    return "\n".join(raw.decode("utf-8", "replace").splitlines()[-LOG_TAIL_LINES:])


def _copy_outputs(source: Path, target: Path, patterns: list[str]) -> int:
    """Copy result files.

    Args:
        source: Results directory of the pipeline.
        target: Destination directory.
        patterns: Glob patterns.

    Returns:
        Number of files copied.
    """
    target.mkdir(parents=True, exist_ok=True)
    count = 0
    for pattern in patterns:
        for path in sorted(source.glob(pattern)):
            shutil.copy2(path, target / path.name)
            count += 1
    return count


def prepare(config: PipelineConfig) -> None:
    """Write the skull-stripped template ``<work>/MNI_brain.nii.gz``.

    Args:
        config: Run configuration.

    Raises:
        RuntimeError: If an AFNI program fails.
    """
    config.work_dir.mkdir(parents=True, exist_ok=True)
    config.results_dir.joinpath("logs").mkdir(parents=True, exist_ok=True)
    env = environment(config.platform, config.afni_dir, dict(os.environ))
    steps = [
        [
            command(config.platform, config.afni_dir, "3dcalc"),
            "-a",
            _path(config.data_dir / TEMPLATE_T1),
            "-b",
            _path(config.data_dir / TEMPLATE_MASK),
            "-expr",
            "a*step(b)",
            "-prefix",
            TEMPLATE,
            "-overwrite",
        ],
        [
            command(config.platform, config.afni_dir, "3drefit"),
            "-space",
            "MNI",
            "-view",
            "tlrc",
            TEMPLATE,
        ],
    ]
    for number, cmd in enumerate(steps, 1):
        log = config.results_dir / "logs" / f"prepare.{number}.log"
        if _run(cmd, config.work_dir, env, log) != 0:
            raise RuntimeError(f"{cmd[0]} failed, see {log}")


def probes(platform: Platform, afni_dir: Path, dataset: Path) -> list[tuple[str, list[str]]]:
    """Ways in which the pipeline starts an AFNI program, each on one dataset.

    Args:
        platform: ``linux`` or ``windows``.
        afni_dir: AFNI directory.
        dataset: Dataset to read (on Windows under a non-ASCII directory).

    Returns:
        (label, command) pairs: the program directly, through ``sh -c``,
        through Python ``shell=True`` (the afnipy path) and through tcsh.
    """
    info = f"3dinfo -d3 {_path(dataset)}"
    script = (
        "import subprocess; "
        f"r = subprocess.run({info!r}, shell=True, capture_output=True); "
        "print(r.returncode, ascii(r.stdout), ascii(r.stderr))"
    )
    if platform == "windows":
        sh = str(afni_dir / "msys" / "usr" / "bin" / "sh.exe")
        python = str(afni_dir / "python" / "bin" / "python.exe")
        return [
            ("direct", [command(platform, afni_dir, "3dinfo"), "-d3", _path(dataset)]),
            ("sh -c", [sh, "-c", info]),
            ("python shell=True", [python, "-c", script]),
            ("tcsh -c", [command(platform, afni_dir, "tcsh"), "-c", info]),
        ]
    return [
        ("direct", [command(platform, afni_dir, "3dinfo"), "-d3", _path(dataset)]),
        ("sh -c", ["sh", "-c", info]),
        ("python shell=True", ["python", "-c", script]),
        ("tcsh -c", ["tcsh", "-c", info]),
    ]


def check(config: PipelineConfig) -> bool:
    """Start ``3dinfo`` in each way of :func:`probes` and log the results.

    Args:
        config: Run configuration (needs the template of ``prepare``).

    Returns:
        True if every probe printed the voxel size.
    """
    env = environment(config.platform, config.afni_dir, dict(os.environ))
    log = config.results_dir / "logs" / "check.log"
    ok = True
    for label, cmd in probes(config.platform, config.afni_dir, config.work_dir / TEMPLATE):
        status = _run(cmd, config.work_dir, env, log)
        output = log.read_bytes().decode("utf-8", "replace").strip()
        passed = status == 0 and "1.000000" in output
        ok = ok and passed
        logger.info(
            "check %s: status %d, %s: %s", label, status, "ok" if passed else "FAILED", output
        )
    return ok


def run_subject(config: PipelineConfig, subject: str) -> SubjectResult:
    """Write and run the pipeline of one subject and copy its outputs.

    Args:
        config: Run configuration.
        subject: Subject number.

    Returns:
        Exit statuses and wall time.
    """
    sid = subject_id(subject)
    work = config.work_dir / sid
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    logs = config.results_dir / "logs"
    env = environment(config.platform, config.afni_dir, dict(os.environ))
    start = time.monotonic()
    ap_status = _run(
        [
            command(config.platform, config.afni_dir, "afni_proc.py"),
            *afni_proc_args(subject, config.data_dir, config.work_dir / TEMPLATE),
        ],
        work,
        env,
        logs / f"afni_proc.{sid}.log",
    )
    proc_status = -1
    if ap_status == 0:
        proc_status = _run(
            [command(config.platform, config.afni_dir, "tcsh"), "-xef", f"proc.{sid}"],
            work,
            env,
            logs / f"output.proc.{sid}",
        )
    seconds = time.monotonic() - start
    if (work / f"proc.{sid}").exists():
        shutil.copy2(work / f"proc.{sid}", logs / f"proc.{sid}")
    copied = _copy_outputs(
        work / f"{sid}.results", config.results_dir / "outputs" / sid, output_patterns(subject)
    )
    logger.info(
        "%s: afni_proc.py %d, proc %d, %.0f s, %d outputs",
        sid,
        ap_status,
        proc_status,
        seconds,
        copied,
    )
    return SubjectResult(
        subject=subject, afni_proc_status=ap_status, proc_status=proc_status, seconds=seconds
    )


def _read_timing(results_dir: Path) -> Timing:
    """Read the timing file of a run, or start an empty one.

    Args:
        results_dir: Results directory.

    Returns:
        Timing so far.
    """
    path = results_dir / TIMING_FILE
    return Timing.model_validate_json(path.read_text()) if path.exists() else Timing()


def subjects(config: PipelineConfig) -> list[SubjectResult]:
    """Run all subjects in parallel and record the wall time.

    Args:
        config: Run configuration.

    Returns:
        One result per subject.
    """
    start = time.monotonic()
    with ThreadPoolExecutor(max_workers=config.jobs) as pool:
        results = list(pool.map(lambda s: run_subject(config, s), config.subjects))
    timing = _read_timing(config.results_dir)
    timing.subjects_wall = time.monotonic() - start
    timing.subjects = {subject_id(r.subject): r.seconds for r in results}
    (config.results_dir / TIMING_FILE).write_text(timing.model_dump_json(indent=2))
    return results


def group(config: PipelineConfig) -> int:
    """Run the group analysis and copy its outputs.

    Windows: the commands are typed into the AFNI shell ``afni-tcsh.cmd``.

    Args:
        config: Run configuration.

    Returns:
        Exit status of the group script.
    """
    env = environment(config.platform, config.afni_dir, dict(os.environ))
    ids = [subject_id(s) for s in config.subjects]
    script = [_path(GROUP_SCRIPT), _path(config.work_dir), *ids]
    log = config.results_dir / "logs" / "group.log"
    start = time.monotonic()
    if config.platform == "windows":
        shell_input = "tcsh -ef " + " ".join(script) + "\nexit $status\n"
        status = _run(
            [command(config.platform, config.afni_dir, "afni-tcsh")],
            config.work_dir,
            env,
            log,
            stdin_text=shell_input,
        )
    else:
        status = _run(
            [command(config.platform, config.afni_dir, "tcsh"), "-ef", *script],
            config.work_dir,
            env,
            log,
        )
    timing = _read_timing(config.results_dir)
    timing.group = time.monotonic() - start
    (config.results_dir / TIMING_FILE).write_text(timing.model_dump_json(indent=2))
    copied = _copy_outputs(
        config.work_dir / "group", config.results_dir / "outputs" / "group", list(GROUP_OUTPUTS)
    )
    logger.info("group: status %d, %.0f s, %d outputs", status, timing.group, copied)
    return status


def time_report(reference: Timing, candidate: Timing, limit: float) -> tuple[bool, str]:
    """Compare the wall times of two runs.

    Only the subjects (all run at once) are checked against the limit; the
    group analysis is reported.

    Args:
        reference: Linux timing.
        candidate: Windows timing.
        limit: Largest allowed ratio candidate / reference for the subjects.

    Returns:
        Whether the subjects are within the limit, and a Markdown report.
    """
    ratio = candidate.subjects_wall / reference.subjects_wall if reference.subjects_wall else 0.0
    ok = 0 < ratio <= limit
    lines = [
        "## Pipeline wall time",
        "",
        f"Subjects (all at once): ratio {ratio:.2f}, limit {limit}: "
        f"**{'passed' if ok else 'FAILED'}**.",
        "",
        "| Step | Linux (s) | Windows (s) | Ratio |",
        "|---|---|---|---|",
    ]
    rows = [("subjects (wall)", reference.subjects_wall, candidate.subjects_wall)]
    rows += [
        (name, seconds, candidate.subjects.get(name, 0.0))
        for name, seconds in sorted(reference.subjects.items())
    ]
    rows.append(("group", reference.group, candidate.group))
    for name, ref, cand in rows:
        lines.append(f"| {name} | {ref:.0f} | {cand:.0f} | {cand / ref if ref else 0:.2f} |")
    return ok, "\n".join(lines) + "\n"


def _parse_args() -> tuple[str, PipelineConfig | TimeConfig]:
    """Parse the command line.

    Returns:
        Subcommand and its configuration.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    for action in ("prepare", "check", "subjects", "group"):
        p = sub.add_parser(action)
        p.add_argument("--platform", choices=["linux", "windows"], required=True)
        p.add_argument("--afni-dir", type=Path, required=True)
        p.add_argument("--data-dir", type=Path, required=True)
        p.add_argument("--work-dir", type=Path, required=True)
        p.add_argument("--results-dir", type=Path, required=True)
        p.add_argument("--subjects", nargs="+", default=list(SUBJECTS))
        p.add_argument("--jobs", type=int, default=4)
    t = sub.add_parser("time")
    t.add_argument("--reference", type=Path, required=True)
    t.add_argument("--candidate", type=Path, required=True)
    t.add_argument("--limit", type=float, default=1.5)
    t.add_argument("--report", type=Path, required=True)
    args = vars(parser.parse_args())
    action = args.pop("action")
    if action == "time":
        return action, TimeConfig(**args)
    return action, PipelineConfig(**args)


def main() -> None:
    """Command line entry point; exits non-zero when a step fails."""
    if isinstance(sys.stderr, io.TextIOWrapper):
        sys.stderr.reconfigure(encoding="utf-8")
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    action, config = _parse_args()
    if isinstance(config, TimeConfig):
        ok, report = time_report(
            Timing.model_validate_json(config.reference.read_text()),
            Timing.model_validate_json(config.candidate.read_text()),
            config.limit,
        )
        config.report.write_text(report)
        logger.info("%s", report)
        sys.exit(0 if ok else 1)
    if action == "prepare":
        prepare(config)
    elif action == "check":
        if not check(config):
            sys.exit(1)
    elif action == "subjects":
        failed = [r for r in subjects(config) if r.afni_proc_status or r.proc_status]
        if failed:
            logger.error("failed subjects: %s", [subject_id(r.subject) for r in failed])
            sys.exit(1)
    elif group(config) != 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
