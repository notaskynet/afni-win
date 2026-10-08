# Research report S0: the AFNI scripting layer on Windows

Upstream `AFNI_26.2.09`. Question: what is needed so that a user can run the standard script-based workflow (`afni_proc.py` and the scripts it calls) on Windows, and which of the strategies A, B, C to follow. This phase changes no release code: the prototype is a separate workflow (`.github/workflows/scripts-prototype.yml`) and two build options that are off by default.

## 1. Method

| Source | What |
|---|---|
| Upstream code | tag cloned into a temporary directory; counts below are from the code (paths and lines given) |
| Linux trace | full upstream CMake build on Ubuntu 24.04 (`COMP_GUI`, `COMP_SUMA`, `COMP_PYTHON`, `COMP_TCSH` on), `afni_proc.py` run on one real subject under `strace -f -e execve`; every process start was recorded |
| Data | OpenNeuro `ds000102` (Flanker task), subject `sub-08`: T1, two BOLD runs of 146 volumes, events (licence PDDL, public domain); template `MNI152NLin2009cAsym` from TemplateFlow (S3). AFNI Bootcamp data are on `afni.nimh.nih.gov`, which has no stated data licence and was not reachable from the research machine (section 9) |
| Pipeline | `tests/scripts/run_ap.tcsh`: blocks `tshift align tlrc volreg blur mask scale regress`, two stimulus classes and one GLT, motion and outlier censoring, ACF blur estimates, `3dClustSim`. The traced run also made the QC report (`-html_review_style pythonic`) |
| Prototype (CI) | `scripts-prototype.yml`: same pipeline on the official Linux CMake build and on the afni-win Windows build, MSYS2 `tcsh` and utilities, native AFNI programs; process start benchmark (`tests/scripts/bench_spawn.tcsh`); comparison with `tests.regression.compare` |

## 2. What the scripting layer is

Installed by upstream CMake (`COMP_TCSH`, `COMP_PYTHON`, `COMP_RSTATS`):

| Kind | Count | Where |
|---|---|---|
| tcsh scripts | 186 | `src/scripts_install` (`#!/usr/bin/env tcsh` or `#!/bin/tcsh`) |
| Python scripts | 65 + 3 | `src/python_scripts/scripts`, 3 in `scripts_install`; library `afnipy` (88 modules) |
| perl scripts | 2 | `3dPAR2AFNI.pl`, `suma_change_spec` |
| R programs | 22 `.R` + 23 tcsh launchers | `src/R_scripts`, `src/scripts_for_r`; only with `COMP_RSTATS` (default off) |

The whole source tree has 573 files with a `#!` line (298 tcsh, 163 Python, 21 R, 53 sh, 28 bash, 5 csh, 2 perl); the sh/bash ones are mostly the build system of the vendored `gts`.

## 3. What a standard pipeline actually runs

Successful process starts in the traced Linux run (`strace`, 46 min with one OpenMP thread):

| | Pipeline (proc script) | QC report (APQC) | Total |
|---|---|---|---|
| All processes | 1327 | 3141 | 4468 |
| AFNI C programs | 292 | 591 | 883 |
| AFNI tcsh scripts | 120 | 186 | 306 |
| AFNI Python scripts | 34 | 108 | 142 |
| `tcsh` / `sh` interpreters | 131 / 43 | 186 / 238 | 598 |
| POSIX utilities | 705 | 1832 | 2537 |

- **AFNI C programs in the pipeline**: 52 different ones (`tests/scripts/ap-programs.txt` plus `afni`, `1dplot`, `3dSkullStrip`, `count_afni`, `whereami_afni`); 15 of them are not in `manifests/programs-required.txt`.
- **POSIX utilities in the pipeline**: `sed` 157, `ls` 121, `cut` 71, `grep` 63, `awk` 55, `dirname` 54, `rm` 48, `cat` 36, `wc` 22, `tee` 20, `tail` 12, `mkdir`, `basename`, `cp`, `touch`, `printf`, `mv`, `expr`, `tr`, `date`, `ps`, `seq`, `rmdir`, and `cjpeg` (from `1dplot -jpg`).
- **Additionally in QC**: `seq` 323, `bc` 312, `perl` 102 (`perl -nl -MPOSIX -e 'print floor($_);'` in `@djunct_montage_coordinator`), `sort`, `uniq`, `fmt`, `chmod`, `sleep`, `Xvfb` 17, `xkbcomp` 31, `cjpeg` 42, `djpeg`, and the `afni` GUI 83 times.
- Most utility calls come from small helper scripts called per dataset (`@GetAfniPrefix` 37, `@GetAfniView` 33, `@parse_afni_name`, `@CheckForAfniDset`, `@global_parse` 95, `@djunct_slice_space` 51): every call costs a `tcsh` start plus several `sed`/`ls`/`cut` processes.

The pipeline needs no GNU-only option found so far; the utility set is that of a POSIX userland (the MSYS2 base set covers all of it, including `perl` and `bc`).

## 4. Findings in upstream itself (also on Linux)

| # | Finding | Evidence | Consequence |
|---|---|---|---|
| U1 | The upstream CMake build does not build `count_afni`, which every `afni_proc.py` script calls (`set runs = (\`count_afni -digits 2 1 2\`)`), nor 12 other programs that `src/Makefile.INCLUDE` builds: `p2dsetstat` (APQC), `dsetstat2p`, `whereami_afni`, `3dmaxdisp`, `3dDiff`, `3dCompareAffine`, `3dBallMatch`, `3dEdu_01_scale`, `get_afni_model_PRF_DN`, `imcat`, `gifti_tool`, `cifti_tool` | `Makefile.INCLUDE:118,217,251,977`; no CMake reference to these names | A CMake build cannot run an `afni_proc.py` script. Prototype: `cmake/afni-extra-programs.cmake` (`AFNI_WIN_EXTRA_PROGRAMS`, off by default) |
| U2 | `src/ptaylor` (`3dClusterize`, `3dNetCorr`, `3dTrackID`, ...) is added only with `COMP_SUMA` (X11, Motif, OpenGL), although these are console programs that need only `libmri` and GSL. `3dClusterize` is called by `@radial_correlate`, which `afni_proc.py` runs by default | `src/CMakeLists.txt:125-129`, `src/ptaylor/CMakeLists.txt:18-60` | Same hook, `AFNI_WIN_PTAYLOR` (off by default) |
| U3 | Dataset names with a space or any byte ≥ 128 (Cyrillic) are rejected unless `AFNI_ALLOW_ARBITRARY_FILENAMES=YES` | `thd_filestuff.c:647-658` | Linux run in a Cyrillic directory: `3dcopy` fails ("Illegal old dataset name"); with the variable the whole pipeline passes (exit 0, 2065 s) |
| U4 | `afni_proc.py` builds shell commands without quotes, e.g. `'3dinfo -%s %s' % (val, dname)` | `afnipy/afni_util.py:1507` | A path with a space fails already in `afni_proc.py` on Linux (`3dinfo -d3: cannot get val list`); the variable of U3 does not help. Generated scripts also use unquoted `$var` everywhere |
| U5 | Every proc script starts with `afni -ver`; with `tcsh -e` a missing `afni` program stops it | `afni_proc.py:3288-3300` | Needs the GUI program or `-check_afni_version no` |
| U6 | APQC (default style `pythonic`; the help text still says `basic`) always uses `@chauffeur_afni`, which starts its own `Xvfb` and the `afni` GUI with driver commands; `afni_proc.py` silently drops the QC report if `Xvfb` is not on `PATH` | `afni_proc.py:1243, 3894-3904`; `@chauffeur_afni:1264-1275, 2368-2422, 2755-2776` | No QC report without an X server and the X build of `afni` |
| U7 | `3dSkullStrip` is part of SUMA (built only with X11/Motif/OpenGL headers and libraries), but uses no display at run time | `src/SUMA/CMakeLists.txt:127,168-180`; no `gl*`/`XOpenDisplay` in `SUMA_3dSkullStrip.c`, `SUMA_BrainWrap.c` | Reached by `align_epi_anat.py` and `@auto_tlrc` whenever the anatomy has its skull (the default), and by `@SSwarper` |
| U8 | `1dplot` (C) is built only with `COMP_GUI`; `3dFWHMx -ACF` and the proc script call it for images; image output needs `cjpeg`/`pnmtopng` on `PATH` | `CMakeLists_binaries.txt:494-546`; traced run: "missing program pnmtopng" | Images missing but not fatal (the calls are not status-checked) |

## 5. Interfaces between the scripts and Windows

### 5.1 How the pieces start each other

| From | To | Mechanism | On Windows (strategy A) |
|---|---|---|---|
| proc script (tcsh) | AFNI program, utility, script | `fork`/`exec`, `#!` line | MSYS2 `tcsh` emulates `fork`; `#!` handled by the MSYS2 runtime; arguments converted to Windows paths for native programs |
| tcsh | Python script | `#!/usr/bin/env python` | `env` finds the UCRT64 `python` |
| Python (`afnipy`) | commands | `shell=True` (18 places), `os.system` (17), `os.popen` (1), all through `afni_base.shell_exec2`/`simple_shell_exec` except a few | native Python on Windows uses `cmd.exe`: single quotes, `$var`, backticks, tcsh scripts do not work |
| Python | tcsh | `tcsh -cf "cmd"` hard-coded in `afni_util.exec_tcsh_command` (13 callers) | works only if `tcsh` is on `PATH` |
| AFNI C program | shell | `system`/`popen` | busybox `sh` from the package (D22) |
| R launchers (tcsh) | R | `R --slave --file=...`; `AFNIio.R` exits if `R_io.so` (a C library built against R) cannot be loaded | needs R, `R_io.dll`, CRAN packages (`afex`, `phia`, ...) |

### 5.2 Generated code is tcsh

`afni_proc.py` writes tcsh text from Python string literals (no abstraction; 37 `db_cmd_*` functions in `afnipy/db_mod.py`, e.g. 58 `foreach`, 90 `$run`, 19 backtick commands, 11 `|&`), and has no other output language (`-bash` is obsolete, `afni_proc.py:1473, 3270`). `-execute` runs `tcsh -xef proc ... | tee` through `os.system` (`afni_proc.py:5070`). `gen_ss_review_scripts.py` writes `@ss_review_basic` and `@ss_review_driver` in tcsh. Strategy C therefore means a second implementation of the code generator (about 10 000 lines in `db_mod.py`) or translating its output, plus the 120 tcsh helper calls of a run.

### 5.3 Paths, names, encodings

- MSYS2 converts POSIX paths in arguments of native programs (`/d/a/x` → `D:/a/x`) and in `PATH`; arguments that only look like paths can be changed too, and `MSYS2_ARG_CONV_EXCL` can exclude patterns. The prototype pipeline (sub-brick selectors, `-expr`, `-gltsym 'SYM: ...'`, `'BLOCK(2,1)'`) needed no exclusion; the design matrix written on Windows is identical to Linux, including the recorded command line.
- AFNI programs accept `D:/a/x` (D14, D20); `\` is not a separator (D20).
- Non-ASCII names: rejected by upstream (U3). With the variable set, Windows adds one more problem: native programs receive `argv` in the ANSI code page, so characters outside it (Cyrillic on a non-Russian system) become `?`. A UTF-8 `activeCodePage` manifest in every `.exe` would fix that at layer level; not done in this phase.
- Spaces: fail upstream (U4), on Linux as well.

## 6. Prototype of strategy A (CI)

`scripts-prototype.yml`, GitHub `windows-latest` (Windows Server 2025), MSYS2 `tcsh` 6.24.16, msys2-runtime 3.6.10, UCRT64 Python 3.14 with numpy/matplotlib; AFNI programs from the afni-win build (53 required + the 18 programs of `ap-programs.txt` and `EXTRA_PROGRAMS`, built with `AFNI_WIN_EXTRA_PROGRAMS` and `AFNI_WIN_PTAYLOR`, all 10 existing patches, no new patch). Same inputs on both platforms: the anatomy is skull-stripped once on Linux (U7), and `-check_afni_version no` (U5) and `-html_review_style none` (U6) are given on both.

### 6.1 Does it run

| Variant | Python shell commands go to | Result |
|---|---|---|
| `cmd-shell` | `cmd.exe` (native Python as is) | **fails** after ~50 s in `align_epi_anat.py`: `'\rm' is not recognized as an internal or external command`, then `3dbucket ... vr_base_min_outlier+orig'[0]'` gets the quote characters (`can't open dataset ./vr_base_min_outlier+orig'`) and the script stops with a Python traceback |
| `posix-shell` | MSYS2 `sh` through `tests/scripts/pyshim/sitecustomize.py` (replaces `subprocess.Popen(shell=True)`, `os.system`, hence `os.popen`; loaded from `PYTHONPATH`, no upstream change) | **passes**: exit code 0, all blocks, `@ss_review_basic` |
| `posix-shell-defender` | same, Defender real-time protection switched on (`RealTimeProtectionEnabled True`) | **passes**, exit code 0 |

Review summary (`out.ss_review.sub08.txt`) printed by the runs:

| | Linux | Windows posix-shell | Windows posix-shell-defender |
|---|---|---|---|
| TRs censored | 4 | 4 | 4 |
| TSNR average | 131.115 | 131.086 | 131.086 |
| GCOR | 0.0725989 | 0.0725823 | 0.0725823 |
| anat/EPI mask Dice | 0.82494 | 0.825125 | 0.825125 |
| anat/template mask Dice | 0.879912 | 0.879912 | 0.879912 |
| maximum F (masked) | 52.2855 | 52.2735 | 52.2735 |
| ACF blur | 0.831795 3.53683 14.7841 | 0.831847 3.53718 14.7868 | 0.831839 3.53717 14.7863 |

The two Windows runs agree with each other to the printed digits except the ACF fit, which upstream does not make reproducible (D29: `powell_int.c` reseeds from `time()+getpid()`). Windows vs Linux: relative differences up to 4·10⁻⁴ (TSNR, F, Dice, ACF), the size expected from the registration chain (D29 class "iterative optimisation", 1e-2). Voxel-wise comparison: section 6.3.

### 6.2 Time

Process start cost from `tcsh` (`bench_spawn.tcsh 200`, ms per call; ranges over the CI runs, each on its own hosted runner):

| | Linux (2 runners) | Windows, Defender off (5 runners) | Windows, Defender on (2 runners) |
|---|---|---|---|
| POSIX utility (`true`) | 0.80 | 10.7 – 17.0 | 13.7 – 19.6 |
| native AFNI program (`ccalc`) | 1.70 | 15.9 – 21.8 | 22.0 – 32.8 |
| tcsh script (`@GetAfniView`) | 13.7 – 13.9 | 62.6 – 90.7 | 70.0 – 101.7 |
| `python -c pass` | 17.0 | 36.4 – 54.1 | 41.7 – 59.3 |

Whole proc script, one OpenMP thread, wall time in seconds. Linux and Windows of the same CI run started at the same time on different hosted runners:

| CI run | Linux | Windows posix-shell | Windows posix-shell-defender | Ratio |
|---|---|---|---|---|
| 37786514059 | 1045 | 1089 | | 1.04 |
| 37793673956 | ≈ 690 (step time) | | 846 | ≈ 1.2 |
| 37796401113 | 1047 | 1386 | 1445 | 1.32 / 1.38 |

- A process start costs about 6–20 times more on Windows for small programs and 2–4 times more for Python, but this pipeline starts only 1327 processes; with the measured differences that adds about 20–30 s to a run of 700–1450 s. Most of the measured difference therefore comes from the programs themselves and from runner variation (Linux alone: 690–1047 s for the same work).
- Ratio Windows/Linux within the same CI run: 1.04–1.38.
- Defender real-time protection (no exclusions), in the run that had both variants: start cost +10 % to +60 % (largest for native programs), whole pipeline +4 % (1445 vs 1386 s).
- The QC report would add 3141 process starts (about 60 s more by the same estimate) if it could run (U6).

### 6.3 Voxel-wise comparison

13 outputs of the run (`run_pipeline.sh`) compared with `tests.regression.compare` and `tests/scripts/tolerance.json`: every output is downstream of the EPI/anatomy registration, so the whole pipeline uses the D29 class "iterative optimisation" (`rtol 1e-2`, `atol 1e-2`·max); the ACF blur estimate is informational (not reproducible upstream). Workflow `scripts-recompare.yml` on the artifacts of CI run 37796401113; both Windows variants give the same table.

| Output | Result | Values beyond tolerance |
|---|---|---|
| `X.xmat.1D`, `dfile_rall.1D`, `motion_sub08_enorm.1D`, `censor_sub08_combined_2.1D`, `anat_final` | identical | 0 |
| `mat.basewarp.aff12.1D` (EPI→anatomy affine), `out.gcor.1D`, `blur_est` | within | 0 (matrix elements up to 0.012 apart) |
| `stats.sub08` | values beyond | 445 of 3 112 960 (0.014 %), max abs 17.6 |
| `TSNR.sub08` | values beyond | 82 of 311 296 (0.026 %) |
| `final_epi_vr_base_min_outlier` | values beyond | 63 of 311 296 (0.020 %) |
| `mask_epi_anat.sub08` | voxels differ | 55 of 311 296 (0.018 %) |
| `out.ss_review.sub08.txt` | numbers within | the only text difference is `AFNI package : Linux_cmake` / `Windows_cmake` |

- The cause is one step: `align_epi_anat.py` (`3dAllineate`, `lpc+ZZ`) stops at a slightly different point on Windows (largest matrix element difference 0.012); everything registered with it differs at brain edges. Everything before the registration and the anatomy-to-template path are bit-identical. This is the effect seen in phase 5 (D29), now on real data.
- Linux against Linux (two local runs, same inputs): all datasets bit-identical; only the `3dClustSim` tables (`AFNI_CLUSTSIM_*` attributes of `stats`) and the ACF blur estimate differ, so these are excluded from the platform comparison. `stats` also carries those attributes on Windows (`AFNI_CLUSTSIM_*`, `MDFCURVE_*`).
- A tolerance for the pipeline as a whole therefore needs a rule for the fraction of voxels beyond the class tolerance (here < 0.03 %), not only per-value tolerances; `tests.regression.compare` has no such rule yet.

### 6.4 Strategy B probe

tcsh has its own native Windows port (`win32/`, MSVC, `WINNT_NATIVE`, `fork` emulated in `win32/fork.c` "based on the ideas used by cygwin"). With tag `TCSH6_24_16` it does not build as distributed: `patchlevel.h` is not generated by `Makefile.win32`, and after generating it the link fails on `fmalloc`/`ffree`/`frealloc` (the port's allocator), also with `HAVE_WORKING_SBRK` defined. Its fast path without `fork` (`nt_try_fast_exec`, `sh.sem.c:103-117`) is used only for interactive shells (`intty || intact`); scripts go through the emulated `fork` like in MSYS2. The probe was stopped there.

## 7. Strategies against the criteria

| Criterion | A: MSYS2 tcsh + POSIX tools, native programs | B: native tcsh | C: no tcsh |
|---|---|---|---|
| 1 `afni_proc.py` pipeline from a command prompt | **shown** (6.1), with the shell shim, U1/U2 targets, a launcher for scripts (7.1) | needs a working native tcsh (6.4) plus native POSIX utilities (busybox-w32 has them) | needs a second implementation of `afni_proc.py`'s output and of the ~120 tcsh helper calls per run (5.2) |
| 2 results match Linux | review values within 4·10⁻⁴; voxel-wise < 0.03 % of values beyond the registration class (6.3) | same programs, same expected result | same programs, same expected result |
| 3 QC report | blocked by U6 in every strategy: needs the X build of `afni` and an X server; MSYS2 has no X11/Motif (`MINGW-packages`/`MSYS2-packages` have no `motif`, `libx11`, `xorg-server` build files) | same | same |
| 4 spaces, Cyrillic | Cyrillic: upstream needs `AFNI_ALLOW_ARBITRARY_FILENAMES=YES` (U3), plus a UTF-8 code-page manifest for native programs (5.3); spaces: fail upstream (U4) in any strategy | same | could quote correctly, but only in the reimplemented generator |
| 5 group analysis | `3dttest++` works (phase 5); `3dMVM` and other R programs need R (MSYS2 `mingw-w64-r` exists), `R_io.dll` and CRAN packages; not prototyped | same | same |
| 6 time vs Linux | 1.04–1.38 within the same CI run (6.2) | no gain for scripts: `fork` is emulated there too (6.4) | fewer processes, but only for the reimplemented part |
| Cost / upstream drift | low: no change to upstream scripts; MSYS2 runtime and packages shipped with the release | high: maintaining a tcsh port | very high: permanent second implementation of a moving generator |

### 7.1 What strategy A still needs

1. **Distribution**: ship a minimal MSYS2 runtime (`msys-2.0.dll`, `tcsh`, `sh`/`bash`, coreutils, `sed`, `grep`, `gawk`, `perl`, `bc`, `which`, `env`) and Python (UCRT64, numpy, matplotlib) with the release, or require MSYS2 and install from it. Licences: msys2-runtime (Cygwin) is LGPLv3, the tools GPL; source offer needed.
2. **Entry points**: `cmd.exe`/PowerShell cannot run `#!` scripts; scripts are started from an "AFNI shell" (MSYS2 `tcsh`/`bash` window with the environment), or through generated `.cmd` launchers (`tcsh -f path/script %*`, `python path/script.py %*`).
3. **Python shell commands**: the shim of the prototype (or the same as a `.pth`/`sitecustomize` in the shipped Python).
4. **Build**: `AFNI_WIN_EXTRA_PROGRAMS` (at least `count_afni`, `p2dsetstat`, `whereami_afni`) and `AFNI_WIN_PTAYLOR` in the release build; the 15 programs of `ap-programs.txt` not yet in the required list.
5. **GUI-only programs**: `3dSkullStrip` (U7; X-free build needs a patch that separates it from the SUMA display code, or a CMake target of our own), `1dplot` images (U8, X-free like patch 0009 did for `3dDeconvolve`), `afni -ver` (U5).
6. **Encoding**: UTF-8 `activeCodePage` manifest for all programs; `AFNI_ALLOW_ARBITRARY_FILENAMES` set by the environment if Cyrillic paths are to be supported.
7. **QC** (criterion 3): needs a separate decision (section 8).
8. **R** (criterion 5): MSYS2 R, `R_io.dll` (C, against R's headers), CRAN packages; to be prototyped.

## 8. Recommendation

**Strategy A**, as prototyped: MSYS2 `tcsh` and POSIX tools for the scripts, native AFNI programs, native Python with the shell shim. It is the only strategy that already runs the standard pipeline end to end, with results matching Linux within the registration tolerance (6.3) and 1.04–1.38 times the Linux time (6.2), and it keeps upstream scripts unchanged. B gives no speed advantage for scripts and needs a tcsh port that does not build today; C is a permanent fork of the generator.

Criteria that no strategy meets without decisions outside this choice:

- **QC report (3)**: options are (a) build the `afni` GUI for Windows with an X11/Motif stack (not in MSYS2; Cygwin has an X server and X libraries, not verified here), (b) render QC images without the GUI, which upstream cannot do and would mean a large patch, (c) ship the QC as "not available" and accept `-html_review_style none`. Needs your decision.
- **Spaces in paths (4)**: fail upstream on Linux too (U4); fixing means patching `afnipy` quoting and the generated tcsh. Proposal: support non-ASCII (Cyrillic) paths, document that paths with spaces are not supported, as upstream.

Draft acceptance criteria for the implementation phases:

1. `ds000102` `sub-08` pipeline of `tests/scripts/run_ap.tcsh` (and the AFNI Bootcamp `FT` example once its data terms are settled) runs from the installed package, started from the AFNI shell and from `cmd.exe` through the launcher.
2. Voxel-wise comparison with the Linux run of the same CI run: per value the D29 class of the registration chain (`rtol 1e-2`, `atol 1e-2`·max), and at most 0.1 % of the values of each dataset beyond it (measured: < 0.03 %); `3dClustSim` tables and ACF estimates informational; review values printed by `@ss_review_basic` within `rtol 1e-2`.
3. A data directory with Cyrillic characters works with `AFNI_ALLOW_ARBITRARY_FILENAMES=YES`.
4. Wall time at most 1.5 × the Linux time of the same CI run (measured 1.04–1.38, 6.2).
5. Group analysis: `3dttest++` (done) and `3dMVM` on the outputs of several subjects, if R is in scope.

## 9. Open points

- AFNI Bootcamp data: no stated licence; `afni.nimh.nih.gov` not reachable from the research machine, reachable from GitHub runners. The prototype uses OpenNeuro `ds000102` (public domain) instead.
- `afni -ver` at the start of every proc script (U5): the GUI program is not built; to be resolved in S1 (no silent stub).

## 10. Decisions and plan

Confirmed (D34): strategy A; QC report later (Cygwin/X research phase); R in scope together with the pipeline; Cyrillic paths supported, paths with spaces not supported (clear error); CI reference data `ds000102` `sub-08`.

| Phase | Content | Done when |
|---|---|---|
| S1 Programs | release build with `AFNI_WIN_EXTRA_PROGRAMS` (`count_afni`, `p2dsetstat`, `whereami_afni`, ...) and `AFNI_WIN_PTAYLOR`; the 15 pipeline programs of `tests/scripts/ap-programs.txt` required; X-free `3dSkullStrip` and `1dplot` image output; `afni -ver` (U5); UTF-8 code-page manifest for all programs | all pipeline programs build in CI; `3dSkullStrip` result matches Linux; the pipeline runs without the shared pre-stripped anatomy |
| S2 Scripting runtime | package and installer carry a minimal MSYS2 userland (`tcsh`, `sh`, coreutils, `sed`, `grep`, `gawk`, `perl`, `bc`), UCRT64 Python with numpy and matplotlib, `afnipy`, the upstream scripts and the shell shim; AFNI shell and `.cmd` launchers for scripts; environment (`AFNI_ALLOW_ARBITRARY_FILENAMES`, space check); licences and source offer | `afni_proc.py` and the proc script run from the installed package, from the AFNI shell and from `cmd.exe` |
| S3 R | R (MSYS2 `mingw-w64-r`), `R_io.dll`, CRAN packages of the R programs; `3dMVM`, `3dLMEr` | R programs run from the package and match Linux |
| S4 Acceptance in CI | pipeline from the installed package vs Linux with the criteria of section 8 (fraction rule added to `tests.regression.compare`), Cyrillic data directory, group analysis (`3dttest++`, `3dMVM`) on several subjects, time ratio | all criteria pass in `build-windows.yml` |
| S5 QC report (later) | research: `afni` GUI under Cygwin/X for `@chauffeur_afni` | separate decision |
