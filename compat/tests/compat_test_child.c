#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <windows.h>

int main(int argc, char **argv) {
  FILE *fp;

  if (argc < 3) {
    return 99;
  }
  fp = fopen(argv[1], "wb");
  if (fp == NULL) {
    return 98;
  }
  for (int i = 3; i < argc; ++i) {
    fprintf(fp, "%s\n", argv[i]);
  }
  if (atoi(argv[2]) == 3) {
    fprintf(fp, "PPID=%d\n", (int)getppid());
  }
  fprintf(fp, "ENV=%s\n", getenv("AFNI_COMPAT_TEST_VAR") ? getenv("AFNI_COMPAT_TEST_VAR") : "");
  fclose(fp);
  if (atoi(argv[2]) == -2) {
    Sleep(60000);
  }
  if (atoi(argv[2]) == -1) {
    volatile int *crash = NULL;
    *crash = 1;
  }
  return atoi(argv[2]);
}
