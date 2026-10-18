/* Standard RVV 1.0 intrinsics: use the actual VL returned by the VPU. */
#include <riscv_vector.h>
void strip_u32(unsigned *out,const unsigned *a,const unsigned *b,unsigned long n){
  while(n){size_t vl=__riscv_vsetvl_e32m1(n);
    vuint32m1_t x=__riscv_vle32_v_u32m1(a,vl),y=__riscv_vle32_v_u32m1(b,vl);
    __riscv_vse32_v_u32m1(out,__riscv_vadd_vv_u32m1(x,y,vl),vl);
    a+=vl;b+=vl;out+=vl;n-=vl;}
}
void strip_u8m8(unsigned char *out,const unsigned char *a,const unsigned char *b,unsigned long n){
  while(n){size_t vl=__riscv_vsetvl_e8m8(n);
    vuint8m8_t x=__riscv_vle8_v_u8m8(a,vl),y=__riscv_vle8_v_u8m8(b,vl);
    __riscv_vse8_v_u8m8(out,__riscv_vadd_vv_u8m8(x,y,vl),vl);
    a+=vl;b+=vl;out+=vl;n-=vl;}
}
void strip_f32(float *out,const float *a,const float *b,unsigned long n){
  while(n){size_t vl=__riscv_vsetvl_e32m1(n);
    vfloat32m1_t x=__riscv_vle32_v_f32m1(a,vl),y=__riscv_vle32_v_f32m1(b,vl);
    __riscv_vse32_v_f32m1(out,__riscv_vfadd_vv_f32m1(x,y,vl),vl);
    a+=vl;b+=vl;out+=vl;n-=vl;}
}
void strip_f64(double *out,const double *a,const double *b,unsigned long n){
  while(n){size_t vl=__riscv_vsetvl_e64m1(n);
    vfloat64m1_t x=__riscv_vle64_v_f64m1(a,vl),y=__riscv_vle64_v_f64m1(b,vl);
    __riscv_vse64_v_f64m1(out,__riscv_vfadd_vv_f64m1(x,y,vl),vl);
    a+=vl;b+=vl;out+=vl;n-=vl;}
}
unsigned long fof_copy(unsigned char *out,const unsigned char *a,const unsigned char *unused,unsigned long n){
  (void)unused;
  size_t actual;
  vuint8m8_t x=__riscv_vle8ff_v_u8m8(a,&actual,n);
  __riscv_vse8_v_u8m8(out,x,actual);
  return actual;
}
