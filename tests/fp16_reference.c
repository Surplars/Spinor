#include <stdint.h>
#include "softfloat.h"
uint64_t spinor_half_reference(unsigned narrow, unsigned rm, uint32_t input, unsigned *flags) {
    softfloat_roundingMode=(uint_fast8_t)rm;
    softfloat_detectTininess=softfloat_tininess_afterRounding;
    softfloat_exceptionFlags=0;
    uint32_t result;
    if(narrow) {
        float32_t x={input};result=f32_to_f16(x).v;
        if((result&0x7fffu)>0x7c00u)result=0x7e00u;
    } else {
        float16_t x={(uint16_t)input};result=f16_to_f32(x).v;
        if((result&0x7fffffffu)>0x7f800000u)result=0x7fc00000u;
    }
    *flags=softfloat_exceptionFlags;return result;
}
