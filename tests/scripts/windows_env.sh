# Environment of the Windows prototype steps (sourced from an MSYS2 UCRT64
# bash): the assembled AFNI directory first on PATH, afnipy importable by the
# native Python, and for the posix-shell variants the Python shell shim.
export PATH="$PWD/afni-bin:$PATH"
export PYTHONPATH
PYTHONPATH="$(cygpath -w "$PWD/afni-bin")"
case "${VARIANT:-}" in
  posix-shell*)
    PYTHONPATH="$(cygpath -w "$PWD/tests/scripts/pyshim");$PYTHONPATH"
    export AFNI_POSIX_SHELL
    AFNI_POSIX_SHELL="$(cygpath -w /usr/bin/sh.exe)"
    ;;
esac
