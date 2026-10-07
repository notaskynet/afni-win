#include <stdio.h>
#include <stdlib.h>

#include "compat_internal.h"

#define SHELL_DETAIL "running shell commands is not implemented yet"

FILE *afni_compat_popen(const char *command, const char *mode) {
  (void)command;
  (void)mode;
  AFNI_COMPAT_UNSUPPORTED(SHELL_DETAIL);
  return NULL;
}

int afni_compat_pclose(FILE *stream) {
  (void)stream;
  AFNI_COMPAT_UNSUPPORTED(SHELL_DETAIL);
  return -1;
}

int afni_compat_system(const char *command) {
  if (command == NULL) {
    return 0;
  }
  AFNI_COMPAT_UNSUPPORTED(SHELL_DETAIL);
  return -1;
}
