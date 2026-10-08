#ifndef AFNI_COMPAT_WINSOCK_BRIDGE_H
#define AFNI_COMPAT_WINSOCK_BRIDGE_H

/*
 * Thin wrappers around Winsock. winsock_bridge.c is compiled without the
 * forced include, because <winsock2.h> defines fd_set, struct sockaddr and
 * the socket functions with the same names as the layer's POSIX headers.
 * Only plain types cross this boundary. On failure a function returns -1
 * (or AFNI_WS_INVALID) and sets errno from WSAGetLastError().
 */

#include <stddef.h>
#include <stdint.h>

#define AFNI_WS_INVALID (~(uintptr_t)0)

typedef struct {
  const char *name;
  char **aliases;
  int addrtype;
  int length;
  char **addr_list;
} afni_ws_host;

int afni_ws_startup(void);
uintptr_t afni_ws_socket(int domain, int type, int protocol);
int afni_ws_close(uintptr_t s);
int afni_ws_bind(uintptr_t s, const void *addr, int addrlen);
int afni_ws_listen(uintptr_t s, int backlog);
uintptr_t afni_ws_accept(uintptr_t s, void *addr, int *addrlen);
int afni_ws_connect(uintptr_t s, const void *addr, int addrlen);
int afni_ws_send(uintptr_t s, const void *buf, int len, int flags);
int afni_ws_recv(uintptr_t s, void *buf, int len, int flags);
int afni_ws_setsockopt(uintptr_t s, int level, int name, const void *value, int length);
int afni_ws_getsockopt(uintptr_t s, int level, int name, void *value, int *length);
int afni_ws_shutdown(uintptr_t s, int how);
int afni_ws_set_nonblocking(uintptr_t s, int enable);
int afni_ws_gethostbyname(const char *name, afni_ws_host *out);
int afni_ws_gethostbyaddr(const void *addr, int len, int type, afni_ws_host *out);

/* ready[i] receives 1 if socket i of each array is ready; the arrays may
   have zero length. timeout_us < 0 waits forever. */
int afni_ws_select(const uintptr_t *read_set, int read_count, int *read_ready,
                   const uintptr_t *write_set, int write_count, int *write_ready,
                   const uintptr_t *except_set, int except_count, int *except_ready,
                   long long timeout_us);

#endif
