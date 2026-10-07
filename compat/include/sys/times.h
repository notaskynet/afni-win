#ifndef AFNI_COMPAT_SYS_TIMES_H
#define AFNI_COMPAT_SYS_TIMES_H

#include <time.h>

#include "afni_compat_api.h"

#ifdef __cplusplus
extern "C" {
#endif

struct tms {
  clock_t tms_utime;
  clock_t tms_stime;
  clock_t tms_cutime;
  clock_t tms_cstime;
};

AFNI_COMPAT_API clock_t times(struct tms *buf);

#ifdef __cplusplus
}
#endif

#endif
