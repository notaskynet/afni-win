#ifndef AFNI_COMPAT_SYS_WAIT_H
#define AFNI_COMPAT_SYS_WAIT_H

#include <sys/types.h>

#include "afni_compat_api.h"

#ifdef __cplusplus
extern "C" {
#endif

#define WNOHANG 1
#define WUNTRACED 2

#define WEXITSTATUS(status) (((status) >> 8) & 0xff)
#define WTERMSIG(status) ((status) & 0x7f)
#define WIFEXITED(status) (WTERMSIG(status) == 0)
#define WIFSIGNALED(status) (WTERMSIG(status) != 0)
#define WIFSTOPPED(status) 0

AFNI_COMPAT_API pid_t waitpid(pid_t pid, int *status, int options);
AFNI_COMPAT_API pid_t wait(int *status);

#ifdef __cplusplus
}
#endif

#endif
