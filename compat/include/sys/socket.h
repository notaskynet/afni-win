#ifndef AFNI_COMPAT_SYS_SOCKET_H
#define AFNI_COMPAT_SYS_SOCKET_H

#include <sys/types.h>

#include "afni_compat_api.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef int socklen_t;
typedef unsigned short sa_family_t;

struct sockaddr {
  sa_family_t sa_family;
  char sa_data[14];
};

struct linger {
  int l_onoff;
  int l_linger;
};

#define AF_UNSPEC 0
#define AF_INET 2
#define PF_UNSPEC AF_UNSPEC
#define PF_INET AF_INET

#define SOCK_STREAM 1
#define SOCK_DGRAM 2

#define SOL_SOCKET 0xffff
#define SO_REUSEADDR 0x0004
#define SO_LINGER 0x0080
#define SO_SNDBUF 0x1001
#define SO_RCVBUF 0x1002

#define MSG_OOB 0x1
#define MSG_PEEK 0x2

#define SHUT_RD 0
#define SHUT_WR 1
#define SHUT_RDWR 2

AFNI_COMPAT_API int socket(int domain, int type, int protocol);
AFNI_COMPAT_API int bind(int sockfd, const struct sockaddr *addr, socklen_t addrlen);
AFNI_COMPAT_API int listen(int sockfd, int backlog);
AFNI_COMPAT_API int accept(int sockfd, struct sockaddr *addr, socklen_t *addrlen);
AFNI_COMPAT_API int connect(int sockfd, const struct sockaddr *addr, socklen_t addrlen);
AFNI_COMPAT_API ssize_t send(int sockfd, const void *buf, size_t len, int flags);
AFNI_COMPAT_API ssize_t recv(int sockfd, void *buf, size_t len, int flags);
AFNI_COMPAT_API int setsockopt(int sockfd, int level, int optname, const void *optval,
                               socklen_t optlen);
AFNI_COMPAT_API int getsockopt(int sockfd, int level, int optname, void *optval,
                               socklen_t *optlen);
AFNI_COMPAT_API int shutdown(int sockfd, int how);

#ifdef __cplusplus
}
#endif

#endif
