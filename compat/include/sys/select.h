#ifndef AFNI_COMPAT_SYS_SELECT_H
#define AFNI_COMPAT_SYS_SELECT_H

#include <string.h>
#include <sys/time.h>

#include "afni_compat_api.h"

#ifdef __cplusplus
extern "C" {
#endif

#ifndef FD_SETSIZE
#define FD_SETSIZE 1024
#endif

#define AFNI_COMPAT_NFDBITS (8 * (int)sizeof(unsigned long))

typedef struct {
  unsigned long fds_bits[FD_SETSIZE / (8 * sizeof(unsigned long))];
} fd_set;

#define FD_ZERO(set) memset((set), 0, sizeof(fd_set))
#define FD_SET(fd, set) \
  ((set)->fds_bits[(fd) / AFNI_COMPAT_NFDBITS] |= (1UL << ((fd) % AFNI_COMPAT_NFDBITS)))
#define FD_CLR(fd, set) \
  ((set)->fds_bits[(fd) / AFNI_COMPAT_NFDBITS] &= ~(1UL << ((fd) % AFNI_COMPAT_NFDBITS)))
#define FD_ISSET(fd, set) \
  (((set)->fds_bits[(fd) / AFNI_COMPAT_NFDBITS] & (1UL << ((fd) % AFNI_COMPAT_NFDBITS))) != 0)

AFNI_COMPAT_API int select(int nfds, fd_set *readfds, fd_set *writefds, fd_set *exceptfds,
                           struct timeval *timeout);

#ifdef __cplusplus
}
#endif

#endif
