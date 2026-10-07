# afni-win

Full spec: `TASK.md`. Work strictly phase by phase; after each phase stop, report, and wait for confirmation.

## Hard rules

- Never commit AFNI upstream code. Upstream is fetched by tag at build time; the local `afni/` checkout is gitignored and read-only for us.
- The compat layer is attached from outside: replacement headers first in the include path, `-include afni_compat.h`, `afni_compat.dll`, binary file mode by default.
- Patches only for what the layer cannot cover; each patch header explains why.
- No silent stubs: unsupported functions are not declared; partial implementations fail with `errno` (e.g. `ENOSYS`) and a stderr message, never fake success. Allowed no-ops only via `manifests/noop-allowlist.txt` (with justification); declared-but-unimplemented functions go to `manifests/enosys.txt`.
- Decisions are recorded in `docs/DECISIONS.md`.
- Do not guess about upstream: read the actual code/build system; if unclear, stop and ask.
- Do only what the current phase requires.
- Every function implemented by the layer goes into `manifests/posix-api.txt` and has unit tests in `compat/tests/`.

## Language

- All repository content is English: code, comments, docstrings, docs, commit messages.

## Code

- C: C11, clean under `-Wall -Wextra`.
- Python 3.12+: `uv`, `ruff`, `ty`; absolute imports; stdlib/third-party/local groups; `logging`, no `print`; return types mandatory; English docstrings (Args/Returns/Raises); Pydantic for config; helpers prefixed `_`; no inline comments.

## Commits

- Commit per layer (docs, compat headers, compat src, cmake, CI, ... separately).
- One short imperative line, no body, no `Co-Authored-By`.
