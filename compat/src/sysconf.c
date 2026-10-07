#include <limits.h>
#include <errno.h>
#include <unistd.h>

#include "compat_internal.h"

long sysconf(int name) {
  SYSTEM_INFO info;
  MEMORYSTATUSEX memory;

  switch (name) {
    case _SC_PAGESIZE:
      GetSystemInfo(&info);
      return (long)info.dwPageSize;
    case _SC_NPROCESSORS_CONF:
      return (long)GetActiveProcessorCount(ALL_PROCESSOR_GROUPS);
    case _SC_NPROCESSORS_ONLN:
      return (long)GetActiveProcessorCount(ALL_PROCESSOR_GROUPS);
    case _SC_PHYS_PAGES:
    case _SC_AVPHYS_PAGES:
      GetSystemInfo(&info);
      memory.dwLength = sizeof(memory);
      if (!GlobalMemoryStatusEx(&memory)) {
        afni_compat_set_errno_from_win32(GetLastError());
        return -1;
      }
      {
        DWORDLONG bytes = (name == _SC_PHYS_PAGES) ? memory.ullTotalPhys : memory.ullAvailPhys;
        DWORDLONG pages = bytes / info.dwPageSize;
        return pages > (DWORDLONG)LONG_MAX ? LONG_MAX : (long)pages;
      }
    default:
      errno = EINVAL;
      return -1;
  }
}
