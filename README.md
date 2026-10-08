# afni-win

Native Windows builds of [AFNI](https://afni.nimh.nih.gov/), the toolkit for analysing functional and structural brain MRI, from unmodified upstream sources.

afni-win does not fork AFNI. For every upstream release tag it fetches the official source code, adds a small POSIX compatibility layer for Windows and a handful of minimal patches, builds the command-line programs with MinGW-w64 (MSYS2 UCRT64), checks their results against the official Linux build of the same tag, and publishes an installer.

## For users

### Install

1. Open the [Releases](https://github.com/notaskynet/afni-win/releases) page and download `afni-<version>-win64-setup.exe` from the newest release.
2. Run it. Windows may show *"Windows protected your PC"* because the installer is not code-signed: choose **More info → Run anyway**.
3. Follow the wizard. Administrator rights are not needed; keep **Add AFNI to PATH** selected.

Requirements: 64-bit Windows 10 or 11.

### Use

Open the Start menu and choose **AFNI Command Prompt**. AFNI programs work in that window:

```bat
cd /d C:\Users\YourName\Documents\mri
3dinfo anat+orig
3dcalc -a anat+orig -expr "a*2" -prefix doubled
```

With *Add AFNI to PATH* selected they also work in any new Command Prompt or PowerShell window.

Things to know:

- Write paths in AFNI commands with forward slashes: `C:/data/anat+orig`.
- Compressed datasets (`.BRIK.gz`, `.nii.gz`) work; `gzip` and `bzip2` are included.
- Programs that start other AFNI programs (for example `3dttest++ -Clustsim`) find them through `PATH`.
- Uninstall from **Settings → Apps → Installed apps → AFNI for Windows**.

Prefer no installer? Each release also has `afni-<version>-win64.zip`: unpack it anywhere and put the folder on `PATH`.

### What is included

- All 53 programs of a typical single-subject pipeline (`3dcalc`, `3dvolreg`, `3dAllineate`, `3dQwarp`, `3dDeconvolve`, `3dREMLfit`, `3dttest++`, `3dClustSim`, …), see [`manifests/programs-required.txt`](manifests/programs-required.txt). Every release is built only if all of them build.
- About 230 further command-line programs on a best-effort basis ([`manifests/programs-optional.txt`](manifests/programs-optional.txt)); each release lists the ones that did not build.
- Not included: the graphical viewer `afni`, SUMA, the tcsh/Python pipeline scripts (such as `afni_proc.py`) and atlas datasets.

### How results are checked

Every build runs a regression scenario that covers all required programs on synthetic data, once with the Windows package and once with the official Linux build of the same tag, and compares the outputs value by value. Most outputs are bit-identical; the rest must agree within tolerances fixed in advance for each kind of algorithm (registration, for example, may stop at a slightly different point because the C runtime's math functions differ in the last bits). The comparison report is attached to every release. Details: [`docs/DECISIONS.md`](docs/DECISIONS.md) (D29) and [`tests/regression/tolerance.json`](tests/regression/tolerance.json).

### Problems

Report problems in [Issues](https://github.com/notaskynet/afni-win/issues). Please include the release version, the exact command and its output. Questions about AFNI itself belong on the [AFNI message board](https://discuss.afni.nimh.nih.gov/).

## For developers

### How it works

| Part | Location |
|---|---|
| Compatibility layer: replacement POSIX headers, `afni_compat.h` (forced include) and `afni_compat.dll` built on WinAPI: processes, `popen`/`system` through busybox `sh`, sockets, `mmap`, `dlopen`, `rand48`, … | [`compat/`](compat/) |
| Toolchain file and the hook that adds the layer to the upstream CMake project | [`cmake/`](cmake/) |
| Minimal upstream patches, each explaining why the layer cannot cover the case | [`patches/`](patches/) |
| Build driver: fetch tag, apply patches, configure, build, report | [`tools/build.py`](tools/build.py) |
| Packaging, installer (Inno Setup), release notes, upstream tag selection, POSIX API report | [`tools/`](tools/), [`installer/`](installer/) |
| Regression scenario and comparison | [`tests/regression/`](tests/regression/) |
| What the layer implements, what fails with `ENOSYS`, and the allowed no-ops | [`manifests/`](manifests/) |

Rules of the project (no committed upstream code, no silent stubs, patches only as a last resort) are in [`CLAUDE.md`](CLAUDE.md) and [`TASK.md`](TASK.md); every design decision is recorded in [`docs/DECISIONS.md`](docs/DECISIONS.md), and the phase reports are in [`docs/reports/`](docs/reports/).

### Build locally

In an **MSYS2 UCRT64** shell:

```sh
pacman -S --needed git make mingw-w64-ucrt-x86_64-{gcc,cmake,ninja,zlib,expat,qhull,libjpeg-turbo,python,python-pydantic}
git clone https://github.com/notaskynet/afni-win && cd afni-win

# compatibility layer and its unit tests
cmake -S compat -B build-compat -G Ninja -DCMAKE_TOOLCHAIN_FILE="$PWD/cmake/toolchain-mingw.cmake"
cmake --build build-compat && ctest --test-dir build-compat

# AFNI: required programs (add --optional-manifest manifests/programs-optional.txt for the rest)
python -m tools.build --tag AFNI_26.2.09 --work-dir build-win
```

The programs are in `build-win/build/targets_built`. For `popen`/`system` put [busybox-w32](https://frippery.org/busybox/) next to them as `busybox.exe`, or set `AFNI_COMPAT_SHELL` to a POSIX `sh`. A cross build on Linux works with the MinGW-w64 UCRT toolchain (see [`tools/docker/Dockerfile`](tools/docker/Dockerfile)).

Python tools use [uv](https://docs.astral.sh/uv/): `uv run ruff check .`, `uv run ty check tools tests`, `uv run pytest`.

### Continuous integration and releases

- [`build-windows.yml`](.github/workflows/build-windows.yml) builds a tag on Linux (reference) and Windows, packages it, builds and tests the installer, runs and compares the regression scenario and, with `publish=true`, publishes the release `<tag>-win`.
- [`watch-upstream-tags.yml`](.github/workflows/watch-upstream-tags.yml) runs daily and starts a publishing build for each new upstream tag. A tag whose build fails gets an issue *"Build failed: &lt;tag&gt;"* and is not retried automatically.

## Licence

afni-win is licensed under the [GPL-3.0](LICENSE). AFNI is mostly public domain with third-party parts under their own licences (see the AFNI `LICENSE.txt` included in every release); the Windows binaries link GPL-3.0 code and are therefore distributed under the GPL-3.0. Bundled third-party programs and libraries and their licences are listed in [`manifests/runtime-deps.txt`](manifests/runtime-deps.txt).

AFNI is developed by the Scientific and Statistical Computing Core of the NIMH. afni-win is an independent project and is not affiliated with or endorsed by the AFNI developers.
