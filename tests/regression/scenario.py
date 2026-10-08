"""Regression scenario for the required programs, identical on Linux and Windows.

``prepare`` generates the synthetic input data with a reference AFNI build.
``run`` copies the inputs to an output directory and runs every scenario step
there, saving stdout, stderr and the exit code of each step under ``logs/``.
``run`` does not judge the exit codes; ``compare`` checks them against the
reference.
"""

import argparse
import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path

from pydantic import BaseModel

from tests.regression.steps import PREPARE_STEPS, SCENARIO, TEXT_INPUTS, Step

logger = logging.getLogger(__name__)

INPUTS_LIST = "inputs.txt"
STEP_TIMEOUT_SECONDS = 1800


class ScenarioConfig(BaseModel):
    """Locations for one invocation."""

    bin_dir: Path
    out_dir: Path
    data_dir: Path | None = None
    launcher: list[str] = []
    isolated_path: bool = False


def _program_path(bin_dir: Path, program: str) -> Path:
    """Find the executable of a program in the binary directory.

    Args:
        bin_dir: Directory with AFNI executables.
        program: Program name without extension.

    Returns:
        Path of the executable.

    Raises:
        FileNotFoundError: If the program is missing.
    """
    for candidate in (bin_dir / f"{program}.exe", bin_dir / program):
        if candidate.is_file():
            return candidate.resolve()
    raise FileNotFoundError(f"{program} not found in {bin_dir}")


def _environment(bin_dir: Path, work_dir: Path, isolated_path: bool) -> dict[str, str]:
    """Build an isolated environment for AFNI programs.

    Args:
        bin_dir: Directory with AFNI executables, put first on PATH.
        work_dir: Working directory, also used as HOME and TMPDIR.
        isolated_path: PATH holds only ``bin_dir`` and the Windows system
            directories, so that everything a package needs must be in it.

    Returns:
        Environment mapping; random seeds are fixed with ``AFNI_RANDOM_SEEDVAL``.
    """
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("AFNI_") and key not in ("HOME", "TMPDIR", "OMP_NUM_THREADS")
    }
    home = work_dir / "home"
    home.mkdir(exist_ok=True)
    env["HOME"] = str(home)
    env["TMPDIR"] = work_dir.resolve().as_posix()
    if isolated_path:
        system_root = env.get("SystemRoot", "C:\\Windows")
        rest = os.pathsep.join([f"{system_root}\\System32", system_root])
    else:
        rest = env.get("PATH", "")
    env["PATH"] = str(bin_dir.resolve()) + os.pathsep + rest
    env["AFNI_COMPRESSOR"] = "NONE"
    env["AFNI_RANDOM_SEEDVAL"] = "31416"
    return env


def _run_step(config: ScenarioConfig, step: Step, work_dir: Path, env: dict[str, str]) -> int:
    """Run one step, storing stdout, stderr and the exit code under ``logs/``.

    Args:
        config: Locations.
        step: Step to run.
        work_dir: Directory in which the program runs.
        env: Base environment; the step's own variables are added.

    Returns:
        Exit code of the program (-1 on timeout).
    """
    logs = work_dir / "logs"
    cmd = [*config.launcher, str(_program_path(config.bin_dir, step.program)), *step.args]
    logger.info("%s: %s %s", step.name, step.program, " ".join(step.args))
    try:
        result = subprocess.run(
            cmd,
            cwd=work_dir,
            env={**env, **step.env},
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=STEP_TIMEOUT_SECONDS,
        )
        stdout, stderr, code = result.stdout, result.stderr, result.returncode
    except subprocess.TimeoutExpired as error:
        stdout, stderr, code = error.stdout or b"", error.stderr or b"", -1
    (logs / f"{step.name}.stdout").write_bytes(stdout)
    (logs / f"{step.name}.stderr").write_bytes(stderr)
    (logs / f"{step.name}.rc").write_text(f"{code}\n")
    if code != 0:
        logger.warning("%s exited with %d", step.name, code)
    return code


def _run_steps(config: ScenarioConfig, steps: list[Step], work_dir: Path) -> int:
    """Run steps in a directory.

    Args:
        config: Locations.
        steps: Steps to run.
        work_dir: Directory in which the programs run.

    Returns:
        Number of steps that exited with a non-zero code.
    """
    env = _environment(config.bin_dir, work_dir, config.isolated_path)
    (work_dir / "logs").mkdir(exist_ok=True)
    return sum(1 for step in steps if _run_step(config, step, work_dir, env) != 0)


def prepare(config: ScenarioConfig) -> int:
    """Generate the input data with a reference build.

    Args:
        config: Locations; ``out_dir`` receives the inputs.

    Returns:
        Number of failed steps.
    """
    config.out_dir.mkdir(parents=True, exist_ok=True)
    for name, text in TEXT_INPUTS.items():
        (config.out_dir / name).write_text(text)
    return _run_steps(config, PREPARE_STEPS, config.out_dir)


def run(config: ScenarioConfig) -> int:
    """Copy the inputs and run the scenario.

    Args:
        config: Locations; ``data_dir`` must contain the inputs.

    Returns:
        Number of steps that exited with a non-zero code.

    Raises:
        ValueError: If ``data_dir`` is not set.
    """
    if config.data_dir is None:
        raise ValueError("data_dir is required for run")
    config.out_dir.mkdir(parents=True, exist_ok=True)
    names = sorted(p.name for p in config.data_dir.iterdir() if p.is_file())
    for name in names:
        shutil.copy2(config.data_dir / name, config.out_dir / name)
    (config.out_dir / INPUTS_LIST).write_text("\n".join(names) + "\n")
    return _run_steps(config, SCENARIO, config.out_dir)


def _parse_args() -> tuple[str, ScenarioConfig]:
    """Parse command line arguments.

    Returns:
        Command name and configuration.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["prepare", "run"])
    parser.add_argument("--bin-dir", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--data-dir", type=Path)
    parser.add_argument(
        "--launcher", default="", help="command that starts the programs, e.g. wine"
    )
    parser.add_argument(
        "--isolated-path",
        action="store_true",
        help="PATH = bin dir + Windows system directories (checks a package)",
    )
    args = parser.parse_args()
    return args.command, ScenarioConfig(
        bin_dir=args.bin_dir,
        out_dir=args.out_dir,
        data_dir=args.data_dir,
        launcher=args.launcher.split(),
        isolated_path=args.isolated_path,
    )


def main() -> None:
    """Run ``prepare`` (fails on any failed step) or ``run`` (never judges exit codes)."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    command, config = _parse_args()
    if command == "prepare":
        sys.exit(1 if prepare(config) else 0)
    failed = run(config)
    logger.info("%d of %d steps exited with a non-zero code", failed, len(SCENARIO))


if __name__ == "__main__":
    main()
