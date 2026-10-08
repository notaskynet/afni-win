#include <windows.h>

#include <stdio.h>
#include <string.h>

#include "test_common.h"

int main(void) {
  /* "тест.txt" in UTF-8 and UTF-16 */
  const char *name = "\xd1\x82\xd0\xb5\xd1\x81\xd1\x82.txt";
  const wchar_t *wide = L"\x0442\x0435\x0441\x0442.txt";
  FILE *file;

  CHECK(GetACP() == CP_UTF8);

  file = fopen(name, "wb");
  CHECK(file != NULL);
  if (file != NULL) {
    fputs("x", file);
    fclose(file);
  }
  file = _wfopen(wide, L"rb");
  CHECK(file != NULL);
  if (file != NULL) {
    CHECK(fgetc(file) == 'x');
    fclose(file);
  }
  _wremove(wide);
  return TEST_RESULT();
}
