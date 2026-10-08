#define FD_SETSIZE 1024
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#include <winsock2.h>
#include <windows.h>

#include <errno.h>
#include <stdlib.h>

#include "winsock_bridge.h"

/* Winsock is loaded with GetProcAddress: linking ws2_32 would pull its
   import thunks named socket, bind, send, ... next to the layer's own
   POSIX functions with the same names. */

typedef int(WSAAPI *startup_fn)(WORD, LPWSADATA);
typedef int(WSAAPI *last_error_fn)(void);
typedef SOCKET(WSAAPI *socket_fn)(int, int, int, LPWSAPROTOCOL_INFOW, GROUP, DWORD);
typedef int(WSAAPI *close_fn)(SOCKET);
typedef int(WSAAPI *bind_fn)(SOCKET, const struct sockaddr *, int);
typedef int(WSAAPI *listen_fn)(SOCKET, int);
typedef SOCKET(WSAAPI *accept_fn)(SOCKET, struct sockaddr *, int *);
typedef int(WSAAPI *send_fn)(SOCKET, const char *, int, int);
typedef int(WSAAPI *recv_fn)(SOCKET, char *, int, int);
typedef int(WSAAPI *setsockopt_fn)(SOCKET, int, int, const char *, int);
typedef int(WSAAPI *getsockopt_fn)(SOCKET, int, int, char *, int *);
typedef int(WSAAPI *shutdown_fn)(SOCKET, int);
typedef int(WSAAPI *ioctl_fn)(SOCKET, long, u_long *);
typedef struct hostent *(WSAAPI *byname_fn)(const char *);
typedef struct hostent *(WSAAPI *byaddr_fn)(const char *, int, int);
typedef int(WSAAPI *select_fn)(int, fd_set *, fd_set *, fd_set *, const struct timeval *);

static struct {
  startup_fn startup;
  last_error_fn last_error;
  socket_fn socket;
  close_fn close;
  bind_fn bind;
  listen_fn listen;
  accept_fn accept;
  bind_fn connect;
  send_fn send;
  recv_fn recv;
  setsockopt_fn setsockopt;
  getsockopt_fn getsockopt;
  shutdown_fn shutdown;
  ioctl_fn ioctl;
  byname_fn gethostbyname;
  byaddr_fn gethostbyaddr;
  select_fn select;
} ws;

static INIT_ONCE startup_once = INIT_ONCE_STATIC_INIT;
static int startup_error = 0;

typedef void (*any_fn)(void);

static any_fn load(HMODULE module, const char *name, int *missing) {
  FARPROC address = GetProcAddress(module, name);
  if (address == NULL) {
    *missing = 1;
  }
  return (any_fn)(void *)address;
}

static void set_errno_from_wsa(int error) {
  switch (error) {
    case WSAEINTR:
      errno = EINTR;
      break;
    case WSAEBADF:
    case WSAENOTSOCK:
      errno = error == WSAEBADF ? EBADF : ENOTSOCK;
      break;
    case WSAEACCES:
      errno = EACCES;
      break;
    case WSAEFAULT:
      errno = EFAULT;
      break;
    case WSAEINVAL:
      errno = EINVAL;
      break;
    case WSAEMFILE:
      errno = EMFILE;
      break;
    case WSAEWOULDBLOCK:
      errno = EWOULDBLOCK;
      break;
    case WSAEINPROGRESS:
      errno = EINPROGRESS;
      break;
    case WSAEALREADY:
      errno = EALREADY;
      break;
    case WSAEDESTADDRREQ:
      errno = EDESTADDRREQ;
      break;
    case WSAEMSGSIZE:
      errno = EMSGSIZE;
      break;
    case WSAEPROTOTYPE:
      errno = EPROTOTYPE;
      break;
    case WSAENOPROTOOPT:
      errno = ENOPROTOOPT;
      break;
    case WSAEPROTONOSUPPORT:
    case WSAESOCKTNOSUPPORT:
      errno = EPROTONOSUPPORT;
      break;
    case WSAEOPNOTSUPP:
      errno = EOPNOTSUPP;
      break;
    case WSAEAFNOSUPPORT:
    case WSAEPFNOSUPPORT:
      errno = EAFNOSUPPORT;
      break;
    case WSAEADDRINUSE:
      errno = EADDRINUSE;
      break;
    case WSAEADDRNOTAVAIL:
      errno = EADDRNOTAVAIL;
      break;
    case WSAENETDOWN:
      errno = ENETDOWN;
      break;
    case WSAENETUNREACH:
      errno = ENETUNREACH;
      break;
    case WSAENETRESET:
      errno = ENETRESET;
      break;
    case WSAECONNABORTED:
      errno = ECONNABORTED;
      break;
    case WSAECONNRESET:
      errno = ECONNRESET;
      break;
    case WSAENOBUFS:
      errno = ENOBUFS;
      break;
    case WSAEISCONN:
      errno = EISCONN;
      break;
    case WSAENOTCONN:
      errno = ENOTCONN;
      break;
    case WSAESHUTDOWN:
      errno = EPIPE;
      break;
    case WSAETIMEDOUT:
      errno = ETIMEDOUT;
      break;
    case WSAECONNREFUSED:
      errno = ECONNREFUSED;
      break;
    case WSAEHOSTDOWN:
    case WSAEHOSTUNREACH:
      errno = EHOSTUNREACH;
      break;
    case WSAHOST_NOT_FOUND:
    case WSANO_DATA:
      errno = ENOENT;
      break;
    case WSATRY_AGAIN:
      errno = EAGAIN;
      break;
    case WSANOTINITIALISED:
    case WSASYSNOTREADY:
    case WSAVERNOTSUPPORTED:
      errno = ENOSYS;
      break;
    default:
      errno = EIO;
      break;
  }
}

static int fail(void) {
  set_errno_from_wsa(ws.last_error());
  return -1;
}

static BOOL CALLBACK startup_callback(PINIT_ONCE once, PVOID parameter, PVOID *context) {
  WSADATA data;
  HMODULE module = LoadLibraryA("ws2_32.dll");
  int missing = 0;
  (void)once;
  (void)parameter;
  (void)context;
  if (module == NULL) {
    startup_error = WSASYSNOTREADY;
    return TRUE;
  }
  ws.startup = (startup_fn)load(module, "WSAStartup", &missing);
  ws.last_error = (last_error_fn)load(module, "WSAGetLastError", &missing);
  ws.socket = (socket_fn)load(module, "WSASocketW", &missing);
  ws.close = (close_fn)load(module, "closesocket", &missing);
  ws.bind = (bind_fn)load(module, "bind", &missing);
  ws.listen = (listen_fn)load(module, "listen", &missing);
  ws.accept = (accept_fn)load(module, "accept", &missing);
  ws.connect = (bind_fn)load(module, "connect", &missing);
  ws.send = (send_fn)load(module, "send", &missing);
  ws.recv = (recv_fn)load(module, "recv", &missing);
  ws.setsockopt = (setsockopt_fn)load(module, "setsockopt", &missing);
  ws.getsockopt = (getsockopt_fn)load(module, "getsockopt", &missing);
  ws.shutdown = (shutdown_fn)load(module, "shutdown", &missing);
  ws.ioctl = (ioctl_fn)load(module, "ioctlsocket", &missing);
  ws.gethostbyname = (byname_fn)load(module, "gethostbyname", &missing);
  ws.gethostbyaddr = (byaddr_fn)load(module, "gethostbyaddr", &missing);
  ws.select = (select_fn)load(module, "select", &missing);
  if (missing) {
    startup_error = WSASYSNOTREADY;
    return TRUE;
  }
  startup_error = ws.startup(MAKEWORD(2, 2), &data);
  return TRUE;
}

int afni_ws_startup(void) {
  InitOnceExecuteOnce(&startup_once, startup_callback, NULL, NULL);
  if (startup_error != 0) {
    set_errno_from_wsa(startup_error);
    return -1;
  }
  return 0;
}

uintptr_t afni_ws_socket(int domain, int type, int protocol) {
  SOCKET s;
  if (afni_ws_startup() != 0) {
    return AFNI_WS_INVALID;
  }
  s = ws.socket(domain, type, protocol, NULL, 0, WSA_FLAG_NO_HANDLE_INHERIT);
  if (s == INVALID_SOCKET) {
    fail();
    return AFNI_WS_INVALID;
  }
  return (uintptr_t)s;
}

int afni_ws_close(uintptr_t s) {
  return ws.close((SOCKET)s) == 0 ? 0 : fail();
}

int afni_ws_bind(uintptr_t s, const void *addr, int addrlen) {
  return ws.bind((SOCKET)s, (const struct sockaddr *)addr, addrlen) == 0 ? 0 : fail();
}

int afni_ws_listen(uintptr_t s, int backlog) {
  return ws.listen((SOCKET)s, backlog) == 0 ? 0 : fail();
}

uintptr_t afni_ws_accept(uintptr_t s, void *addr, int *addrlen) {
  SOCKET client = ws.accept((SOCKET)s, (struct sockaddr *)addr, addrlen);
  if (client == INVALID_SOCKET) {
    fail();
    return AFNI_WS_INVALID;
  }
  SetHandleInformation((HANDLE)client, HANDLE_FLAG_INHERIT, 0);
  return (uintptr_t)client;
}

int afni_ws_connect(uintptr_t s, const void *addr, int addrlen) {
  return ws.connect((SOCKET)s, (const struct sockaddr *)addr, addrlen) == 0 ? 0 : fail();
}

int afni_ws_send(uintptr_t s, const void *buf, int len, int flags) {
  int n = ws.send((SOCKET)s, (const char *)buf, len, flags);
  return n == SOCKET_ERROR ? fail() : n;
}

int afni_ws_recv(uintptr_t s, void *buf, int len, int flags) {
  int n = ws.recv((SOCKET)s, (char *)buf, len, flags);
  return n == SOCKET_ERROR ? fail() : n;
}

int afni_ws_setsockopt(uintptr_t s, int level, int name, const void *value, int length) {
  return ws.setsockopt((SOCKET)s, level, name, (const char *)value, length) == 0 ? 0 : fail();
}

int afni_ws_getsockopt(uintptr_t s, int level, int name, void *value, int *length) {
  return ws.getsockopt((SOCKET)s, level, name, (char *)value, length) == 0 ? 0 : fail();
}

int afni_ws_shutdown(uintptr_t s, int how) {
  return ws.shutdown((SOCKET)s, how) == 0 ? 0 : fail();
}

int afni_ws_set_nonblocking(uintptr_t s, int enable) {
  u_long mode = enable ? 1UL : 0UL;
  return ws.ioctl((SOCKET)s, FIONBIO, &mode) == 0 ? 0 : fail();
}

static int copy_host(const struct hostent *host, afni_ws_host *out) {
  if (host == NULL) {
    return fail();
  }
  out->name = host->h_name;
  out->aliases = host->h_aliases;
  out->addrtype = host->h_addrtype;
  out->length = host->h_length;
  out->addr_list = host->h_addr_list;
  return 0;
}

int afni_ws_gethostbyname(const char *name, afni_ws_host *out) {
  if (afni_ws_startup() != 0) {
    return -1;
  }
  return copy_host(ws.gethostbyname(name), out);
}

int afni_ws_gethostbyaddr(const void *addr, int len, int type, afni_ws_host *out) {
  if (afni_ws_startup() != 0) {
    return -1;
  }
  return copy_host(ws.gethostbyaddr((const char *)addr, len, type), out);
}

static void fill(fd_set *set, const uintptr_t *sockets, int count) {
  set->fd_count = 0;
  for (int i = 0; i < count; ++i) {
    set->fd_array[set->fd_count++] = (SOCKET)sockets[i];
  }
}

static void mark(const fd_set *set, const uintptr_t *sockets, int count, int *ready) {
  for (int i = 0; i < count; ++i) {
    ready[i] = 0;
    for (u_int j = 0; j < set->fd_count; ++j) {
      if (set->fd_array[j] == (SOCKET)sockets[i]) {
        ready[i] = 1;
        break;
      }
    }
  }
}

int afni_ws_select(const uintptr_t *read_set, int read_count, int *read_ready,
                   const uintptr_t *write_set, int write_count, int *write_ready,
                   const uintptr_t *except_set, int except_count, int *except_ready,
                   long long timeout_us) {
  fd_set *sets = (fd_set *)malloc(3 * sizeof(fd_set));
  struct timeval tv;
  int result;

  if (sets == NULL) {
    errno = ENOMEM;
    return -1;
  }
  fill(&sets[0], read_set, read_count);
  fill(&sets[1], write_set, write_count);
  fill(&sets[2], except_set, except_count);
  if (timeout_us >= 0) {
    tv.tv_sec = (long)(timeout_us / 1000000);
    tv.tv_usec = (long)(timeout_us % 1000000);
  }
  result = ws.select(0, read_count > 0 ? &sets[0] : NULL, write_count > 0 ? &sets[1] : NULL,
                  except_count > 0 ? &sets[2] : NULL, timeout_us >= 0 ? &tv : NULL);
  if (result == SOCKET_ERROR) {
    free(sets);
    return fail();
  }
  mark(&sets[0], read_set, read_count, read_ready);
  mark(&sets[1], write_set, write_count, write_ready);
  mark(&sets[2], except_set, except_count, except_ready);
  free(sets);
  return result;
}
