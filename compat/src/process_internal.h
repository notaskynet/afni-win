#ifndef AFNI_COMPAT_PROCESS_INTERNAL_H
#define AFNI_COMPAT_PROCESS_INTERNAL_H

#include <time.h>

#include "compat_internal.h"

void afni_compat_children_times(clock_t *user, clock_t *system_time);
char *afni_compat_command_line(char *const argv[]);
int afni_compat_wait_status(DWORD code);

#endif
