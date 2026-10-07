#include <limits.h>
#include <stdarg.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

#include "compat_internal.h"

#include <winioctl.h>

#ifndef SYMLINK_FLAG_RELATIVE
#define SYMLINK_FLAG_RELATIVE 1
#endif

typedef struct {
  ULONG ReparseTag;
  USHORT ReparseDataLength;
  USHORT Reserved;
  union {
    struct {
      USHORT SubstituteNameOffset;
      USHORT SubstituteNameLength;
      USHORT PrintNameOffset;
      USHORT PrintNameLength;
      ULONG Flags;
      WCHAR PathBuffer[1];
    } SymbolicLink;
    struct {
      USHORT SubstituteNameOffset;
      USHORT SubstituteNameLength;
      USHORT PrintNameOffset;
      USHORT PrintNameLength;
      WCHAR PathBuffer[1];
    } MountPoint;
  } u;
} compat_reparse_buffer;

static const DWORD share_all = FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE;

static int link_target(const char *path, char *out, size_t out_size, size_t *out_length) {
  union {
    compat_reparse_buffer header;
    BYTE bytes[MAXIMUM_REPARSE_DATA_BUFFER_SIZE];
  } data;
  DWORD returned = 0;
  const WCHAR *name;
  USHORT offset;
  USHORT length;
  HANDLE handle;
  int converted;

  handle = CreateFileA(path, FILE_READ_ATTRIBUTES, share_all, NULL, OPEN_EXISTING,
                       FILE_FLAG_OPEN_REPARSE_POINT | FILE_FLAG_BACKUP_SEMANTICS, NULL);
  if (handle == INVALID_HANDLE_VALUE) {
    afni_compat_set_errno_from_win32(GetLastError());
    return -1;
  }
  if (!DeviceIoControl(handle, FSCTL_GET_REPARSE_POINT, NULL, 0, &data, sizeof(data), &returned,
                       NULL)) {
    DWORD error = GetLastError();
    CloseHandle(handle);
    afni_compat_set_errno_from_win32(error);
    return -1;
  }
  CloseHandle(handle);
  if (data.header.ReparseTag == IO_REPARSE_TAG_SYMLINK) {
    offset = data.header.u.SymbolicLink.PrintNameOffset;
    length = data.header.u.SymbolicLink.PrintNameLength;
    if (length == 0) {
      offset = data.header.u.SymbolicLink.SubstituteNameOffset;
      length = data.header.u.SymbolicLink.SubstituteNameLength;
    }
    name = data.header.u.SymbolicLink.PathBuffer + offset / sizeof(WCHAR);
  } else if (data.header.ReparseTag == IO_REPARSE_TAG_MOUNT_POINT) {
    offset = data.header.u.MountPoint.PrintNameOffset;
    length = data.header.u.MountPoint.PrintNameLength;
    if (length == 0) {
      offset = data.header.u.MountPoint.SubstituteNameOffset;
      length = data.header.u.MountPoint.SubstituteNameLength;
    }
    name = data.header.u.MountPoint.PathBuffer + offset / sizeof(WCHAR);
  } else {
    errno = EINVAL;
    return -1;
  }
  if (length >= 8 && wcsncmp(name, L"\\??\\", 4) == 0) {
    name += 4;
    length = (USHORT)(length - 8);
  }
  converted = WideCharToMultiByte(CP_ACP, 0, name, length / (int)sizeof(WCHAR), out,
                                  (int)out_size, NULL, NULL);
  if (converted <= 0 && length > 0) {
    afni_compat_set_errno_from_win32(GetLastError());
    return -1;
  }
  *out_length = (size_t)converted;
  return 0;
}

ssize_t readlink(const char *path, char *buf, size_t bufsiz) {
  char target[MAXIMUM_REPARSE_DATA_BUFFER_SIZE];
  size_t length = 0;

  if (path == NULL || buf == NULL) {
    errno = EFAULT;
    return -1;
  }
  if (link_target(path, target, sizeof(target), &length) != 0) {
    return -1;
  }
  if (length > bufsiz) {
    length = bufsiz;
  }
  memcpy(buf, target, length);
  return (ssize_t)length;
}

char *realpath(const char *path, char *resolved_path) {
  char buffer[32768];
  char *start = buffer;
  DWORD length;
  HANDLE handle;

  if (path == NULL) {
    errno = EINVAL;
    return NULL;
  }
  if (path[0] == '\0') {
    errno = ENOENT;
    return NULL;
  }
  handle = CreateFileA(path, 0, share_all, NULL, OPEN_EXISTING, FILE_FLAG_BACKUP_SEMANTICS, NULL);
  if (handle == INVALID_HANDLE_VALUE) {
    afni_compat_set_errno_from_win32(GetLastError());
    return NULL;
  }
  length = GetFinalPathNameByHandleA(handle, buffer, (DWORD)sizeof(buffer),
                                     FILE_NAME_NORMALIZED | VOLUME_NAME_DOS);
  CloseHandle(handle);
  if (length == 0 || length >= sizeof(buffer)) {
    afni_compat_set_errno_from_win32(length == 0 ? GetLastError() : ERROR_INSUFFICIENT_BUFFER);
    return NULL;
  }
  if (strncmp(start, "\\\\?\\UNC\\", 8) == 0) {
    start += 6;
    start[0] = '\\';
  } else if (strncmp(start, "\\\\?\\", 4) == 0) {
    start += 4;
  }
  for (char *p = start; *p != '\0'; ++p) {
    if (*p == '\\') {
      *p = '/';
    }
  }
  if (resolved_path == NULL) {
    char *copy = _strdup(start);
    if (copy == NULL) {
      errno = ENOMEM;
    }
    return copy;
  }
  if (strlen(start) >= PATH_MAX) {
    errno = ENAMETOOLONG;
    return NULL;
  }
  strcpy(resolved_path, start);
  return resolved_path;
}

static time_t filetime_to_time(const FILETIME *ft) {
  ULARGE_INTEGER value;
  value.LowPart = ft->dwLowDateTime;
  value.HighPart = ft->dwHighDateTime;
  return (time_t)((value.QuadPart - 116444736000000000ULL) / 10000000ULL);
}

int lstat(const char *path, struct stat *buf) {
  WIN32_FIND_DATAA find;
  DWORD attributes;
  HANDLE search;
  char target[MAXIMUM_REPARSE_DATA_BUFFER_SIZE];
  size_t length = 0;

  if (path == NULL || buf == NULL) {
    errno = EFAULT;
    return -1;
  }
  attributes = GetFileAttributesA(path);
  if (attributes == INVALID_FILE_ATTRIBUTES) {
    afni_compat_set_errno_from_win32(GetLastError());
    return -1;
  }
  if ((attributes & FILE_ATTRIBUTE_REPARSE_POINT) == 0 || strpbrk(path, "*?") != NULL) {
    return stat(path, buf);
  }
  search = FindFirstFileA(path, &find);
  if (search == INVALID_HANDLE_VALUE) {
    afni_compat_set_errno_from_win32(GetLastError());
    return -1;
  }
  FindClose(search);
  if (find.dwReserved0 != IO_REPARSE_TAG_SYMLINK &&
      find.dwReserved0 != IO_REPARSE_TAG_MOUNT_POINT) {
    return stat(path, buf);
  }
  if (link_target(path, target, sizeof(target), &length) != 0) {
    return -1;
  }
  memset(buf, 0, sizeof(*buf));
  buf->st_mode = (unsigned short)(S_IFLNK | 0777);
  buf->st_nlink = 1;
  buf->st_size = (off_t)length;
  buf->st_atime = filetime_to_time(&find.ftLastAccessTime);
  buf->st_mtime = filetime_to_time(&find.ftLastWriteTime);
  buf->st_ctime = filetime_to_time(&find.ftCreationTime);
  return 0;
}

int afni_compat_mkdir(const char *path, mode_t mode) {
  (void)mode;
  return _mkdir(path);
}

int fsync(int fd) {
  return _commit(fd);
}

int flock(int fd, int operation) {
  HANDLE handle = (HANDLE)_get_osfhandle(fd);
  OVERLAPPED overlapped;
  DWORD flags = 0;
  int base = operation & ~LOCK_NB;

  if (handle == INVALID_HANDLE_VALUE) {
    errno = EBADF;
    return -1;
  }
  memset(&overlapped, 0, sizeof(overlapped));
  if (base == LOCK_UN) {
    if (!UnlockFileEx(handle, 0, MAXDWORD, MAXDWORD, &overlapped) &&
        GetLastError() != ERROR_NOT_LOCKED) {
      afni_compat_set_errno_from_win32(GetLastError());
      return -1;
    }
    return 0;
  }
  if (base == LOCK_EX) {
    flags |= LOCKFILE_EXCLUSIVE_LOCK;
  } else if (base != LOCK_SH) {
    errno = EINVAL;
    return -1;
  }
  if (operation & LOCK_NB) {
    flags |= LOCKFILE_FAIL_IMMEDIATELY;
  }
  UnlockFileEx(handle, 0, MAXDWORD, MAXDWORD, &overlapped);
  memset(&overlapped, 0, sizeof(overlapped));
  if (!LockFileEx(handle, flags, 0, MAXDWORD, MAXDWORD, &overlapped)) {
    DWORD error = GetLastError();
    if (error == ERROR_LOCK_VIOLATION || error == ERROR_IO_PENDING) {
      errno = EWOULDBLOCK;
    } else {
      afni_compat_set_errno_from_win32(error);
    }
    return -1;
  }
  return 0;
}

int fcntl(int fd, int cmd, ...) {
  (void)fd;
  (void)cmd;
  AFNI_COMPAT_UNSUPPORTED("file descriptor flags (used only for sockets)");
  return -1;
}
