#include <errno.h>
#include <stdio.h>
#include <string.h>

/* POSIX fopen() has no text mode: "r" and "rb" are the same. The UCRT reads
   "r" in text mode unless the host executable set _fmode to binary at
   startup, which AFNI programs do (binmode.c) but R.exe, python.exe and other
   hosts of AFNI code (R_io.so) do not; there a Ctrl-Z byte ends the read and
   CR LF pairs shrink. AFNI code therefore gets binary mode unless it asks for
   text mode with "t". */
FILE *afni_compat_fopen(const char *path, const char *mode) {
  char binary_mode[16];
  size_t length;

  if (mode == NULL) {
    errno = EINVAL;
    return NULL;
  }
  length = strlen(mode);
  if (strpbrk(mode, "bt,") != NULL || length + 2 > sizeof(binary_mode)) {
    return fopen(path, mode);
  }
  memcpy(binary_mode, mode, length);
  binary_mode[length] = 'b';
  binary_mode[length + 1] = '\0';
  return fopen(path, binary_mode);
}
