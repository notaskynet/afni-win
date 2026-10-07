#ifndef AFNI_COMPAT_API_H
#define AFNI_COMPAT_API_H

#if defined(AFNI_COMPAT_BUILDING)
#define AFNI_COMPAT_API __declspec(dllexport)
#else
#define AFNI_COMPAT_API __declspec(dllimport)
#endif

#endif
