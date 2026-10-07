#include <pwd.h>
#include <stdlib.h>
#include <string.h>

#include "compat_internal.h"

static char passwd_name[257];
static char passwd_dir[MAX_PATH + 1];
static char passwd_empty[1];
static struct passwd passwd_entry;

uid_t getuid(void) {
  return 0;
}

uid_t geteuid(void) {
  return 0;
}

struct passwd *getpwuid(uid_t uid) {
  DWORD size = (DWORD)sizeof(passwd_name);
  const char *home;

  if (uid != getuid()) {
    return NULL;
  }
  if (!GetUserNameA(passwd_name, &size)) {
    afni_compat_set_errno_from_win32(GetLastError());
    return NULL;
  }
  home = getenv("USERPROFILE");
  if (home == NULL || strlen(home) >= sizeof(passwd_dir)) {
    errno = ENOENT;
    return NULL;
  }
  strcpy(passwd_dir, home);
  for (char *p = passwd_dir; *p != '\0'; ++p) {
    if (*p == '\\') {
      *p = '/';
    }
  }
  passwd_entry.pw_name = passwd_name;
  passwd_entry.pw_passwd = passwd_empty;
  passwd_entry.pw_uid = uid;
  passwd_entry.pw_gid = 0;
  passwd_entry.pw_gecos = passwd_name;
  passwd_entry.pw_dir = passwd_dir;
  passwd_entry.pw_shell = passwd_empty;
  return &passwd_entry;
}
