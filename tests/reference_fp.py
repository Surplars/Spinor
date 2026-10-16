"""ctypes access to independent SoftFloat. No Python host-float expectations."""
import ctypes
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

class Reference:
    def __init__(self):
        p=ROOT/'tools/fp/libfp-reference.so'
        if not p.exists():raise RuntimeError('Run python3 scripts/bootstrap_fp.py first')
        self.lib=ctypes.CDLL(str(p))
        self.lib.fp_reference.argtypes=[ctypes.c_uint,ctypes.c_int,ctypes.c_uint,
            ctypes.c_uint64,ctypes.c_uint64,ctypes.c_uint64,ctypes.POINTER(ctypes.c_uint)]
        self.lib.fp_reference.restype=ctypes.c_uint64
        self.anchors=0
        self.check_anchors()
    def __call__(self,op,d,rm,a,b=0,c=0):
        flags=ctypes.c_uint()
        value=self.lib.fp_reference(op,int(d),rm,a,b,c,ctypes.byref(flags))
        return value,flags.value
    def check_anchors(self):
        for d in [False,True]:
            one=0x3ff0000000000000 if d else 0x3f800000
            sign=1<<(63 if d else 31);inf=0x7ff0000000000000 if d else 0x7f800000
            qnan=inf|(1<<(51 if d else 22));snan=inf|1
            half=0x3fe0000000000000 if d else 0x3f000000
            tiny=0x0010000000000000 if d else 0x00800000
            two=0x4000000000000000 if d else 0x40000000
            halfway=0x3ca0000000000000 if d else 0x33800000
            eps=one+1;below=one-2
            fused=0xb970000000000000 if d else 0xa8800000
            cases=[
                (0,0,one,one,0,two,0),(0,0,one,halfway,0,one,1),
                (0,4,one,halfway,0,one+1,1),(0,3,one,halfway,0,one+1,1),
                (0,2,0,sign,0,sign,0),(2,0,sign,one,0,sign,0),
                (2,0,tiny,half,0,tiny//2,0),(2,0,1,half,0,0,3),(2,3,1,half,0,1,3),
                (2,0,inf-1,two,0,inf,5),(2,1,inf-1,two,0,inf-1,5),
                (1,0,inf,inf,0,qnan,16),(3,0,one,0,0,inf,8),(3,0,0,0,0,qnan,16),
                (4,0,one|sign,0,0,qnan,16),(0,0,qnan,one,0,qnan,0),
                (0,0,snan,one,0,qnan,16),(5,0,eps,below,one|sign,fused,0),
                (9,0,snan,one,0,one,16),(11,0,qnan,one,0,0,0),
                (12,0,qnan,one,0,1,0),(13,0,qnan,one,0,0,16),
                (20,0,1,0,0,32,0),(20,0,sign,0,0,8,0),(20,0,snan,0,0,256,0),
                (17,0,snan,sign,0,snan|sign,0)]
            for op,rm,a,b,c,value,flags in cases:
                actual=self(op,d,rm,a,b,c)
                assert actual==(value,flags),('SoftFloat known-answer anchor',op,d,rm,hex(a),actual,(value,flags))
                self.anchors+=1
