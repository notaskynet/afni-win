#!/usr/bin/env bash
#
# Download the prototype inputs into DIR: OpenNeuro ds000102 (PDDL) subject
# sub-08 and the TemplateFlow MNI152NLin2009cAsym T1 and brain mask, then
# write the stimulus timing files congruent.1D and incongruent.1D.
#
#   bash fetch_data.sh DIR
set -euo pipefail
dir=$1
mkdir -p "$dir"
cd "$dir"
ds=https://s3.amazonaws.com/openneuro.org/ds000102/sub-08
tf=https://templateflow.s3.amazonaws.com/tpl-MNI152NLin2009cAsym
get() { curl -fsSL --retry 5 --retry-all-errors -o "$(basename "$1")" "$1"; }
get "$ds/anat/sub-08_T1w.nii.gz"
for run in 1 2; do
  get "$ds/func/sub-08_task-flanker_run-${run}_bold.nii.gz"
  get "$ds/func/sub-08_task-flanker_run-${run}_events.tsv"
done
get "$tf/tpl-MNI152NLin2009cAsym_res-01_T1w.nii.gz"
get "$tf/tpl-MNI152NLin2009cAsym_res-01_desc-brain_mask.nii.gz"
for cond in congruent incongruent; do
  for run in 1 2; do
    awk -F'\t' -v c="$cond" 'NR > 1 && $8 == c { t = t s $1; s = " " } END { print t }' \
      "sub-08_task-flanker_run-${run}_events.tsv"
  done > "$cond.1D"
done
