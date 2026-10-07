# Spec: afni-win — compatibility layer for building AFNI on Windows

## 1. Goal

Create the `afni-win` repository which, without modifying AFNI source code (except for a minimal set of patches), builds native Windows AFNI binaries for every new tag of the upstream repository https://github.com/afni/afni.

The build uses the MinGW-w64 toolchain (MSYS2, UCRT64 environment). POSIX functionality missing on Windows is provided by our own compatibility layer on top of WinAPI.

## 2. Key principles

1. **Upstream is not modified and not stored in this repository.** AFNI sources are fetched by tag at build time. Committing AFNI code into `afni-win` is forbidden.
2. **The layer is attached from outside:** replacement headers (first in the include path), forced include (`-include afni_compat.h`), a library of implementations (`afni_compat.dll`, see `docs/DECISIONS.md` D5a), runtime settings (binary file mode by default).
3. **Patches are the last resort.** A patch is allowed only for what the layer cannot cover (e.g. `fork()` without `exec`). Each patch has a header explaining why the layer is not suitable.
4. **No silent stubs.** A function the layer does not support must not be declared in replacement headers, so that its use causes a compile or link error. If a partial implementation is unavoidable, unsupported cases return an error (`errno = ENOSYS` etc.) and print a message to stderr. Returning "success" without performing the action is forbidden. The only exception is a no-op whose absence of action cannot change any result (e.g. a handler for a signal Windows never raises); each such case is listed with a justification in `manifests/noop-allowlist.txt`. Functions that are declared but not yet implemented are listed in `manifests/enosys.txt`.
5. **Do not invent anything about upstream.** Before any decision about building AFNI, study the actual upstream code and build system. If something is unclear, stop and ask.

## 3. Repository layout

```
afni-win/
├── compat/
│   ├── include/            # replacement POSIX headers + afni_compat.h
│   ├── src/                # WinAPI-based implementations
│   └── tests/              # layer unit tests
├── patches/                # 0001-*.patch, applied via git apply --3way
├── cmake/
│   ├── toolchain-mingw.cmake
│   ├── afni-win-project.cmake   # hook: adds the compat layer to the upstream project
│   └── gifti/                   # builds the in-tree gifti library
├── manifests/
│   ├── programs-required.txt
│   ├── programs-optional.txt
│   └── posix-api.txt       # whitelist of APIs implemented by the layer
├── tools/                  # helper scripts (Python)
├── tests/
│   └── regression/         # Linux vs Windows result comparison
├── docs/
│   └── inventory/          # inventory reports
└── .github/workflows/
    ├── watch-upstream-tags.yml
    └── build-windows.yml
```

## 4. Phases

After each phase: stop, report briefly (what was done, what failed, which decisions were made and why) and wait for confirmation before the next phase.

### Phase 0. Research (no layer code)

1. Clone upstream AFNI (latest tag) into a temporary directory outside the repository.
2. Study the upstream build system: CMake and/or `Makefile.*` in `src/`, list of built programs, external dependencies, vendored third-party libraries.
3. Inventory POSIX dependencies: find across all C code the calls to `fork`, `vfork`, `exec*`, `waitpid`, `shmget`/`shmat`/`shmdt`/`shmctl`, `mmap`/`munmap`, `dlopen`/`dlsym`, `popen`, `system`, `signal`/`sigaction`, `alarm`, sockets, `getpwuid`, `symlink`/`readlink`, and the use of `long` for file sizes and offsets.
4. For each `fork` occurrence determine whether it is followed by `exec` (emulatable) or not (requires a patch).
5. Check how AFNI plugins obtain symbols from the main executable.

**Deliverable:** `docs/inventory/REPORT.md` with tables: API → number of calls → files → affected programs; proposed classification of programs into required/optional; list of places requiring patches; risks.

**Acceptance:** the report is based on the actual code (with file paths), without assumptions.

### Phase 1. Repository skeleton and building console programs without POSIX dependencies

1. Create the layout from section 3.
2. `cmake/toolchain-mingw.cmake`: MinGW-w64 UCRT64, `compat/include` first in the include path, `-include afni_compat.h`, linking with `libafni_compat`, binary file mode by default.
3. Minimal `afni_compat.h` and only the headers needed for this phase.
4. Build the base AFNI library and a small set of console programs that do not use problematic APIs (chosen from the phase 0 report; reference: `3dinfo`, `3dcalc`, `3dTstat`).

**Acceptance:** programs build in MSYS2 UCRT64 on Windows, `3dinfo` correctly reads a test NIfTI and BRIK dataset, `3dcalc` produces a result matching the Linux build of the same tag.

### Phase 2. Compatibility layer

Implement in `compat/src/` one module per API group, in the order determined by the phase 0 report (whatever unlocks more programs first):

| Group | Implementation |
|---|---|
| Shared memory (`shm*`) | `CreateFileMapping` / `MapViewOfFile` |
| `mmap` / `munmap` | `CreateFileMapping` / `MapViewOfFile` |
| Processes (`fork`+`exec`, `waitpid`) | `CreateProcess`, `WaitForSingleObject`, `GetExitCodeProcess` |
| Dynamic loading (`dl*`) | `LoadLibrary`, `GetProcAddress`, `dlerror` with text from `GetLastError` |
| Sockets | Winsock, `WSAStartup` initialization at startup |
| Signals, timers | only the cases actually used; everything else is an error |
| Paths and environment | `HOME` → `%USERPROFILE%`, `/tmp` → `GetTempPath`, `/dev/null` → `NUL` |

Requirements:
- Every implemented function is listed in `manifests/posix-api.txt`.
- Every module is covered by unit tests in `compat/tests/`, tests run in CI.
- Error handling: correct `errno`, clear message.

**Acceptance:** all programs classified as required in phase 0 build (except those requiring patches), layer unit tests pass.

### Phase 3. Patches

1. Prepare patches only for the places listed in the phase 0 report as impossible to handle in the layer.
2. Each patch is minimal, applies via `git apply --3way`, and states the reason in its header.

**Acceptance:** all patches apply to the latest upstream tag; programs that need them build.

### Phase 4. CI

1. `watch-upstream-tags.yml`: runs on schedule (daily) and manually (`workflow_dispatch`). Gets upstream tags via `git ls-remote --tags`, compares with already published releases, triggers `build-windows.yml` for each new tag.
2. `build-windows.yml` (input: upstream tag):
   - checkout upstream at the tag and `afni-win`;
   - apply patches; on failure — fail naming the patch;
   - build on `windows-latest` with MSYS2 UCRT64;
   - required programs must build, otherwise no release is published; optional — best effort, with a report;
   - layer unit tests;
   - regression tests (phase 5);
   - report of POSIX call differences vs the previous built tag;
   - publish GitHub Release `<tag>-win` with a zip archive and a build report.
3. A tag that failed to build must not be retried forever: mark it as failed (e.g. an issue or a state file) and do not rebuild it without a manual run.

**Acceptance:** a manual run for the latest upstream tag creates a release; a subsequent scheduled run does not create duplicates.

### Phase 5. Regression testing

1. Parallel Linux build of the same tag (using the official upstream method).
2. A small set of test data (openly redistributable only) and run scenarios for required programs.
3. A script comparing Linux and Windows output datasets with numerical tolerance, and a discrepancy report.

**Acceptance:** the comparison runs in CI; discrepancies beyond tolerance mark the build as failed.

### Out of scope

GUI (`afni`, `suma`), tcsh scripts, installer (MSI/NSIS). These will be handled separately after phases 0–5 are complete. Do not start this work without a separate request.

## 5. Code requirements

**C (compatibility layer):** C11, builds without warnings with `-Wall -Wextra`, no global side effects from including headers other than declared ones.

**Python (scripts in `tools/`, result comparison):**
- Python 3.12+, absolute imports only, order: stdlib → third-party → local, groups separated by a blank line;
- `logging` instead of `print()`;
- modern annotations (`int | None`, `list`, `dict`), return type annotations mandatory, `cast()` where needed;
- a docstring for every function, in English (Args, Returns, Raises sections);
- configuration via Pydantic models; complex nested structures via dedicated types;
- helper functions prefixed with `_`;
- no inline comments.

**General:** do only what the current phase specifies; do not add functionality beyond the spec. All repository content (code, docs, commit messages) is in English.

## 6. License

AFNI is distributed mostly under the GPL. The `afni-win` repository must have a GPL-compatible license; releases must state which upstream tag and which patches the binary was built from.

## 7. When to stop and ask

- upstream behavior is unclear or contradicts this spec;
- a program from the required list needs a large patch;
- a decision affects architecture (e.g. moving the core into a DLL for plugins);
- a choice between several equivalent approaches is needed.
