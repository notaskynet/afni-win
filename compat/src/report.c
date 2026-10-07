#include <stdio.h>

#include "compat_internal.h"

void afni_compat_report(const char *function, const char *detail) {
  if (detail != NULL && detail[0] != '\0') {
    fprintf(stderr, "** afni-win: %s() is not supported on Windows: %s\n", function, detail);
  } else {
    fprintf(stderr, "** afni-win: %s() is not supported on Windows\n", function);
  }
  fflush(stderr);
}

void afni_compat_set_errno_from_win32(DWORD error) {
  switch (error) {
    case ERROR_FILE_NOT_FOUND:
    case ERROR_PATH_NOT_FOUND:
    case ERROR_INVALID_DRIVE:
    case ERROR_BAD_NETPATH:
    case ERROR_BAD_PATHNAME:
      errno = ENOENT;
      break;
    case ERROR_ACCESS_DENIED:
    case ERROR_SHARING_VIOLATION:
    case ERROR_LOCK_VIOLATION:
      errno = EACCES;
      break;
    case ERROR_NOT_ENOUGH_MEMORY:
    case ERROR_OUTOFMEMORY:
    case ERROR_COMMITMENT_LIMIT:
      errno = ENOMEM;
      break;
    case ERROR_INVALID_HANDLE:
      errno = EBADF;
      break;
    case ERROR_INVALID_PARAMETER:
      errno = EINVAL;
      break;
    case ERROR_FILENAME_EXCED_RANGE:
    case ERROR_INSUFFICIENT_BUFFER:
      errno = ENAMETOOLONG;
      break;
    case ERROR_NOT_A_REPARSE_POINT:
      errno = EINVAL;
      break;
    case ERROR_DISK_FULL:
    case ERROR_HANDLE_DISK_FULL:
      errno = ENOSPC;
      break;
    default:
      errno = EIO;
      break;
  }
}
