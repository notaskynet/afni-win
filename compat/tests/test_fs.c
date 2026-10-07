#include <fcntl.h>
#include <limits.h>
#include <sys/stat.h>
#include <unistd.h>

#include "test_common.h"

static void write_file(const char *path, const char *text) {
  FILE *fp = fopen(path, "wb");
  CHECK(fp != NULL);
  if (fp != NULL) {
    fputs(text, fp);
    fclose(fp);
  }
}

int main(void) {
  char resolved[PATH_MAX];
  char buf[64];
  struct stat st;
  char *dynamic;
  int fd1;
  int fd2;

  write_file("compat_fs_file.txt", "abc");

  CHECK(realpath("compat_fs_file.txt", resolved) == resolved);
  CHECK(strchr(resolved, '\\') == NULL);
  CHECK(strstr(resolved, "compat_fs_file.txt") != NULL);
  dynamic = realpath(".", NULL);
  CHECK(dynamic != NULL);
  free(dynamic);
  CHECK_ERRNO(realpath("no_such_file_here.txt", resolved), ENOENT);
  CHECK_ERRNO(realpath("", resolved), ENOENT);

  CHECK_ERRNO(readlink("compat_fs_file.txt", buf, sizeof(buf)), EINVAL);
  CHECK_ERRNO(readlink("no_such_file_here.txt", buf, sizeof(buf)), ENOENT);

  CHECK(lstat("compat_fs_file.txt", &st) == 0);
  CHECK(S_ISREG(st.st_mode));
  CHECK(!S_ISLNK(st.st_mode));
  CHECK(st.st_size == 3);
  CHECK_ERRNO(lstat("no_such_file_here.txt", &st), ENOENT);

  _rmdir("compat_fs_dir");
  CHECK(mkdir("compat_fs_dir", 0755) == 0);
  CHECK(stat("compat_fs_dir", &st) == 0 && S_ISDIR(st.st_mode));
  CHECK_ERRNO(mkdir("compat_fs_dir", 0755), EEXIST);
  CHECK(_rmdir("compat_fs_dir") == 0);

  fd1 = open("compat_fs_file.txt", O_RDWR);
  fd2 = open("compat_fs_file.txt", O_RDWR);
  CHECK(fd1 >= 0 && fd2 >= 0);
  CHECK(fsync(fd1) == 0);
  CHECK(flock(fd1, LOCK_EX | LOCK_NB) == 0);
  CHECK_ERRNO(flock(fd2, LOCK_EX | LOCK_NB), EWOULDBLOCK);
  CHECK_ERRNO(flock(fd2, LOCK_SH | LOCK_NB), EWOULDBLOCK);
  CHECK(flock(fd1, LOCK_UN) == 0);
  CHECK(flock(fd2, LOCK_SH | LOCK_NB) == 0);
  CHECK(flock(fd1, LOCK_SH | LOCK_NB) == 0);
  CHECK(flock(fd1, LOCK_UN) == 0);
  CHECK(flock(fd2, LOCK_UN) == 0);
  CHECK_ERRNO(flock(fd1, 0), EINVAL);
  CHECK_ERRNO(flock(-1, LOCK_EX), EBADF);
  CHECK_ERRNO(fcntl(fd1, F_GETFL), ENOSYS);
  close(fd1);
  close(fd2);

  {
    FILE *fp = fopen("compat_fs_file.txt", "rb");
    CHECK(fp != NULL);
    if (fp != NULL) {
      CHECK(fseek(fp, 2, SEEK_SET) == 0);
      CHECK(ftell(fp) == 2);
      CHECK(sizeof(ftell(fp)) == 8);
      fclose(fp);
    }
  }
  CHECK(sizeof(st.st_size) == 8);
  CHECK(sizeof(off_t) == 8);

  remove("compat_fs_file.txt");
  return TEST_RESULT();
}
