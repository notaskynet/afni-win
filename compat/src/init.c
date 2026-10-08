#include <fcntl.h>
#include <io.h>
#include <stdio.h>

#include "compat_internal.h"

void afni_compat_runtime(void) {
}

__attribute__((constructor)) static void afni_compat_init(void) {
  _setmode(_fileno(stdin), _O_BINARY);
  _setmode(_fileno(stdout), _O_BINARY);
  _setmode(_fileno(stderr), _O_BINARY);
  afni_compat_init_environment();
}
