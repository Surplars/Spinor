
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

// Derived from HardFloat c1105e6 postMul. Modified: staged sum, magnitude,
// leading-zero, shifts and result; per-bit prefix carries for increments. Original retained.
package vpu

import chisel3._
import chisel3.util._
import hardfloat._
import hardfloat.consts._

/** Capacity one: inputs are stable from start until done, by the lane's owner
  * protocol. Payload registers need no reset; flush kills the phase only.
  * Numerical formulas follow the licensed HardFloat postMul implementation.
  */
class StagedFmaPost extends Module {
  val e=11; val s=53; val sumWidth=3*s+3
  val io=IO(new Bundle {
    val start=Input(Bool()); val flush=Input(Bool()); val done=Output(Bool())
    val fromPreMul=Input(new MulAddRecFN_interIo(e,s))
    val mulAddResult=Input(UInt((2*s+1).W)); val roundingMode=Input(UInt(3.W))
    val invalidExc=Output(Bool()); val rawOut=Output(new RawFloat(e,s+2))
  })
  val phase=RegInit(0.U(3.W))
  io.done:=phase===6.U && !io.flush
  // Per-bit prefix carries avoid combining a wide reduction with a local
  // ripple increment before absolute-value selection.
  def increment(x:UInt,enable:Bool):UInt = ParallelIncrement(x,enable)
  val sigSum=Reg(UInt(sumWidth.W))
  // The low 104 sum bits are a direct concatenation of the multiplier result
  // and aligned-C bit zero. Capture their byte prefixes with sigSum, so the
  // magnitude stage only increments independent chunks of at most eight bits.
  val magnitudePrefix=Reg(Vec((2*s+2)/8,Bool()))
  val cAbs=Reg(UInt((2*s+2).W)); val nAbs=Reg(UInt((2*s+3).W))
  val cAbsExtra=Reg(Bool()); val nSign=Reg(Bool())
  val reduced=Reg(UInt(((2*s+4)/2).W))
  val norm2=Reg(UInt(6.W)); val nearNorm=Cat(norm2,0.U(1.W))
  val cShiftLow=Reg(UInt((2*s+2).W)); val nShiftLow=Reg(UInt((2*s+4).W))
  val cShift=Reg(UInt((2*s+2).W)); val nShift=Reg(UInt((2*s+4).W))
  val cExtra=Reg(Bool()); val nExtra=Reg(Bool())
  val result=Reg(new RawFloat(e,s+2)); val invalid=Reg(Bool())
  io.rawOut:=result;io.invalidExc:=invalid
  val m=io.fromPreMul
  when(phase===0.U && io.start && !io.flush) {
    sigSum:=Cat(increment(m.highAlignedSigC,io.mulAddResult(2*s)),
      io.mulAddResult(2*s-1,0),m.bit0AlignedSigC)
    for(byte<-1 to (2*s+2)/8) {
      magnitudePrefix(byte-1):=m.bit0AlignedSigC.asBool && io.mulAddResult(8*byte-2,0).andR
    }
    phase:=1.U
  }
  when(phase===1.U) {
    nSign:=sigSum(2*s+3)
    val magnitudeIncrement=Cat((0 to (2*s+2)/8).reverse.map { byte =>
      val carry=if(byte==0)m.doSubMags else m.doSubMags && magnitudePrefix(byte-1)
      increment(sigSum(math.min(8*byte+7,2*s+2),8*byte),carry)
    })
    nAbs:=Mux(sigSum(2*s+3),~sigSum(2*s+2,0),magnitudeIncrement)
    cAbs:=Mux(m.doSubMags,~sigSum(sumWidth-1,s+1),
      Cat(0.U(1.W),m.highAlignedSigC(s+1,s),sigSum(sumWidth-3,s+2)))
    cAbsExtra:=Mux(m.doSubMags,(~sigSum(s,1)).orR,sigSum(s+1,1).orR)
    phase:=2.U
  }
  when(phase===2.U) {
    val r=orReduceBy2(nAbs)
    reduced:=r;norm2:=BalancedLeadingZeros(r)
    phase:=3.U
  }
  when(phase===3.U) {
    cShiftLow:=(cAbs<<m.CDom_CAlignDist(2,0))(2*s+1,0)
    nShiftLow:=(nAbs<<nearNorm(2,0))(2*s+3,0)
    cExtra:=(orReduceBy4(cAbs(s-1,0)<<(~s & 3)) &
      lowMask(m.CDom_CAlignDist>>2,0,s>>2)).orR || cAbsExtra
    nExtra:=(orReduceBy2(reduced(s>>1,0)<<((s>>1)&1)) &
      lowMask(norm2>>1,0,(s+2)>>2)).orR
    phase:=4.U
  }
  when(phase===4.U) {
    cShift:=(cShiftLow<<Cat(m.CDom_CAlignDist(5,3),0.U(3.W)))(2*s+1,0)
    nShift:=(nShiftLow<<Cat(nearNorm(6,3),0.U(3.W)))(2*s+3,0)
    phase:=5.U
  }
  val cMain=cShift(2*s+1,s-3)
  val nMain=nShift(2*s+3,s-1)
  val cSig=Cat(cMain>>3,cMain(2,0).orR||cExtra)
  val nSig=Cat(nMain>>3,nMain(2,0).orR||nExtra)
  val cancellation=nSig(s+2,s+1)===0.U
  val roundMin=io.roundingMode===round_min
  val signC=m.signProd^m.doSubMags
  val infProd=m.isInfA||m.isInfB
  val infOut=infProd||m.isInfC
  val zeros=(m.isZeroA||m.isZeroB)&&m.isZeroC
  when(phase===5.U) {
    invalid:=m.isSigNaNAny || (m.isInfA&&m.isZeroB) || (m.isZeroA&&m.isInfB) ||
      (!m.isNaNAOrB && infProd && m.isInfC && m.doSubMags)
    result.isNaN:=m.isNaNAOrB||m.isNaNC
    result.isInf:=infOut
    result.isZero:=zeros||(!m.CIsDominant&&cancellation)
    result.sign:=(infProd&&m.signProd)||(m.isInfC&&signC)||
      (zeros && !roundMin && m.signProd && signC)||
      (zeros && roundMin && (m.signProd||signC))||
      (!infOut && !zeros && Mux(m.CIsDominant,signC,Mux(cancellation,roundMin,m.signProd^nSign)))
    result.sExp:=Mux(m.CIsDominant,m.sExpSum-m.doSubMags.zext,m.sExpSum-nearNorm.zext)
    result.sig:=Mux(m.CIsDominant,cSig,nSig)
    phase:=6.U
  }
  when(phase===6.U) { phase:=0.U }
  when(io.flush) { phase:=0.U }
}
