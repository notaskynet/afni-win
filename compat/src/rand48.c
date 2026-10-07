#include <stdint.h>
#include <stdlib.h>

#define RAND48_MASK ((UINT64_C(1) << 48) - 1)
#define RAND48_DEFAULT_A UINT64_C(0x5DEECE66D)
#define RAND48_DEFAULT_C UINT64_C(0xB)

static unsigned short rand48_x[3];
static unsigned short rand48_old_x[3];
static uint64_t rand48_a = RAND48_DEFAULT_A;
static uint64_t rand48_c = RAND48_DEFAULT_C;

static uint64_t rand48_load(const unsigned short x[3]) {
  return (uint64_t)x[0] | ((uint64_t)x[1] << 16) | ((uint64_t)x[2] << 32);
}

static void rand48_store(unsigned short x[3], uint64_t value) {
  x[0] = (unsigned short)(value & 0xffff);
  x[1] = (unsigned short)((value >> 16) & 0xffff);
  x[2] = (unsigned short)((value >> 32) & 0xffff);
}

static uint64_t rand48_step(unsigned short x[3]) {
  uint64_t next = (rand48_load(x) * rand48_a + rand48_c) & RAND48_MASK;
  rand48_store(x, next);
  return next;
}

double erand48(unsigned short xsubi[3]) {
  return (double)rand48_step(xsubi) / (double)(UINT64_C(1) << 48);
}

double drand48(void) {
  return erand48(rand48_x);
}

long nrand48(unsigned short xsubi[3]) {
  return (long)(rand48_step(xsubi) >> 17);
}

long lrand48(void) {
  return nrand48(rand48_x);
}

long jrand48(unsigned short xsubi[3]) {
  return (long)(int32_t)(uint32_t)(rand48_step(xsubi) >> 16);
}

long mrand48(void) {
  return jrand48(rand48_x);
}

void srand48(long seedval) {
  uint32_t seed = (uint32_t)seedval;
  rand48_x[0] = 0x330E;
  rand48_x[1] = (unsigned short)(seed & 0xffff);
  rand48_x[2] = (unsigned short)(seed >> 16);
  rand48_a = RAND48_DEFAULT_A;
  rand48_c = RAND48_DEFAULT_C;
}

unsigned short *seed48(unsigned short seed16v[3]) {
  rand48_old_x[0] = rand48_x[0];
  rand48_old_x[1] = rand48_x[1];
  rand48_old_x[2] = rand48_x[2];
  rand48_x[0] = seed16v[0];
  rand48_x[1] = seed16v[1];
  rand48_x[2] = seed16v[2];
  rand48_a = RAND48_DEFAULT_A;
  rand48_c = RAND48_DEFAULT_C;
  return rand48_old_x;
}

void lcong48(unsigned short param[7]) {
  rand48_x[0] = param[0];
  rand48_x[1] = param[1];
  rand48_x[2] = param[2];
  rand48_a = rand48_load(&param[3]);
  rand48_c = param[6];
}
