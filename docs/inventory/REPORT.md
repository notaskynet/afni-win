# Phase 0 report: AFNI upstream inventory for a native Windows (MinGW-w64 UCRT64) build

## 1. Scope and method

| Item | Value |
|---|---|
| Upstream tag | `AFNI_26.2.09` (commit `8252af5308d26b90cab50e68eb9b18a4e0351c26`, 2026-09-19) — latest `AFNI_*` tag from `git ls-remote --tags` |
| Linux reference build | Ubuntu, GCC 15.2, CMake 4.2.3, upstream CMake, `COMP_GUI=OFF`, `BUILD_SHARED_LIBS=OFF`, OpenMP on, per-executable linker maps (`-Wl,-Map`) |
| Second Linux build | same, `COMP_GUI=ON`, only the X-dependent console programs (section 7) |
| Windows probe toolchain | Fedora 44 container: `ucrt64-gcc 16.2.1`, `ucrt64-crt 13.0.0`, `ucrt64-headers 13.0.0` (same CRT family as MSYS2 UCRT64) |

All numbers below come from four independent measurements, not from reading code alone:

1. **Link-level inventory.** Every executable (303 link maps, 302 linked successfully) was re-linked with a linker map. The map lists exactly which archive members (`libmri.a(foo.c.o)`, …) are pulled into the program. For each object, `nm -u` gives its undefined symbols. This yields, per program, the exact set of POSIX symbols it would need on Windows.
2. **Symbol availability on UCRT64.** All 318 external symbols referenced by the Linux objects were normalised (glibc `__*_chk`, `__isoc23_*`, `*64` aliases) and linked against the UCRT64 default libraries, with and without `-lws2_32`. Unresolved symbols = missing on Windows.
3. **Compile probe.** All 362 translation units of `libmri` plus `3dinfo`, `3dcalc`, `3dTstat` were compiled with `x86_64-w64-mingw32ucrt-gcc -fsyntax-only` using the exact flags from `compile_commands.json` (minus `-DLINUX2 -D_GNU_SOURCE`). A second pass used empty placeholder headers for the missing POSIX headers to reveal the next layer of errors.
4. **Textual call sites.** Comment/string-stripped regex search over `src/**/*.c` excluding vendored third-party trees. These counts are approximate and are given only as an indication of code volume; the link-level data is authoritative. Example of why: `strcasestr` has 164 textual calls but `machdep.h:426` already maps it to `AFNI_strcasestr`, so only `thd_http.c` (which does not include `machdep.h`) needs it at link level. `stpcpy` appears in `nm` output only because GCC turns `strcpy`+`strlen` into `stpcpy` on glibc; it has zero textual calls.

## 2. Upstream build system

### 2.1 Two official build systems

- **Make**: `src/Makefile.INCLUDE` (4358 lines) + one `Makefile.<platform>` per platform (70+). Official binary distributions use it (`.docker/make_build.dockerfile`: `make itall` with `Makefile.linux_ubuntu_16_64_glw_local_shared`). Contains `Makefile.cygwin` (legacy, X11/LessTif, plugins compiled statically) and `Makefile.anyos_text`.
- **CMake**: root `CMakeLists.txt`, `cmake/*.cmake`, `src/CMakeLists.txt`, `src/CMakeLists_{mri,binaries,x_dependent,plugins}.txt`. Used in upstream CI (`.docker/cmake_build.dockerfile`, Ninja).

CMake is the natural base for `cmake/toolchain-mingw.cmake` required by the spec.

### 2.2 CMake components (`cmake/afni_cmake_build_options.cmake`, `packaging/installation_components.txt`)

| Component | Option | Entries in `installation_components.txt` |
|---|---|---|
| corelibs (libmri, models, eispack, 3DEdge, …) | always | 33 |
| corebinaries (console C programs) | `COMP_COREBINARIES` | 293 |
| gui (afni, plugins, X-dependent programs) | `COMP_GUI` | 69 |
| suma | `COMP_SUMA` | 91 |
| tcsh / python / rstats scripts | `COMP_TCSH` / `COMP_PYTHON` / `COMP_RSTATS` | 160 / 108 / 48 |

### 2.3 Core library

`AFNI::mri` (`src/CMakeLists_mri.txt`) is assembled from object libraries: `niml`, `afsliceobjs`, `cs_objs`, `edt_objs`, `misc_objs`, `mri_objs`, `parser`, `pcor_objs`, `someafobjs`, `suma_objs`, `thd_objs`, plus `rickr/r_*.c` — about 360 translation units. It links `m`, `GIFTI::giftiio`, `AFNI::3DEdge`, `AFNI::eispack`, `NIFTI::nifti2`, `NIFTI::nifticdf`.

### 2.4 External dependencies

| Dependency | Where | Needed for console scope | Notes |
|---|---|---|---|
| zlib | `find_package(ZLIB REQUIRED)` | yes | MSYS2 package exists |
| expat | via gifti_clib | yes | compile probe: `expat.h` missing in a bare toolchain; MSYS2 package exists |
| OpenMP | `find_package(OpenMP)`, `USE_OMP` | yes (≈30 programs) | libgomp is part of MSYS2 GCC |
| Python ≥ 3.6 | `find_package(Python REQUIRED)` at configure time | configure only | |
| nifti_clib, gifti_clib | `FetchContent` from GitHub **master, no pinned commit** (`cmake/afni_project_dependencies.cmake`) | yes | Not reproducible per tag. In-tree copies exist in `src/nifti`, `src/gifti`; `FETCHCONTENT_SOURCE_DIR_NIFTI_CLIB` / `..._GIFTI_CLIB` can point to them without patching |
| qhull | `USE_SYSTEM_QHULL=ON` by default; used at runtime via `popen("qhull …")` (`cs_qhull.c:66`) | runtime only | |
| f2c (libf2c) | bundled `src/f2c` | yes | |
| X11, Motif, libjpeg, XmHTML | `COMP_GUI` | no (section 7) | |
| OpenGL, GLUT, GSL, GLib, GTS | `COMP_SUMA` | no | |
| dcm2niix (C++) | bundled `src/crorden` | optional | uses `popen`, `realpath`, `memmem`, `lstat` |

### 2.5 Findings about the upstream CMake build

1. **Platform flags exist only for Linux and Darwin** (`CMakeLists.txt`: `-DREAD_WRITE_64 -DLINUX2 -D_GNU_SOURCE` / `-DLINUX -DDARWIN`). For Windows nothing is set, so `machdep.h` takes no platform branch and `THD_MMAP_FLAG`, `THD_MKDIR_MODE` stay undefined (confirmed by the compile probe).
2. **`COMP_GUI=OFF` fails at configure time** with "The build has not built all the targets expected … 3dmaxima;Vecwarp;adwarp;afni_vcheck" (`cmake/get_build_macros_and_functions.cmake:132`). `-DREMOVE_BUILD_PARITY_CHECKS=ON` works around it.
3. **Static linking is broken for two programs**: `Dimon1` and `3dDeconvolve` fail with "multiple definition of `nifti_*`" because they pull both `libniftiio` (NIfTI-1) and `libnifti2`. The default upstream build is shared (`BUILD_SHARED_LIBS=ON`), where this does not show up.
4. **Several important console programs are in the GUI block** of `src/CMakeLists_binaries.txt` (`if(COMP_GUI)`): `3dDeconvolve`, `3dDeconvolve_f`, `3dNLfim`, `to3d`, `1dplot`, `1dgrayplot`, `3dmaxima`, `adwarp`, `Vecwarp`, `afni_vcheck`, `3dExchange`, `FD2`, `imreg`. Section 7 shows which of them really need X.
5. Libraries and binaries are linked with `--no-undefined` and `--as-needed` (`cmake/get_build_macros_and_functions.cmake:249-267`).

## 3. Portability switches that already exist upstream

These are compile-time macros, so we can set them from outside (command line or forced include) without patching:

| Macro | Effect | Where |
|---|---|---|
| `DONT_USE_SHM` | Turns off SysV shared memory in `thd_iochan.c`, `niml/niml_stream.c`, `3dGroupInCorr.c`. `iochan_init("shm:…")` then returns NULL (`thd_iochan.c:709`), which is an error, not fake success | `thd_iochan.h:12`, `niml/niml.h:282` (auto-defined for `CYGWIN`) |
| `DONT_USE_FORK` | Turns off the fork-based `-jobs` parallelism in `3dDeconvolve.c:336` and `3dNLfim.c:128` | |
| `MMAP_THRESHOLD -1` | Datasets are never loaded via `mmap` (`thd_initdblk.c:316`, `thd_forcemalloc.c:26`) | `machdep.h:331` (CYGWIN branch) |
| `NO_DYNAMIC_LOADING` | Plugins are linked statically (`afni_plugin.c:399`, `fixed_plugins.h`) — GUI only | `machdep.h:332` |
| `ENABLE_THD_check_AFNI_version` | **Not** defined by default, so the double-`fork` version check in `thd_vcheck.c:111` is compiled out (`THD_check_AFNI_version` is an empty function, `thd_vcheck.c:45`) | |
| `strcasestr` → `AFNI_strcasestr` | Already replaced in `machdep.h:426` | |

A `CYGWIN` branch exists in `machdep.h:326-339`. Defining `CYGWIN` ourselves is **not** recommended: it also enables LessTif/X-specific paths (`USING_LESSTIF`, `imseq.c`, `mri_write.c:452`, `afni_version.c:129`) and assumes a POSIX runtime. The equivalent settings (`THD_MMAP_FLAG`, `THD_MKDIR_MODE`, `MMAP_THRESHOLD`, `DONT_USE_STRPTIME`, …) can instead be provided by `afni_compat.h`.

## 4. Compile probe with MinGW-w64 UCRT64

### 4.1 First pass (no layer)

344 of 362 translation units fail. The first fatal error per file:

| Missing header | Files | Path |
|---|---|---|
| `sys/wait.h` | 300 | every unit including `mrilib.h` → `thd_iochan.h:16` |
| `sys/socket.h` | 24 | `niml/niml.h` (all of `niml/*.c`), `thd_trusthost.c`, `thd_logafni.c` |
| `sys/utsname.h` | 1 | `thd_vcheck.c` |
| `pwd.h` | 1 | `thd_filestuff.c` |
| `netinet/in.h` | 1 | |

POSIX headers used by AFNI sources and absent in UCRT64 (from all `#include <…>` in `src/`): `sys/wait.h`, `sys/socket.h`, `netinet/in.h`, `netinet/tcp.h`, `arpa/inet.h`, `netdb.h`, `sys/mman.h`, `sys/shm.h`, `sys/ipc.h`, `pwd.h`, `sys/utsname.h`, `sys/times.h`, `sys/resource.h`, `sys/select.h`, `sys/ioctl.h`, `sys/vfs.h`, `sys/statvfs.h`, `sys/mount.h`, `dlfcn.h`, `termios.h`, `regex.h`, `net/if.h`, `alloca.h`, `values.h`.

### 4.2 Second pass (empty placeholder headers)

325 of 362 units still fail. The most common errors:

| Error | Count | Cause |
|---|---|---|
| unknown type `key_t` | 306 | `thd_iochan.h:128` (`string_to_key`) — SysV IPC type, used even if `DONT_USE_SHM` |
| unknown type `int64_t` | 17 | `cs.h` relies on `<sys/types.h>` pulling `<stdint.h>` on glibc |
| `SIGPIPE`, `SIGBUS` undeclared | 9, 5 | `DBG_SIGNALS` in `debugtrace.h:259-264`, used by `mainENTRY` in practically every program |
| `SIGALRM`, `SIGURG`, `ITIMER_REAL` undeclared | 1 each | `thd_vcheck.c`, `thd_iochan.c` |
| socket constants and types (`AF_INET`, `SOCK_STREAM`, `SOL_SOCKET`, `fd_set`, `socklen_t`, `struct hostent`) | 4–7 | `thd_iochan.c`, `niml/niml_stream.c` |
| `mkdir` called with 2 arguments | 3 | MinGW `mkdir` takes 1 argument (`mri_dicom_hdr.c`, `thd_filestuff.c`, `thd_writedblk.c`) |
| `THD_MMAP_FLAG`, `THD_MKDIR_MODE`, `PROT_READ`, `IPC_*` undeclared | 1 each | section 2.5 item 1 |
| implicit `drand48`/`srand48`/`lrand48`/`erand48`/`jrand48`/`nrand48` | 5/4/4/1/1/1 | |
| implicit `fork`, `waitpid`, `getuid`, `getpwuid`, `realpath`, `readlink`, `statfs`, `uname`, `setitimer`, `shm*`, `mmap`, `munmap`, sockets | 1–3 each | |

### 4.3 Symbols missing at link time (UCRT64 + `ws2_32`)

`cfsetispeed cfsetospeed dlclose dlerror dlopen dlsym drand48 erand48 fcntl flock fork fsync getppid getpwuid getuid jrand48 kill lrand48 lstat malloc_stats mallopt memmem mmap munmap nice nrand48 pause readlink realpath setitimer shmat shmctl shmdt shmget srand48 statfs stpcpy strcasestr sync sysconf tcgetattr tcsetattr times uname wait waitpid` (`stdin`/`stdout`/`stderr`/`environ` are macros in UCRT and are false positives).

Only with `-lws2_32` (Winsock, different semantics): `accept bind connect gethostbyaddr gethostbyname gethostname getsockopt inet_ntoa listen recv select send setsockopt shutdown socket`.

### 4.4 Present in MinGW but not usable as-is

| API | Problem | Evidence |
|---|---|---|
| `alarm` | **Silent stub**: `libmingwex.a` `alarm` is `xor eax,eax; ret` and is declared only under `__USE_MINGW_ALARM` (`io.h:375`). This violates principle 4 if it is ever linked | disassembly of `libmingwex.a` |
| `popen`/`system` | Run through `cmd.exe`. AFNI command strings use POSIX shell syntax, e.g. single-quoted file names `"gzip -dc '%s'"` (`thd_compress.h`, used by `thd_compress.c:296`), `qhull -i -Pp < %s`, `>& /dev/null` with `tcsh -c` (`cs_playsound.c:214`) | source |
| `execvp` | UCRT `_execvp` does not replace the process (it spawns and exits); argument quoting differs | |
| `select` | Winsock `select` works only on sockets and rejects calls where all three sets are NULL. AFNI uses `select(1,NULL,NULL,NULL,&tv)` as a millisecond sleep (`NI_sleep`, `niml/niml_util.c:61`; `afni_logger.c:34`), and the return value is ignored, so the sleep would silently become a no-op | source |
| `close` on sockets | `CLOSEDOWN` = `shutdown()` + `close()` (`niml/niml_stream.c:32`); Winsock needs `closesocket` | source |
| `signal` | UCRT accepts only `SIGINT SIGILL SIGFPE SIGSEGV SIGTERM SIGABRT`; other numbers trigger the invalid-parameter handler | |
| `stat`, `off_t` | 32-bit `st_size`/`off_t` by default; `-D_FILE_OFFSET_BITS=64` makes both 8 bytes (verified) | probe |
| `fseek`/`ftell` | Take/return `long`, which is 32 bits on Windows (LLP64). 158 textual call sites; also `znzlib.c:207,232` (NIfTI I/O) | probe + source |
| `mkdir` | One argument, no mode | probe |

## 5. Link-level inventory: why almost every program needs the layer

`libmri` is tightly interconnected. Opening any dataset pulls `thd_opendset.c` → `thd_mastery.c` (`fork`+`execvp`), `niml_*` → `niml_stream.c` (sockets, SysV shm), `thd_iochan.c` (sockets, shm, `fork`), `thd_filestuff.c` (`getpwuid`, `readlink`, `statfs`), `machdep.c` (`mallopt`, `sysconf`, `*rand48`), etc.

| API group | Programs affected (of 303) | Main libmri sources |
|---|---|---|
| sockets | 269 | `niml/niml_stream.c`, `thd_iochan.c`, `niml/niml_util.c`, `afni_ports.c`, `thd_notes.c` |
| signals/timers | 269 | `DBG_SIGNALS` (own `main`), `thd_iochan.c`, `niml_stream.c`, `mri_read_stuff.c`, `mri_write.c`, `thd_vcheck.c` |
| process (`fork`, `waitpid`, `execvp`, `getppid`) | 268 | `thd_mastery.c`, `thd_iochan.c`, `niml/niml_uuid.c` |
| SysV shm | 267 | `niml/niml_stream.c`, `thd_iochan.c`, `thd_loaddblk.c` |
| `mmap`/`munmap` | 267 | `thd_loaddblk.c`, `thd_purgedblk.c`, `thd_writedblk.c` |
| `popen`/`system` | 271 | `thd_compress.c`, `mcw_glob.c`, `mri_read_stuff.c`, `mri_write.c`, `thd_http.c`, `niml/niml_url.c`, `thd_getpathprogs.c`, `thd_ttatlas_query.c`, `thd_initsess.c`, `svdlib.c`, `cs_qhull.c` |
| users (`getuid`, `getpwuid`) | 267 | `thd_filestuff.c`, `thd_notes.c`, `niml/niml_uuid.c` |
| fs (`readlink`, `lstat`, `realpath`, `statfs`, `flock`, `fcntl`, `mkdir`, `chmod`, `fsync`) | 272 | `thd_filestuff.c`, `mcw_glob.c`, `thd_idcode.c`, `thd_niftiread.c`, `thd_sarr.c`, `afni_logger.c` |
| sysinfo (`uname`, `sysconf`, `times`) | 268 | `niml/niml_uuid.c`, `machdep.c` |
| `*rand48` | 267 | `machdep.c`, `cs_pv.c`, `cs_symeig.c`, `edt_geomcon.c`, `parser_int.c`, `powell_int.c`, `thd_correlate.c`, … |
| glibc malloc (`mallopt`, `malloc_stats`) | 267 | `machdep.c:40` |
| `dl*` | 1 (`3dTSgen`) | own source |
| tty | 1 (`serial_helper`) | own source |

Only 29 executables are free of problematic symbols, and most of them are NIfTI/GIFTI test tools: `1dAstrip 3dAcost 3dConvolve 3dFWHM 3dNwarpCalc afni_check_omp afni_history byteorder column_cat ge_header help_format ibinom mayo_analyze mycat quotize sqwave tokens whirlgif` + `nifti_*`, `gifti_*`, `clib_02_nifti2`.

**Consequence for phase 1.** `3dinfo`, `3dcalc` and `3dTstat` link the same `libmri` closure as almost every other program (tables in Appendix A). There is no subset of "console programs without POSIX dependencies" except the trivial ones above. Phase 1 as written ("minimal `afni_compat.h`, only headers needed for this phase") cannot produce `3dinfo` without most of the layer surface (at least declarations and error-returning or real implementations of everything in the table above). See question Q1.

## 6. `fork` analysis

| Site | Followed by `exec`? | Built in console scope? | Reachable from | Classification |
|---|---|---|---|---|
| `thd_mastery.c:556` | yes, `execvp("3dcalc", …)` + `waitpid` | yes (libmri) | `THD_open_dataset` with `3dcalc(...)` syntax — all dataset programs | Needs a code change: no layer can make `fork()` return twice. Minimal patch: replace `fork`/`execvp`/`waitpid` with a spawn call (e.g. `posix_spawnp`, which the layer can implement with `CreateProcess`) |
| `thd_iochan.c:1631` (`iochan_fork_relay`) | no | yes (libmri) | **no callers** in the tree | Needs a patch (or a `fork` that always fails with `ENOSYS`, see Q3). The object is always linked because `iochan_*` is used widely |
| `thd_logafni.c:34` (`AFNI_serverlog`) | no | yes (libmri) | **no callers** in the tree | Same as above; dropped by the static linker when unused, but must resolve if libmri is a DLL |
| `thd_vcheck.c:111,123` | no (double fork, HTTP) | compiled out | `ENABLE_THD_check_AFNI_version` not defined | No action |
| `3dttest++.c:2377` (`start_job`) | no — child calls `system(cmd)` then `_exit` | yes | `-Clustsim` / `-ETAC` parallel jobs (`3dttest++.c:5473,5483`); uses `kill`, `waitpid`, `wait` | Needs a patch: replace with an asynchronous spawn of the command |
| `cs_playsound.c:176` | no — child calls `system("tcsh -c '…'")` | yes (libmri) | `1dsound`, GUI | Patch or exclude `1dsound` (optional) |
| `3dDeconvolve.c:7520`, `3dNLfim.c:3679` | no (worker processes with SysV shm) | GUI block in CMake | `-jobs N` | Compile with `DONT_USE_FORK` + `DONT_USE_SHM`: no patch. `-jobs` then not available (OpenMP is not used by these two) |
| `mpeg_encodedir/parallel.c:1959` | yes (`execvp`) + sockets | yes (`mpeg_encode`) | parallel encoding mode only | Optional program |
| `xutil.c:2725,2735`, `afni.c:2471`, `afni_version.c:152`, `plug_realtime.c:2501` | mixed | no (GUI) | | Out of scope |
| `wrap.c:18`, `daemonize.c:12,18` | no | **not built** by CMake | | No action |
| `f2c/sysdep.c:243` | — | not built (only `libf2c` is) | | No action |

**Contradiction with the spec.** The spec lists "Processes (`fork`+`exec`, `waitpid`) → `CreateProcess`" as a layer group and says patches are needed only for `fork` without `exec`. In C, `fork()` must return twice (parent and child); a library cannot emulate that with `CreateProcess`. Every `fork` site therefore needs a code change, including the `fork`+`exec` one in `thd_mastery.c`. The layer can provide the spawn primitive (`posix_spawnp`/`waitpid`) so that the patch is a few lines. See Q2.

## 7. GUI-block console programs: do they really need X11?

Built on Linux with `COMP_GUI=ON`; for each program's own objects, undefined symbols were matched against what `libmrix.a` and `libcoxplot.a` define:

| Program | Symbols used from `mrix` | From `coxplot` | Needs X11? |
|---|---|---|---|
| `3dDeconvolve`, `3dDeconvolve_f` | `memplot_to_RGB_sef` (defined in `mri_coxplot.c`, which includes only `mrilib.h` and `coxplot.h`) | `*_memplot` (in-memory plotting) | **no** |
| `3dNLfim`, `3dmaxima`, `adwarp`, `Vecwarp`, `afni_vcheck`, `3dExchange`, `imreg` | none | none | **no** — CMake over-links `AFNI::mrix` |
| `to3d` | `MCW_*`, `open_MCW_imseq`, `new_MCW_bbox`, … | | yes |
| `1dplot`, `1dgrayplot`, `FD2` | X plotting | | yes |

So `3dDeconvolve` and seven other programs can be built without X11, but upstream CMake only defines them under `COMP_GUI`, which requires X11 + Motif + libjpeg. This needs either a patch to `src/CMakeLists_binaries.txt` or our own CMake target definitions (Q4).

## 8. Plugins and models: symbol resolution

- **Plugins** (`plug_*.c`, `src/CMakeLists_plugins.txt`) link `PRIVATE AFNI::mrix` (and transitively `AFNI::mri`). With the default shared build they get AFNI symbols from the shared libraries `libmrix.so`/`libmri.so`, not from the `afni` executable, and are loaded by `afni_plugin.c` through `dlopen(…, RTLD_LAZY)`/`dlsym` (`afni_plugin.h:92,100`). GUI only, out of scope.
- **NLfit models** (`model_*.c`, 29 libraries, `src/CMakeLists.txt`) link `PRIVATE AFNI::mri NIFTI::nifti2 NIFTI::nifticdf` and are loaded with `dlopen`/`dlsym` from `NLfit_model.c` (`NLfit_model.h:83,91`), using `DYNAMIC_suffix` (set from `CMAKE_SHARED_LIBRARY_SUFFIX`, i.e. `.dll` on Windows). Users: `3dNLfim` (X-free per section 7), `3dTSgen`, `1dNLfit`.
- On Windows a DLL cannot have undefined symbols that the host executable fills in at load time. Models work as Windows DLLs only if `libmri` is itself a DLL (`libmri.dll`) that both the program and the model import. With a static `libmri`, each model DLL would carry its own copy of `libmri` with its own globals. This is the "core in a DLL" architecture decision from spec section 7 (Q5).
- Building `libmri` as a DLL also means **every** object in it must link, including ones with no callers (`iochan_fork_relay`, `AFNI_serverlog`); a static archive would let the linker drop unused objects.

## 9. Other semantic issues found

1. **`alarm` + `longjmp` watchdog in `3dQwarp`** (`mri_nwarp.c:10851,12249`, handler `IW3D_signal_quit` at `mri_nwarp.c:8069`, `signal(SIGALRM, …)` at `mri_nwarp.c:8097`). Under OpenMP it sets an alarm of 99–1888 s and `longjmp`s out of the optimizer if gcc OpenMP freezes. Windows has no asynchronous signals; a timer-thread emulation would run the handler on another thread, and `longjmp` across threads is undefined behaviour. Options: `alarm` returns an error with a stderr message (no watchdog), or a patch (Q6).
2. **`DBG_SIGNALS`** (`debugtrace.h:259`) installs handlers for `SIGPIPE`, `SIGSEGV`, `SIGINT`, `SIGBUS`, `SIGTERM`, `SIGABRT` in nearly every `main`. `SIGPIPE` and `SIGBUS` do not exist on Windows. The spec forbids returning success without doing anything, but an error message would print on every program start (Q7).
3. **`popen`/`system` command syntax.** Commands are written for `/bin/sh` (single quotes, `<`, `>&`, `tcsh -c`). Under `cmd.exe`, `.BRIK.gz`/`.bz2` reading (`thd_compress.c:296,344`) breaks. NIfTI `.nii.gz` is read through zlib (`znzlib`) and is not affected. A layer `popen` that understands POSIX quoting and starts the program directly (no shell) would fix the common cases. `tcsh -c` and redirections need a POSIX shell at runtime (Q8).
4. **`*rand48` reproducibility.** 267 programs use the `rand48` family (≈235 textual call sites). The POSIX algorithm is fully specified (48-bit LCG, `a=0x5DEECE66D`, `c=0xB`), so an exact implementation gives bit-identical sequences to glibc for the same seed. This matters for phase 5 (e.g. `3dClustSim`, `3dttest++ -Clustsim`). Default seeds come from time/pid (`init_rand_seed`, `machdep.c`), so regression scenarios need explicit seeds.
5. **Large files (LLP64).** `long` is 32 bits on Windows. `THD_filesize` returns `long long` from `stat` (`thd_filestuff.c`) — fine with `-D_FILE_OFFSET_BITS=64`. `fseek(…, long, …)` is used in `mri_read.c` (16 sites, including `im->foffset` for `3D:` raw reads) and in `znzlib.c:207` (`znzseek`, NIfTI). `.BRIK` loading reads sequentially with `fread`. Offsets above 2 GiB through these `fseek` calls would be wrong on Windows. It is not yet measured which real workflows hit them (sub-brick selection from > 2 GiB NIfTI is the most likely).
6. **mmap uses.** `thd_loaddblk.c:414` (read-only file mapping of `.BRIK`, can be disabled by `MMAP_THRESHOLD -1` or `AFNI_NOMMAP`), `3dClustSim.c:1695` (`MAP_ANON|MAP_SHARED`), `3dXClustSim.c`, `3dAutoTcorrelate.c:588` (`-mmap` writes output via shared file mapping), `3dExtractGroupInCorr.c:308`, `3dGroupInCorr.c`. Both anonymous and file-backed mappings are needed.
7. **SysV shm** is used for IPC with the AFNI GUI (`shm:` iochan/NIML streams, `3dGroupInCorr` ↔ `afni`) and for `DATABLOCK_MEM_SHARED` (`thd_loaddblk.c:956`, already disabled under `DONT_USE_SHM`). The GUI is out of scope, so `DONT_USE_SHM` is an alternative to implementing `shm*` (Q9).
8. **Sockets.** Real runtime use in console scope: `NI_read_URL`/`thd_http.c` (datasets from `http://`), `3dGroupInCorr`, `Dimon` real-time mode, `plugout_*`, `rtfeedme`, `niml_feedme` (all of which talk to the GUI). The fd vs `SOCKET` mismatch (`close`, `read`/`write`, `fcntl(O_NONBLOCK)`, `select` as sleep) needs careful handling in the layer.
9. **`mallopt(M_MMAP_MAX,1)`** in `machdep.c:40` and **`sysconf(_SC_NPROCESSORS_CONF/_SC_PAGESIZE/_SC_PHYS_PAGES/_SC_AVPHYS_PAGES)`** in `machdep.c:120-152`: `sysconf` maps to `GetSystemInfo`/`GlobalMemoryStatusEx`; `mallopt` has no UCRT equivalent (Q7 applies).
10. **Binary mode.** UCRT64 ships `binmode.o`; linking it sets `_fmode = _O_BINARY` for the whole program, which is the documented way to get "binary file mode by default" without code changes.

## 10. Proposed classification

The spec leaves the lists to this phase. Proposal, based on the inventory and on what a typical `afni_proc.py` single-subject pipeline calls. To be confirmed by you.

**required** (≈50): `3dinfo 3dcalc 3dTstat 3dTcat 3dbucket 3drefit 3dcopy 3dresample 3dAFNItoNIFTI 3dZeropad 3dAutomask 3dAutobox 3dvolreg 3dAllineate 3dQwarp 3dNwarpApply 3dNwarpCat 3dTshift 3dDespike 3dToutcount 3dTnorm 3dDetrend 3dBandpass 3dTproject 3dBlurToFWHM 3dBlurInMask 3dmerge 3dmaskave 3dmask_tool 3dmaskdump 3dROIstats 3dBrickStat 3dhistog 3dnvals 3dUndump 3dUnifize 3dClustSim 3dFWHMx 3dREMLfit 3dDeconvolve 3dttest++ 3dclust 3dMean 3dLocalstat 1deval 1dcat 1dtranspose ccalc cat_matvec whereami`

Of these, need a patch (section 11): `3dttest++` (only for `-Clustsim`/`-ETAC`), all of them for `thd_mastery.c`; need a build-file change: `3dDeconvolve`.

**optional**: all other `corebinaries` built on Linux (≈250), plus the X-free GUI-block programs `3dNLfim 3dmaxima adwarp Vecwarp afni_vcheck 3dExchange imreg 3dDeconvolve_f`, plus `dcm2niix_afni`, `mpeg_encode`, `Dimon`, `1dsound`, `3dTSgen`.

**excluded**: GUI and SUMA (`afni`, plugins, `suma`, and SUMA-component programs like `3dSkullStrip`), X-dependent `to3d 1dplot 1dgrayplot FD2`, programs that exist to talk to a running AFNI (`plugout_* rtfeedme niml_feedme serial_helper`), test/demo programs (`nifti_tester* nifti_*_test_program clib_02_nifti2 test_powell testcox fftest 3dToyProg`), `Dimon1` (legacy, static link failure).

Note: `3dSkullStrip` and the surface programs are in the SUMA component, and the pipeline drivers (`afni_proc.py` output) are tcsh scripts, both out of scope.

## 11. Places that need patches (candidates)

| # | File | Why the layer cannot cover it | Estimated size |
|---|---|---|---|
| P1 | `src/thd_mastery.c:556-575` | `fork`+`execvp`+`waitpid` → spawn | ~10 lines |
| P2 | `src/thd_iochan.c:1631` (`iochan_fork_relay`, no callers) | `fork` without `exec` | ~5 lines (`#ifdef` out), or none if Q3 = "fork fails with ENOSYS" |
| P3 | `src/thd_logafni.c:34` (`AFNI_serverlog`, no callers) | same | same as P2 |
| P4 | `src/3dttest++.c:2377` (`start_job`/`wait_for_jobs`) | `fork`+`system` → async spawn of a shell command | ~20 lines |
| P5 | `src/cs_playsound.c:176` | `fork`+`system("tcsh -c …")` | optional (`1dsound`) |
| P6 | `src/mri_nwarp.c` alarm watchdog | asynchronous signal + `longjmp` | depends on Q6 |
| P7 | `src/CMakeLists_binaries.txt` | `3dDeconvolve` & co. only defined under `COMP_GUI` | small, or zero with own CMake (Q4) |

Not patches (compile flags only): `DONT_USE_FORK` for `3dDeconvolve`/`3dNLfim`, `DONT_USE_SHM`, `MMAP_THRESHOLD`, `REMOVE_BUILD_PARITY_CHECKS`, `FETCHCONTENT_SOURCE_DIR_*`.

## 12. Risks

1. **Layer surface is large from day one.** Section 5: the core library alone needs sockets, process, shm (unless `DONT_USE_SHM`), mmap, users, fs, sysinfo, rand48 and signals.
2. **Socket/fd duality** (`close`, `read`, `write`, `fcntl`, `select` used both on sockets and as a sleep) is the hardest part to get right without patches.
3. **Shell semantics of `popen`/`system`**: a lot of runtime functionality (compressed `.BRIK`, image filters `cjpeg`/`djpeg`/`pnmtopng`, `qhull`, `curl`/`wget` downloads, `apsearch`) depends on external Unix tools being on `PATH` and on POSIX-shell syntax.
4. **LLP64 `long`** for offsets (section 9.5) and possibly elsewhere (pointer↔`long` casts were not measurable because compilation stops on errors; to be measured in phase 1 with `-Wpointer-to-int-cast`).
5. **Unpinned nifti_clib/gifti_clib** in upstream CMake: the same AFNI tag can build different library code on different days.
6. **Static linking breaks** `3dDeconvolve` and `Dimon1` (duplicate NIfTI-1/NIfTI-2 symbols). Either use shared libraries (DLLs) as upstream does or handle link order.
7. **Upstream drift**: `CMakeLists_*.txt` lists change between tags; any own build description or build-file patch has to follow them (phase 4 report of differences helps).
8. **Regression comparability**: random seeds from time/pid, OpenMP non-determinism in reductions, and `-ffast-math`-like differences between GCC versions can create differences unrelated to the port.
9. **MinGW silent stubs** (`alarm` confirmed) can slip in through the default libraries; the layer must make sure they are never linked (e.g. by providing its own definitions or failing the link).

## 13. Open questions (decisions needed before phase 1)

- **Q1. Phase 1 scope.** No real program can be built without most of the layer (section 5). Options: (a) merge phases 1 and 2 — build `libmri` + `3dinfo`/`3dcalc`/`3dTstat` together with the layer; (b) phase 1 uses error-returning implementations (`ENOSYS` + stderr) for everything not yet implemented, phase 2 replaces them with real ones.
- **Q2. `fork`+`exec`.** Agree that every `fork` site is a patch (P1, P4), with the layer providing `posix_spawnp`/`waitpid` via `CreateProcess`?
- **Q3. Unused `fork` sites (P2, P3).** Patch them out, or let the layer declare `fork()` that always fails with `errno=ENOSYS` and a stderr message? The second avoids patches but technically declares a function the layer does not support.
- **Q4. Build description.** (a) Use upstream CMake + toolchain file + minimal build-file patches (e.g. move X-free programs out of `COMP_GUI`); (b) maintain our own `CMakeLists.txt` in `afni-win` that builds `libmri` and selected programs from upstream sources (more control, more drift).
- **Q5. `libmri` as DLL or static.** DLL: matches upstream (shared by default), makes NLfit models (`3dNLfim`, `3dTSgen`, `1dNLfit`) and future plugins possible, avoids the duplicate-symbol link failures; but every object must link. Static: simpler, unused objects drop out, models do not work as DLLs.
- **Q6. `3dQwarp` alarm watchdog.** `alarm()` returns an error with a stderr message (watchdog disabled), or patch `mri_nwarp.c`?
- **Q7. Handlers for signals that cannot occur on Windows** (`SIGPIPE`, `SIGBUS` in `DBG_SIGNALS`) and `mallopt`. Treat "install a handler for a signal that Windows never raises" as a correct no-op, or return `SIG_ERR` + stderr message on every start?
- **Q8. `popen`/`system`.** Layer parses POSIX quoting/redirection and starts programs directly (no shell), or requires a POSIX shell (`sh` from MSYS2/Git) at runtime and runs commands through it?
- **Q9. SysV shm.** Implement `shm*` via `CreateFileMapping` as the spec says, or build with `DONT_USE_SHM` since its only consumers talk to the out-of-scope GUI?
- **Q10. required/optional lists** in section 10.

## Appendix A. Generated tables

### A1. Per-API link-level inventory

"Programs linking it" counts executables whose link map contains an object referencing the symbol. `own:` = program's own source; `libX.a:` = archive member. "Missing in UCRT64" = unresolved when linking against UCRT64 defaults (+`ws2_32` for sockets).

| Group | API | Missing in UCRT64 | Textual call sites | Objects referencing it (link-level) | Programs linking it |
|---|---|---|---|---|---|
| process | `fork` | yes | 17 | `libmri.a:thd_iochan.c`, `libmri.a:thd_mastery.c`, `own:1dsound.c`, `own:3dttest++.c`, `own:parallel.c` | 268 |
| process | `execvp` | no | 1 | `libmri.a:thd_mastery.c`, `own:parallel.c` | 268 |
| process | `wait` | yes | 2 | `own:3dttest++.c` | 1 |
| process | `waitpid` | yes | 13 | `libmri.a:thd_iochan.c`, `libmri.a:thd_mastery.c`, `own:3dttest++.c` | 267 |
| process | `kill` | yes | 12 | `own:3dttest++.c`, `own:parallel.c` | 2 |
| process | `getppid` | yes | 1 | `libmri.a:niml_uuid.c` | 267 |
| process | `nice` | yes | 5 | `own:Dimon.c`, `own:Dimon1.c` | 2 |
| process | `setsid` | no | 1 | — | 0 |
| popen/system | `popen` | no | 33 | `libmri.a:mcw_glob.c`, `libmri.a:mri_read_stuff.c`, `libmri.a:mri_write.c`, `libmri.a:thd_compress.c`, `libmri.a:thd_http.c`, `own:3dSetupGroupInCorr.c`, `own:apsearch.c`, `own:main_console.cpp` (+3) | 269 |
| popen/system | `pclose` | no | 43 | `libmri.a:mcw_glob.c`, `libmri.a:mri_read_stuff.c`, `libmri.a:mri_write.c`, `libmri.a:thd_compress.c`, `libmri.a:thd_http.c`, `own:3dSetupGroupInCorr.c`, `own:apsearch.c`, `own:main_console.cpp` (+3) | 269 |
| popen/system | `system` | no | 116 | `libmri.a:mri_read_mpeg.c`, `libmri.a:niml_url.c`, `libmri.a:thd_getpathprogs.c`, `libmri.a:thd_http.c`, `libmri.a:thd_ttatlas_query.c`, `own:1dsound.c`, `own:3dANOVA.c`, `own:3dANOVA2.c` (+17) | 271 |
| shm | `shmget` | yes | 5 | `libmri.a:niml_stream.c`, `libmri.a:thd_iochan.c` | 267 |
| shm | `shmat` | yes | 3 | `libmri.a:niml_stream.c`, `libmri.a:thd_iochan.c` | 267 |
| shm | `shmdt` | yes | 8 | `libmri.a:niml_stream.c`, `libmri.a:thd_iochan.c` | 267 |
| shm | `shmctl` | yes | 20 | `libmri.a:niml_stream.c`, `libmri.a:thd_iochan.c`, `libmri.a:thd_loaddblk.c` | 267 |
| mmap | `mmap` | yes | 11 | `libmri.a:thd_loaddblk.c`, `own:3dAutoTcorrelate.c`, `own:3dClustSim.c`, `own:3dExtractGroupInCorr.c`, `own:3dGroupInCorr.c`, `own:3dXClustSim.c` | 267 |
| mmap | `munmap` | yes | 6 | `libmri.a:thd_purgedblk.c`, `libmri.a:thd_writedblk.c`, `own:3dAutoTcorrelate.c`, `own:3dClustSim.c`, `own:3dXClustSim.c` | 267 |
| dl | `dlopen` | yes | 1 | `own:3dTSgen.c` | 1 |
| dl | `dlsym` | yes | 1 | `own:3dTSgen.c` | 1 |
| dl | `dlclose` | yes | 1 | `own:3dTSgen.c` | 1 |
| dl | `dlerror` | yes | 1 | `own:3dTSgen.c` | 1 |
| signals/timers | `signal` | no | 104 | `libmri.a:mri_read_stuff.c`, `libmri.a:mri_write.c`, `libmri.a:niml_stream.c`, `libmri.a:thd_iochan.c`, `libmri.a:thd_vcheck.c`, `own:1dBport.c`, `own:1dCorrelate.c`, `own:1dNLfit.c` (+194) | 269 |
| signals/timers | `alarm` | no | 6 | `own:3dQwarp.c` | 1 |
| signals/timers | `setitimer` | yes | 1 | `libmri.a:thd_vcheck.c` | 13 |
| sockets | `socket` | ws2_32 only | 7 | `libmri.a:niml_stream.c`, `libmri.a:thd_iochan.c`, `own:parallel.c`, `own:serial_helper.c` | 269 |
| sockets | `bind` | ws2_32 only | 3 | `libmri.a:niml_stream.c`, `libmri.a:thd_iochan.c`, `own:parallel.c`, `own:serial_helper.c` | 269 |
| sockets | `listen` | ws2_32 only | 3 | `libmri.a:niml_stream.c`, `libmri.a:thd_iochan.c`, `own:parallel.c`, `own:serial_helper.c` | 269 |
| sockets | `accept` | ws2_32 only | 3 | `libmri.a:niml_stream.c`, `libmri.a:thd_iochan.c`, `own:parallel.c`, `own:serial_helper.c` | 269 |
| sockets | `connect` | ws2_32 only | 3 | `libmri.a:niml_stream.c`, `libmri.a:thd_iochan.c`, `own:parallel.c` | 268 |
| sockets | `select` | ws2_32 only | 12 | `libmri.a:afni_logger.c`, `libmri.a:niml_stream.c`, `libmri.a:niml_util.c`, `libmri.a:thd_iochan.c` | 267 |
| sockets | `send` | ws2_32 only | 7 | `libmri.a:niml_stream.c`, `libmri.a:thd_iochan.c` | 267 |
| sockets | `recv` | ws2_32 only | 7 | `libmri.a:niml_stream.c`, `libmri.a:thd_iochan.c`, `own:serial_helper.c` | 268 |
| sockets | `setsockopt` | ws2_32 only | 16 | `libmri.a:niml_stream.c`, `libmri.a:thd_iochan.c` | 267 |
| sockets | `getsockopt` | ws2_32 only | 4 | `libmri.a:niml_stream.c` | 267 |
| sockets | `shutdown` | ws2_32 only | 3 | `libmri.a:afni_ports.c`, `libmri.a:niml_stream.c`, `libmri.a:thd_iochan.c` | 267 |
| sockets | `gethostbyname` | ws2_32 only | 10 | `libmri.a:niml_stream.c`, `libmri.a:thd_iochan.c`, `own:parallel.c` | 268 |
| sockets | `gethostbyaddr` | ws2_32 only | 2 | `libmri.a:thd_iochan.c` | 267 |
| sockets | `gethostname` | ws2_32 only | 3 | `libmri.a:thd_notes.c` | 267 |
| sockets | `inet_ntoa` | ws2_32 only | 8 | `libmri.a:niml_stream.c`, `libmri.a:thd_iochan.c`, `own:serial_helper.c` | 268 |
| users | `getpwuid` | yes | 2 | `libmri.a:thd_filestuff.c`, `libmri.a:thd_notes.c` | 267 |
| users | `getuid` | yes | 4 | `libmri.a:niml_uuid.c`, `libmri.a:thd_filestuff.c`, `libmri.a:thd_notes.c` | 267 |
| links/fs | `readlink` | yes | 3 | `libmri.a:thd_filestuff.c`, `own:Ifile.c` | 268 |
| links/fs | `lstat` | yes | 6 | `libmri.a:mcw_glob.c`, `own:Ifile.c`, `own:nii_dicom_batch.cpp` | 269 |
| links/fs | `realpath` | yes | 4 | `libmri.a:thd_idcode.c`, `libmri.a:thd_niftiread.c`, `libmri.a:thd_sarr.c`, `own:nii_dicom_batch.cpp` | 268 |
| links/fs | `statfs` | yes | 2 | `libmri.a:thd_filestuff.c` | 267 |
| links/fs | `fsync` | yes | 7 | `own:24swap.c`, `own:2swap.c`, `own:3dcopy.c`, `own:3dmaskdump.c`, `own:4swap.c`, `own:rmz.c` | 6 |
| links/fs | `sync` | yes | 5 | `own:rmz.c` | 1 |
| links/fs | `flock` | yes | 2 | `libmri.a:afni_logger.c` | 148 |
| links/fs | `lockf` | no | 2 | — | 0 |
| links/fs | `fcntl` | yes | 6 | `libmri.a:niml_stream.c`, `own:serial_helper.c` | 268 |
| links/fs | `mkdir` | no | 5 | `libmri.a:mri_dicom_hdr.c`, `libmri.a:thd_filestuff.c`, `libmri.a:thd_writedblk.c`, `own:nii_dicom_batch.cpp` | 268 |
| links/fs | `chmod` | no | 3 | `libmri.a:niml_url.c`, `libmri.a:thd_http.c` | 267 |
| sysinfo | `uname` | yes | 4 | `libmri.a:niml_uuid.c` | 267 |
| sysinfo | `sysconf` | yes | 4 | `libmri.a:machdep.c` | 267 |
| sysinfo | `times` | yes | 3 | `own:iframe.c` | 1 |
| rand48 | `drand48` | yes | 85 | `libmri.a:cs_symeig.c`, `libmri.a:edt_geomcon.c`, `libmri.a:parser_int.c`, `libmri.a:powell_int.c`, `libmri.a:thd_ttatlas_query.c`, `own:3dAnhist.c`, `own:3dBrainSync.c`, `own:3dIntracranial.c` (+11) | 267 |
| rand48 | `erand48` | yes | 5 | `libmri.a:cs_pv.c`, `own:3dLocalPV.c`, `own:3dShuffle.c`, `own:3dTsort.c` | 115 |
| rand48 | `jrand48` | yes | 2 | `libmri.a:cs_pv.c`, `own:3dLocalPV.c` | 114 |
| rand48 | `lrand48` | yes | 90 | `libmri.a:machdep.c`, `libmri.a:mri_cat2D.c`, `libmri.a:thd_correlate.c`, `own:1dCorrelate.c`, `own:1dsound.c`, `own:2perm.c`, `own:3dAllineate.c`, `own:3dGroupInCorr.c` (+6) | 267 |
| rand48 | `nrand48` | yes | 11 | `libmri.a:thd_correlate.c`, `own:3dAllineate.c`, `own:3dTsort.c`, `own:3dttest++.c`, `own:thd_permute.c` | 115 |
| rand48 | `srand48` | yes | 42 | `libmri.a:machdep.c`, `libmri.a:parser_int.c`, `libmri.a:powell_int.c`, `libmri.a:thd_ttatlas_query.c`, `own:1dCorrelate.c`, `own:1dgenARMA11.c`, `own:3dAllineate.c`, `own:3dAnhist.c` (+13) | 267 |
| gnu-strings | `memmem` | yes | 0 | `own:nii_dicom_batch.cpp` | 1 |
| tty | `tcgetattr` | yes | 2 | `own:serial_helper.c` | 1 |
| tty | `tcsetattr` | yes | 2 | `own:serial_helper.c` | 1 |
| tty | `cfsetispeed` | yes | 2 | `own:serial_helper.c` | 1 |
| tty | `cfsetospeed` | yes | 2 | `own:serial_helper.c` | 1 |
| glibc-malloc | `malloc_stats` | yes | 2 | `own:get_afni_model_PRF.c` | 1 |
| glibc-malloc | `mallopt` | yes | 1 | `libmri.a:machdep.c` | 267 |
| file-offsets | `ftell` | no | 8 | `libf2c.a:endfile.c`, `libf2c.a:err.c`, `libgiftiio.a:gifti_io.c`, `libmri.a:mri_read.c`, `libznz.a:znzlib.c`, `own:ge_header.c`, `own:jpg_0XC3.cpp`, `own:nii_dicom.cpp` (+1) | 279 |
| file-offsets | `fseek` | no | 158 | `libf2c.a:endfile.c`, `libf2c.a:err.c`, `libf2c.a:open.c`, `libf2c.a:rdfmt.c`, `libf2c.a:wrtfmt.c`, `libf2c.a:wsfe.c`, `libgiftiio.a:gifti_io.c`, `libmri.a:afni_logger.c` (+21) | 282 |
| file-offsets | `fseeko` | no | 4 | `libmri.a:mri_read.c`, `libmri.a:niml_stream.c`, `libmri.a:thd_dset_to_vectim.c`, `own:nii_dicom.cpp`, `own:nii_dicom_batch.cpp` | 268 |
| file-offsets | `ftello` | no | 1 | `libmri.a:niml_stream.c`, `own:nii_dicom.cpp`, `own:nii_dicom_batch.cpp` | 268 |
| file-offsets | `lseek` | no | 19 | `libmri.a:mri_dicom_hdr.c`, `libmri.a:mri_read_dicom.c` | 267 |
| file-offsets | `stat` | no | 56 | `libmri.a:mcw_glob.c`, `libmri.a:mri_dicom_hdr.c`, `libmri.a:mri_read.c`, `libmri.a:niml_util.c`, `libmri.a:suma_utils.c`, `libmri.a:thd_compress.c`, `libmri.a:thd_filestuff.c`, `libnifti2.a:nifti2_io.c` (+12) | 282 |
| file-offsets | `fstat` | no | 4 | `libmri.a:mri_dicom_hdr.c`, `libmri.a:mri_read.c` | 267 |

### A2. Programs whose own sources (not libmri) use problematic APIs

| Program | APIs (own objects only) |
|---|---|
| 1dCorrelate | `lrand48`, `srand48` |
| 1dTrdm | `drand48`, `nrand48`, `srand48` |
| 1dgenARMA11 | `srand48` |
| 1dsound | `fork`, `lrand48`, `system` |
| 24swap | `fsync` |
| 2perm | `lrand48` |
| 2swap | `fsync` |
| 3dANOVA | `system` |
| 3dANOVA2 | `system` |
| 3dANOVA3 | `system` |
| 3dAllineate | `lrand48`, `nrand48`, `srand48` |
| 3dAnhist | `drand48`, `srand48`, `system` |
| 3dAutoTcorrelate | `mmap`, `munmap` |
| 3dBlurToFWHM | `system` |
| 3dBrainSync | `drand48` |
| 3dClustSim | `mmap`, `munmap`, `srand48` |
| 3dExtractGroupInCorr | `mmap` |
| 3dFWHMx | `system` |
| 3dGroupInCorr | `lrand48`, `mmap` |
| 3dIntracranial | `drand48`, `srand48` |
| 3dLocalACF | `drand48`, `srand48` |
| 3dLocalPV | `erand48`, `jrand48` |
| 3dQwarp | `alarm`, `drand48`, `lrand48`, `srand48`, `system` |
| 3dREMLfit | `drand48` |
| 3dRSA | `drand48`, `nrand48`, `srand48` |
| 3dRegAna | `system` |
| 3dSetupGroupInCorr | `pclose`, `popen` |
| 3dShuffle | `erand48` |
| 3dTSgen | `dlclose`, `dlerror`, `dlopen`, `dlsym`, `drand48`, `srand48` |
| 3dToyProg | `drand48` |
| 3dTsort | `erand48`, `lrand48`, `nrand48` |
| 3dUniformize | `drand48`, `srand48` |
| 3dXClustSim | `mmap`, `munmap` |
| 3danisosmooth | `system` |
| 3dcopy | `fsync` |
| 3dmaskdump | `fsync` |
| 3dttest++ | `fork`, `kill`, `lrand48`, `nrand48`, `system`, `wait`, `waitpid` |
| 4swap | `fsync` |
| AlphaSim | `srand48` |
| Dimon | `nice`, `system` |
| Dimon1 | `nice`, `system` |
| Ifile | `lstat`, `readlink`, `system` |
| RSFgen | `drand48`, `srand48` |
| apsearch | `pclose`, `popen`, `system` |
| bitvec | `drand48`, `lrand48`, `srand48` |
| count | `drand48`, `srand48` |
| dcm2niix | `lstat`, `memmem`, `mkdir`, `pclose`, `popen`, `realpath`, `system` |
| file_tool | `system` |
| get_afni_model_PRF | `malloc_stats`, `system` |
| mpeg_encode | `accept`, `bind`, `connect`, `execvp`, `fork`, `gethostbyname`, `kill`, `listen`, `pclose`, `popen`, `socket`, `system`, `times` |
| plugout_tta | `system` |
| rmz | `fsync`, `lrand48`, `srand48`, `sync` |
| serial_helper | `accept`, `bind`, `cfsetispeed`, `cfsetospeed`, `fcntl`, `inet_ntoa`, `listen`, `recv`, `socket`, `tcgetattr`, `tcsetattr` |
| unu | `drand48`, `lrand48`, `srand48` |

### A3. Programs with no problematic API at link level (excluding stdio offsets)

`1dAstrip`, `3dAcost`, `3dConvolve`, `3dFWHM`, `3dNwarpCalc`, `afni_check_omp`, `afni_history`, `byteorder`, `clib_02_nifti2`, `column_cat`, `ge_header`, `gifti_test`, `gifti_tool`, `help_format`, `ibinom`, `mayo_analyze`, `mycat`, `nifti1_test`, `nifti1_tool`, `nifti_first_test_program`, `nifti_second_test_program`, `nifti_stats`, `nifti_tester001`, `nifti_tester002`, `nifti_tool`, `quotize`, `sqwave`, `tokens`, `whirlgif`

Total analysed executables: 303 link maps (302 linked; `Dimon1` failed, section 2.5).
