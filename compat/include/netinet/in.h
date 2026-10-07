#ifndef AFNI_COMPAT_NETINET_IN_H
#define AFNI_COMPAT_NETINET_IN_H

#include <stdint.h>
#include <sys/socket.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef uint32_t in_addr_t;
typedef uint16_t in_port_t;

struct in_addr {
  in_addr_t s_addr;
};

struct sockaddr_in {
  sa_family_t sin_family;
  in_port_t sin_port;
  struct in_addr sin_addr;
  unsigned char sin_zero[8];
};

#define IPPROTO_IP 0
#define IPPROTO_TCP 6

#define INADDR_ANY ((in_addr_t)0x00000000)
#define INADDR_LOOPBACK ((in_addr_t)0x7f000001)
#define INADDR_NONE ((in_addr_t)0xffffffff)

static inline uint16_t afni_compat_bswap16(uint16_t x) {
  return (uint16_t)((x >> 8) | (x << 8));
}

static inline uint32_t afni_compat_bswap32(uint32_t x) {
  return ((x >> 24) & 0xffu) | ((x >> 8) & 0xff00u) | ((x << 8) & 0xff0000u) | (x << 24);
}

#define htons(x) afni_compat_bswap16((uint16_t)(x))
#define ntohs(x) afni_compat_bswap16((uint16_t)(x))
#define htonl(x) afni_compat_bswap32((uint32_t)(x))
#define ntohl(x) afni_compat_bswap32((uint32_t)(x))

#ifdef __cplusplus
}
#endif

#endif
