#include <ctype.h>
#include <string.h>

char *strcasestr(const char *haystack, const char *needle) {
  size_t length = strlen(needle);

  if (length == 0) {
    return (char *)haystack;
  }
  for (; *haystack != '\0'; ++haystack) {
    if (tolower((unsigned char)*haystack) == tolower((unsigned char)*needle) &&
        _strnicmp(haystack, needle, length) == 0) {
      return (char *)haystack;
    }
  }
  return NULL;
}
