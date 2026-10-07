# Decisions

Decisions taken after the phase 0 report (`docs/inventory/REPORT.md`, section 13) and during phase 1. Each entry says what was decided and where it is implemented.

| # | Topic | Decision | Implemented in |
|---|---|---|---|
| D0 | No silent stubs (spec principle 4) | Refined: a no-op is allowed only when doing nothing cannot change any result. Every such case is listed with a justification in `manifests/noop-allowlist.txt`. Everything else either works or fails with an error and a stderr message. | `manifests/noop-allowlist.txt` |
| D1 | Phase 1 scope | The layer declares everything `libmri` needs. Functions that are not implemented yet fail with `errno = ENOSYS` and print a message once. They are listed in `manifests/enosys.txt`, which must shrink. Real implementations first for what runs in `3dinfo`/`3dcalc`/`3dTstat`. | `compat/`, `manifests/enosys.txt` |
| D2 | `fork`+`exec` | Every `fork` call site gets a patch. The layer provides `posix_spawn[p]`/`waitpid` via `CreateProcess`. | `patches/0002`, `compat/src/process.c` |
| D3 | `fork` without callers | Patched out. `fork` is not declared by the layer, so a new upstream use fails to compile. | `patches/0003`, `patches/0004` |
| D4 | Build description | Upstream CMake + `cmake/toolchain-mingw.cmake` + minimal build-file patches. NIfTI from the in-tree copy via `FETCHCONTENT_SOURCE_DIR_NIFTI_CLIB`. | `patches/0001`, `tools/build.py` |
| D4a | GIFTI | The in-tree `src/gifti/CMakeLists.txt` cannot be used through `FETCHCONTENT_SOURCE_DIR_GIFTI_CLIB` (it downloads nifti_clib master again and redefines the NIfTI targets). `FETCHCONTENT_SOURCE_DIR_GIFTI_CLIB` points to `cmake/gifti/`, which builds the in-tree `src/gifti/gifti_io.c` and `gifti_xml.c` as `GIFTI::giftiio`. No upstream code is copied. | `cmake/gifti/CMakeLists.txt` |
| D5 | `libmri` | Shared library (DLL), as upstream builds it by default. | upstream default `BUILD_SHARED_LIBS=ON` |
| D5a | Compat library | `afni_compat.dll` (not a static library as the spec originally said). A static layer linked into both `libmri.dll` and each program would have two copies of its state (`rand48` seed, child process table, …). | `compat/CMakeLists.txt` |
| D6 | `alarm` watchdog in `3dQwarp` | Patched out under `_WIN32`. `alarm` is not declared. The toolchain links with `-Wl,--wrap=alarm`, and `compat/CMakeLists.txt` fails the configure step if `alarm` still links, so MinGW's silent stub can never be used. | `patches/0006`, `cmake/toolchain-mingw.cmake`, `compat/CMakeLists.txt` |
| D7 | Signals | Installing a handler for `SIGPIPE`/`SIGBUS` is an allowed no-op; `mallopt` would return 0 without a message (allowlist). Other signals that Windows does not have: `SIG_ERR` + `ENOSYS` + message. | `compat/src/signal.c` |
| D8 | `popen`/`system` | Run through `sh` from busybox-w32, which ships with the release. No own POSIX shell parser. Checked before implementation (phase 1 report, section 4). | phase 2 |
| D9 | SysV shm | Built with `DONT_USE_SHM`. The layer only provides `key_t`. `mmap` (including `MAP_ANON|MAP_SHARED`) stays in the layer. | `compat/include/afni_compat.h` |
| D10 | Program lists | Section 10 lists accepted, plus `3dAttribute 3dSynthesize 3dNotes 3dnewid` in required. | `manifests/programs-*.txt` |
| D11 | 64-bit offsets | `fseek`→`_fseeki64`, `ftell`→`_ftelli64` in the forced include; `_FILE_OFFSET_BITS=64`. | `compat/include/afni_compat.h` |
| D12 | Binary mode | MinGW-w64's `binmode.o` is empty in the UCRT CRT 13 used for the build, so the layer provides the `_fmode = _O_BINARY` definition itself (`afni_compat_binmode`, linked into every consumer) and switches stdin/stdout/stderr to binary in the DLL constructor. | `compat/src/binmode.c`, `compat/src/init.c` |
