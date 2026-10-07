#include <sys/select.h>
#include <sys/time.h>
#include <sys/times.h>

#include "compat_internal.h"
#include "process_internal.h"

static int set_has_descriptors(const fd_set *set, int nfds) {
  if (set == NULL) {
    return 0;
  }
  for (int fd = 0; fd < nfds; ++fd) {
    if (FD_ISSET(fd, set)) {
      return 1;
    }
  }
  return 0;
}

int select(int nfds, fd_set *readfds, fd_set *writefds, fd_set *exceptfds,
           struct timeval *timeout) {
  if (nfds < 0 || nfds > FD_SETSIZE) {
    errno = EINVAL;
    return -1;
  }
  if (set_has_descriptors(readfds, nfds) || set_has_descriptors(writefds, nfds) ||
      set_has_descriptors(exceptfds, nfds)) {
    AFNI_COMPAT_UNSUPPORTED("waiting on file descriptors or sockets");
    return -1;
  }
  if (timeout == NULL) {
    for (;;) {
      Sleep(INFINITE);
    }
  }
  if (timeout->tv_sec < 0 || timeout->tv_usec < 0 || timeout->tv_usec >= 1000000) {
    errno = EINVAL;
    return -1;
  }
  {
    unsigned long long ms =
        (unsigned long long)timeout->tv_sec * 1000ULL + ((unsigned long long)timeout->tv_usec + 999ULL) / 1000ULL;
    while (ms > 0) {
      DWORD chunk = ms > 0x7fffffffULL ? 0x7fffffffUL : (DWORD)ms;
      Sleep(chunk);
      ms -= chunk;
    }
  }
  return 0;
}

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
