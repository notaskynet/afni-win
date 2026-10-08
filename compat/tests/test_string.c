#include <string.h>

#include "test_common.h"

int main(void) {
  const char *text = "Hello World of AFNI";

  CHECK(strcasestr(text, "world") == text + 6);
  CHECK(strcasestr(text, "AFNI") == text + 15);
  CHECK(strcasestr(text, "afnI") == text + 15);
  CHECK(strcasestr(text, "") == text);
  CHECK(strcasestr(text, "missing") == NULL);
  CHECK(strcasestr("", "x") == NULL);

  CHECK(index(text, 'o') == text + 4);
  CHECK(index(text, 'Z') == NULL);
  CHECK(index(text, '\0') == text + strlen(text));
  return TEST_RESULT();
}
