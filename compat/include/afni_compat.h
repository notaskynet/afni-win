#ifndef AFNI_COMPAT_H
#define AFNI_COMPAT_H

/* src/winsock_bridge.c includes <winsock2.h> itself and must not see the
   POSIX declarations below (the toolchain forces this header everywhere). */
#ifndef AFNI_COMPAT_WINSOCK_BRIDGE

/*
 * Forced include for every translation unit of the Windows build
 * (-include afni_compat.h). It must be processed before any system header.
 *
 * Declarations of POSIX functions that belong to headers MinGW already ships
 * (stdlib.h, stdio.h, string.h, unistd.h, signal.h, sys/stat.h, sys/time.h)
 * live here, after the MinGW header is included. Headers MinGW does not ship
 * at all (sys/wait.h, sys/mman.h, pwd.h, ...) are separate replacement files
 * in this directory.
 */

#if !defined(_WIN32)
#error "afni_compat.h is only meant for Windows (MinGW-w64) builds"
#endif

#ifndef _FILE_OFFSET_BITS
#define _FILE_OFFSET_BITS 64
#endif

#if !defined(AFNI_COMPAT_BUILDING) && !defined(_WINSOCKAPI_)
#define _WINSOCKAPI_
#endif

#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <signal.h>
#include <fcntl.h>
#include <sys/types.h>
#include <sys/stat.h>
#include <sys/time.h>
#include <io.h>
#include <direct.h>
#include <process.h>
#include <unistd.h>

#include "afni_compat_api.h"

#ifdef __cplusplus
extern "C" {
#endif

AFNI_COMPAT_API void afni_compat_runtime(void);

typedef int uid_t;
typedef int gid_t;
typedef int key_t;

/* ---- AFNI machdep.h settings (no Windows branch exists upstream) ---- */

#define THD_MKDIR_MODE 0755
#define DYNAMIC_LOADING_VIA_DL
#define DYNAMIC_suffix ".dll"
#define DONT_USE_SHM
#define DONT_USE_FORK
#define READ_WRITE_64

/* ---- winsock.h is blocked above; upstream _WIN32 code includes it only for these ---- */

#if !defined(AFNI_COMPAT_BUILDING)
typedef uintptr_t SOCKET;
#define INVALID_SOCKET ((SOCKET)(~(uintptr_t)0))
#endif

/* ---- 64-bit file offsets: long is 32 bits on Windows ---- */

#define fseek _fseeki64
#define ftell _ftelli64

/* ---- stdlib.h ---- */

AFNI_COMPAT_API double drand48(void);
AFNI_COMPAT_API double erand48(unsigned short xsubi[3]);
AFNI_COMPAT_API long lrand48(void);
AFNI_COMPAT_API long nrand48(unsigned short xsubi[3]);
AFNI_COMPAT_API long mrand48(void);
AFNI_COMPAT_API long jrand48(unsigned short xsubi[3]);
AFNI_COMPAT_API void srand48(long seedval);
AFNI_COMPAT_API unsigned short *seed48(unsigned short seed16v[3]);
AFNI_COMPAT_API void lcong48(unsigned short param[7]);

AFNI_COMPAT_API char *realpath(const char *path, char *resolved_path);

/* ---- stdio.h / stdlib.h: commands run through a POSIX shell ---- */

AFNI_COMPAT_API FILE *afni_compat_popen(const char *command, const char *mode);
AFNI_COMPAT_API int afni_compat_pclose(FILE *stream);
AFNI_COMPAT_API int afni_compat_system(const char *command);

/* Not POSIX: starts "sh -c command" like system() but does not wait; the
   child is reaped with wait()/waitpid(). Returns 0 or an errno value. Used
   where upstream runs system() in a fork()ed child (patches/0010). */
AFNI_COMPAT_API int afni_compat_spawn_shell(pid_t *pid, const char *command);

/* ---- string.h ---- */

AFNI_COMPAT_API char *strcasestr(const char *haystack, const char *needle);

/* ---- sys/stat.h ---- */

#ifndef S_IFLNK
#define S_IFLNK 0xA000
#endif
#ifndef S_ISLNK
#define S_ISLNK(m) (((m) & S_IFMT) == S_IFLNK)
#endif

AFNI_COMPAT_API int lstat(const char *path, struct stat *buf);
AFNI_COMPAT_API int afni_compat_mkdir(const char *path, mode_t mode);

/* ---- sys/time.h ---- */

#define ITIMER_REAL 0
#define ITIMER_VIRTUAL 1
#define ITIMER_PROF 2

struct itimerval {
  struct timeval it_interval;
  struct timeval it_value;
};

AFNI_COMPAT_API int setitimer(int which, const struct itimerval *new_value,
                              struct itimerval *old_value);

/* ---- unistd.h ---- */

#define _SC_PAGESIZE 30
#define _SC_PAGE_SIZE _SC_PAGESIZE
#define _SC_NPROCESSORS_CONF 83
#define _SC_NPROCESSORS_ONLN 84
#define _SC_PHYS_PAGES 85
#define _SC_AVPHYS_PAGES 86

AFNI_COMPAT_API long sysconf(int name);
AFNI_COMPAT_API ssize_t readlink(const char *path, char *buf, size_t bufsiz);
AFNI_COMPAT_API uid_t getuid(void);
AFNI_COMPAT_API uid_t geteuid(void);
AFNI_COMPAT_API pid_t getppid(void);
AFNI_COMPAT_API int fsync(int fd);
AFNI_COMPAT_API int pause(void);
AFNI_COMPAT_API int gethostname(char *name, size_t len);
AFNI_COMPAT_API int nice(int inc);

/* ---- fcntl.h ---- */

#define F_GETFL 3
#define F_SETFL 4
#define F_SETOWN 8
#define O_NONBLOCK 0x100000
#define O_NDELAY O_NONBLOCK

AFNI_COMPAT_API int fcntl(int fd, int cmd, ...);

/* close() that also closes sockets (see sys/socket.h). Consumers declare it
   without dllimport (the import library thunk is used), because upstream
   f2c/rawio.h redeclares close() itself. */
#if defined(AFNI_COMPAT_BUILDING)
AFNI_COMPAT_API int afni_compat_close(int fd);
#else
int afni_compat_close(int fd);
#endif

/* ---- sys/file.h ---- */

#define LOCK_SH 1
#define LOCK_EX 2
#define LOCK_NB 4
#define LOCK_UN 8

AFNI_COMPAT_API int flock(int fd, int operation);

/* ---- signal.h: signals that Windows does not define ---- */

#ifndef SIGHUP
#define SIGHUP 1
#endif
#ifndef SIGQUIT
#define SIGQUIT 3
#endif
#ifndef SIGTRAP
#define SIGTRAP 5
#endif
#ifndef SIGBUS
#define SIGBUS 7
#endif
#ifndef SIGKILL
#define SIGKILL 9
#endif
#ifndef SIGUSR1
#define SIGUSR1 10
#endif
#ifndef SIGUSR2
#define SIGUSR2 12
#endif
#ifndef SIGPIPE
#define SIGPIPE 13
#endif
#ifndef SIGALRM
#define SIGALRM 14
#endif
#ifndef SIGCHLD
#define SIGCHLD 17
#endif
#ifndef SIGURG
#define SIGURG 23
#endif
#ifndef SIGIOT
#define SIGIOT SIGABRT
#endif

typedef void (*afni_compat_sighandler_t)(int);

AFNI_COMPAT_API afni_compat_sighandler_t afni_compat_signal(int sig,
                                                            afni_compat_sighandler_t handler);
AFNI_COMPAT_API int kill(pid_t pid, int sig);

#ifdef __cplusplus
}
#endif

#include <sys/select.h>
#include <sys/mman.h>

#define THD_MMAP_FLAG MAP_SHARED

/* ---- Redirections of functions MinGW declares with other semantics ---- */

#if !defined(AFNI_COMPAT_BUILDING)
#define signal(sig, handler) afni_compat_signal((sig), (handler))
/* mkdir(path, mode) is POSIX; mkdir(path) is the Windows form that upstream
   C++ code (dcm2niix) uses in its own _WIN32 branches. */
#define AFNI_COMPAT_MKDIR_SELECT(_1, _2, name, ...) name
#define mkdir(...) AFNI_COMPAT_MKDIR_SELECT(__VA_ARGS__, afni_compat_mkdir, _mkdir)(__VA_ARGS__)
#undef popen
#undef pclose
#define popen(command, mode) afni_compat_popen((command), (mode))
#define pclose(stream) afni_compat_pclose(stream)
#define system(command) afni_compat_system(command)
#ifndef __cplusplus
#define close(fd) afni_compat_close(fd)
#endif
#endif

#endif /* AFNI_COMPAT_WINSOCK_BRIDGE */

#endif
