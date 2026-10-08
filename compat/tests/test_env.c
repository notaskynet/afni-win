#include <spawn.h>
#include <sys/wait.h>
#include <windows.h>

#include "test_common.h"

static char *read_all(const char *path) {
  static char text[4096];
  FILE *fp = fopen(path, "rb");
  size_t n = 0;
  if (fp != NULL) {
    n = fread(text, 1, sizeof(text) - 1, fp);
    fclose(fp);
  }
  text[n] = '\0';
  return text;
}

int main(int argc, char **argv) {
  const char *home = getenv("HOME");
  const char *tmpdir = getenv("TMPDIR");
  char self[MAX_PATH];
  char system_root[MAX_PATH + 16];
  char *child_argv[] = {"test_env", "child", NULL};
  char *child_env[] = {"HOME=C:/preset/home", "TMPDIR=C:/preset/tmp", system_root, NULL};
  pid_t pid;
  int status;

  if (argc == 2 && strcmp(argv[1], "child") == 0) {
    FILE *fp = fopen("compat_env_out.txt", "wb");
    if (fp == NULL) {
      return 1;
    }
    fprintf(fp, "%s|%s", home != NULL ? home : "", tmpdir != NULL ? tmpdir : "");
    fclose(fp);
    return 0;
  }

  CHECK(home != NULL && home[0] != '\0');
  CHECK(tmpdir != NULL && tmpdir[0] != '\0');

  GetModuleFileNameA(NULL, self, sizeof(self));
  snprintf(system_root, sizeof(system_root), "SystemRoot=%s",
           getenv("SystemRoot") != NULL ? getenv("SystemRoot") : "C:\\Windows");
  CHECK(posix_spawn(&pid, self, NULL, NULL, child_argv, child_env) == 0);
  CHECK(waitpid(pid, &status, 0) == pid && WIFEXITED(status) && WEXITSTATUS(status) == 0);
  CHECK(strcmp(read_all("compat_env_out.txt"), "C:/preset/home|C:/preset/tmp") == 0);

  {
    char *unset_env[] = {"USERPROFILE=C:\\Users\\someone", "TMP=C:\\Temp\\afni dir\\",
                         system_root, NULL};
    CHECK(posix_spawn(&pid, self, NULL, NULL, child_argv, unset_env) == 0);
    CHECK(waitpid(pid, &status, 0) == pid && WIFEXITED(status) && WEXITSTATUS(status) == 0);
    CHECK(strcmp(read_all("compat_env_out.txt"), "C:/Users/someone|C:/Temp/afni dir") == 0);
  }
  remove("compat_env_out.txt");
  return TEST_RESULT();
}
