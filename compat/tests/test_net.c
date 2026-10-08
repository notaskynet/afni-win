#include <arpa/inet.h>
#include <fcntl.h>
#include <netdb.h>
#include <netinet/in.h>
#include <netinet/tcp.h>
#include <sys/select.h>
#include <sys/socket.h>
#include <unistd.h>

#include "test_common.h"

static int listening_socket(struct sockaddr_in *addr) {
  int bound = 0;
  int optval = 1;
  struct linger lg = {1, 2};
  struct linger back = {0, 0};
  socklen_t back_length = sizeof(back);
  int sd = socket(AF_INET, SOCK_STREAM, 0);

  CHECK(sd >= 0);
  CHECK(setsockopt(sd, SOL_SOCKET, SO_REUSEADDR, (char *)&optval, sizeof(optval)) == 0);
  CHECK(setsockopt(sd, SOL_SOCKET, SO_LINGER, (void *)&lg, sizeof(lg)) == 0);
  CHECK(getsockopt(sd, SOL_SOCKET, SO_LINGER, (void *)&back, &back_length) == 0);
  CHECK(back.l_onoff == 1 && back.l_linger == 2 && back_length == sizeof(back));
  memset(addr, 0, sizeof(*addr));
  addr->sin_family = AF_INET;
  addr->sin_addr.s_addr = htonl(INADDR_LOOPBACK);
  for (int port = 23456; port < 23556 && !bound; ++port) {
    addr->sin_port = htons(port);
    bound = bind(sd, (struct sockaddr *)addr, sizeof(*addr)) == 0;
  }
  CHECK(bound);
  CHECK(listen(sd, 1) == 0);
  return sd;
}

int main(void) {
  struct in_addr in;
  struct sockaddr_in addr;
  struct sockaddr_in peer;
  socklen_t peer_length = sizeof(peer);
  struct hostent *host;
  struct timeval tv;
  fd_set rfds;
  fd_set wfds;
  char buffer[16];
  int server;
  int client;
  int conn;
  int l = 1;
  int q = 0;
  socklen_t qq = sizeof(q);
  int file_fd;

  CHECK(htons(0x1234) == 0x3412);
  CHECK(ntohs(htons(0xBEEF)) == 0xBEEF);
  CHECK(htonl(0x01020304u) == 0x04030201u);
  CHECK(ntohl(htonl(0xDEADBEEFu)) == 0xDEADBEEFu);
  in.s_addr = htonl(0xC0A80001u);
  CHECK(strcmp(inet_ntoa(in), "192.168.0.1") == 0);
  CHECK(sizeof(struct sockaddr_in) == 16);

  host = gethostbyname("localhost");
  CHECK(host != NULL);
  if (host != NULL) {
    CHECK(host->h_addrtype == AF_INET && host->h_length == 4);
    CHECK(strcmp(inet_ntoa(*((struct in_addr *)(host->h_addr))), "127.0.0.1") == 0);
  }

  server = listening_socket(&addr);
  client = socket(AF_INET, SOCK_STREAM, 0);
  CHECK(client >= 0 && client != server);
  CHECK(setsockopt(client, IPPROTO_TCP, TCP_NODELAY, (void *)&l, sizeof(int)) == 0);
  CHECK(getsockopt(client, SOL_SOCKET, SO_SNDBUF, (void *)&q, &qq) == 0 && q > 0);

  FD_ZERO(&rfds);
  FD_SET(server, &rfds);
  tv.tv_sec = 0;
  tv.tv_usec = 0;
  CHECK(select(server + 1, &rfds, NULL, NULL, &tv) == 0);
  CHECK(!FD_ISSET(server, &rfds));

  CHECK(connect(client, (struct sockaddr *)&addr, sizeof(addr)) == 0);
  FD_ZERO(&rfds);
  FD_SET(server, &rfds);
  tv.tv_sec = 5;
  CHECK(select(server + 1, &rfds, NULL, NULL, &tv) == 1);
  CHECK(FD_ISSET(server, &rfds));
  conn = accept(server, (struct sockaddr *)&peer, &peer_length);
  CHECK(conn >= 0);
  CHECK(strcmp(inet_ntoa(peer.sin_addr), "127.0.0.1") == 0);

  FD_ZERO(&wfds);
  FD_SET(client, &wfds);
  CHECK(select(client + 1, NULL, &wfds, NULL, &tv) == 1 && FD_ISSET(client, &wfds));
  CHECK(send(client, "hello", 5, 0) == 5);
  FD_ZERO(&rfds);
  FD_SET(conn, &rfds);
  CHECK(select(conn + 1, &rfds, NULL, NULL, &tv) == 1 && FD_ISSET(conn, &rfds));
  CHECK(recv(conn, buffer, 1, MSG_PEEK) == 1 && buffer[0] == 'h');
  CHECK(recv(conn, buffer, sizeof(buffer), 0) == 5 && memcmp(buffer, "hello", 5) == 0);
  CHECK(write(conn, "via write", 9) == 9);
  CHECK(read(client, buffer, 9) == 9 && memcmp(buffer, "via write", 9) == 0);

  CHECK(fcntl(conn, F_GETFL) == O_RDWR);
  CHECK(fcntl(conn, F_SETFL, O_NONBLOCK) == 0);
  CHECK((fcntl(conn, F_GETFL) & O_NONBLOCK) != 0);
  CHECK_ERRNO(recv(conn, buffer, sizeof(buffer), 0), EWOULDBLOCK);
  CHECK(fcntl(conn, F_SETOWN, 1234) == 0);
  CHECK(fcntl(conn, F_SETFL, 0) == 0);
  CHECK(fcntl(conn, F_GETFL) == O_RDWR);
  CHECK_ERRNO(fcntl(conn, 99), EINVAL);

  CHECK(shutdown(client, SHUT_RDWR) == 0);
  CHECK(close(client) == 0);
  CHECK(recv(conn, buffer, sizeof(buffer), 0) == 0);
  CHECK(close(conn) == 0);
  CHECK(close(server) == 0);
  CHECK_ERRNO(send(server, "x", 1, 0), ENOTSOCK);

  client = socket(AF_INET, SOCK_STREAM, 0);
  CHECK(client >= 0);
  CHECK_ERRNO(connect(client, (struct sockaddr *)&addr, sizeof(addr)), ECONNREFUSED);
  CHECK(close(client) == 0);

  file_fd = open("compat_net_file.txt", O_CREAT | O_WRONLY, 0644);
  CHECK(file_fd >= 0);
  CHECK_ERRNO(send(file_fd, "x", 1, 0), ENOTSOCK);
  CHECK_ERRNO(fcntl(file_fd, F_GETFL), ENOSYS);
  FD_ZERO(&rfds);
  FD_SET(file_fd, &rfds);
  CHECK_ERRNO(select(file_fd + 1, &rfds, NULL, NULL, &tv), ENOSYS);
  CHECK(close(file_fd) == 0);
  remove("compat_net_file.txt");
  CHECK_ERRNO(fcntl(file_fd, F_GETFL), EBADF);
  CHECK(gethostbyname("no-such-host.invalid") == NULL);

  return TEST_RESULT();
}
