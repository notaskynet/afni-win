"""Smoke scenario for 3dinfo, 3dcalc and 3dTstat, identical on Linux and Windows.

``prepare`` generates the input datasets with a reference AFNI build.
``run`` copies the inputs to an output directory and runs every scenario step
there, saving stdout and stderr of each step next to the produced datasets.
"""

import argparse
import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path

from pydantic import BaseModel

logger = logging.getLogger(__name__)

INPUT_FILES: tuple[str, ...] = ("rnd+orig.HEAD", "rnd+orig.BRIK", "rnd.nii.gz", "rnd_short.nii")


class Step(BaseModel):
    """One scenario step."""

    name: str
    program: str
    args: list[str]


PREPARE_STEPS: list[Step] = [
    Step(
        name="gen_rnd",
        program="3dcalc",
        args=[
            "-a",
            "jRandomDataset:32,32,16,6",
            "-expr",
            "a*100",
            "-datum",
            "float",
            "-prefix",
            "rnd",
        ],
    ),
    Step(
        name="gen_short",
        program="3dcalc",
        args=["-a", "rnd+orig", "-expr", "a*10", "-datum", "short", "-prefix", "rnd_short.nii"],
    ),
    Step(
        name="gen_niigz",
        program="3dcalc",
        args=["-a", "rnd+orig", "-expr", "a", "-prefix", "rnd.nii.gz"],
    ),
]

SCENARIO: list[Step] = [
    Step(name="info_brik", program="3dinfo", args=["rnd+orig"]),
    Step(name="info_nii", program="3dinfo", args=["rnd_short.nii"]),
    Step(name="info_niigz", program="3dinfo", args=["rnd.nii.gz"]),
    Step(name="info_verb", program="3dinfo", args=["-verb", "rnd+orig"]),
    Step(
        name="calc_c1",
        program="3dcalc",
        args=[
            "-a",
            "rnd+orig",
            "-b",
            "rnd.nii.gz",
            "-expr",
            "a*b/100+sqrt(abs(a))",
            "-prefix",
            "c1",
        ],
    ),
    Step(
        name="calc_c2",
        program="3dcalc",
        args=[
            "-a",
            "rnd+orig",
            "-expr",
            "sin(a)*exp(-abs(a)/50)+log(1+abs(a))",
            "-prefix",
            "c2.nii",
        ],
    ),
    Step(
        name="calc_c3",
        program="3dcalc",
        args=[
            "-a",
            "rnd_short.nii",
            "-expr",
            "step(a)*a",
            "-datum",
            "short",
            "-prefix",
            "c3.nii.gz",
        ],
    ),
    Step(
        name="tstat_t1",
        program="3dTstat",
        args=["-mean", "-stdev", "-max", "-prefix", "t1", "rnd+orig"],
    ),
    Step(
        name="tstat_t2",
        program="3dTstat",
        args=["-median", "-prefix", "t2.nii.gz", "rnd.nii.gz"],
    ),
    Step(
        name="calc_spawn",
        program="3dinfo",
        args=["-n4", "-max", "3dcalc( -a rnd+orig -expr 2*a -datum float )"],
    ),
]


class SmokeConfig(BaseModel):
    """Locations for one invocation."""

    bin_dir: Path
    out_dir: Path
    data_dir: Path | None = None


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


def _environment(bin_dir: Path, work_dir: Path) -> dict[str, str]:
    """Build an isolated environment for AFNI programs.

    Args:
        bin_dir: Directory with AFNI executables, put first on PATH.
        work_dir: Working directory, also used as HOME and TMPDIR.

    Returns:
        Environment mapping.
    """
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("AFNI_") and key not in ("HOME", "TMPDIR")
    }
    home = work_dir / "home"
    home.mkdir(exist_ok=True)
    env["HOME"] = str(home)
    env["TMPDIR"] = "."
    env["PATH"] = str(bin_dir.resolve()) + os.pathsep + env.get("PATH", "")
    env["AFNI_COMPRESSOR"] = "NONE"
    return env


def _run_steps(config: SmokeConfig, steps: list[Step], work_dir: Path) -> int:
    """Run steps in a directory, storing stdout, stderr and exit codes.

    Args:
        config: Locations.
        steps: Steps to run.
        work_dir: Directory in which the programs run.

    Returns:
        Number of steps that exited with a non-zero code.
    """
    env = _environment(config.bin_dir, work_dir)
    failures = 0
    logs = work_dir / "logs"
    logs.mkdir(exist_ok=True)
    for step in steps:
        cmd = [str(_program_path(config.bin_dir, step.program)), *step.args]
        logger.info("%s: %s", step.name, " ".join(step.args))
        result = subprocess.run(
            cmd, cwd=work_dir, env=env, stdin=subprocess.DEVNULL, capture_output=True
        )
        (logs / f"{step.name}.stdout").write_bytes(result.stdout)
        (logs / f"{step.name}.stderr").write_bytes(result.stderr)
        (logs / f"{step.name}.rc").write_text(f"{result.returncode}\n")
        if result.returncode != 0:
            failures += 1
            logger.error("%s exited with %d", step.name, result.returncode)
    return failures


def prepare(config: SmokeConfig) -> int:
    """Generate the input datasets with a reference build.

    Args:
        config: Locations; ``out_dir`` receives the inputs.

    Returns:
        Number of failed steps.
    """
    config.out_dir.mkdir(parents=True, exist_ok=True)
    failures = _run_steps(config, PREPARE_STEPS, config.out_dir)
    missing = [name for name in INPUT_FILES if not (config.out_dir / name).is_file()]
    if missing:
        logger.error("Inputs not created: %s", missing)
        failures += 1
    return failures


def run(config: SmokeConfig) -> int:
    """Copy the inputs and run the scenario.

    Args:
        config: Locations; ``data_dir`` must contain the inputs.

    Returns:
        Number of failed steps.

    Raises:
        ValueError: If ``data_dir`` is not set.
    """
    if config.data_dir is None:
        raise ValueError("data_dir is required for run")
    config.out_dir.mkdir(parents=True, exist_ok=True)
    for name in INPUT_FILES:
        shutil.copy2(config.data_dir / name, config.out_dir / name)
    return _run_steps(config, SCENARIO, config.out_dir)


def _parse_args() -> tuple[str, SmokeConfig]:
    """Parse command line arguments.

    Returns:
        Command name and configuration.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["prepare", "run"])
    parser.add_argument("--bin-dir", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--data-dir", type=Path)
    args = parser.parse_args()
    return args.command, SmokeConfig(
        bin_dir=args.bin_dir, out_dir=args.out_dir, data_dir=args.data_dir
    )


def main() -> None:
    """Run the smoke scenario from the command line."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    command, config = _parse_args()
    failures = prepare(config) if command == "prepare" else run(config)
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
