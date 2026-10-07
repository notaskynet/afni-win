#include <fcntl.h>
#include <io.h>
#include <stdio.h>
#include <unistd.h>

#include "test_common.h"

int main(void) {
  const char *path = "compat_init_file.bin";
  unsigned char bytes[64];
  int mode = -1;
  FILE *fp;
  int fd;

  for (int i = 0; i < 64; ++i) {
    bytes[i] = (unsigned char)(i == 10 ? 0x1A : (i == 20 ? '\n' : (i == 30 ? '\r' : 'x')));
  }
  fp = fopen(path, "w");
  CHECK(fp != NULL && fwrite(bytes, 1, 64, fp) == 64);
  fclose(fp);

  CHECK(_get_fmode(&mode) == 0 && mode == _O_BINARY);

  fp = fopen(path, "r");
  CHECK(fp != NULL);
  if (fp != NULL) {
    unsigned char back[128];
    CHECK(fread(back, 1, sizeof(back), fp) == 64);
    CHECK(memcmp(back, bytes, 64) == 0);
    fclose(fp);
  }

  fd = open(path, O_RDONLY);
  CHECK(fd >= 0);
  if (fd >= 0) {
    unsigned char back[128];
    CHECK(read(fd, back, sizeof(back)) == 64);
    close(fd);
  }

  CHECK(_setmode(_fileno(stdout), _O_BINARY) == _O_BINARY);
  CHECK(_setmode(_fileno(stderr), _O_BINARY) == _O_BINARY);
  CHECK(_setmode(_fileno(stdin), _O_BINARY) == _O_BINARY);

  remove(path);
  return TEST_RESULT();
}
