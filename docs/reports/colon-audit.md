# Audit: parsing of file names and variables at `:` (decision D14)

Upstream `AFNI_26.2.09`. Scope: `libmri` and the console programs in `manifests/programs-required.txt` and `programs-optional.txt` (GUI and SUMA excluded, except `suma_*.c` files that are part of `libmri`). Patch: `patches/0007` (section 7).

## 1. Method

1. Code search over the scope for `strchr/strrchr(…, ':')`, `strstr(…, ":")`, `== ':'`, `strtok(…, ":")`, `sscanf` formats containing `:`, and every string literal ending in `:` (`"1D:"`, `"tcp:"`, …): 155 call sites plus 45 distinct literal prefixes. Every site was classified by what it parses.
2. Empirical check under wine with the phase 1 build: datasets copied to `C:\data`, every relevant form of name used with `C:/…` and `C:\…` (section 4). Results under wine are preliminary (D17).

## 2. Lists of directories split at `:` — need the D14 macro

All use the same idiom: copy the variable, replace every `:` by a space, then `sscanf("%s")` word by word. A Windows value such as `C:\afni;D:\atlases` is cut into `C`, `\afni;D`, `\atlases`.

| Location | Function | Variables | Used by (in scope) |
|---|---|---|---|
| `thd_getpathprogs.c:154` | `THD_find_regular_file` | `PATH` or a caller-supplied list (atlas path) | `find_atlas_niml_file` → `AFNI_atlas_spaces.niml` lookup |
| `thd_getpathprogs.c:360` | `THD_getpathprogs` | `PATH` | `THD_find_executable` (e.g. `gzip`, `bzip2` for compressed datasets, `curl`, viewers) |
| `thd_opendset.c:97` | `Add_plausible_path` | `AFNI_R_PATH`, `AFNI_PLUGINPATH`, `AFNI_PLUGIN_PATH`, `PATH` | locating R scripts (`3dTsmoothR`, `toyR`; not in scope) |
| `thd_ttatlas_query.c:618` | `get_atlas_dirname` | `AFNI_ATLAS_PATH`, `AFNI_PLUGINPATH`, `AFNI_PLUGIN_PATH`, `PATH` (`get_env_atlas_path`, line 640) | atlas lookup (`whereami`, `3dROIstats` with atlas names, …) |
| `thd_ttatlas_query.c:719` | `get_atlas` | same | same |
| `thd_get1D.c:72` | `THD_get_many_timeseries` | `AFNI_TSPATH` or caller list | callers are GUI only (`afni.c`, `afni_func.c`) |
| `thd_get_tcsv.c:75` | `THD_get_many_tcsv` | `AFNI_TSPATH` or caller list | GUI only |
| `NLfit_model.c:250` | NLfit model directory scan | `AFNI_MODELPATH`, `AFNI_PLUGINPATH`, `PATH` | `3dNLfim`, `1dNLfit`, `3dTSgen` (optional) |
| `suma_utils.c:2021` | `SUMA_search_file` | caller list (`epath`) | part of `libmri`; SUMA-related file search |

Phase 1 already showed the effect: under wine `THD_getpathprogs` saw fewer directories than on Linux (phase 1 report, section 4.2).

## 3. Prefixes in file and dataset names — no change needed

Every prefix check is anchored at the start of the string and needs at least two specific characters before the `:` (or `://`), so a drive letter `C:` cannot match. Checked:

| Prefix | Where | Why `C:/…` / `C:\…` is safe |
|---|---|---|
| `3D:`, `3Ds:`, `3Dr:`, … | `mri_read.c:1234,1451,3066,5073`, `mcw_glob.c:873` | requires `name[0]=='3' && name[1]=='D'` |
| `3A:` | `mri_read.c:1239,1507,5079`, `mcw_glob.c:888` | requires `'3','A'` |
| `1D:` | `thd_1Ddset.c`, `mri_read.c`, `mri_fromstring.c`, `thd_table.c`, `3dcalc.c` and others | compared as a literal at the start of the name |
| `jRandomDataset:`, `jRandom1D:` | `thd_mastery.c:43` | literal prefix |
| `filelist:` | `thd_opendset.c`, `thd_mastery.c`, `thd_opentcat.c` | literal prefix |
| `3dcalc(` | `thd_mastery.c:70` | literal prefix, then the name inside is a normal name |
| `file:`, `str:`, `fd:`, `shm:`, `tcp:`, `stdin:`, `stdout:`, `stderr:` | `niml/niml_stream.c:985,1707`, `thd_iochan.c:637,715`, output `-prefix stdout:` | literal prefixes of ≥ 2 letters |
| `http://`, `ftp://` | `thd_http.c:137,819`, `niml/niml_url.c:96,298` | `://` after the scheme; host/port parsing only after it |
| `RL: LR: AP: PA: IS: SI: VEC: UNI: FAC:` | `mri_nwarp.c:6568-6655` (warp specs) | two- or three-letter codes; the optional scale factor is taken only if the next character is numeric (`isnumeric(*up)`, line 6604), so `RL:C:/w.nii` works |
| `SYM:` | `3dDeconvolve.c:10559`, `3dREMLfit.c:429` | literal |
| `D:`, `d:` | `edt_geomcon.c:49` | inside geometry strings after `XYZ:`, never a file name |

Other `:` uses are not file names: sub-brick ranges `[a:b]` (`thd_intlist.c:367,653`), box ranges `-xbox a:b` (`3dmaskdump.c:252`, `thd_makemask.c:828`), stat specs (`3dLocalstat.c:44`), `3dQwarp` level syntax (`3dQwarp.c:2374,2414`), ROI strings (`thd_ttatlas_query.c:3369`), `3dAllineate` options (`3dAllineate.c:5475`), `3dttest++` labels (`3dttest++.c:2820`).

`mri_nwarp.c:6860` sends a warp name containing `:` (or `(`) to the general parser instead of the single-dataset shortcut. With `C:/…` it still works (checked below), only via the longer path.

## 4. Empirical results (wine)

| Command (data in `C:\data`) | Result |
|---|---|
| `3dinfo -n4 C:/data/rnd+orig` / `C:/data/rnd+orig.HEAD` / `C:/data/rnd.nii.gz` | correct |
| `3dinfo -n4 C:\data\rnd.nii.gz` | correct |
| `3dinfo -nv 'C:/data/rnd+orig[1..3]'`, same with `C:\data\…` | correct (3) |
| `3dinfo -n4 'C:/data/rnd+orig[0]{1..2}'` | correct |
| `3dinfo -n4 'C:/data/*.HEAD'` (glob) | correct |
| `1deval -a C:/data/x.1D`, `'C:/data/x.1D[1]'`, `'C:\data\x.1D{1}'` | correct |
| `1dcat 'C:/data/x.1D[0]' 'C:\data\x.1D[2]'` | correct |
| `3dcalc -a '3dcalc( -a C:/data/rnd+orig -expr 2*a )' …` | input read correctly |
| `3dNwarpApply -nwarp C:/data/zwarp.nii …` and `-nwarp 'RL:C:/data/zwarp.nii[0]'` | correct, output written to `C:/data/` |
| **`3dcalc … -prefix C:/data/out1`** | **fails**: `cannot mkdir new directory: ./C:/data/` |
| **`3dcalc … -prefix C:/data/out3.nii`** | **fails**: `cannot open output file './C:/data/out3.nii'` |
| **`3dcalc … -prefix C:\data\out2`** | **fails**: `failed (2) to open file ./C:\data\out2+orig.HEAD` |
| **`3dTcat … 'C:\data\rnd+orig[1]'`**, **`3dinfo '3dcalc( -a C:\data\rnd+orig …)'`** | **fails**: header is read, data is not: `have no warp but have no data on disk` |
| `3dinfo -prefix C:\data\rnd+orig` | prints `C:\data\rnd` instead of `rnd` |

## 5. Conclusion

- **No name is mistaken for a prefix** because of a drive letter, neither with `C:/` nor with `C:\`.
- **`:` as a list separator**: the 9 sites in section 2 need the D14 macro. They can be patched with one macro as decided.
- **Two problems that are not about `:`** but make Windows paths fail, found during the empirical check:
  1. **Absolute paths are recognised only by a leading `/`.** `thd_initdkptr.c:43` (`if( prefixname[0] == '/' ) ld = 0 ;`) decides whether `-prefix` is relative to the session directory; `C:/data/out` is treated as relative and becomes `./C:/data/out`. Same pattern: `thd_loaddblk.c:648`, `thd_getpathprogs.c:221`, `3dttest++.c:3708`, `1dTrdm.c:305`, `3dRSA.c:3004,3068`, `suma_utils.c:1183`.
  2. **`\` is not a directory separator.** Directory and prefix are split at the last `/` (`thd_initdkptr.c:41`, `thd_initprefix.c:59`, `THD_trailname`, `THD_filehaspath` and others). With `C:\data\rnd+orig` the header opens (the name is passed to `fopen` unchanged), but the `.BRIK` path is rebuilt from a wrong directory (`./`), and output prefixes with `\` cannot be written.

## 6. Decisions needed

1. Confirm the D14 patch scope: the 9 sites in section 2, separator macro `;` under `_WIN32`.
2. Absolute paths (5.1): add a second macro to the same patch, e.g. `THD_IS_ABSPATH(p)` = `p[0]=='/'` or, under `_WIN32`, a drive letter followed by `:` and `/` or `\`. Without it, `-prefix C:/…` does not work in most programs.
3. Backslashes (5.2): (a) document that paths must use `/` (Windows accepts `C:/…` everywhere); (b) convert `\` to `/` in the layer, e.g. in `argv` at program start — this changes every argument, including expressions, and is not recommended; (c) patch every place that splits at `/` — many call sites, large patch. Recommendation: (a).

## 7. Decisions taken

1. D14 confirmed: the 9 sites in section 2 split at `THD_PATH_LIST_SEP` (`;` under `_WIN32`).
2. `THD_IS_ABSPATH()` added to the same patch and used at the 8 sites in section 5.1 (`thd_initdkptr.c:43`, `thd_loaddblk.c:648`, `thd_getpathprogs.c:221`, `3dttest++.c:3708`, `1dTrdm.c:305`, `3dRSA.c:3004,3068`, `suma_utils.c:1183`).
3. Backslashes (D20): option (a), paths must use `/`.

Checks of `patches/0007`: patches 0001-0007 apply in order to `AFNI_26.2.09` with `git apply --3way`; the patched tree builds on Linux (`libmri`, `3dcalc`, `3dinfo`, `3dTstat`, `3dttest++`, `3dRSA`, `1dTrdm`) without new warnings and the smoke scenario passes; the `_WIN32` and non-`_WIN32` forms of the macros were tested separately. `NLfit_model.c` is not part of the upstream CMake build (it needs X11 headers), so its one-line change is not compiled. Not yet checked on Windows.

Remaining finding, not covered by the patch: `SUMA_ParseFname` (`suma_utils.c:1070,1077`) rejects a working directory that does not start with `/`. On Windows `getcwd()` returns `C:\...`, so the function returns `NULL` when called without an explicit working directory.
