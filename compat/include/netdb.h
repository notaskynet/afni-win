#ifndef AFNI_COMPAT_NETDB_H
#define AFNI_COMPAT_NETDB_H

#include <netinet/in.h>

#include "afni_compat_api.h"

#ifdef __cplusplus
extern "C" {
#endif

struct hostent {
  char *h_name;
  char **h_aliases;
  int h_addrtype;
  int h_length;
  char **h_addr_list;
};

#define h_addr h_addr_list[0]

AFNI_COMPAT_API struct hostent *gethostbyname(const char *name);
AFNI_COMPAT_API struct hostent *gethostbyaddr(const void *addr, socklen_t len, int type);

#ifdef __cplusplus
}
#endif

#endif
