
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

// Derived from HardFloat c1105e6 preMul. Modified: staged raw operands,
// exponent alignment, split signed shift and metadata outputs. Original retained.
package vpu

import chisel3._
import chisel3.util._
import hardfloat._

/** Inputs are sampled on start. Outputs hold after done for a single owner. */
class StagedFmaPre extends Module {
  val e=11;val s=53;val sw=3*s+3;val mw=sw+3
  val io=IO(new Bundle {
    val start=Input(Bool());val flush=Input(Bool());val done=Output(Bool())
    val op=Input(UInt(2.W));val a=Input(UInt(65.W));val b=Input(UInt(65.W));val c=Input(UInt(65.W))
    val mulAddA=Output(UInt(s.W));val mulAddB=Output(UInt(s.W));val mulAddC=Output(UInt((2*s).W))
    val toPostMul=Output(new MulAddRecFN_interIo(e,s))
  })
  val phase=RegInit(0.U(4.W))
  io.done:=phase===7.U && !io.flush
  val a=Reg(new RawFloat(e,s));val b=Reg(new RawFloat(e,s));val c=Reg(new RawFloat(e,s));val op=Reg(UInt(2.W))
  val signProd=a.sign^b.sign^op(1)
  val subtract=signProd^c.sign^op(0)
  val alignedExp=Reg(SInt((e+3).W))
  val naturalDist=Reg(SInt((e+4).W))
  val dist=Reg(UInt(8.W));val dominant=Reg(Bool())
  val base=Reg(SInt(mw.W));val lowShift=Reg(SInt(mw.W));val main=Reg(SInt(mw.W))
  val reducedExtra=Reg(Bool())
  val outA=Reg(UInt(s.W));val outB=Reg(UInt(s.W));val outC=Reg(UInt((2*s).W))
  val metadata=Reg(new MulAddRecFN_interIo(e,s))
  io.mulAddA:=outA;io.mulAddB:=outB;io.mulAddC:=outC;io.toPostMul:=metadata
  when(phase===0.U && io.start && !io.flush) {
    a:=rawFloatFromRecFN(e,s,io.a);b:=rawFloatFromRecFN(e,s,io.b);c:=rawFloatFromRecFN(e,s,io.c);op:=io.op
    phase:=1.U
  }
  when(phase===1.U) {
    alignedExp:=a.sExp+&b.sExp+(-(BigInt(1)<<e)+s+3).S
    phase:=2.U
  }
  when(phase===2.U) { naturalDist:=alignedExp-c.sExp;phase:=3.U }
  val positive=naturalDist(e+1,0)
  val minimum=a.isZero||b.isZero||naturalDist<0.S
  when(phase===3.U) {
    dist:=Mux(minimum,0.U,Mux(positive<(sw-1).U,positive(7,0),(sw-1).U))
    dominant:= !c.isZero && (minimum || positive<=s.U)
    base:=Cat(Mux(subtract,~c.sig,c.sig),Fill(sw-s+2,subtract)).asSInt
    phase:=4.U
  }
  when(phase===4.U) {
    lowShift:=base>>dist(3,0)
    reducedExtra:=(orReduceBy4(c.sig<<((sw-s-1)&3)) & lowMask(dist>>2,(sw-1)>>2,(sw-s-1)>>2)).orR
    phase:=5.U
  }
  when(phase===5.U) { main:=lowShift>>Cat(dist(7,4),0.U(4.W));phase:=6.U }
  val aligned=Cat(main>>3,Mux(subtract,main(2,0).andR && !reducedExtra,main(2,0).orR||reducedExtra))
  when(phase===6.U) {
    outA:=a.sig(s-1,0);outB:=b.sig(s-1,0);outC:=aligned(2*s,1)
    metadata.isSigNaNAny:=isSigNaNRawFloat(a)||isSigNaNRawFloat(b)||isSigNaNRawFloat(c)
    metadata.isNaNAOrB:=a.isNaN||b.isNaN
    metadata.isInfA:=a.isInf;metadata.isZeroA:=a.isZero
    metadata.isInfB:=b.isInf;metadata.isZeroB:=b.isZero;metadata.signProd:=signProd
    metadata.isNaNC:=c.isNaN;metadata.isInfC:=c.isInf;metadata.isZeroC:=c.isZero
    metadata.sExpSum:=Mux(dominant,c.sExp,(alignedExp-s.S)(e+1,0).asSInt)
    metadata.doSubMags:=subtract;metadata.CIsDominant:=dominant
    metadata.CDom_CAlignDist:=dist(5,0)
    metadata.highAlignedSigC:=aligned(sw-1,2*s+1)
    metadata.bit0AlignedSigC:=aligned(0)
    phase:=7.U
  }
  when(phase===7.U) { phase:=0.U }
  when(io.flush) { phase:=0.U }
}
