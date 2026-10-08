#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "test_common.h"

static size_t read_all(const char *path, const char *mode, char *buf, size_t size) {
  FILE *fp = fopen(path, mode);
  size_t got;

  CHECK(fp != NULL);
  if (fp == NULL) {
    return 0;
  }
  got = fread(buf, 1, size, fp);
  fclose(fp);
  return got;
}

int main(void) {
  static const char data[] = {'a', '\r', '\n', 0x1a, 'b'};
  char buf[16];
  FILE *fp;

  /* A host process (R.exe, python.exe) that leaves the UCRT default. */
  CHECK(_set_fmode(_O_TEXT) == 0);

  fp = fopen("compat_stdio.bin", "w");
  CHECK(fp != NULL);
  if (fp != NULL) {
    CHECK(fwrite(data, 1, sizeof(data), fp) == sizeof(data));
    fclose(fp);
  }
  CHECK(read_all("compat_stdio.bin", "r", buf, sizeof(buf)) == sizeof(data));
  CHECK(memcmp(buf, data, sizeof(data)) == 0);
  CHECK(read_all("compat_stdio.bin", "r+", buf, sizeof(buf)) == sizeof(data));

  /* An explicit "t" keeps text mode: CR LF becomes LF, Ctrl-Z ends the file. */
  CHECK(read_all("compat_stdio.bin", "rt", buf, sizeof(buf)) == 2);
  CHECK(memcmp(buf, "a\n", 2) == 0);

  CHECK_ERRNO(fopen("compat_stdio_missing.bin", "r"), ENOENT);
  CHECK_ERRNO(afni_compat_fopen("compat_stdio.bin", NULL), EINVAL);

  CHECK(_set_fmode(_O_BINARY) == 0);
  remove("compat_stdio.bin");
  return TEST_RESULT();
}
