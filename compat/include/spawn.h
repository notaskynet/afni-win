#ifndef AFNI_COMPAT_SPAWN_H
#define AFNI_COMPAT_SPAWN_H

#include <sys/types.h>

#include "afni_compat_api.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef struct afni_compat_spawn_file_actions *posix_spawn_file_actions_t;
typedef struct afni_compat_spawnattr *posix_spawnattr_t;

AFNI_COMPAT_API int posix_spawn(pid_t *pid, const char *path,
                                const posix_spawn_file_actions_t *file_actions,
                                const posix_spawnattr_t *attrp, char *const argv[],
                                char *const envp[]);
AFNI_COMPAT_API int posix_spawnp(pid_t *pid, const char *file,
                                 const posix_spawn_file_actions_t *file_actions,
                                 const posix_spawnattr_t *attrp, char *const argv[],
                                 char *const envp[]);

#ifdef __cplusplus
}
#endif

#endif
