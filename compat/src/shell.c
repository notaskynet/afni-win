#include <fcntl.h>
#include <io.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "compat_internal.h"
#include "process_internal.h"

#define SHELL_ENV "AFNI_COMPAT_SHELL"
#define BUSYBOX_NAME "busybox.exe"
#define MAX_STREAMS 64

typedef struct {
  FILE *stream;
  HANDLE process;
} pipe_stream;

static SRWLOCK streams_lock = SRWLOCK_INIT;
static pipe_stream streams[MAX_STREAMS];
static int streams_count = 0;

static int module_directory(char *out, size_t out_size) {
  HMODULE module = NULL;
  DWORD length;
  char *slash;

  if (!GetModuleHandleExA(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS |
                              GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
                          (LPCSTR)(void *)&module_directory, &module)) {
    return -1;
  }
  length = GetModuleFileNameA(module, out, (DWORD)out_size);
  if (length == 0 || length >= out_size) {
    return -1;
  }
  slash = strrchr(out, '\\');
  if (slash == NULL) {
    return -1;
  }
  *slash = '\0';
  return 0;
}

static int find_shell(char *path, size_t path_size, int *busybox) {
  const char *configured = getenv(SHELL_ENV);
  char dir[MAX_PATH];
  DWORD attributes;

  if (configured != NULL && configured[0] != '\0') {
    if ((size_t)snprintf(path, path_size, "%s", configured) >= path_size) {
      return -1;
    }
    *busybox = 0;
  } else {
    if (module_directory(dir, sizeof(dir)) != 0 ||
        (size_t)snprintf(path, path_size, "%s\\%s", dir, BUSYBOX_NAME) >= path_size) {
      return -1;
    }
    *busybox = 1;
  }
  attributes = GetFileAttributesA(path);
  if (attributes == INVALID_FILE_ATTRIBUTES || (attributes & FILE_ATTRIBUTE_DIRECTORY) != 0) {
    return -1;
  }
  return 0;
}

static void report_no_shell(const char *function) {
  static volatile LONG reported = 0;
  if (InterlockedExchange(&reported, 1) == 0) {
    fprintf(stderr,
            "** afni-win: %s(): no POSIX shell found (expected " BUSYBOX_NAME
            " next to afni_compat.dll, or the path of a sh in " SHELL_ENV ")\n",
            function);
    fflush(stderr);
  }
  errno = ENOENT;
}

static HANDLE inheritable_copy(HANDLE handle) {
  HANDLE copy = NULL;
  if (handle == NULL || handle == INVALID_HANDLE_VALUE) {
    return NULL;
  }
  if (!DuplicateHandle(GetCurrentProcess(), handle, GetCurrentProcess(), &copy, 0, TRUE,
                       DUPLICATE_SAME_ACCESS)) {
    return NULL;
  }
  return copy;
}

static HANDLE std_handle(int fd, DWORD which) {
  intptr_t handle = _get_osfhandle(fd);
  if (handle != -1 && handle != -2) {
    return (HANDLE)handle;
  }
  return GetStdHandle(which);
}

/* Starts "<shell> -c command" (or "busybox sh -c command") with the given
   standard handles; only these handles are inherited by the child. */
static int start_shell(const char *function, const char *command, HANDLE in, HANDLE out,
                       HANDLE err, HANDLE *process, DWORD *pid) {
  char shell[MAX_PATH];
  char *argv[5];
  char *command_line;
  HANDLE inherited[3];
  HANDLE unique[3];
  DWORD unique_count = 0;
  SIZE_T attributes_size = 0;
  LPPROC_THREAD_ATTRIBUTE_LIST attributes = NULL;
  STARTUPINFOEXA startup;
  PROCESS_INFORMATION info;
  int busybox = 0;
  int argc = 0;
  int result = -1;

  if (find_shell(shell, sizeof(shell), &busybox) != 0) {
    report_no_shell(function);
    return -1;
  }
  argv[argc++] = busybox ? "busybox" : shell;
  if (busybox) {
    argv[argc++] = "sh";
  }
  argv[argc++] = "-c";
  argv[argc++] = (char *)command;
  argv[argc] = NULL;
  command_line = afni_compat_command_line(argv);
  if (command_line == NULL) {
    errno = ENOMEM;
    return -1;
  }

  inherited[0] = inheritable_copy(in);
  inherited[1] = inheritable_copy(out);
  inherited[2] = inheritable_copy(err);
  for (int i = 0; i < 3; ++i) {
    if (inherited[i] != NULL) {
      unique[unique_count++] = inherited[i];
    }
  }

  memset(&startup, 0, sizeof(startup));
  startup.StartupInfo.cb = sizeof(startup);
  startup.StartupInfo.dwFlags = STARTF_USESTDHANDLES;
  startup.StartupInfo.hStdInput = inherited[0];
  startup.StartupInfo.hStdOutput = inherited[1];
  startup.StartupInfo.hStdError = inherited[2];

  InitializeProcThreadAttributeList(NULL, 1, 0, &attributes_size);
  attributes = (LPPROC_THREAD_ATTRIBUTE_LIST)malloc(attributes_size);
  if (attributes == NULL || !InitializeProcThreadAttributeList(attributes, 1, 0, &attributes_size)) {
    errno = ENOMEM;
    free(attributes);
    attributes = NULL;
    goto done;
  }
  if (unique_count > 0 &&
      !UpdateProcThreadAttribute(attributes, 0, PROC_THREAD_ATTRIBUTE_HANDLE_LIST, unique,
                                 unique_count * sizeof(HANDLE), NULL, NULL)) {
    afni_compat_set_errno_from_win32(GetLastError());
    goto done;
  }
  startup.lpAttributeList = attributes;
  if (!CreateProcessA(shell, command_line, NULL, NULL, unique_count > 0,
                      EXTENDED_STARTUPINFO_PRESENT, NULL, NULL, &startup.StartupInfo, &info)) {
    afni_compat_set_errno_from_win32(GetLastError());
    goto done;
  }
  CloseHandle(info.hThread);
  *process = info.hProcess;
  if (pid != NULL) {
    *pid = info.dwProcessId;
  }
  result = 0;

done:
  if (attributes != NULL) {
    DeleteProcThreadAttributeList(attributes);
    free(attributes);
  }
  for (DWORD i = 0; i < unique_count; ++i) {
    CloseHandle(unique[i]);
  }
  free(command_line);
  return result;
}

static int wait_process(HANDLE process) {
  DWORD code = 0;
  WaitForSingleObject(process, INFINITE);
  if (!GetExitCodeProcess(process, &code)) {
    afni_compat_set_errno_from_win32(GetLastError());
    CloseHandle(process);
    return -1;
  }
  CloseHandle(process);
  return afni_compat_wait_status(code);
}

FILE *afni_compat_popen(const char *command, const char *mode) {
  HANDLE read_end;
  HANDLE write_end;
  HANDLE process;
  HANDLE parent_end;
  int reading;
  int fd;
  FILE *stream;

  if (command == NULL || mode == NULL || (mode[0] != 'r' && mode[0] != 'w')) {
    errno = EINVAL;
    return NULL;
  }
  reading = mode[0] == 'r';
  if (!CreatePipe(&read_end, &write_end, NULL, 0)) {
    afni_compat_set_errno_from_win32(GetLastError());
    return NULL;
  }
  if (start_shell("popen", command, reading ? std_handle(0, STD_INPUT_HANDLE) : read_end,
                  reading ? write_end : std_handle(1, STD_OUTPUT_HANDLE),
                  std_handle(2, STD_ERROR_HANDLE), &process, NULL) != 0) {
    int saved = errno;
    CloseHandle(read_end);
    CloseHandle(write_end);
    errno = saved;
    return NULL;
  }
  CloseHandle(reading ? write_end : read_end);
  parent_end = reading ? read_end : write_end;
  fd = _open_osfhandle((intptr_t)parent_end, (reading ? _O_RDONLY : _O_WRONLY) | _O_BINARY);
  if (fd == -1) {
    CloseHandle(parent_end);
    wait_process(process);
    errno = EMFILE;
    return NULL;
  }
  stream = _fdopen(fd, reading ? "rb" : "wb");
  if (stream == NULL) {
    int saved = errno;
    _close(fd);
    wait_process(process);
    errno = saved;
    return NULL;
  }
  AcquireSRWLockExclusive(&streams_lock);
  if (streams_count == MAX_STREAMS) {
    ReleaseSRWLockExclusive(&streams_lock);
    fclose(stream);
    wait_process(process);
    errno = EMFILE;
    return NULL;
  }
  streams[streams_count].stream = stream;
  streams[streams_count].process = process;
  ++streams_count;
  ReleaseSRWLockExclusive(&streams_lock);
  return stream;
}

int afni_compat_pclose(FILE *stream) {
  HANDLE process = NULL;

  AcquireSRWLockExclusive(&streams_lock);
  for (int i = 0; i < streams_count; ++i) {
    if (streams[i].stream == stream) {
      process = streams[i].process;
      streams[i] = streams[streams_count - 1];
      --streams_count;
      break;
    }
  }
  ReleaseSRWLockExclusive(&streams_lock);
  if (process == NULL) {
    errno = ECHILD;
    return -1;
  }
  fclose(stream);
  return wait_process(process);
}

int afni_compat_system(const char *command) {
  HANDLE process;

  if (command == NULL) {
    char shell[MAX_PATH];
    int busybox;
    return find_shell(shell, sizeof(shell), &busybox) == 0;
  }
  if (start_shell("system", command, std_handle(0, STD_INPUT_HANDLE),
                  std_handle(1, STD_OUTPUT_HANDLE), std_handle(2, STD_ERROR_HANDLE),
                  &process, NULL) != 0) {
    return -1;
  }
  return wait_process(process);
}

int afni_compat_spawn_shell(pid_t *pid, const char *command) {
  HANDLE process;
  DWORD id;
  int error;

  if (command == NULL) {
    return EINVAL;
  }
  if (start_shell("afni_compat_spawn_shell", command, std_handle(0, STD_INPUT_HANDLE),
                  std_handle(1, STD_OUTPUT_HANDLE), std_handle(2, STD_ERROR_HANDLE), &process,
                  &id) != 0) {
    return errno;
  }
  error = afni_compat_add_child((pid_t)id, process);
  if (error != 0) {
    TerminateProcess(process, 1);
    CloseHandle(process);
    return error;
  }
  if (pid != NULL) {
    *pid = (pid_t)id;
  }
  return 0;
}
