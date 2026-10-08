#include <fcntl.h>
#include <io.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* Not linked with the layer: this program stands in for an external sh. */
#undef fopen

/* Stand-in for "sh -c COMMAND" used by test_shell. It understands:
   echo TEXT | exit N | save FILE (stdin to FILE) | dump FILE (FILE to stdout)
   | stderr TEXT. It tests the layer's pipes and status codes, not a shell. */

static int copy(FILE *in, FILE *out) {
  char buffer[4096];
  size_t n;
  while ((n = fread(buffer, 1, sizeof(buffer), in)) > 0) {
    if (fwrite(buffer, 1, n, out) != n) {
      return 1;
    }
  }
  return 0;
}

int main(int argc, char **argv) {
  const char *command;

  _setmode(0, _O_BINARY);
  _setmode(1, _O_BINARY);
  if (argc != 3 || strcmp(argv[1], "-c") != 0) {
    return 90;
  }
  command = argv[2];
  if (strncmp(command, "echo ", 5) == 0) {
    printf("%s\n", command + 5);
    return 0;
  }
  if (strncmp(command, "stderr ", 7) == 0) {
    fprintf(stderr, "%s\n", command + 7);
    return 0;
  }
  if (strncmp(command, "exit ", 5) == 0) {
    return atoi(command + 5);
  }
  if (strncmp(command, "save ", 5) == 0) {
    FILE *out = fopen(command + 5, "wb");
    int failed;
    if (out == NULL) {
      return 91;
    }
    failed = copy(stdin, out);
    fclose(out);
    return failed ? 92 : 0;
  }
  if (strncmp(command, "dump ", 5) == 0) {
    FILE *in = fopen(command + 5, "rb");
    int failed;
    if (in == NULL) {
      return 93;
    }
    failed = copy(in, stdout);
    fclose(in);
    return failed ? 94 : 0;
  }
  return 127;
}
