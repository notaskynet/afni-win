#include <spawn.h>
#include <sys/times.h>
#include <sys/wait.h>
#include <unistd.h>
#include <windows.h>

#include "test_common.h"

static char child_path[MAX_PATH];

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

int main(void) {
  char *argv[] = {"compat_test_child", "compat_process_out.txt", "7", "plain",
                  "with space", "with \"quote\"", "trailing\\", "back\\\\slash \"q\"", "",
                  NULL};
  char *crash_argv[] = {"compat_test_child", "compat_process_out.txt", "-1", NULL};
  char *env_argv[] = {"compat_test_child", "compat_process_out.txt", "0", NULL};
  char *envp[] = {"AFNI_COMPAT_TEST_VAR=hello", NULL};
  pid_t pid = 0;
  int status = -1;
  struct tms t;
  char *slash;

  GetModuleFileNameA(NULL, child_path, sizeof(child_path));
  slash = strrchr(child_path, '\\');
  strcpy(slash + 1, "compat_test_child.exe");

  CHECK(posix_spawn(&pid, child_path, NULL, NULL, argv, _environ) == 0);
  CHECK(pid > 0);
  CHECK(waitpid(pid, &status, 0) == pid);
  CHECK(WIFEXITED(status));
  CHECK(WEXITSTATUS(status) == 7);
  CHECK(strcmp(read_all("compat_process_out.txt"),
               "plain\nwith space\nwith \"quote\"\ntrailing\\\nback\\\\slash \"q\"\n\nENV=\n") == 0);
  CHECK_ERRNO(waitpid(pid, &status, 0), ECHILD);

  {
    char dir[MAX_PATH];
    char path_env[MAX_PATH + 16];
    strcpy(dir, child_path);
    *strrchr(dir, '\\') = '\0';
    snprintf(path_env, sizeof(path_env), "PATH=%s", dir);
    _putenv(path_env);
    CHECK(posix_spawnp(&pid, "compat_test_child", NULL, NULL, env_argv, envp) == 0);
    CHECK(wait(&status) == pid);
    CHECK(WIFEXITED(status) && WEXITSTATUS(status) == 0);
    CHECK(strcmp(read_all("compat_process_out.txt"), "ENV=hello\n") == 0);
  }

  {
    char *ppid_argv[] = {"compat_test_child", "compat_process_out.txt", "3", NULL};
    char expected[64];
    CHECK(posix_spawn(&pid, child_path, NULL, NULL, ppid_argv, _environ) == 0);
    CHECK(waitpid(pid, &status, 0) == pid);
    CHECK(WIFEXITED(status) && WEXITSTATUS(status) == 3);
    snprintf(expected, sizeof(expected), "PPID=%d\nENV=\n", (int)getpid());
    CHECK(strcmp(read_all("compat_process_out.txt"), expected) == 0);
  }

  CHECK(posix_spawn(&pid, child_path, NULL, NULL, crash_argv, _environ) == 0);
  CHECK(waitpid(-1, &status, 0) == pid);
  CHECK(WIFSIGNALED(status));
  CHECK(WTERMSIG(status) == SIGSEGV);

  CHECK(posix_spawnp(&pid, "no_such_program_xyz", NULL, NULL, argv, _environ) == ENOENT);
  CHECK(posix_spawn(&pid, "C:\\no\\such\\program.exe", NULL, NULL, argv, _environ) == ENOENT);
  {
    posix_spawn_file_actions_t actions = NULL;
    CHECK(posix_spawn(&pid, child_path, &actions, NULL, argv, _environ) == ENOSYS);
  }

  CHECK_ERRNO(waitpid(-1, &status, WNOHANG), ECHILD);
  CHECK_ERRNO(waitpid(0, &status, 0), ENOSYS);
  CHECK_ERRNO(waitpid(-1, &status, WUNTRACED), ENOSYS);

  {
    char *sleep_argv[] = {"compat_test_child", "compat_process_sleep.txt", "-2", NULL};
    pid_t sleeper;
    CHECK(posix_spawn(&sleeper, child_path, NULL, NULL, sleep_argv, _environ) == 0);
    CHECK(kill(sleeper, 0) == 0);
    CHECK(waitpid(sleeper, &status, WNOHANG) == 0);
    CHECK_ERRNO(kill(sleeper, SIGINT), ENOSYS);
    CHECK(kill(sleeper, SIGTERM) == 0);
    CHECK(waitpid(sleeper, &status, 0) == sleeper);
    CHECK(WIFSIGNALED(status) && WTERMSIG(status) == SIGTERM);
    CHECK(posix_spawn(&sleeper, child_path, NULL, NULL, sleep_argv, _environ) == 0);
    CHECK(kill(sleeper, SIGKILL) == 0);
    CHECK(wait(&status) == sleeper);
    CHECK(WIFSIGNALED(status) && WTERMSIG(status) == SIGKILL);
    CHECK_ERRNO(kill(-5, SIGTERM), ENOSYS);
    remove("compat_process_sleep.txt");
  }

  {
    enum { MANY = 70 };
    char *many_argv[] = {"compat_test_child", "compat_process_many.txt", "4", NULL};
    int started = 0;
    int reaped = 0;
    for (int i = 0; i < MANY; ++i) {
      started += posix_spawn(&pid, child_path, NULL, NULL, many_argv, _environ) == 0;
    }
    CHECK(started == MANY);
    while (wait(&status) > 0) {
      reaped += WIFEXITED(status) && WEXITSTATUS(status) == 4;
    }
    CHECK(errno == ECHILD);
    CHECK(reaped == MANY);
    remove("compat_process_many.txt");
  }

  CHECK(times(&t) != (clock_t)-1);
  CHECK(t.tms_cutime >= 0);

  remove("compat_process_out.txt");
  return TEST_RESULT();
}
