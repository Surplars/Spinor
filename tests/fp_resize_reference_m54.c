#include <stdint.h>
#include <stdbool.h>
#include "softfloat.h"
uint64_t fp_resize_reference(unsigned op,unsigned mode,unsigned d,unsigned rm,uint64_t a,unsigned *flags) {
 bool src64=mode==0?d:mode==2;unsigned dst=d?64:mode==6?16:32;
 unsigned r=op==25 || op==26?1:op==29?6:rm;
 softfloat_roundingMode=r;softfloat_detectTininess=softfloat_tininess_afterRounding;softfloat_exceptionFlags=0;
 float32_t x32={(uint32_t)a};float64_t x64={a};uint64_t v=0;
 bool toInt=op==21 || op==22 || op==25 || op==26,sgn=op==22 || op==26;
 if(toInt) {
  if(dst==64)v=sgn?(src64?(uint64_t)f64_to_i64(x64,r,true):(uint64_t)f32_to_i64(x32,r,true)):(src64?f64_to_ui64(x64,r,true):f32_to_ui64(x32,r,true));
  else v=sgn?(uint32_t)(src64?f64_to_i32(x64,r,true):f32_to_i32(x32,r,true)):(uint32_t)(src64?f64_to_ui32(x64,r,true):f32_to_ui32(x32,r,true));
  if(dst==16 && !(softfloat_exceptionFlags&softfloat_flag_invalid) && (sgn?((int32_t)v < -32768 || (int32_t)v > 32767):v>65535))softfloat_exceptionFlags=softfloat_flag_invalid;
  if(softfloat_exceptionFlags&softfloat_flag_invalid) {
   bool nan=src64?((a&UINT64_C(0x7fffffffffffffff))>UINT64_C(0x7ff0000000000000)):(((uint32_t)a&0x7fffffffU)>0x7f800000U);
   bool neg=!nan && !!(a&(src64?UINT64_C(0x8000000000000000):UINT64_C(0x80000000)));
   uint64_t top=UINT64_C(1)<<(dst-1);v=sgn?(neg?top:top-1):(neg?0:top|(top-1));
  }
  if(dst<64)v&=(UINT64_C(1)<<dst)-1;
 } else if(op==23 || op==24) {
  if(mode==5)a=op==24?(uint32_t)(int32_t)(int16_t)a:(uint16_t)a;
  if(d)v=op==24?(src64?i64_to_f64((int64_t)a).v:i32_to_f64((int32_t)a).v):(src64?ui64_to_f64(a).v:ui32_to_f64((uint32_t)a).v);
  else v=op==24?(src64?i64_to_f32((int64_t)a).v:i32_to_f32((int32_t)a).v):(src64?ui64_to_f32(a).v:ui32_to_f32((uint32_t)a).v);
 } else if(op==28 && mode==5) {float16_t h={(uint16_t)a};v=f16_to_f32(h).v;}
 else if(op==28 && mode==6)v=f32_to_f16(x32).v;
 else v=d?f32_to_f64(x32).v:f64_to_f32(x64).v;
 if(op==28 && mode==6) {if((v&0x7fffU)>0x7c00U)v=0x7e00U;}
 else if(!toInt) {
  if(d && (v&UINT64_C(0x7fffffffffffffff))>UINT64_C(0x7ff0000000000000))v=UINT64_C(0x7ff8000000000000);
  if(!d && (v&0x7fffffffU)>0x7f800000U)v=0x7fc00000U;
 }
 unsigned f=softfloat_exceptionFlags;*flags=!!(f&softfloat_flag_invalid)*16+!!(f&softfloat_flag_infinite)*8+!!(f&softfloat_flag_overflow)*4+!!(f&softfloat_flag_underflow)*2+!!(f&softfloat_flag_inexact);return v;
}
