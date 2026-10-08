#include <stdio.h>
#include <stdlib.h>
#include <sys/wait.h>
#include <windows.h>

#include "test_common.h"

static char helper[MAX_PATH];

static void use_shell(const char *path) {
  char setting[MAX_PATH + 32];
  snprintf(setting, sizeof(setting), "AFNI_COMPAT_SHELL=%s", path);
  _putenv(setting);
}

int main(void) {
  unsigned char bytes[256];
  char line[64];
  FILE *fp;
  pid_t pid;
  int status;
  char *slash;

  GetModuleFileNameA(NULL, helper, sizeof(helper));
  slash = strrchr(helper, '\\');
  strcpy(slash + 1, "compat_test_sh.exe");
  for (int i = 0; i < 256; ++i) {
    bytes[i] = (unsigned char)i;
  }

  use_shell("C:\\no\\such\\sh.exe");
  CHECK(system(NULL) == 0);
  CHECK_ERRNO(system("echo hi"), ENOENT);
  CHECK(popen("echo hi", "r") == NULL);
  CHECK_ERRNO(popen("echo hi", "r"), ENOENT);

  use_shell(helper);
  CHECK(system(NULL) != 0);
  CHECK_ERRNO(popen("echo hi", "x"), EINVAL);
  CHECK_ERRNO(pclose(stdin), ECHILD);

  fp = popen("echo hello world", "r");
  CHECK(fp != NULL);
  if (fp != NULL) {
    CHECK(fgets(line, sizeof(line), fp) != NULL && strcmp(line, "hello world\n") == 0);
    CHECK(fgets(line, sizeof(line), fp) == NULL);
    status = pclose(fp);
    CHECK(WIFEXITED(status) && WEXITSTATUS(status) == 0);
  }

  fp = popen("exit 3", "r");
  CHECK(fp != NULL);
  if (fp != NULL) {
    status = pclose(fp);
    CHECK(WIFEXITED(status) && WEXITSTATUS(status) == 3);
  }

  fp = popen("save compat_shell_out.bin", "w");
  CHECK(fp != NULL);
  if (fp != NULL) {
    CHECK(fwrite(bytes, 1, sizeof(bytes), fp) == sizeof(bytes));
    CHECK(pclose(fp) == 0);
  }
  fp = popen("dump compat_shell_out.bin", "r");
  CHECK(fp != NULL);
  if (fp != NULL) {
    unsigned char back[512];
    CHECK(fread(back, 1, sizeof(back), fp) == sizeof(bytes));
    CHECK(memcmp(back, bytes, sizeof(bytes)) == 0);
    CHECK(pclose(fp) == 0);
  }

  {
    FILE *first = popen("dump compat_shell_out.bin", "r");
    FILE *second = popen("echo second", "r");
    CHECK(first != NULL && second != NULL);
    if (second != NULL) {
      CHECK(fgets(line, sizeof(line), second) != NULL && strcmp(line, "second\n") == 0);
      CHECK(pclose(second) == 0);
    }
    if (first != NULL) {
      CHECK(pclose(first) == 0);
    }
  }

  status = system("exit 5");
  CHECK(WIFEXITED(status) && WEXITSTATUS(status) == 5);
  CHECK(system("stderr message from the test shell") == 0);
  status = system("no such command");
  CHECK(WIFEXITED(status) && WEXITSTATUS(status) == 127);

  {
    pid_t first = 0;
    pid_t second = 0;
    int codes = 0;
    CHECK(afni_compat_spawn_shell(&first, "exit 6") == 0);
    CHECK(afni_compat_spawn_shell(&second, "exit 7") == 0);
    CHECK(first > 0 && second > 0 && first != second);
    while ((pid = wait(&status)) > 0) {
      CHECK(WIFEXITED(status));
      codes += WEXITSTATUS(status);
    }
    CHECK(codes == 13);
    CHECK(afni_compat_spawn_shell(NULL, NULL) == EINVAL);
  }

  remove("compat_shell_out.bin");
  return TEST_RESULT();
}
