"""RVV 1.0 oracle: exact rational midpoint arithmetic, no hardware table import."""
from math import isqrt

def nearest_sqrt(n,d):
 q=isqrt(n//d)
 return q+int(4*n>d*(2*q+1)**2)

def estimate(op,double,rm,x):
 assert op in [30,31]
 w,p,e=(64,52,11) if double else (32,23,8)
 x&=(1<<w)-1;sg=x>>(w-1);fraction=x&((1<<p)-1);exponent=(x>>p)&((1<<e)-1);bias=(1<<(e-1))-1
 inf=((1<<e)-1)<<p;sign=sg<<(w-1);nan=inf|(1<<(p-1))
 if exponent==(1<<e)-1 and fraction:return nan,16 if fraction>>(p-1)==0 else 0
 if op==31 and sg and (exponent or fraction):return nan,16
 if not exponent and not fraction:return sign|inf,8
 if exponent==(1<<e)-1:return sign,0
 if exponent:
  normalized=exponent;f=fraction
 else:
  shift=p-fraction.bit_length()+1;normalized=1-shift;f=(fraction<<shift)&((1<<p)-1)
 if op==30:
  i=f>>(p-7);d=257+2*i;v=(65536+d//2)//d-128;out=2*bias-1-normalized
  if out>2*bias:
   finite=rm==1 or rm==2 and not sg or rm==3 and sg
   return sign|(inf-1 if finite else inf),5
  sig=v<<(p-7)
  if out<=0:sig=((1<<p)|sig)>>(1-out);out=0
 else:
  i=f>>(p-6);v=nearest_sqrt(128**2*(512 if normalized&1 else 256),129+2*i)-128
  out=(3*bias-1-normalized)//2;sig=v<<(p-7)
 return sign|(out<<p)|sig,0

ANCHORS=[(30,False,0,0x00718abc,0x7e900000,0),(30,False,0,0x7f765432,0x00214000,0),(31,False,7,0x00718abc,0x5f080000,0),(31,False,7,0x7f765432,0x1f820000,0),(30,False,1,1,0x7f7fffff,5),(30,False,0,1,0x7f800000,5),(31,True,0,0xbff0000000000000,0x7ff8000000000000,16),(31,True,0,0x8000000000000000,0xfff0000000000000,8)]
for op,d,rm,x,y,f in ANCHORS:assert estimate(op,d,rm,x)==(y,f)
