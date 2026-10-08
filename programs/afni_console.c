/* afni-win: console stand-in for the AFNI GUI program `afni`, which the
 * Windows build does not have (docs/DECISIONS.md D36).
 *
 * The version queries print what afni prints: the same macros as
 * show_AFNI_version(), show_AFNI_vnum() and show_AFNI_package() in
 * src/afni.c, compiled with SHOWOFF as upstream compiles afni.c. Every
 * proc script of afni_proc.py starts with `afni -ver`. Any other use reports
 * that the GUI is missing and exits with status 1. */

#include "mrilib.h"
#include "RomanImperator.h"

#ifdef SHOWOFF
#undef SHSH
#undef SHSHSH
#undef SHSTRING
#define SHSH(x) #x
#define SHSHSH(x) SHSH(x)
#define SHSTRING SHSHSH(SHOWOFF)
#else
#undef SHSTRING
#endif

static int has_option(int argc, char *argv[], const char *option) {
  for (int ii = 1; ii < argc; ii++) {
    if (strcmp(argv[ii], option) == 0) {
      return 1;
    }
  }
  return 0;
}

static void show_version(void) {
  const char *rimp = AFNI_VERSION_RomanImperator;
  char vvvv[1024];

  if (rimp != NULL && *rimp != '\0') {
    snprintf(vvvv, sizeof(vvvv), "%s '%s'", AFNI_VERSION_LABEL, rimp);
  } else {
    snprintf(vvvv, sizeof(vvvv), "%s", AFNI_VERSION_LABEL);
  }
#ifdef SHSTRING
  printf("Precompiled binary " SHSTRING ": " __DATE__ " (Version %s)\n", vvvv);
#else
  printf("Compile date = " __DATE__ " " __TIME__ " (Version %s)\n", vvvv);
#endif
}

static void show_package(void) {
#ifdef SHSTRING
  printf(SHSTRING "\n");
#else
  printf("Compiled: " __DATE__);
#endif
}

int main(int argc, char *argv[]) {
  int answered = 0;

  if (has_option(argc, argv, "-ver") || has_option(argc, argv, "--ver") ||
      has_option(argc, argv, "-version") || has_option(argc, argv, "--version")) {
    show_version();
    answered = 1;
  }
  if (has_option(argc, argv, "-vnum")) {
    printf(AFNI_VERSION_LABEL "\n");
    answered = 1;
  }
  if (has_option(argc, argv, "-package")) {
    show_package();
    answered = 1;
  }
  if (answered) {
    return 0;
  }
  fprintf(stderr,
          "** afni-win: the AFNI GUI (afni) is not part of the Windows build;\n"
          "   only 'afni -ver', 'afni -vnum' and 'afni -package' are available.\n");
  return 1;
}
