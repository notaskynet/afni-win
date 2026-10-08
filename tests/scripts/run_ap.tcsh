#!/usr/bin/env tcsh
#
# Prototype pipeline for the scripting research (docs/inventory/scripts-REPORT.md):
# afni_proc.py on one OpenNeuro ds000102 subject with an affine MNI template.
#
#   tcsh run_ap.tcsh DATA_DIR ANAT_SS TEMPLATE WORK_DIR
#
# ANAT_SS is the skull-stripped T1 (3dSkullStrip is built only with SUMA, so
# both platforms get the same stripped anatomy). -check_afni_version no drops
# the `afni -ver` line: the afni GUI program is not part of the Windows build.
# The QC report (@chauffeur_afni: afni GUI + Xvfb) is off for the same reason.
# The proc script is written to WORK_DIR; running it is a separate step.

if ( $#argv != 4 ) then
   echo "usage: run_ap.tcsh DATA_DIR ANAT_SS TEMPLATE WORK_DIR"
   exit 1
endif
set data = "$argv[1]"
set anat = "$argv[2]"
set tpl  = "$argv[3]"
set work = "$argv[4]"

mkdir -p "$work"
cd "$work"

afni_proc.py -subj_id sub08                                              \
    -script proc.sub08 -scr_overwrite                                    \
    -check_afni_version no                                               \
    -dsets "$data/sub-08_task-flanker_run-1_bold.nii.gz"                 \
           "$data/sub-08_task-flanker_run-2_bold.nii.gz"                 \
    -copy_anat "$anat" -anat_has_skull no                                \
    -blocks tshift align tlrc volreg blur mask scale regress             \
    -align_opts_aea -cost lpc+ZZ -giant_move                             \
    -tlrc_base "$tpl"                                                    \
    -volreg_align_to MIN_OUTLIER                                         \
    -volreg_align_e2a                                                    \
    -volreg_tlrc_warp                                                    \
    -blur_size 4.0                                                       \
    -regress_stim_times "$data/congruent.1D" "$data/incongruent.1D"      \
    -regress_stim_labels congruent incongruent                           \
    -regress_basis 'BLOCK(2,1)'                                          \
    -regress_censor_motion 0.3                                           \
    -regress_censor_outliers 0.05                                        \
    -regress_motion_per_run                                              \
    -regress_opts_3dD -jobs 1                                            \
        -gltsym 'SYM: incongruent -congruent' -glt_label 1 inc-con       \
    -regress_make_ideal_sum sum_ideal.1D                                 \
    -regress_est_blur_epits                                              \
    -regress_est_blur_errts                                              \
    -html_review_style none
