#include <stdlib.h>

#include "test_common.h"

typedef struct {
  long seed;
  double d0;
  double d1;
  long l;
  long m;
} seeded_case;

static const seeded_case seeded[] = {
    {0L, 0x1.5ddb16e28808p-3, 0x1.7ff32702c6fp-1, 206956554, -556347614},
    {1L, 0x1.5509292a202p-5, 0x1.d16677a98dep-2, 1792756325, 1443049011},
    {12345L, 0x1.cd79090a8808p-3, 0x1.d69f29c4c6fp-1, 444188209, -1182062101},
    {-1L, 0x1.3339f1bd4404p-2, 0x1.7331230c6fp-5, 768640432, 1739223057},
    {2147483647L, 0x1.999cf8dea202p-1, 0x1.17331230c6fp-1, 1842382256, -408260591},
    {1234567890L, 0x1.f976848ca202p-1, 0x1.02b9df46c6fp-1, 269241159, -2031031020},
};

int main(void) {
  CHECK(mrand48() == 0);
  CHECK(lrand48() == 2116118);
  CHECK(drand48() == 0x1.550a89cb27ap-5);

  for (size_t i = 0; i < sizeof(seeded) / sizeof(seeded[0]); ++i) {
    srand48(seeded[i].seed);
    CHECK(drand48() == seeded[i].d0);
    CHECK(drand48() == seeded[i].d1);
    CHECK(lrand48() == seeded[i].l);
    CHECK(mrand48() == seeded[i].m);
  }

  {
    unsigned short x[3] = {0x1234, 0x5678, 0x9abc};
    CHECK(erand48(x) == 0x1.257a45a9e0bcp-2);
    CHECK(nrand48(x) == 2006585297);
    CHECK(jrand48(x) == -1996062933);
    CHECK(x[0] == 2049 && x[1] == 32555 && x[2] == 35078);
  }

  {
    unsigned short seed[3] = {1, 2, 3};
    unsigned short *old;
    srand48(99);
    old = seed48(seed);
    CHECK(old[0] == 13070 && old[1] == 99 && old[2] == 0);
    CHECK(drand48() == 0x1.c49aaf1b99ep-2);
  }

  {
    unsigned short param[7] = {1, 2, 3, 5, 0, 0, 7};
    lcong48(param);
    CHECK(drand48() == 0x1.e00140018p-13);
    CHECK(lrand48() == 2457625);
  }

  {
    double sum = 0.0;
    srand48(42);
    for (int i = 0; i < 100000; ++i) {
      sum += drand48();
    }
    CHECK(sum == 0x1.852fc9a336ad5p+15);
    CHECK(lrand48() == 885389225);
  }

  return TEST_RESULT();
}
