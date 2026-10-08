#!/usr/bin/env bash
#
# Generate and run the prototype pipeline, then collect the results:
# status.txt (exit code), seconds.txt (wall time of the proc script),
# output.proc.sub08 (its log) and outputs/ (files compared between platforms).
#
#   bash run_pipeline.sh DATA_DIR INPUTS_DIR WORK_DIR RESULTS_DIR
set -uo pipefail
data=$1
inputs=$2
work=$3
results=$4
here=$(cd "$(dirname "$0")" && pwd)
mkdir -p "$results/outputs/logs"
tcsh "$here/run_ap.tcsh" "$data" "$inputs/anat_ss.nii.gz" "$inputs/MNI_brain.nii.gz" "$work" \
  > "$results/afni_proc.log" 2>&1
echo "afni_proc.py exit code $?"
cd "$work"
start=$(date +%s)
tcsh -xef proc.sub08 > "$results/output.proc.sub08" 2>&1
status=$?
echo $(( $(date +%s) - start )) > "$results/seconds.txt"
echo "$status" > "$results/status.txt"
echo "proc.sub08 exit code $status after $(cat "$results/seconds.txt") s"
tail -n 30 "$results/output.proc.sub08"
cp proc.sub08 "$results"/
cd sub08.results 2>/dev/null || exit 0
for f in stats.sub08+tlrc.* X.xmat.1D dfile_rall.1D motion_sub08_enorm.1D \
  censor_sub08_combined_2.1D out.ss_review.sub08.txt blur_est.sub08.1D \
  mask_epi_anat.sub08+tlrc.* anat_final.sub08+tlrc.* final_epi_vr_base_min_outlier+tlrc.* \
  mat.basewarp.aff12.1D out.gcor.1D TSNR.sub08+tlrc.*; do
  [ -e "$f" ] && cp "$f" "$results/outputs/"
done
exit 0
