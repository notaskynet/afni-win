#include <pwd.h>
#include <unistd.h>

#include "test_common.h"

int main(void) {
  struct passwd *pw;

  CHECK(getuid() == 0);
  CHECK(geteuid() == getuid());
  pw = getpwuid(getuid());
  CHECK(pw != NULL);
  if (pw != NULL) {
    CHECK(pw->pw_name != NULL && pw->pw_name[0] != '\0');
    CHECK(pw->pw_dir != NULL && pw->pw_dir[0] != '\0');
    CHECK(strchr(pw->pw_dir, '\\') == NULL);
    CHECK(pw->pw_uid == 0);
  }
  CHECK(getpwuid(1000) == NULL);
  return TEST_RESULT();
}
