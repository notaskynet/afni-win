#include <dlfcn.h>
#include <stdio.h>
#include <string.h>

#include "compat_internal.h"

/* One error for the whole process (not per thread): _Thread_local would make
   the DLL depend on libgcc_s_seh-1.dll (emulated TLS). */
static SRWLOCK error_lock = SRWLOCK_INIT;
static char error_text[512];
static char error_copy[512];
static int error_set = 0;

static void set_error(const char *what, const char *name) {
  DWORD error = GetLastError();
  char message[256] = "";
  size_t length;

  FormatMessageA(FORMAT_MESSAGE_FROM_SYSTEM | FORMAT_MESSAGE_IGNORE_INSERTS, NULL, error, 0,
                 message, sizeof(message), NULL);
  length = strlen(message);
  while (length > 0 && (message[length - 1] == '\n' || message[length - 1] == '\r' ||
                        message[length - 1] == ' ' || message[length - 1] == '.')) {
    message[--length] = '\0';
  }
  AcquireSRWLockExclusive(&error_lock);
  snprintf(error_text, sizeof(error_text), "%s %s: %s (error %lu)", what, name, message,
           (unsigned long)error);
  error_set = 1;
  ReleaseSRWLockExclusive(&error_lock);
}

void *dlopen(const char *filename, int flags) {
  char path[MAX_PATH];
  HMODULE module;
  DWORD load_flags = 0;

  (void)flags;
  if (filename == NULL) {
    return (void *)GetModuleHandleA(NULL);
  }
  if (snprintf(path, sizeof(path), "%s", filename) >= (int)sizeof(path)) {
    SetLastError(ERROR_FILENAME_EXCED_RANGE);
    set_error("dlopen", filename);
    return NULL;
  }
  for (char *p = path; *p != '\0'; ++p) {
    if (*p == '/') {
      *p = '\\';
    }
  }
  if (strchr(path, '\\') != NULL) {
    load_flags = LOAD_WITH_ALTERED_SEARCH_PATH;
  }
  module = LoadLibraryExA(path, NULL, load_flags);
  if (module == NULL) {
    set_error("dlopen", filename);
  }
  return (void *)module;
}

void *dlsym(void *handle, const char *symbol) {
  FARPROC address;
  if (handle == NULL || symbol == NULL) {
    SetLastError(ERROR_INVALID_HANDLE);
    set_error("dlsym", symbol != NULL ? symbol : "(null)");
    return NULL;
  }
  address = GetProcAddress((HMODULE)handle, symbol);
  if (address == NULL) {
    set_error("dlsym", symbol);
  }
  return (void *)address;
}

int dlclose(void *handle) {
  if (handle == (void *)GetModuleHandleA(NULL)) {
    return 0;
  }
  if (handle == NULL || !FreeLibrary((HMODULE)handle)) {
    set_error("dlclose", "handle");
    return -1;
  }
  return 0;
}

char *dlerror(void) {
  char *result = NULL;
  AcquireSRWLockExclusive(&error_lock);
  if (error_set) {
    memcpy(error_copy, error_text, sizeof(error_copy));
    error_set = 0;
    result = error_copy;
  }
  ReleaseSRWLockExclusive(&error_lock);
  return result;
}
