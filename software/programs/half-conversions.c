/* M54 minimal FP16 vector conversions; no scalar half arithmetic. */
#include <stddef.h>
#include <riscv_vector.h>
void spinor_half_to_float(float *dst,const _Float16 *src,size_t n) {
    while(n) {
        size_t vl=__riscv_vsetvl_e16m1(n);
        vfloat16m1_t h=__riscv_vle16_v_f16m1(src,vl);
        vfloat32m2_t f=__riscv_vfwcvt_f_f_v_f32m2(h,vl);
        __riscv_vse32_v_f32m2(dst,f,vl);
        src+=vl;dst+=vl;n-=vl;
    }
}
void spinor_float_to_half(_Float16 *dst,const float *src,size_t n) {
    while(n) {
        size_t vl=__riscv_vsetvl_e16m1(n);
        vfloat32m2_t f=__riscv_vle32_v_f32m2(src,vl);
        vfloat16m1_t h=__riscv_vfncvt_f_f_w_f16m1(f,vl);
        __riscv_vse16_v_f16m1(dst,h,vl);
        src+=vl;dst+=vl;n-=vl;
    }
}
