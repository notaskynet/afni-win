#include <fcntl.h>
#include <sys/mman.h>
#include <unistd.h>

#include "test_common.h"

int main(void) {
  const char *path = "compat_mman_file.bin";
  const size_t size = 200000;
  unsigned char *data = (unsigned char *)malloc(size);
  unsigned char *view;
  int fd;

  for (size_t i = 0; i < size; ++i) {
    data[i] = (unsigned char)(i * 7 + 3);
  }
  {
    FILE *fp = fopen(path, "wb");
    CHECK(fp != NULL && fwrite(data, 1, size, fp) == size);
    fclose(fp);
  }

  fd = open(path, O_RDONLY | O_BINARY);
  CHECK(fd >= 0);
  view = (unsigned char *)mmap(NULL, size, PROT_READ, MAP_SHARED, fd, 0);
  CHECK(view != MAP_FAILED);
  if (view != MAP_FAILED) {
    CHECK(memcmp(view, data, size) == 0);
    CHECK(munmap(view, size) == 0);
  }

  view = (unsigned char *)mmap(NULL, 1000, PROT_READ, MAP_PRIVATE, fd, 70000);
  CHECK(view != MAP_FAILED);
  if (view != MAP_FAILED) {
    CHECK(memcmp(view, data + 70000, 1000) == 0);
    CHECK(munmap(view, 1000) == 0);
  }
  close(fd);

  fd = open(path, O_RDWR | O_BINARY);
  view = (unsigned char *)mmap(NULL, size, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);
  CHECK(view != MAP_FAILED);
  if (view != MAP_FAILED) {
    view[10] = 0xAB;
    CHECK(munmap(view, size) == 0);
  }
  close(fd);
  {
    FILE *fp = fopen(path, "rb");
    unsigned char byte = 0;
    fseek(fp, 10, SEEK_SET);
    CHECK(fread(&byte, 1, 1, fp) == 1 && byte == 0xAB);
    fclose(fp);
  }

  view = (unsigned char *)mmap(NULL, 1 << 20, PROT_READ | PROT_WRITE, MAP_ANON | MAP_SHARED, -1, 0);
  CHECK(view != MAP_FAILED);
  if (view != MAP_FAILED) {
    CHECK(view[12345] == 0);
    memset(view, 0x5A, 1 << 20);
    CHECK(view[(1 << 20) - 1] == 0x5A);
    CHECK_ERRNO(munmap(view, 4096), ENOSYS);
    CHECK(munmap(view, 1 << 20) == 0);
  }

  CHECK_ERRNO(munmap(data, size), EINVAL);
  CHECK_ERRNO(mmap(NULL, 0, PROT_READ, MAP_SHARED, 0, 0), EINVAL);
  CHECK_ERRNO(mmap(NULL, 10, PROT_READ, MAP_SHARED | MAP_PRIVATE, 0, 0), EINVAL);
  CHECK_ERRNO(mmap(NULL, 10, PROT_READ, MAP_SHARED, -1, 0), EBADF);
  CHECK_ERRNO(mmap(NULL, 10, PROT_READ | PROT_EXEC, MAP_ANON | MAP_PRIVATE, -1, 0), ENOSYS);
  CHECK_ERRNO(mmap((void *)0x10000, 10, PROT_READ, MAP_ANON | MAP_PRIVATE | MAP_FIXED, -1, 0),
              ENOSYS);

  free(data);
  remove(path);
  return TEST_RESULT();
}
