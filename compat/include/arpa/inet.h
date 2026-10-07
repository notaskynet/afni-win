#ifndef AFNI_COMPAT_ARPA_INET_H
#define AFNI_COMPAT_ARPA_INET_H

#include <netinet/in.h>

#include "afni_compat_api.h"

#ifdef __cplusplus
extern "C" {
#endif

AFNI_COMPAT_API char *inet_ntoa(struct in_addr in);

#ifdef __cplusplus
}
#endif

#endif
