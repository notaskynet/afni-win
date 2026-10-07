#include <sys/time.h>
#include <sys/times.h>

#include "compat_internal.h"
#include "process_internal.h"

int setitimer(int which, const struct itimerval *new_value, struct itimerval *old_value) {
  (void)which;
  (void)new_value;
  (void)old_value;
  AFNI_COMPAT_UNSUPPORTED("interval timers deliver asynchronous signals");
  return -1;
}

static clock_t filetime_to_ticks(const FILETIME *ft) {
  ULARGE_INTEGER value;
  value.LowPart = ft->dwLowDateTime;
  value.HighPart = ft->dwHighDateTime;
  return (clock_t)(value.QuadPart / (10000000ULL / CLOCKS_PER_SEC));
}

clock_t times(struct tms *buf) {
  FILETIME creation;
  FILETIME exit_time;
  FILETIME kernel;
  FILETIME user;

  if (buf != NULL) {
    if (!GetProcessTimes(GetCurrentProcess(), &creation, &exit_time, &kernel, &user)) {
      afni_compat_set_errno_from_win32(GetLastError());
      return (clock_t)-1;
    }
    buf->tms_utime = filetime_to_ticks(&user);
    buf->tms_stime = filetime_to_ticks(&kernel);
    afni_compat_children_times(&buf->tms_cutime, &buf->tms_cstime);
  }
  return (clock_t)(GetTickCount64() / (1000ULL / CLOCKS_PER_SEC));
}
