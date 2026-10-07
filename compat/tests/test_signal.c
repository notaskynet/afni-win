#include <signal.h>

#include "test_common.h"

static volatile sig_atomic_t received = 0;

static void handler(int sig) {
  received = sig;
}

int main(void) {
  CHECK(signal(SIGPIPE, handler) == SIG_DFL);
  CHECK(signal(SIGBUS, SIG_IGN) == SIG_DFL);

  errno = 0;
  CHECK(signal(SIGALRM, handler) == SIG_ERR);
  CHECK(errno == ENOSYS);
  errno = 0;
  CHECK(signal(SIGHUP, handler) == SIG_ERR);
  CHECK(errno == ENOSYS);
  errno = 0;
  CHECK(signal(SIGQUIT, handler) == SIG_ERR);
  CHECK(errno == ENOSYS);

  CHECK(signal(SIGINT, handler) != SIG_ERR);
  CHECK(raise(SIGINT) == 0);
  CHECK(received == SIGINT);
  CHECK(signal(SIGTERM, handler) != SIG_ERR);
  CHECK(signal(SIGTERM, SIG_DFL) == handler);

  CHECK(SIGIOT == SIGABRT);
  CHECK(SIGPIPE != SIGINT && SIGBUS != SIGFPE && SIGALRM != SIGTERM);

  return TEST_RESULT();
}
