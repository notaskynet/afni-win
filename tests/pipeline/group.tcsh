#!/usr/bin/env tcsh
#
# Group analysis of the acceptance pipeline (docs/DECISIONS.md D40), on the
# results that tests/pipeline/run.py leaves in WORK_DIR/<subj>/<subj>.results:
# intersection mask, 3dttest++ on the incongruent-congruent contrast and
# 3dMVM (R) with condition as within-subject factor. Outputs go to
# WORK_DIR/group.
#
#   tcsh -ef group.tcsh WORK_DIR SUBJ_ID SUBJ_ID ...

if ( $#argv < 3 ) then
   echo "usage: group.tcsh WORK_DIR SUBJ_ID SUBJ_ID ..."
   exit 1
endif

# Sub-brick selectors such as [inc-con_GLT#0_Coef] are not file patterns.
set noglob

set work = "$argv[1]"
set subjects = ( $argv[2-] )
cd "$work"
rm -rf group
mkdir group

set masks = ( )
set setA = ( )
echo "Subj condition InputFile" > group/mvm_table.txt
foreach s ( $subjects )
   set stats = "$s/$s.results/stats.$s+tlrc"
   set masks = ( $masks "$s/$s.results/mask_epi_anat.$s+tlrc.HEAD" )
   set setA = ( $setA $s "${stats}[inc-con_GLT#0_Coef]" )
   echo "$s congruent ${stats}[congruent#0_Coef]" >> group/mvm_table.txt
   echo "$s incongruent ${stats}[incongruent#0_Coef]" >> group/mvm_table.txt
end

3dmask_tool -input $masks -frac 1.0 -prefix group/group_mask

3dttest++ -prefix group/ttest.inc-con -mask group/group_mask+tlrc \
   -setA inc-con $setA

3dMVM -prefix group/MVM -jobs 1 -mask group/group_mask+tlrc \
   -bsVars 1 -wsVars condition                                \
   -num_glt 1 -gltLabel 1 inc-con                             \
   -gltCode 1 'condition : 1*incongruent -1*congruent'        \
   -dataTable @group/mvm_table.txt
