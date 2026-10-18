/* Independent IEEE numerical oracle: unmodified Berkeley SoftFloat operations.
 * Source widths are explicit; conversion flags are retained across arithmetic.
 */
#include <stdint.h>
#include "softfloat.h"
uint64_t fp_widen_reference(unsigned op,unsigned widths,unsigned rm,uint64_t a,uint64_t b,uint64_t c,unsigned *flags) {
 softfloat_roundingMode=rm;softfloat_detectTininess=softfloat_tininess_afterRounding;softfloat_exceptionFlags=0;
 float64_t left=(widths&1)?f32_to_f64((float32_t){(uint32_t)a}):(float64_t){a};
 float64_t right=(widths&2)?f32_to_f64((float32_t){(uint32_t)b}):(float64_t){b};
 float64_t result={0};
 switch(op) {
 case 0:result=f64_add(left,right);break;
 case 1:result=f64_sub(left,right);break;
 case 2:result=f64_mul(left,right);break;
 case 5:case 6:case 7:case 8: {
  if(op==7 || op==8)left.v^=UINT64_C(0x8000000000000000);
  float64_t third={c^((op==6 || op==8)?UINT64_C(0x8000000000000000):0)};
  result=f64_mulAdd(left,right,third);break;
 }
 }
 unsigned f=softfloat_exceptionFlags;
 *flags=!!(f&softfloat_flag_invalid)*16+!!(f&softfloat_flag_infinite)*8+!!(f&softfloat_flag_overflow)*4+!!(f&softfloat_flag_underflow)*2+!!(f&softfloat_flag_inexact);
 if((result.v&UINT64_C(0x7ff0000000000000))==UINT64_C(0x7ff0000000000000) && (result.v&UINT64_C(0x000fffffffffffff)))return UINT64_C(0x7ff8000000000000);
 return result.v;
}
