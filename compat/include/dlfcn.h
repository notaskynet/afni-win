#ifndef AFNI_COMPAT_DLFCN_H
#define AFNI_COMPAT_DLFCN_H

#include "afni_compat_api.h"

#ifdef __cplusplus
extern "C" {
#endif

/* Windows resolves all imports when a DLL is loaded and has no global symbol
   namespace, so these flags are accepted and ignored (noop-allowlist.txt). */
#define RTLD_LAZY 0x0001
#define RTLD_NOW 0x0002
#define RTLD_LOCAL 0x0000
#define RTLD_GLOBAL 0x0100

AFNI_COMPAT_API void *dlopen(const char *filename, int flags);
AFNI_COMPAT_API void *dlsym(void *handle, const char *symbol);
AFNI_COMPAT_API int dlclose(void *handle);
AFNI_COMPAT_API char *dlerror(void);

#ifdef __cplusplus
}
#endif

#endif
