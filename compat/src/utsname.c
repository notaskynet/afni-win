#include <stdio.h>
#include <string.h>
#include <sys/utsname.h>
#include <unistd.h>

#include "compat_internal.h"

typedef LONG(WINAPI *rtl_get_version_fn)(PRTL_OSVERSIONINFOW);

static int get_version(RTL_OSVERSIONINFOW *info) {
  HMODULE ntdll = GetModuleHandleA("ntdll.dll");
  rtl_get_version_fn fn;

  if (ntdll == NULL) {
    return -1;
  }
  fn = (rtl_get_version_fn)(void *)GetProcAddress(ntdll, "RtlGetVersion");
  if (fn == NULL) {
    return -1;
  }
  memset(info, 0, sizeof(*info));
  info->dwOSVersionInfoSize = sizeof(*info);
  return fn(info) == 0 ? 0 : -1;
}

int gethostname(char *name, size_t len) {
  char buffer[MAX_COMPUTERNAME_LENGTH + 256];
  DWORD size = (DWORD)sizeof(buffer);

  if (name == NULL) {
    errno = EFAULT;
    return -1;
  }
  if (!GetComputerNameExA(ComputerNameDnsHostname, buffer, &size)) {
    afni_compat_set_errno_from_win32(GetLastError());
    return -1;
  }
  if (strlen(buffer) + 1 > len) {
    errno = ENAMETOOLONG;
    return -1;
  }
  strcpy(name, buffer);
  return 0;
}

int uname(struct utsname *buf) {
  RTL_OSVERSIONINFOW version;
  SYSTEM_INFO info;

  if (buf == NULL) {
    errno = EFAULT;
    return -1;
  }
  if (get_version(&version) != 0) {
    errno = EIO;
    return -1;
  }
  memset(buf, 0, sizeof(*buf));
  snprintf(buf->sysname, sizeof(buf->sysname), "Windows");
  if (gethostname(buf->nodename, sizeof(buf->nodename)) != 0) {
    return -1;
  }
  snprintf(buf->release, sizeof(buf->release), "%lu.%lu", (unsigned long)version.dwMajorVersion,
           (unsigned long)version.dwMinorVersion);
  snprintf(buf->version, sizeof(buf->version), "%lu", (unsigned long)version.dwBuildNumber);
  GetNativeSystemInfo(&info);
  switch (info.wProcessorArchitecture) {
    case PROCESSOR_ARCHITECTURE_AMD64:
      snprintf(buf->machine, sizeof(buf->machine), "x86_64");
      break;
    case PROCESSOR_ARCHITECTURE_ARM64:
      snprintf(buf->machine, sizeof(buf->machine), "aarch64");
      break;
    case PROCESSOR_ARCHITECTURE_INTEL:
      snprintf(buf->machine, sizeof(buf->machine), "i686");
      break;
    default:
      snprintf(buf->machine, sizeof(buf->machine), "unknown");
      break;
  }
  return 0;
}
