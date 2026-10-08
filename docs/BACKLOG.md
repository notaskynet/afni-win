# Backlog

Work agreed on but not scheduled. Each item names where its background is.

## QC report of `afni_proc.py` (scripting phase S5)

The QC report (APQC) is off in the Windows pipeline (`-html_review_style none`, `docs/DECISIONS.md` D34).

- **Why:** every QC style draws its images with `@chauffeur_afni`, which starts its own `Xvfb` and the X11/Motif `afni` GUI with driver commands (`docs/inventory/scripts-REPORT.md`, finding U6). MSYS2 has no X11, Motif or X server.
- **To research:** build the `afni` GUI and `Xvfb` under Cygwin/X, check whether Cygwin has the X libraries and Motif, and find out how `@chauffeur_afni` would reach them from the native/MSYS2 environment.
- **Done when:** the QC report of the reference pipeline (`tests/pipeline`, `afni_proc.py` with `-html_review_style pythonic`) is produced on Windows and matches the Linux report.
- **Cost:** about 3100 more process starts per subject (scripts-REPORT section 3).
