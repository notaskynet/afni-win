#include <stdio.h>
#include <stdlib.h>
#include <sys/wait.h>

#include "test_common.h"

int main(void) {
  unsigned char bytes[256];
  unsigned char back[512];
  FILE *fp;
  int status;

  for (int i = 0; i < 256; ++i) {
    bytes[i] = (unsigned char)i;
  }
  CHECK(system(NULL) != 0);

  status = system("exit 4");
  CHECK(WIFEXITED(status) && WEXITSTATUS(status) == 4);
  CHECK(system("echo discarded > /dev/null") == 0);
  CHECK(system("echo discarded >& /dev/null") == 0);

  fp = popen("printf 'a\\r\\nb'", "r");
  CHECK(fp != NULL);
  if (fp != NULL) {
    CHECK(fread(back, 1, sizeof(back), fp) == 4 && memcmp(back, "a\r\nb", 4) == 0);
    CHECK(pclose(fp) == 0);
  }

  CHECK(system("mkdir -p 'compat shell dir'") == 0);
  fp = popen("gzip -c > 'compat shell dir/data.gz'", "w");
  CHECK(fp != NULL);
  if (fp != NULL) {
    CHECK(fwrite(bytes, 1, sizeof(bytes), fp) == sizeof(bytes));
    CHECK(pclose(fp) == 0);
  }
  fp = popen("gzip -dc 'compat shell dir/data.gz'", "r");
  CHECK(fp != NULL);
  if (fp != NULL) {
    CHECK(fread(back, 1, sizeof(back), fp) == sizeof(bytes));
    CHECK(memcmp(back, bytes, sizeof(bytes)) == 0);
    CHECK(pclose(fp) == 0);
  }
  CHECK(system("rm -rf 'compat shell dir'") == 0);
  return TEST_RESULT();
}
