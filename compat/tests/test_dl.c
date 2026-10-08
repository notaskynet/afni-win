#include <dlfcn.h>
#include <windows.h>

#include "test_common.h"

int main(void) {
  char path[MAX_PATH];
  char *slash;
  void *module;
  int (*answer)(void);
  int *value;

  GetModuleFileNameA(NULL, path, sizeof(path));
  for (char *p = path; *p != '\0'; ++p) {
    if (*p == '\\') {
      *p = '/';
    }
  }
  slash = strrchr(path, '/');
  strcpy(slash + 1, "compat_test_module.dll");

  CHECK(dlerror() == NULL);
  module = dlopen(path, RTLD_LAZY);
  CHECK(module != NULL);
  if (module != NULL) {
    answer = (int (*)(void))(void (*)(void))dlsym(module, "compat_test_answer");
    value = (int *)dlsym(module, "compat_test_value");
    CHECK(answer != NULL && answer() == 42);
    CHECK(value != NULL && *value == 7);
    CHECK(dlsym(module, "no_such_symbol") == NULL);
    CHECK(dlerror() != NULL);
    CHECK(dlerror() == NULL);
    CHECK(dlclose(module) == 0);
  }

  CHECK(dlopen("C:/no/such/library.dll", RTLD_NOW) == NULL);
  {
    char *message = dlerror();
    CHECK(message != NULL && strstr(message, "library.dll") != NULL);
  }
  CHECK(dlopen(NULL, RTLD_NOW) == (void *)GetModuleHandleA(NULL));
  CHECK(dlclose(dlopen(NULL, RTLD_NOW)) == 0);
  return TEST_RESULT();
}
