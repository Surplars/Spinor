
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

// Derived from HardFloat c1105e6 fNFromRecFN. Modified: register exponent,
// subnormal shift distance and significand before the denormal barrel shift.
package vpu

import chisel3._
import chisel3.util._
import hardfloat._

/** One enabled preparation register, owned and cancelled by the FP lane. */
class StagedIeeeUnrecode(expWidth:Int,sigWidth:Int) extends Module {
  override def desiredName=s"StagedIeeeUnrecode_e${expWidth}_s${sigWidth}"
  val io=IO(new Bundle {
    val capture=Input(Bool());val in=Input(UInt((expWidth+sigWidth+1).W))
    val out=Output(UInt((expWidth+sigWidth).W))
  })
  val raw=rawFloatFromRecFN(expWidth,sigWidth,io.in)
  val sub=Reg(Bool());val inf=Reg(Bool());val sign=Reg(Bool())
  val sig=Reg(UInt(sigWidth.W));val exp=Reg(UInt(expWidth.W))
  val shift=Reg(UInt(log2Ceil(sigWidth-1).W))
  val isSubnormal=raw.sExp<((BigInt(1)<<(expWidth-1))+2).S
  when(io.capture) {
    sub:=isSubnormal;inf:=raw.isInf;sign:=raw.sign;sig:=raw.sig
    shift:=1.U-raw.sExp(log2Ceil(sigWidth-1)-1,0)
    exp:=Mux(isSubnormal,0.U,raw.sExp(expWidth-1,0)-((BigInt(1)<<(expWidth-1))+1).U) |
      Fill(expWidth,raw.isNaN || raw.isInf)
  }
  val fraction=Mux(sub,((sig>>1)>>shift)(sigWidth-2,0),Mux(inf,0.U,sig(sigWidth-2,0)))
  io.out:=Cat(sign,exp,fraction)
}
