"""Download the inputs of the acceptance pipeline (docs/DECISIONS.md D40).

OpenNeuro ``ds000102`` (flanker task, PDDL) subjects and the TemplateFlow
``MNI152NLin2009cAsym`` 1 mm T1 and brain mask. For each subject it writes the
stimulus timing files ``sub-XX_congruent.1D`` and ``sub-XX_incongruent.1D``
(one line of onsets per run) from the ``Stimulus`` column of the events files.
"""

import argparse
import csv
import logging
import time
import urllib.error
import urllib.request
from pathlib import Path

from pydantic import BaseModel

logger = logging.getLogger(__name__)

DATASET_URL = "https://s3.amazonaws.com/openneuro.org/ds000102"
TEMPLATE_URL = "https://templateflow.s3.amazonaws.com/tpl-MNI152NLin2009cAsym"
TEMPLATE_T1 = "tpl-MNI152NLin2009cAsym_res-01_T1w.nii.gz"
TEMPLATE_MASK = "tpl-MNI152NLin2009cAsym_res-01_desc-brain_mask.nii.gz"
SUBJECTS: tuple[str, ...] = ("08", "01", "02", "03")
RUNS: tuple[int, ...] = (1, 2)
CONDITIONS: tuple[str, ...] = ("congruent", "incongruent")
STIMULUS_COLUMN = "Stimulus"
ATTEMPTS = 5


class DataConfig(BaseModel):
    """Inputs of the download."""

    data_dir: Path
    subjects: list[str] = list(SUBJECTS)


def bold_name(subject: str, run: int) -> str:
    """Name of a functional run.

    Args:
        subject: Subject number such as ``08``.
        run: Run number.

    Returns:
        File name of the BOLD series.
    """
    return f"sub-{subject}_task-flanker_run-{run}_bold.nii.gz"


def anat_name(subject: str) -> str:
    """Name of the T1 anatomy.

    Args:
        subject: Subject number.

    Returns:
        File name of the T1.
    """
    return f"sub-{subject}_T1w.nii.gz"


def timing_name(subject: str, condition: str) -> str:
    """Name of a stimulus timing file.

    Args:
        subject: Subject number.
        condition: Condition from :data:`CONDITIONS`.

    Returns:
        File name of the timing file.
    """
    return f"sub-{subject}_{condition}.1D"


def subject_urls(subject: str) -> list[tuple[str, str]]:
    """List the files of one subject.

    Args:
        subject: Subject number.

    Returns:
        (URL, file name) pairs.
    """
    base = f"{DATASET_URL}/sub-{subject}"
    files = [(f"{base}/anat/{anat_name(subject)}", anat_name(subject))]
    for run in RUNS:
        for name in (bold_name(subject, run), f"sub-{subject}_task-flanker_run-{run}_events.tsv"):
            files.append((f"{base}/func/{name}", name))
    return files


def timing_line(events: str, condition: str) -> str:
    """Onsets of one condition in one run.

    Args:
        events: Text of a BIDS events file (tab-separated, with header).
        condition: Value of the ``Stimulus`` column.

    Returns:
        Onsets separated by spaces.

    Raises:
        ValueError: If the file has no ``Stimulus`` column or no onset of the condition.
    """
    rows = list(csv.DictReader(events.splitlines(), delimiter="\t"))
    if not rows or STIMULUS_COLUMN not in rows[0]:
        raise ValueError(f"events file without a '{STIMULUS_COLUMN}' column")
    onsets = [row["onset"] for row in rows if row[STIMULUS_COLUMN] == condition]
    if not onsets:
        raise ValueError(f"no '{condition}' trials")
    return " ".join(onsets)


def _download(url: str, target: Path) -> None:
    """Fetch a file unless it exists, retrying transient failures.

    Args:
        url: Source URL.
        target: Destination file.

    Raises:
        urllib.error.URLError: If every attempt fails.
    """
    if target.exists():
        return
    for attempt in range(1, ATTEMPTS + 1):
        try:
            logger.info("Downloading %s", url)
            with urllib.request.urlopen(url, timeout=300) as response:
                data = response.read()
            target.with_suffix(".part").write_bytes(data)
            target.with_suffix(".part").replace(target)
            return
        except urllib.error.URLError:
            if attempt == ATTEMPTS:
                raise
            time.sleep(2**attempt)


def fetch(config: DataConfig) -> None:
    """Download the template and the subjects and write the timing files.

    Args:
        config: Data directory and subjects.
    """
    config.data_dir.mkdir(parents=True, exist_ok=True)
    for name in (TEMPLATE_T1, TEMPLATE_MASK):
        _download(f"{TEMPLATE_URL}/{name}", config.data_dir / name)
    for subject in config.subjects:
        for url, name in subject_urls(subject):
            _download(url, config.data_dir / name)
        for condition in CONDITIONS:
            lines = [
                timing_line(
                    (
                        config.data_dir / f"sub-{subject}_task-flanker_run-{run}_events.tsv"
                    ).read_text(encoding="utf-8"),
                    condition,
                )
                for run in RUNS
            ]
            (config.data_dir / timing_name(subject, condition)).write_text(
                "\n".join(lines) + "\n", encoding="utf-8"
            )


def main() -> None:
    """Command line entry point."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--subjects", nargs="+", default=list(SUBJECTS))
    fetch(DataConfig(**vars(parser.parse_args())))


if __name__ == "__main__":
    main()
