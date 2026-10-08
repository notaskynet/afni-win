#!/usr/bin/env bash
#
# Put built programs, the upstream tcsh and Python scripts and the afnipy
# package into one directory, the layout of an upstream installation.
#
#   bash assemble.sh UPSTREAM_DIR PROGRAMS_DIR OUT_DIR
set -euo pipefail
upstream=$1
programs=$2
out=$3
mkdir -p "$out"
cp -r "$programs"/. "$out"/
find "$upstream/src/scripts_install" "$upstream/src/python_scripts/scripts" -maxdepth 1 -type f \
  ! -name CMakeLists.txt -exec cp {} "$out"/ \;
cp -r "$upstream/src/python_scripts/afnipy" "$out"/afnipy
