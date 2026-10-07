#ifndef AFNI_COMPAT_PWD_H
#define AFNI_COMPAT_PWD_H

#include <sys/types.h>

#include "afni_compat_api.h"

#ifdef __cplusplus
extern "C" {
#endif

struct passwd {
  char *pw_name;
  char *pw_passwd;
  uid_t pw_uid;
  gid_t pw_gid;
  char *pw_gecos;
  char *pw_dir;
  char *pw_shell;
};

AFNI_COMPAT_API struct passwd *getpwuid(uid_t uid);

#ifdef __cplusplus
}
#endif

#endif
