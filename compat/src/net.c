#include <arpa/inet.h>
#include <netdb.h>
#include <stdio.h>
#include <sys/socket.h>

#include "compat_internal.h"

#define SOCKETS_DETAIL "sockets are not implemented yet"

int socket(int domain, int type, int protocol) {
  (void)domain;
  (void)type;
  (void)protocol;
  AFNI_COMPAT_UNSUPPORTED(SOCKETS_DETAIL);
  return -1;
}

int bind(int sockfd, const struct sockaddr *addr, socklen_t addrlen) {
  (void)sockfd;
  (void)addr;
  (void)addrlen;
  AFNI_COMPAT_UNSUPPORTED(SOCKETS_DETAIL);
  return -1;
}

int listen(int sockfd, int backlog) {
  (void)sockfd;
  (void)backlog;
  AFNI_COMPAT_UNSUPPORTED(SOCKETS_DETAIL);
  return -1;
}

int accept(int sockfd, struct sockaddr *addr, socklen_t *addrlen) {
  (void)sockfd;
  (void)addr;
  (void)addrlen;
  AFNI_COMPAT_UNSUPPORTED(SOCKETS_DETAIL);
  return -1;
}

int connect(int sockfd, const struct sockaddr *addr, socklen_t addrlen) {
  (void)sockfd;
  (void)addr;
  (void)addrlen;
  AFNI_COMPAT_UNSUPPORTED(SOCKETS_DETAIL);
  return -1;
}

ssize_t send(int sockfd, const void *buf, size_t len, int flags) {
  (void)sockfd;
  (void)buf;
  (void)len;
  (void)flags;
  AFNI_COMPAT_UNSUPPORTED(SOCKETS_DETAIL);
  return -1;
}

ssize_t recv(int sockfd, void *buf, size_t len, int flags) {
  (void)sockfd;
  (void)buf;
  (void)len;
  (void)flags;
  AFNI_COMPAT_UNSUPPORTED(SOCKETS_DETAIL);
  return -1;
}

int setsockopt(int sockfd, int level, int optname, const void *optval, socklen_t optlen) {
  (void)sockfd;
  (void)level;
  (void)optname;
  (void)optval;
  (void)optlen;
  AFNI_COMPAT_UNSUPPORTED(SOCKETS_DETAIL);
  return -1;
}

int getsockopt(int sockfd, int level, int optname, void *optval, socklen_t *optlen) {
  (void)sockfd;
  (void)level;
  (void)optname;
  (void)optval;
  (void)optlen;
  AFNI_COMPAT_UNSUPPORTED(SOCKETS_DETAIL);
  return -1;
}

int shutdown(int sockfd, int how) {
  (void)sockfd;
  (void)how;
  AFNI_COMPAT_UNSUPPORTED(SOCKETS_DETAIL);
  return -1;
}

struct hostent *gethostbyname(const char *name) {
  (void)name;
  AFNI_COMPAT_UNSUPPORTED(SOCKETS_DETAIL);
  return NULL;
}

struct hostent *gethostbyaddr(const void *addr, socklen_t len, int type) {
  (void)addr;
  (void)len;
  (void)type;
  AFNI_COMPAT_UNSUPPORTED(SOCKETS_DETAIL);
  return NULL;
}

char *inet_ntoa(struct in_addr in) {
  static char text[16];
  uint32_t value = ntohl(in.s_addr);
  snprintf(text, sizeof(text), "%u.%u.%u.%u", (unsigned)(value >> 24) & 0xffu,
           (unsigned)(value >> 16) & 0xffu, (unsigned)(value >> 8) & 0xffu,
           (unsigned)value & 0xffu);
  return text;
}
