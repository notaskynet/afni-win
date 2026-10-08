#include <arpa/inet.h>
#include <fcntl.h>
#include <io.h>
#include <netdb.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/select.h>
#include <sys/socket.h>

#include "compat_internal.h"
#include "winsock_bridge.h"

/* A socket is a CRT file descriptor whose OS handle is the SOCKET
   (_open_osfhandle), so descriptor numbers never collide with files and
   read()/write() work on it. This table remembers which descriptors are
   sockets and whether they are non-blocking (Winsock cannot be asked). */

enum { FD_PLAIN = 0, FD_SOCKET = 1, FD_SOCKET_NONBLOCKING = 2 };

static SRWLOCK sockets_lock = SRWLOCK_INIT;
static unsigned char socket_kind[FD_SETSIZE];

static int kind_of(int fd) {
  int kind;
  if (fd < 0 || fd >= FD_SETSIZE) {
    return FD_PLAIN;
  }
  AcquireSRWLockShared(&sockets_lock);
  kind = socket_kind[fd];
  ReleaseSRWLockShared(&sockets_lock);
  return kind;
}

static void set_kind(int fd, int kind) {
  AcquireSRWLockExclusive(&sockets_lock);
  socket_kind[fd] = (unsigned char)kind;
  ReleaseSRWLockExclusive(&sockets_lock);
}

static int lookup(int fd, uintptr_t *s) {
  if (kind_of(fd) == FD_PLAIN) {
    errno = fd < 0 ? EBADF : ENOTSOCK;
    return -1;
  }
  *s = (uintptr_t)_get_osfhandle(fd);
  return 0;
}

static int adopt(uintptr_t s) {
  int fd;
  if (s == AFNI_WS_INVALID) {
    return -1;
  }
  fd = _open_osfhandle((intptr_t)s, _O_RDWR | _O_BINARY);
  if (fd < 0) {
    afni_ws_close(s);
    errno = EMFILE;
    return -1;
  }
  if (fd >= FD_SETSIZE) {
    afni_ws_close(s);
    _close(fd);
    errno = EMFILE;
    return -1;
  }
  set_kind(fd, FD_SOCKET);
  return fd;
}

int socket(int domain, int type, int protocol) {
  return adopt(afni_ws_socket(domain, type, protocol));
}

int afni_compat_close(int fd) {
  uintptr_t s;
  if (kind_of(fd) == FD_PLAIN) {
    return _close(fd);
  }
  s = (uintptr_t)_get_osfhandle(fd);
  set_kind(fd, FD_PLAIN);
  if (afni_ws_close(s) != 0) {
    int saved = errno;
    _close(fd);
    errno = saved;
    return -1;
  }
  /* Frees the descriptor; its CloseHandle on the closed SOCKET fails. */
  _close(fd);
  return 0;
}

int bind(int sockfd, const struct sockaddr *addr, socklen_t addrlen) {
  uintptr_t s;
  return lookup(sockfd, &s) != 0 ? -1 : afni_ws_bind(s, addr, addrlen);
}

int listen(int sockfd, int backlog) {
  uintptr_t s;
  return lookup(sockfd, &s) != 0 ? -1 : afni_ws_listen(s, backlog);
}

int accept(int sockfd, struct sockaddr *addr, socklen_t *addrlen) {
  uintptr_t s;
  return lookup(sockfd, &s) != 0 ? -1 : adopt(afni_ws_accept(s, addr, addrlen));
}

int connect(int sockfd, const struct sockaddr *addr, socklen_t addrlen) {
  uintptr_t s;
  return lookup(sockfd, &s) != 0 ? -1 : afni_ws_connect(s, addr, addrlen);
}

static int clamp_length(size_t len) {
  return len > 0x7fffffff ? 0x7fffffff : (int)len;
}

ssize_t send(int sockfd, const void *buf, size_t len, int flags) {
  uintptr_t s;
  return lookup(sockfd, &s) != 0 ? -1 : afni_ws_send(s, buf, clamp_length(len), flags);
}

ssize_t recv(int sockfd, void *buf, size_t len, int flags) {
  uintptr_t s;
  return lookup(sockfd, &s) != 0 ? -1 : afni_ws_recv(s, buf, clamp_length(len), flags);
}

int setsockopt(int sockfd, int level, int optname, const void *optval, socklen_t optlen) {
  uintptr_t s;
  if (lookup(sockfd, &s) != 0) {
    return -1;
  }
  if (level == SOL_SOCKET && optname == SO_LINGER) {
    const struct linger *lg = (const struct linger *)optval;
    unsigned short pair[2];
    if (optval == NULL || optlen < (socklen_t)sizeof(struct linger)) {
      errno = EINVAL;
      return -1;
    }
    pair[0] = (unsigned short)(lg->l_onoff != 0);
    pair[1] = (unsigned short)lg->l_linger;
    return afni_ws_setsockopt(s, level, optname, pair, (int)sizeof(pair));
  }
  return afni_ws_setsockopt(s, level, optname, optval, optlen);
}

int getsockopt(int sockfd, int level, int optname, void *optval, socklen_t *optlen) {
  uintptr_t s;
  if (lookup(sockfd, &s) != 0) {
    return -1;
  }
  if (level == SOL_SOCKET && optname == SO_LINGER) {
    unsigned short pair[2];
    int length = (int)sizeof(pair);
    struct linger *lg = (struct linger *)optval;
    if (optval == NULL || optlen == NULL || *optlen < (socklen_t)sizeof(struct linger)) {
      errno = EINVAL;
      return -1;
    }
    if (afni_ws_getsockopt(s, level, optname, pair, &length) != 0) {
      return -1;
    }
    lg->l_onoff = pair[0];
    lg->l_linger = pair[1];
    *optlen = (socklen_t)sizeof(struct linger);
    return 0;
  }
  return afni_ws_getsockopt(s, level, optname, optval, optlen);
}

int shutdown(int sockfd, int how) {
  uintptr_t s;
  return lookup(sockfd, &s) != 0 ? -1 : afni_ws_shutdown(s, how);
}

static struct hostent host_entry;

static struct hostent *convert_host(int result, const afni_ws_host *host) {
  if (result != 0) {
    return NULL;
  }
  host_entry.h_name = (char *)host->name;
  host_entry.h_aliases = host->aliases;
  host_entry.h_addrtype = host->addrtype;
  host_entry.h_length = host->length;
  host_entry.h_addr_list = host->addr_list;
  return &host_entry;
}

struct hostent *gethostbyname(const char *name) {
  afni_ws_host host;
  return convert_host(afni_ws_gethostbyname(name, &host), &host);
}

struct hostent *gethostbyaddr(const void *addr, socklen_t len, int type) {
  afni_ws_host host;
  return convert_host(afni_ws_gethostbyaddr(addr, len, type, &host), &host);
}

char *inet_ntoa(struct in_addr in) {
  static char text[16];
  uint32_t value = ntohl(in.s_addr);
  snprintf(text, sizeof(text), "%u.%u.%u.%u", (unsigned)(value >> 24) & 0xffu,
           (unsigned)(value >> 16) & 0xffu, (unsigned)(value >> 8) & 0xffu,
           (unsigned)value & 0xffu);
  return text;
}

int fcntl(int fd, int cmd, ...) {
  int kind = kind_of(fd);
  int arg = 0;
  va_list args;

  va_start(args, cmd);
  if (cmd == F_SETFL || cmd == F_SETOWN) {
    arg = va_arg(args, int);
  }
  va_end(args);

  if (cmd != F_GETFL && cmd != F_SETFL && cmd != F_SETOWN) {
    errno = EINVAL;
    return -1;
  }
  if (kind == FD_PLAIN) {
    if (_get_osfhandle(fd) == -1) {
      errno = EBADF;
      return -1;
    }
    AFNI_COMPAT_UNSUPPORTED("file status flags are only supported on sockets");
    return -1;
  }
  switch (cmd) {
    case F_GETFL:
      return O_RDWR | (kind == FD_SOCKET_NONBLOCKING ? O_NONBLOCK : 0);
    case F_SETFL:
      if ((arg & ~(O_NONBLOCK | O_ACCMODE)) != 0) {
        AFNI_COMPAT_UNSUPPORTED("only O_NONBLOCK can be changed on a socket");
        return -1;
      }
      if (afni_ws_set_nonblocking((uintptr_t)_get_osfhandle(fd), (arg & O_NONBLOCK) != 0) != 0) {
        return -1;
      }
      set_kind(fd, (arg & O_NONBLOCK) != 0 ? FD_SOCKET_NONBLOCKING : FD_SOCKET);
      return 0;
    default:
      /* F_SETOWN only selects who receives SIGURG/SIGIO, which Windows never
         raises (see manifests/noop-allowlist.txt). */
      return 0;
  }
}

static int collect(const fd_set *set, int nfds, uintptr_t *sockets, int *fds, int *count) {
  *count = 0;
  if (set == NULL) {
    return 0;
  }
  for (int fd = 0; fd < nfds; ++fd) {
    if (FD_ISSET(fd, set)) {
      if (kind_of(fd) == FD_PLAIN) {
        return -1;
      }
      sockets[*count] = (uintptr_t)_get_osfhandle(fd);
      fds[*count] = fd;
      ++*count;
    }
  }
  return 0;
}

static void store(fd_set *set, const int *fds, const int *ready, int count) {
  if (set == NULL) {
    return;
  }
  FD_ZERO(set);
  for (int i = 0; i < count; ++i) {
    if (ready[i]) {
      FD_SET(fds[i], set);
    }
  }
}

static int sleep_for(const struct timeval *timeout) {
  unsigned long long ms;
  if (timeout == NULL) {
    for (;;) {
      Sleep(INFINITE);
    }
  }
  ms = (unsigned long long)timeout->tv_sec * 1000ULL +
       ((unsigned long long)timeout->tv_usec + 999ULL) / 1000ULL;
  while (ms > 0) {
    DWORD chunk = ms > 0x7fffffffULL ? 0x7fffffffUL : (DWORD)ms;
    Sleep(chunk);
    ms -= chunk;
  }
  return 0;
}

typedef struct {
  uintptr_t sockets[3][FD_SETSIZE];
  int fds[3][FD_SETSIZE];
  int ready[3][FD_SETSIZE];
  int counts[3];
} select_sets;

int select(int nfds, fd_set *readfds, fd_set *writefds, fd_set *exceptfds,
           struct timeval *timeout) {
  select_sets *sets;
  int result;

  if (nfds < 0 || nfds > FD_SETSIZE ||
      (timeout != NULL &&
       (timeout->tv_sec < 0 || timeout->tv_usec < 0 || timeout->tv_usec >= 1000000))) {
    errno = EINVAL;
    return -1;
  }
  sets = (select_sets *)malloc(sizeof(select_sets));
  if (sets == NULL) {
    errno = ENOMEM;
    return -1;
  }
  if (collect(readfds, nfds, sets->sockets[0], sets->fds[0], &sets->counts[0]) != 0 ||
      collect(writefds, nfds, sets->sockets[1], sets->fds[1], &sets->counts[1]) != 0 ||
      collect(exceptfds, nfds, sets->sockets[2], sets->fds[2], &sets->counts[2]) != 0) {
    free(sets);
    AFNI_COMPAT_UNSUPPORTED("waiting is only supported on sockets");
    return -1;
  }
  if (sets->counts[0] + sets->counts[1] + sets->counts[2] == 0) {
    free(sets);
    return sleep_for(timeout);
  }
  result = afni_ws_select(sets->sockets[0], sets->counts[0], sets->ready[0], sets->sockets[1],
                          sets->counts[1], sets->ready[1], sets->sockets[2], sets->counts[2],
                          sets->ready[2],
                          timeout == NULL ? -1
                                          : (long long)timeout->tv_sec * 1000000LL +
                                                timeout->tv_usec);
  if (result >= 0) {
    store(readfds, sets->fds[0], sets->ready[0], sets->counts[0]);
    store(writefds, sets->fds[1], sets->ready[1], sets->counts[1]);
    store(exceptfds, sets->fds[2], sets->ready[2], sets->counts[2]);
  }
  free(sets);
  return result;
}
