
/*============================================================================

This Chisel source file is part of a pre-release version of the HardFloat IEEE
Floating-Point Arithmetic Package, by John R. Hauser (with some contributions
from Yunsup Lee and Andrew Waterman, mainly concerning testing).

Copyright 2010, 2011, 2012, 2013, 2014, 2015, 2016, 2017 The Regents of the
University of California.  All rights reserved.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:

 1. Redistributions of source code must retain the above copyright notice,
    this list of conditions, and the following disclaimer.

 2. Redistributions in binary form must reproduce the above copyright notice,
    this list of conditions, and the following disclaimer in the documentation
    and/or other materials provided with the distribution.

 3. Neither the name of the University nor the names of its contributors may
    be used to endorse or promote products derived from this software without
    specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE REGENTS AND CONTRIBUTORS "AS IS", AND ANY
EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE, ARE
DISCLAIMED.  IN NO EVENT SHALL THE REGENTS OR CONTRIBUTORS BE LIABLE FOR ANY
DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
(INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND
ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
(INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

=============================================================================*/

package vpu

import chisel3._
import chisel3.util._

/** Adapted from pinned HardFloat rawFloatFromFN / recFNFromFN.
  * The caller registers countLeadingZeros before this exact encoding step.
  * No rounding or NaN quieting; all original payload/sign bits are retained.
  */
object IeeeRecode {
  def apply(e:Int,p:Int,in:UInt,norm:UInt):UInt = {
    val exponent=in(e+p-2,p-1);val fraction=in(p-2,0)
    val subnormal=exponent===0.U;val zeroFraction=fraction===0.U
    val shifted=(fraction<<norm)(p-3,0)<<1
    val adjusted=Mux(subnormal,norm ^ ((BigInt(1)<<(e+1))-1).U,exponent)+
      ((BigInt(1)<<(e-1)).U | Mux(subnormal,2.U,1.U))
    val zero=subnormal && zeroFraction
    val nan=adjusted(e,e-1)===3.U && !zeroFraction
    Cat(in(e+p-1),(Mux(zero,0.U(3.W),adjusted(e,e-2)) | nan.asUInt),adjusted(e-3,0),Mux(subnormal,shifted,fraction))
  }
}
