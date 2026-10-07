#include <arpa/inet.h>
#include <netdb.h>
#include <netinet/in.h>
#include <netinet/tcp.h>
#include <sys/socket.h>

#include "test_common.h"

int main(void) {
  struct in_addr addr;
  struct sockaddr_in sin;

  CHECK(htons(0x1234) == 0x3412);
  CHECK(ntohs(htons(0xBEEF)) == 0xBEEF);
  CHECK(htonl(0x01020304u) == 0x04030201u);
  CHECK(ntohl(htonl(0xDEADBEEFu)) == 0xDEADBEEFu);

  addr.s_addr = htonl(0xC0A80001u);
  CHECK(strcmp(inet_ntoa(addr), "192.168.0.1") == 0);
  addr.s_addr = htonl(INADDR_LOOPBACK);
  CHECK(strcmp(inet_ntoa(addr), "127.0.0.1") == 0);

  CHECK(sizeof(struct sockaddr_in) == 16);
  memset(&sin, 0, sizeof(sin));
  CHECK_ERRNO(socket(AF_INET, SOCK_STREAM, 0), ENOSYS);
  CHECK_ERRNO(connect(3, (struct sockaddr *)&sin, sizeof(sin)), ENOSYS);
  CHECK_ERRNO(gethostbyname("localhost"), ENOSYS);
  CHECK(gethostbyname("localhost") == NULL);

  return TEST_RESULT();
}
