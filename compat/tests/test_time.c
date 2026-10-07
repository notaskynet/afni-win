#include <sys/select.h>
#include <sys/time.h>
#include <sys/times.h>
#include <windows.h>

#include "test_common.h"

int main(void) {
  struct timeval tv;
  struct itimerval itv;
  struct tms t;
  fd_set set;
  ULONGLONG start;
  ULONGLONG elapsed;

  tv.tv_sec = 0;
  tv.tv_usec = 200000;
  start = GetTickCount64();
  CHECK(select(1, NULL, NULL, NULL, &tv) == 0);
  elapsed = GetTickCount64() - start;
  CHECK(elapsed >= 150);

  tv.tv_sec = 0;
  tv.tv_usec = 0;
  FD_ZERO(&set);
  CHECK(select(0, &set, NULL, NULL, &tv) == 0);

  FD_ZERO(&set);
  FD_SET(3, &set);
  CHECK(FD_ISSET(3, &set));
  CHECK(!FD_ISSET(4, &set));
  CHECK_ERRNO(select(4, &set, NULL, NULL, &tv), ENOSYS);
  FD_CLR(3, &set);
  CHECK(!FD_ISSET(3, &set));

  tv.tv_usec = 1000000;
  CHECK_ERRNO(select(1, NULL, NULL, NULL, &tv), EINVAL);
  CHECK_ERRNO(select(-1, NULL, NULL, NULL, &tv), EINVAL);

  memset(&itv, 0, sizeof(itv));
  CHECK_ERRNO(setitimer(ITIMER_REAL, &itv, NULL), ENOSYS);

  CHECK(times(&t) != (clock_t)-1);
  CHECK(t.tms_utime >= 0 && t.tms_stime >= 0);
  CHECK(t.tms_cutime == 0 && t.tms_cstime == 0);

  return TEST_RESULT();
}
