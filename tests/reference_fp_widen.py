"""SoftFloat widening + binary64 arithmetic. No Python host-float expectations."""
import ctypes
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class WideReference:
 def __init__(self):
  self.lib=ctypes.CDLL(str(ROOT/'tools/fp/libfp-widen-reference.so'))
  self.lib.fp_widen_reference.argtypes=[ctypes.c_uint,ctypes.c_uint,ctypes.c_uint,ctypes.c_uint64,ctypes.c_uint64,ctypes.c_uint64,ctypes.POINTER(ctypes.c_uint)]
  self.lib.fp_widen_reference.restype=ctypes.c_uint64
  self.anchors=0
  cases=[(0,3,0,0x3f800000,0x3f800000,0,0x4000000000000000,0),
   (2,3,0,0x3f800001,0x3f7ffffe,0,0x3fefffffffffff80,0),
   (5,3,0,0x3f800001,0x3f7ffffe,0xbff0000000000000,0xbd10000000000000,0),
   (0,2,0,0x4340000000000000,0x3f800000,0,0x4340000000000000,1),
   (0,2,3,0x4340000000000000,0x3f800000,0,0x4340000000000001,1),
   (0,3,0,0x7f800001,0x3f800000,0,0x7ff8000000000000,16),
   (0,3,0,1,0,0,0x36a0000000000000,0),
   (2,3,0,0x7f7fffff,0x7f7fffff,0,0x4fefffffc0000020,0)]
  for op,w,rm,a,b,c,value,flags in cases:
   actual=self(op,w,rm,a,b,c);assert actual==(value,flags),(op,w,hex(a),actual,(hex(value),flags));self.anchors+=1
 def __call__(self,op,widths,rm,a,b,c=0):
  flags=ctypes.c_uint();value=self.lib.fp_widen_reference(op,widths,rm,a,b,c,ctypes.byref(flags));return value,flags.value
