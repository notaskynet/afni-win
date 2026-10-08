#include <signal.h>
#include <stdio.h>

#include "compat_internal.h"

#define MAX_REPORTED_SIGNAL 64

static volatile LONG reported[MAX_REPORTED_SIGNAL];

afni_compat_sighandler_t afni_compat_signal(int sig, afni_compat_sighandler_t handler) {
  switch (sig) {
    case SIGINT:
    case SIGILL:
    case SIGFPE:
    case SIGSEGV:
    case SIGTERM:
    case SIGBREAK:
    case SIGABRT:
    case SIGABRT_COMPAT:
      return signal(sig, handler);
    case SIGPIPE:
    case SIGBUS:
    case SIGQUIT:
      return SIG_DFL;
    default:
      break;
  }
  if (sig < 0 || sig >= MAX_REPORTED_SIGNAL || InterlockedExchange(&reported[sig], 1) == 0) {
    fprintf(stderr, "** afni-win: signal(%d) is not supported on Windows: no such signal\n", sig);
    fflush(stderr);
  }
  errno = ENOSYS;
  return SIG_ERR;
}

int pause(void) {
  AFNI_COMPAT_UNSUPPORTED("there are no asynchronous signals to wait for");
  return -1;
}
