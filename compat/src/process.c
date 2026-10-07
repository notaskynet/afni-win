#include <signal.h>
#include <spawn.h>
#include <stdlib.h>
#include <string.h>
#include <sys/wait.h>

#include "compat_internal.h"
#include "process_internal.h"

#include <tlhelp32.h>

#define MAX_CHILDREN 256

typedef struct {
  pid_t pid;
  HANDLE process;
} child;

static SRWLOCK children_lock = SRWLOCK_INIT;
static child children[MAX_CHILDREN];
static int children_count = 0;
static ULONGLONG children_user = 0;
static ULONGLONG children_kernel = 0;

typedef struct {
  char *data;
  size_t length;
  size_t capacity;
} buffer;

static int buffer_append(buffer *out, const char *text, size_t length) {
  if (out->length + length + 1 > out->capacity) {
    size_t capacity = out->capacity == 0 ? 256 : out->capacity;
    char *data;
    while (out->length + length + 1 > capacity) {
      capacity *= 2;
    }
    data = (char *)realloc(out->data, capacity);
    if (data == NULL) {
      return -1;
    }
    out->data = data;
    out->capacity = capacity;
  }
  memcpy(out->data + out->length, text, length);
  out->length += length;
  out->data[out->length] = '\0';
  return 0;
}

static int append_repeated(buffer *out, char c, size_t count) {
  for (size_t i = 0; i < count; ++i) {
    if (buffer_append(out, &c, 1) != 0) {
      return -1;
    }
  }
  return 0;
}

static int append_quoted_argument(buffer *out, const char *arg) {
  if (arg[0] != '\0' && strpbrk(arg, " \t\n\v\"") == NULL) {
    return buffer_append(out, arg, strlen(arg));
  }
  if (buffer_append(out, "\"", 1) != 0) {
    return -1;
  }
  for (const char *p = arg;; ++p) {
    size_t backslashes = 0;
    while (*p == '\\') {
      ++backslashes;
      ++p;
    }
    if (*p == '\0') {
      if (append_repeated(out, '\\', backslashes * 2) != 0) {
        return -1;
      }
      break;
    }
    if (*p == '"') {
      if (append_repeated(out, '\\', backslashes * 2 + 1) != 0 || buffer_append(out, "\"", 1) != 0) {
        return -1;
      }
    } else if (append_repeated(out, '\\', backslashes) != 0 || buffer_append(out, p, 1) != 0) {
      return -1;
    }
  }
  return buffer_append(out, "\"", 1);
}

char *afni_compat_command_line(char *const argv[]) {
  buffer out = {NULL, 0, 0};
  for (int i = 0; argv[i] != NULL; ++i) {
    if ((i > 0 && buffer_append(&out, " ", 1) != 0) || append_quoted_argument(&out, argv[i]) != 0) {
      free(out.data);
      return NULL;
    }
  }
  if (out.data == NULL && buffer_append(&out, "", 0) != 0) {
    return NULL;
  }
  return out.data;
}

static char *build_environment(char *const envp[]) {
  buffer out = {NULL, 0, 0};
  for (int i = 0; envp[i] != NULL; ++i) {
    if (buffer_append(&out, envp[i], strlen(envp[i]) + 1) != 0) {
      free(out.data);
      return NULL;
    }
  }
  if (buffer_append(&out, "\0", 1) != 0) {
    free(out.data);
    return NULL;
  }
  return out.data;
}

static int is_file(const char *path) {
  DWORD attributes = GetFileAttributesA(path);
  return attributes != INVALID_FILE_ATTRIBUTES && (attributes & FILE_ATTRIBUTE_DIRECTORY) == 0;
}

static int try_candidate(const char *dir, size_t dir_length, const char *file, char *out,
                         size_t out_size) {
  static const char *const suffixes[] = {"", ".exe"};
  for (size_t i = 0; i < sizeof(suffixes) / sizeof(suffixes[0]); ++i) {
    int written;
    if (dir_length > 0) {
      written = snprintf(out, out_size, "%.*s\\%s%s", (int)dir_length, dir, file, suffixes[i]);
    } else {
      written = snprintf(out, out_size, "%s%s", file, suffixes[i]);
    }
    if (written > 0 && (size_t)written < out_size && is_file(out)) {
      return 0;
    }
  }
  return -1;
}

static int resolve_program(const char *file, int search_path, char *out, size_t out_size) {
  const char *path;
  const char *start;

  if (!search_path || strpbrk(file, "/\\:") != NULL) {
    return try_candidate("", 0, file, out, out_size) == 0 ? 0 : ENOENT;
  }
  path = getenv("PATH");
  if (path == NULL) {
    return ENOENT;
  }
  start = path;
  for (;;) {
    const char *end = strchr(start, ';');
    size_t length = end != NULL ? (size_t)(end - start) : strlen(start);
    if (length > 0 && try_candidate(start, length, file, out, out_size) == 0) {
      return 0;
    }
    if (end == NULL) {
      return ENOENT;
    }
    start = end + 1;
  }
}

static int spawn(pid_t *pid, const char *file, int search_path,
                 const posix_spawn_file_actions_t *file_actions, const posix_spawnattr_t *attrp,
                 char *const argv[], char *const envp[]) {
  char program[32768];
  char *command_line;
  char *environment = NULL;
  STARTUPINFOA startup;
  PROCESS_INFORMATION info;
  int error;

  if (file_actions != NULL || attrp != NULL) {
    AFNI_COMPAT_UNSUPPORTED("file actions and spawn attributes");
    return ENOSYS;
  }
  if (file == NULL || argv == NULL) {
    return EINVAL;
  }
  error = resolve_program(file, search_path, program, sizeof(program));
  if (error != 0) {
    return error;
  }
  command_line = afni_compat_command_line(argv);
  if (command_line == NULL) {
    return ENOMEM;
  }
  if (envp != NULL && envp != _environ) {
    environment = build_environment(envp);
    if (environment == NULL) {
      free(command_line);
      return ENOMEM;
    }
  }
  memset(&startup, 0, sizeof(startup));
  startup.cb = sizeof(startup);
  startup.dwFlags = STARTF_USESTDHANDLES;
  startup.hStdInput = GetStdHandle(STD_INPUT_HANDLE);
  startup.hStdOutput = GetStdHandle(STD_OUTPUT_HANDLE);
  startup.hStdError = GetStdHandle(STD_ERROR_HANDLE);
  AcquireSRWLockExclusive(&children_lock);
  if (children_count == MAX_CHILDREN) {
    ReleaseSRWLockExclusive(&children_lock);
    free(command_line);
    free(environment);
    return EAGAIN;
  }
  if (!CreateProcessA(program, command_line, NULL, NULL, TRUE, 0, environment, NULL, &startup,
                      &info)) {
    DWORD win_error = GetLastError();
    ReleaseSRWLockExclusive(&children_lock);
    free(command_line);
    free(environment);
    afni_compat_set_errno_from_win32(win_error);
    return errno;
  }
  CloseHandle(info.hThread);
  children[children_count].pid = (pid_t)info.dwProcessId;
  children[children_count].process = info.hProcess;
  ++children_count;
  ReleaseSRWLockExclusive(&children_lock);
  free(command_line);
  free(environment);
  if (pid != NULL) {
    *pid = (pid_t)info.dwProcessId;
  }
  return 0;
}

int posix_spawn(pid_t *pid, const char *path, const posix_spawn_file_actions_t *file_actions,
                const posix_spawnattr_t *attrp, char *const argv[], char *const envp[]) {
  return spawn(pid, path, 0, file_actions, attrp, argv, envp);
}

int posix_spawnp(pid_t *pid, const char *file, const posix_spawn_file_actions_t *file_actions,
                 const posix_spawnattr_t *attrp, char *const argv[], char *const envp[]) {
  return spawn(pid, file, 1, file_actions, attrp, argv, envp);
}

int afni_compat_wait_status(DWORD code) {
  switch (code) {
    case 0xC0000005u:
    case 0xC00000FDu:
      return SIGSEGV;
    case 0xC000001Du:
    case 0xC0000096u:
      return SIGILL;
    case 0xC000008Du:
    case 0xC000008Eu:
    case 0xC000008Fu:
    case 0xC0000090u:
    case 0xC0000091u:
    case 0xC0000092u:
    case 0xC0000093u:
    case 0xC0000094u:
    case 0xC0000095u:
    case 0xC00002B4u:
    case 0xC00002B5u:
      return SIGFPE;
    case 0xC0000409u:
      return SIGABRT;
    default:
      break;
  }
  if ((code & 0xC0000000u) == 0xC0000000u) {
    return SIGKILL;
  }
  return (int)((code & 0xffu) << 8);
}

static ULONGLONG filetime_value(const FILETIME *ft) {
  ULARGE_INTEGER value;
  value.LowPart = ft->dwLowDateTime;
  value.HighPart = ft->dwHighDateTime;
  return value.QuadPart;
}

static void reap(int index, int *status) {
  DWORD code = 0;
  FILETIME creation;
  FILETIME exit_time;
  FILETIME kernel;
  FILETIME user;

  GetExitCodeProcess(children[index].process, &code);
  if (GetProcessTimes(children[index].process, &creation, &exit_time, &kernel, &user)) {
    children_user += filetime_value(&user);
    children_kernel += filetime_value(&kernel);
  }
  CloseHandle(children[index].process);
  children[index] = children[children_count - 1];
  --children_count;
  if (status != NULL) {
    *status = afni_compat_wait_status(code);
  }
}

void afni_compat_children_times(clock_t *user, clock_t *system_time) {
  AcquireSRWLockShared(&children_lock);
  *user = (clock_t)(children_user / (10000000ULL / CLOCKS_PER_SEC));
  *system_time = (clock_t)(children_kernel / (10000000ULL / CLOCKS_PER_SEC));
  ReleaseSRWLockShared(&children_lock);
}

pid_t waitpid(pid_t pid, int *status, int options) {
  HANDLE handles[MAXIMUM_WAIT_OBJECTS];
  pid_t pids[MAXIMUM_WAIT_OBJECTS];
  DWORD timeout = (options & WNOHANG) ? 0 : INFINITE;
  DWORD count = 0;
  DWORD result;

  if ((options & ~WNOHANG) != 0) {
    AFNI_COMPAT_UNSUPPORTED("options other than WNOHANG");
    return -1;
  }
  if (pid == 0 || pid < -1) {
    AFNI_COMPAT_UNSUPPORTED("process groups");
    return -1;
  }
  AcquireSRWLockShared(&children_lock);
  for (int i = 0; i < children_count; ++i) {
    if (pid == -1 || children[i].pid == pid) {
      if (count == MAXIMUM_WAIT_OBJECTS) {
        ReleaseSRWLockShared(&children_lock);
        AFNI_COMPAT_UNSUPPORTED("waiting for more than 64 children at once");
        return -1;
      }
      handles[count] = children[i].process;
      pids[count] = children[i].pid;
      ++count;
    }
  }
  ReleaseSRWLockShared(&children_lock);
  if (count == 0) {
    errno = ECHILD;
    return -1;
  }
  result = WaitForMultipleObjects(count, handles, FALSE, timeout);
  if (result == WAIT_TIMEOUT) {
    return 0;
  }
  if (result >= WAIT_OBJECT_0 + count) {
    afni_compat_set_errno_from_win32(GetLastError());
    return -1;
  }
  AcquireSRWLockExclusive(&children_lock);
  for (int i = 0; i < children_count; ++i) {
    if (children[i].pid == pids[result - WAIT_OBJECT_0]) {
      reap(i, status);
      break;
    }
  }
  ReleaseSRWLockExclusive(&children_lock);
  return pids[result - WAIT_OBJECT_0];
}

pid_t wait(int *status) {
  return waitpid(-1, status, 0);
}

pid_t getppid(void) {
  PROCESSENTRY32 entry;
  DWORD self = GetCurrentProcessId();
  HANDLE snapshot = CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0);

  if (snapshot == INVALID_HANDLE_VALUE) {
    afni_compat_set_errno_from_win32(GetLastError());
    return -1;
  }
  entry.dwSize = sizeof(entry);
  if (Process32First(snapshot, &entry)) {
    do {
      if (entry.th32ProcessID == self) {
        CloseHandle(snapshot);
        return (pid_t)entry.th32ParentProcessID;
      }
    } while (Process32Next(snapshot, &entry));
  }
  CloseHandle(snapshot);
  errno = ESRCH;
  return -1;
}
