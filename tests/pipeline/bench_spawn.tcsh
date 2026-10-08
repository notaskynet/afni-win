#!/usr/bin/env tcsh
#
# Process start cost from tcsh: N runs each of a POSIX utility, a native
# AFNI program, a tcsh script and the Python interpreter. Prints
# "<what> <total seconds> <ms per call>".
#
#   tcsh bench_spawn.tcsh N

set n = $argv[1]
3dcalc -a 'jRandomDataset:4,4,4,1' -expr a -prefix bench_dset >& /dev/null

foreach what ( true ccalc @GetAfniView python )
   set t0 = `date +%s.%N`
   set i = 0
   while ( $i < $n )
      switch ( $what )
      case true:
         true
         breaksw
      case ccalc:
         ccalc -expr 1 > /dev/null
         breaksw
      case @GetAfniView:
         @GetAfniView bench_dset+orig > /dev/null
         breaksw
      case python:
         python -c pass
         breaksw
      endsw
      @ i ++
   end
   set t1 = `date +%s.%N`
   echo $what $t0 $t1 $n | awk '{ printf "%s %.3f %.2f\n", $1, $3 - $2, 1000 * ($3 - $2) / $4 }'
end
