#include <stdint.h>
#include <stdlib.h>
#include <sys/mman.h>

#include "compat_internal.h"

typedef struct mapping {
  void *address;
  void *view;
  size_t length;
  struct mapping *next;
} mapping;

static SRWLOCK mappings_lock = SRWLOCK_INIT;
static mapping *mappings = NULL;

static size_t page_rounded(size_t length) {
  SYSTEM_INFO info;
  GetSystemInfo(&info);
  return (length + info.dwPageSize - 1) / info.dwPageSize * info.dwPageSize;
}

static DWORD allocation_granularity(void) {
  SYSTEM_INFO info;
  GetSystemInfo(&info);
  return info.dwAllocationGranularity;
}

void *mmap(void *addr, size_t length, int prot, int flags, int fd, off_t offset) {
  int anonymous = (flags & MAP_ANONYMOUS) != 0;
  int shared = (flags & MAP_SHARED) != 0;
  int private_map = (flags & MAP_PRIVATE) != 0;
  DWORD protect;
  DWORD access;
  HANDLE file = INVALID_HANDLE_VALUE;
  HANDLE section;
  uint64_t aligned_offset;
  uint64_t delta;
  uint64_t view_length;
  uint64_t section_size;
  void *view;
  mapping *entry;

  (void)addr;
  if (length == 0 || shared == private_map || offset < 0) {
    errno = EINVAL;
    return MAP_FAILED;
  }
  if ((flags & MAP_FIXED) != 0) {
    AFNI_COMPAT_UNSUPPORTED("MAP_FIXED");
    return MAP_FAILED;
  }
  if ((prot & PROT_EXEC) != 0 || prot == PROT_NONE) {
    AFNI_COMPAT_UNSUPPORTED("PROT_EXEC and PROT_NONE mappings");
    return MAP_FAILED;
  }
  if ((prot & PROT_WRITE) != 0) {
    if (private_map && !anonymous) {
      protect = PAGE_WRITECOPY;
      access = FILE_MAP_COPY;
    } else {
      protect = PAGE_READWRITE;
      access = FILE_MAP_WRITE;
    }
  } else {
    protect = PAGE_READONLY;
    access = FILE_MAP_READ;
  }
  if (anonymous) {
    if (offset != 0) {
      errno = EINVAL;
      return MAP_FAILED;
    }
    protect = PAGE_READWRITE;
    access = FILE_MAP_WRITE;
  } else {
    file = (HANDLE)_get_osfhandle(fd);
    if (file == INVALID_HANDLE_VALUE) {
      errno = EBADF;
      return MAP_FAILED;
    }
  }
  aligned_offset = (uint64_t)offset - ((uint64_t)offset % allocation_granularity());
  delta = (uint64_t)offset - aligned_offset;
  view_length = delta + (uint64_t)length;
  section_size = anonymous ? (uint64_t)length : 0;
  section = CreateFileMappingA(file, NULL, protect, (DWORD)(section_size >> 32),
                               (DWORD)(section_size & 0xffffffffu), NULL);
  if (section == NULL) {
    afni_compat_set_errno_from_win32(GetLastError());
    return MAP_FAILED;
  }
  view = MapViewOfFile(section, access, (DWORD)(aligned_offset >> 32),
                       (DWORD)(aligned_offset & 0xffffffffu), (SIZE_T)view_length);
  CloseHandle(section);
  if (view == NULL) {
    afni_compat_set_errno_from_win32(GetLastError());
    return MAP_FAILED;
  }
  entry = (mapping *)malloc(sizeof(*entry));
  if (entry == NULL) {
    UnmapViewOfFile(view);
    errno = ENOMEM;
    return MAP_FAILED;
  }
  entry->view = view;
  entry->address = (char *)view + delta;
  entry->length = length;
  AcquireSRWLockExclusive(&mappings_lock);
  entry->next = mappings;
  mappings = entry;
  ReleaseSRWLockExclusive(&mappings_lock);
  return entry->address;
}

int munmap(void *addr, size_t length) {
  mapping **link;
  mapping *found = NULL;

  AcquireSRWLockExclusive(&mappings_lock);
  for (link = &mappings; *link != NULL; link = &(*link)->next) {
    if ((*link)->address == addr) {
      found = *link;
      if (page_rounded(length) == page_rounded(found->length)) {
        *link = found->next;
      }
      break;
    }
  }
  ReleaseSRWLockExclusive(&mappings_lock);
  if (found == NULL) {
    errno = EINVAL;
    return -1;
  }
  if (page_rounded(length) != page_rounded(found->length)) {
    AFNI_COMPAT_UNSUPPORTED("partial unmapping of a region");
    return -1;
  }
  if (!UnmapViewOfFile(found->view)) {
    afni_compat_set_errno_from_win32(GetLastError());
    free(found);
    return -1;
  }
  free(found);
  return 0;
}
