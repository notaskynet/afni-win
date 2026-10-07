#include <sys/utsname.h>
#include <unistd.h>

#include "test_common.h"

int main(void) {
  struct utsname name;
  char host[256];

  CHECK(sysconf(_SC_PAGESIZE) >= 4096);
  CHECK(sysconf(_SC_PAGE_SIZE) == sysconf(_SC_PAGESIZE));
  CHECK(sysconf(_SC_NPROCESSORS_CONF) >= 1);
  CHECK(sysconf(_SC_NPROCESSORS_ONLN) >= 1);
  CHECK(sysconf(_SC_PHYS_PAGES) > 0);
  CHECK(sysconf(_SC_AVPHYS_PAGES) > 0);
  CHECK(sysconf(_SC_AVPHYS_PAGES) <= sysconf(_SC_PHYS_PAGES));
  CHECK_ERRNO(sysconf(-12345), EINVAL);

  CHECK(uname(&name) == 0);
  CHECK(strcmp(name.sysname, "Windows") == 0);
  CHECK(name.nodename[0] != '\0');
  CHECK(name.release[0] != '\0');
  CHECK(name.machine[0] != '\0');

  CHECK(gethostname(host, sizeof(host)) == 0);
  CHECK(strcmp(host, name.nodename) == 0);
  CHECK_ERRNO(gethostname(host, 1), ENAMETOOLONG);

  CHECK(getppid() >= 0);
  CHECK(getppid() != getpid());

  return TEST_RESULT();
}
