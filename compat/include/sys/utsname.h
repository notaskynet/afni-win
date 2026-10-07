#ifndef AFNI_COMPAT_SYS_UTSNAME_H
#define AFNI_COMPAT_SYS_UTSNAME_H

#include "afni_compat_api.h"

#ifdef __cplusplus
extern "C" {
#endif

#define AFNI_COMPAT_UTSNAME_LENGTH 65

struct utsname {
  char sysname[AFNI_COMPAT_UTSNAME_LENGTH];
  char nodename[AFNI_COMPAT_UTSNAME_LENGTH];
  char release[AFNI_COMPAT_UTSNAME_LENGTH];
  char version[AFNI_COMPAT_UTSNAME_LENGTH];
  char machine[AFNI_COMPAT_UTSNAME_LENGTH];
};

AFNI_COMPAT_API int uname(struct utsname *buf);

#ifdef __cplusplus
}
#endif

#endif
