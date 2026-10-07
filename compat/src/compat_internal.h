#ifndef AFNI_COMPAT_INTERNAL_H
#define AFNI_COMPAT_INTERNAL_H

#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#include <windows.h>

#include <errno.h>

void afni_compat_report(const char *function, const char *detail);
void afni_compat_set_errno_from_win32(DWORD error);

#define AFNI_COMPAT_UNSUPPORTED(detail)            \
  do {                                             \
    static volatile LONG reported_ = 0;            \
    if (InterlockedExchange(&reported_, 1) == 0) { \
      afni_compat_report(__func__, (detail));      \
    }                                              \
    errno = ENOSYS;                                \
  } while (0)

#endif
