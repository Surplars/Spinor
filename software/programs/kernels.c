/* Freestanding C: no vector intrinsics, assembly, runtime, or expected results. */
#define ADD(T,N) __attribute__((noinline)) void add_##N(T *restrict out,const T *restrict a,const T *restrict b,unsigned long n){for(unsigned long i=0;i<n;i++)out[i]=a[i]+b[i];}
ADD(unsigned char,u8)
ADD(unsigned short,u16)
ADD(unsigned int,u32)
ADD(unsigned long,u64)
__attribute__((noinline)) void macc_u32(unsigned *restrict out,const unsigned *restrict a,const unsigned *restrict b,unsigned long n){for(unsigned long i=0;i<n;i++)out[i]=a[i]*7u+b[i];}
__attribute__((noinline)) void clamp_i32(int *restrict out,const int *restrict a,const int *restrict b,unsigned long n){(void)b;for(unsigned long i=0;i<n;i++){int x=a[i];out[i]=x < -37 ? -37 : x > 91 ? 91 : x;}}
__attribute__((noinline)) void select_u32(unsigned *restrict out,const unsigned *restrict a,const unsigned *restrict b,unsigned long n){for(unsigned long i=0;i<n;i++)out[i]=a[i]>0x7fffffffu?a[i]+b[i]:b[i]^0x13579bdfu;}
__attribute__((noinline)) unsigned sum_u32(unsigned *out,const unsigned *a,const unsigned *b,unsigned long n){(void)out;(void)b;unsigned s=0;for(unsigned long i=0;i<n;i++)s+=a[i];return s;}
__attribute__((noinline)) unsigned dot_i16(unsigned *out,const short *a,const short *b,unsigned long n){(void)out;unsigned s=0;for(unsigned long i=0;i<n;i++)s+=(unsigned)((int)a[i]*(int)b[i]);return s;}
__attribute__((noinline)) void gather_u32(unsigned *restrict out,const unsigned *restrict a,const unsigned *restrict indices,unsigned long n){for(unsigned long i=0;i<n;i++)out[i]=a[indices[i]];}
__attribute__((noinline)) void aos2_u32(unsigned *restrict out,const unsigned *restrict a,const unsigned *unused,unsigned long n){(void)unused;for(unsigned long i=0;i<n;i++)out[i]=a[2*i]+a[2*i+1];}
__attribute__((noinline)) void sar_i32(int *restrict out,const int *restrict a,const unsigned *restrict b,unsigned long n){for(unsigned long i=0;i<n;i++)out[i]=a[i]>>(b[i]&31);}
/* Inputs deliberately exclude C's divide-by-zero and INT_MIN/-1 UB cases. */
__attribute__((noinline)) void quotrem_i32(int *restrict out,const int *restrict a,const int *restrict b,unsigned long n){for(unsigned long i=0;i<n;i++)out[i]=a[i]/b[i]+a[i]%b[i];}
