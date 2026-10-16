/* Independent numerical oracle: Berkeley SoftFloat, not HardFloat equations.
 * IDs below are test-file data, not RTL decode constants. Inputs are unboxed
 * IEEE vector elements; RISC-V canonical NaNs and flag semantics are explicit.
 */
#include <stdint.h>
#include <stdbool.h>
#include "softfloat.h"

static bool is_nan_bits(uint64_t x,int d) { return d ? (x&UINT64_C(0x7fffffffffffffff))>UINT64_C(0x7ff0000000000000) :
    (uint32_t)(x&0x7fffffffU)>0x7f800000U; }
static bool snan(uint64_t x,int d) { return is_nan_bits(x,d) && !(x&(d?UINT64_C(0x0008000000000000):0x00400000U)); }
static uint64_t canonical(uint64_t x,int d) { return is_nan_bits(x,d)?(d?UINT64_C(0x7ff8000000000000):0x7fc00000U):x; }
static unsigned flags(void) {
    unsigned f=softfloat_exceptionFlags;
    return !!(f&softfloat_flag_invalid)*16 + !!(f&softfloat_flag_infinite)*8 +
        !!(f&softfloat_flag_overflow)*4 + !!(f&softfloat_flag_underflow)*2 + !!(f&softfloat_flag_inexact);
}
uint64_t fp_reference(unsigned op,int d,unsigned rm,uint64_t a,uint64_t b,uint64_t c,unsigned *out_flags) {
    if(!d) { a=(uint32_t)a; b=(uint32_t)b; c=(uint32_t)c; }
    const float32_t a32={(uint32_t)a},b32={(uint32_t)b};
    const float64_t a64={a},b64={b};
    const uint64_t sign=d?UINT64_C(0x8000000000000000):0x80000000U;
    softfloat_roundingMode=rm;softfloat_detectTininess=softfloat_tininess_afterRounding;softfloat_exceptionFlags=0;
    uint64_t x=0;
    switch(op) {
    case 27:x=f64_add(f32_to_f64(a32),b64).v;break;
    case 0:x=d?f64_add(a64,b64).v:f32_add(a32,b32).v;break;
    case 1:x=d?f64_sub(a64,b64).v:f32_sub(a32,b32).v;break;
    case 2:x=d?f64_mul(a64,b64).v:f32_mul(a32,b32).v;break;
    case 3:x=d?f64_div(a64,b64).v:f32_div(a32,b32).v;break;
    case 4:x=d?f64_sqrt(a64).v:f32_sqrt(a32).v;break;
    case 5:case 6:case 7:case 8: {
        uint64_t left=a^((op==7 || op==8)?sign:0),third=c^((op==6 || op==8)?sign:0);
        x=d?f64_mulAdd((float64_t){left},b64,(float64_t){third}).v:
            f32_mulAdd((float32_t){(uint32_t)left},b32,(float32_t){(uint32_t)third}).v;break;
    }
    case 9:case 10: {
        bool an=is_nan_bits(a,d),bn=is_nan_bits(b,d),eq=false,lt=false;
        if(!an && !bn) {eq=d?f64_eq(a64,b64):f32_eq(a32,b32);lt=d?f64_lt_quiet(a64,b64):f32_lt_quiet(a32,b32);}
        bool zeros=!(a&~sign) && !(b&~sign);
        bool choose=eq?(!zeros || (op==9?!!(a&sign):!(a&sign))):(op==9?lt:!lt);
        x=an?b:bn?a:choose?a:b;
        softfloat_exceptionFlags=(snan(a,d)||snan(b,d))?softfloat_flag_invalid:0;break;
    }
    case 11:x=d?f64_eq(a64,b64):f32_eq(a32,b32);break;
    case 12:x=!(d?f64_eq(a64,b64):f32_eq(a32,b32));break;
    case 13:x=d?f64_lt(a64,b64):f32_lt(a32,b32);break;
    case 14:x=d?f64_le(a64,b64):f32_le(a32,b32);break;
    case 15:x=d?f64_lt(b64,a64):f32_lt(b32,a32);break;
    case 16:x=d?f64_le(b64,a64):f32_le(b32,a32);break;
    case 17:case 18:case 19:
        x=(a&~sign)|(op==17?(b&sign):op==18?(~b&sign):((a^b)&sign));break;
    case 20: {
        unsigned frac=d?52:23;uint64_t em=d?2047:255;
        uint64_t e=(a>>frac)&em,f=a&((UINT64_C(1)<<frac)-1);bool neg=!!(a&sign);
        unsigned bit=e==em?(f?(snan(a,d)?8:9):(neg?0:7)):e?(neg?1:6):f?(neg?2:5):(neg?3:4);
        x=UINT64_C(1)<<bit;break;
    }
    case 21:case 25:x=d?f64_to_ui64(a64,op==25?softfloat_round_minMag:rm,true):f32_to_ui32(a32,op==25?softfloat_round_minMag:rm,true);break;
    case 22:case 26:x=d?(uint64_t)f64_to_i64(a64,op==26?softfloat_round_minMag:rm,true):(uint32_t)f32_to_i32(a32,op==26?softfloat_round_minMag:rm,true);break;
    case 23:x=d?ui64_to_f64(a).v:ui32_to_f32((uint32_t)a).v;break;
    case 24:x=d?i64_to_f64((int64_t)a).v:i32_to_f32((int32_t)a).v;break;
    default:*out_flags=0;return 0;
    }
    /* SoftFloat's default integer invalid-result specialization is not RISC-V.
       Keep its flags/rounding calculation, apply ISA saturation on invalid. */
    if((op==21 || op==22 || op==25 || op==26) && (softfloat_exceptionFlags&softfloat_flag_invalid)) {
        bool signedOut=op==22 || op==26;
        bool negative=!is_nan_bits(a,d) && !!(a&sign);
        uint64_t top=d?UINT64_C(0x8000000000000000):UINT64_C(0x80000000);
        x=signedOut?(negative?top:top-1):(negative?0:(d?UINT64_MAX:UINT32_MAX));
    }
    if(op<=10 || op==27)x=canonical(x,d);
    *out_flags=flags();return d?x:(uint32_t)x;
}
