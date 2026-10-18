import ctypes
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class ResizeReference:
 def __init__(self):
  self.lib=ctypes.CDLL(str(ROOT/'tools/fp/libfp-resize-reference.so'))
  self.lib.fp_resize_reference.argtypes=[ctypes.c_uint]*4+[ctypes.c_uint64,ctypes.POINTER(ctypes.c_uint)]
  self.lib.fp_resize_reference.restype=ctypes.c_uint64
  cases=[(28,1,1,0,0x3f800000,0x3ff0000000000000,0),(28,2,0,0,0x3ff0000010000000,0x3f800000,1),(29,2,0,7,0x3ff0000010000000,0x3f800001,1),(21,1,1,0,0x4f800000,0x100000000,0),(22,6,0,0,0x47000000,0x7fff,16),(24,5,0,0,0xffff,0xbf800000,0),(28,2,0,0,0x7ff0000000000001,0x7fc00000,16),(28,1,1,0,1,0x36a0000000000000,0)]
  self.anchors=0
  for op,m,d,rm,a,v,f in cases:assert self(op,m,d,rm,a)==(v,f),(op,m,d,rm,hex(a),self(op,m,d,rm,a),(hex(v),f));self.anchors+=1
 def __call__(self,op,mode,d,rm,a):
  f=ctypes.c_uint();v=self.lib.fp_resize_reference(op,mode,int(d),rm,a,ctypes.byref(f));return v,f.value
