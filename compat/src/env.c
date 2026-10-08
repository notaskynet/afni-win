#include <stdlib.h>
#include <string.h>

#include "compat_internal.h"

static void forward_slashes(char *text) {
  for (char *p = text; *p != '\0'; ++p) {
    if (*p == '\\') {
      *p = '/';
    }
  }
}

static int unset(const char *name) {
  const char *value = getenv(name);
  return value == NULL || value[0] == '\0';
}

static void set_home(void) {
  const char *profile = getenv("USERPROFILE");
  char home[MAX_PATH + 1];

  if (!unset("HOME") || profile == NULL || profile[0] == '\0' || strlen(profile) >= sizeof(home)) {
    return;
  }
  strcpy(home, profile);
  forward_slashes(home);
  _putenv_s("HOME", home);
}

static void set_tmpdir(void) {
  char tmp[MAX_PATH + 1];
  DWORD length;

  if (!unset("TMPDIR")) {
    return;
  }
  length = GetTempPathA(sizeof(tmp), tmp);
  if (length == 0 || length >= sizeof(tmp)) {
    return;
  }
  while (length > 3 && (tmp[length - 1] == '\\' || tmp[length - 1] == '/')) {
    tmp[--length] = '\0';
  }
  forward_slashes(tmp);
  _putenv_s("TMPDIR", tmp);
}

void afni_compat_init_environment(void) {
  set_home();
  set_tmpdir();
}
