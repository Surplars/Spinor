// raw32 normalization is adapted from pinned HardFloat rawFloatFromFN.
// The following notice applies to those derived portions.
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
import hardfloat._

object FpOp {
  val add=0; val sub=1; val mul=2; val div=3; val sqrt=4
  val fma=5; val fmsub=6; val fnmsub=7; val fnmadd=8
  val min=9; val max=10; val eq=11; val ne=12; val lt=13; val le=14; val gt=15; val ge=16
  val toUInt=21; val toInt=22; val fromUInt=23; val fromInt=24; val toUIntRtz=25; val toIntRtz=26
  val widenAdd=27 // internal FP32 A + FP64 B -> FP64; not a standalone ISA conversion
  val sgnj=17; val sgnjn=18; val sgnjx=19; val classify=20
}

class FpRequest extends Bundle {
  val a=UInt(64.W); val b=UInt(64.W); val c=UInt(64.W)
  val double=Bool(); val op=UInt(5.W); val rounding=UInt(3.W); val tag=UInt(8.W)
}
class FpResponse extends Bundle {
  val data=UInt(64.W); val flags=UInt(5.W); val tag=UInt(8.W); val illegal=Bool()
}

object FpBits {
  /** Exact pinned HardFloat raw decode, using a balanced normalization tree.
    * Special classification stays independent of normalization. No rounding.
    */
  def raw32(x:UInt):RawFloat = {
    val exponent=x(30,23);val significand=x(22,0)
    val norm=BalancedLeadingZeros(significand)
    val subnormal= !exponent.orR
    val normalized=(significand<<norm)(21,0)<<1
    val adjusted=Mux(subnormal,norm ^ 511.U(9.W),exponent)+
      (128.U | Mux(subnormal,2.U,1.U))
    val out=Wire(new RawFloat(8,24))
    val special=exponent.andR;val fraction=significand.orR
    out.isNaN:=special && fraction;out.isInf:=special && !fraction
    out.isZero:=subnormal && !fraction;out.sign:=x(31)
    out.sExp:=adjusted(8,0).zext
    out.sig:=Cat(0.U(1.W),!out.isZero,Mux(subnormal,normalized,significand))
    out
  }
  /** IEEE fclass bits directly from the encoding; subnormals need no normalization. */
  def classify(x: UInt,e: Int,p: Int): UInt = {
    val s=x(e+p-1);val exponent=x(e+p-2,p-1);val fraction=x(p-2,0)
    val ez= !exponent.orR;val em=exponent.andR;val fz= !fraction.orR
    val nan=em && !fz;val inf=em && fz;val zero=ez && fz
    val sub=ez && !fz;val normal= !ez && !em
    Cat(nan && fraction(p-2),nan && !fraction(p-2),
      inf && !s,normal && !s,sub && !s,zero && !s,
      zero && s,sub && s,normal && s,inf && s)
  }
  def nan(x: UInt, d: Bool): Bool = Mux(d,x(62,52).andR && x(51,0).orR,x(30,23).andR && x(22,0).orR)
  def canonical(d: Bool): UInt = Mux(d,"h7ff8000000000000".U(64.W),"h7fc00000".U(64.W))
  def sign(x: UInt,d: Bool): Bool = Mux(d,x(63),x(31))
  def zero(x: UInt,d: Bool): Bool = Mux(d,!x(62,0).orR,!x(30,0).orR)
  /** Exact recoded widening, NOT a floating-point conversion/rounding operation.
    * Retains NaN payload and signaling bit; no first rounding to binary64.
    */
  def wideRecRaw(in: RawFloat): UInt = {
    val raw=resizeRawFloat(11,53,in)
    val exp=Mux(raw.isNaN,3584.U(12.W),Mux(raw.isInf,3072.U(12.W),Mux(raw.isZero,0.U(12.W),raw.sExp.asUInt(11,0))))
    Cat(raw.sign,exp,raw.sig(51,0))
  }
}

/** Capacity-one FP32/FP64 numerical lane. One shared 53-bit FMA and iterative
  * divider/sqrt. FP32 operands widen EXACTLY; raw results round DIRECTLY to the
  * selected format, avoiding double rounding and premature NaN quieting.
  * Add/sub use a*1 +/- b. Multiply adds a zero with the product's sign so -0
  * multiplication is preserved for every rounding mode.
  * Staged align, tiled product/CSA, split add, normalize, round and div/sqrt.
  * Capacity remains one; device timing and throughput remain unqualified.
  */
class FloatingPointLane extends Module {
  val io=IO(new Bundle {
    val flush=Input(Bool()); val in=Flipped(Decoupled(new FpRequest)); val out=Decoupled(new FpResponse)
  })
  val states=Enum(25)
  val Seq(idle,recode,prepare,preWait,multiply,reduceA,reduceB,reduceC,add0,add1,add2,add3,
    normalize,postWait,rounding,roundWait,divLaunch,divWait,misc,miscReply,reply)=states.take(21)
  val convertStart=states(21);val convertWait=states(22);val recodeFinish=states(23);val roundPack=states(24)
  val state=RegInit(idle)
  val request=Reg(new FpRequest)
  val response=Reg(new FpResponse)
  val ra=Reg(UInt(65.W)); val rb=Reg(UInt(65.W)); val rc=Reg(UInt(65.W))
  io.in.ready := state===idle && !io.flush
  io.out.valid := state===reply && !io.flush
  io.out.bits := response
  val isDiv=request.op===FpOp.div.U || request.op===FpOp.sqrt.U
  val isWideAdd=request.op===FpOp.widenAdd.U
  val isMisc=request.op>=FpOp.min.U && !isWideAdd
  when(io.in.fire) {
    request:=io.in.bits
    response:=0.U.asTypeOf(new FpResponse)
    response.tag:=io.in.bits.tag
    val rtz=io.in.bits.op>=FpOp.toUIntRtz.U && io.in.bits.op<=FpOp.toIntRtz.U
    val legal=(io.in.bits.rounding<=4.U || rtz) && (io.in.bits.op<=FpOp.toIntRtz.U ||
      (io.in.bits.op===FpOp.widenAdd.U && io.in.bits.double))
    response.illegal := !legal
    state:=Mux(legal,recode,reply)
  }
  // Register FP32 normalization before exponent widening / special packing.
  // Preserve signaling NaNs and payload; this is exact widening, no rounding.
  val raw32=Reg(Vec(3,new RawFloat(8,24)))
  val norm64=Reg(Vec(3,UInt(6.W)))
  when(state===recode) {
    for((x,k)<-Seq(request.a,request.b,request.c).zipWithIndex) {
      raw32(k):=FpBits.raw32(x);norm64(k):=countLeadingZeros(x(51,0))
    }
    state:=recodeFinish
  }
  when(state===recodeFinish) {
    ra:=Mux(request.double && !isWideAdd,IeeeRecode(11,53,request.a,norm64(0)),FpBits.wideRecRaw(raw32(0)))
    when(request.double) {
      rb:=IeeeRecode(11,53,request.b,norm64(1));rc:=IeeeRecode(11,53,request.c,norm64(2))
    }.otherwise {
      rb:=FpBits.wideRecRaw(raw32(1));rc:=FpBits.wideRecRaw(raw32(2))
    }
    state:=Mux(request.op>=FpOp.toUInt.U && !isWideAdd,convertStart,Mux(isDiv,divLaunch,Mux(isMisc,misc,prepare)))
  }
  val pre=Module(new StagedFmaPre)
  pre.io.start:=state===prepare && !io.flush;pre.io.flush:=io.flush
  val isAdd=request.op===FpOp.add.U || request.op===FpOp.sub.U || isWideAdd
  val isMul=request.op===FpOp.mul.U
  val signedZero=Cat(ra(64)^rb(64),0.U(64.W))
  pre.io.a:=ra
  pre.io.b:=Mux(isAdd,recFNFromFN(11,53,"h3ff0000000000000".U(64.W)),rb)
  pre.io.c:=Mux(isAdd,rb,Mux(isMul,signedZero,rc))
  pre.io.op:=Mux(isAdd,Cat(false.B,request.op===FpOp.sub.U),
    Mux(isMul,0.U,Cat(request.op===FpOp.fnmsub.U || request.op===FpOp.fnmadd.U,
      request.op===FpOp.fmsub.U || request.op===FpOp.fnmadd.U)))
  val ma=Reg(UInt(53.W)); val mb=Reg(UInt(53.W)); val aligned=Reg(UInt(106.W))
  val metadata=Reg(chiselTypeOf(pre.io.toPostMul))
  val sums=Reg(Vec(4,UInt(32.W))); val carry=Reg(Bool())
  when(state===prepare) {
    state:=preWait
  }
  when(state===preWait && pre.io.done) {
    ma:=pre.io.mulAddA; mb:=pre.io.mulAddB; aligned:=pre.io.mulAddC; metadata:=pre.io.toPostMul
    state:=multiply
  }
  // Unsigned 26x17 chunks fit the DSP48E2 multiplier's signed 27x18 ports.
  // Register each product before any wide summation. Edge chunks become LUTs.
  val partials=for(i<-0 until 3;j<-0 until 4)yield {
    val aw=math.min(26,53-26*i);val bw=math.min(17,53-17*j)
    val p=Reg(UInt((aw+bw).W))
    when(state===multiply) { p:=ma(26*i+aw-1,26*i)*mb(17*j+bw-1,17*j) }
    (p.pad(107)<<(26*i+17*j))(106,0)
  }
  def compress(xs: Seq[UInt]): Seq[UInt] = xs.grouped(3).toSeq.flatMap { g=>
    if(g.size<3)g else {
      val Seq(x,y,z)=g
      Seq(x^y^z,(((x&y)|(x&z)|(y&z))<<1)(106,0))
    }
  }
  val aTerms=compress(compress(partials:+aligned.pad(107)))
  val savedA=Reg(Vec(aTerms.size,UInt(107.W)))
  val bTerms=compress(compress(savedA.toSeq))
  val savedB=Reg(Vec(bTerms.size,UInt(107.W)))
  val cTerms=compress(savedB.toSeq)
  require(cTerms.size==2)
  val savedC=Reg(Vec(2,UInt(107.W)))
  when(state===multiply) { state:=reduceA }
  when(state===reduceA) { savedA:=VecInit(aTerms);state:=reduceB }
  when(state===reduceB) { savedB:=VecInit(bTerms);state:=reduceC }
  when(state===reduceC) { savedC:=VecInit(cTerms);state:=add0 }
  for ((s,k)<-Seq(add0,add1,add2,add3).zipWithIndex) {
    val hi=math.min(106,32*k+31); val width=hi-32*k+1
    val sum=CarrySelect.add(savedC(0)(hi,32*k),savedC(1)(hi,32*k),Mux((k==0).B,false.B,carry))
    when(state===s) {
      sums(k):=sum(width-1,0); carry:=sum(width)
      state:= (if(k==3) normalize else Seq(add1,add2,add3)(k))
    }
  }
  val post=Module(new StagedFmaPost)
  post.io.start:=state===normalize && !io.flush
  post.io.flush:=io.flush
  post.io.fromPreMul:=metadata
  post.io.mulAddResult:=Cat(sums(3)(10,0),sums(2),sums(1),sums(0))
  post.io.roundingMode:=request.rounding
  val raw=Reg(new RawFloat(11,55)); val invalid=Reg(Bool()); val infinite=Reg(Bool())
  when(state===normalize) { state:=postWait }
  when(state===postWait && post.io.done) { raw:=post.io.rawOut; invalid:=post.io.invalidExc; infinite:=false.B; state:=rounding }
  val divider=withReset(reset.asBool || io.flush) { Module(new StagedDivSqrt) }
  divider.io.inValid:=state===divLaunch && !io.flush
  divider.io.sqrtOp:=request.op===FpOp.sqrt.U
  divider.io.a:=rawFloatFromRecFN(11,53,ra); divider.io.b:=rawFloatFromRecFN(11,53,rb)
  divider.io.roundingMode:=request.rounding
  when(state===divLaunch && divider.io.inReady) { state:=divWait }
  when(state===divWait && (divider.io.rawOutValid_div || divider.io.rawOutValid_sqrt)) {
    raw:=divider.io.rawOut; invalid:=divider.io.invalidExc; infinite:=divider.io.infiniteExc; state:=rounding
  }
  val r32=Module(new StagedRound(11,55,8,24,0))
  val r64=Module(new StagedRound(11,55,11,53,0))
  for (r<-Seq(r32,r64)) {
    r.io.start:=state===rounding && !io.flush;r.io.flush:=io.flush
    r.io.in:=raw; r.io.invalidExc:=invalid; r.io.infiniteExc:=infinite
    r.io.roundingMode:=request.rounding; r.io.detectTininess:=true.B
  }
  val u32=Module(new StagedIeeeUnrecode(8,24))
  val u64=Module(new StagedIeeeUnrecode(11,53))
  val rounded=state===roundWait && r32.io.done && r64.io.done && !io.flush
  u32.io.in:=r32.io.out;u64.io.in:=r64.io.out
  u32.io.capture:=rounded;u64.io.capture:=rounded
  val ieee=Mux(request.double,u64.io.out,u32.io.out.pad(64))
  when(state===rounding) { state:=roundWait }
  when(rounded) {
    response.flags:=Mux(request.double,r64.io.exceptionFlags,r32.io.exceptionFlags)
    state:=roundPack
  }
  when(state===roundPack) {
    response.data:=Mux(FpBits.nan(ieee,request.double),FpBits.canonical(request.double),ieee)
    state:=reply
  }
  val converter=Module(new FloatingPointConvert)
  converter.io.flush:=io.flush;converter.io.in.bits:=request
  converter.io.in.valid:=state===convertStart && !io.flush
  converter.io.out.ready:=state===convertWait && !io.flush
  when(converter.io.in.fire) { state:=convertWait }
  when(converter.io.out.fire) { response:=converter.io.out.bits;state:=reply }
  val cmp=Module(new CompareRecFN(11,53))
  cmp.io.a:=ra; cmp.io.b:=rb
  cmp.io.signaling:=request.op>=FpOp.lt.U && request.op<=FpOp.ge.U
  val cmpEq=Reg(Bool());val cmpLt=Reg(Bool());val cmpGt=Reg(Bool());val cmpFlags=Reg(UInt(5.W))
  when(state===misc) {
    cmpEq:=cmp.io.eq;cmpLt:=cmp.io.lt;cmpGt:=cmp.io.gt;cmpFlags:=cmp.io.exceptionFlags
    state:=miscReply
  }
  // Consume the registered exact recoding. Re-decoding request operands here
  // lets synthesis share the FP32 normalization cone with min/max selection.
  val an=Mux(request.double,ra(63,61)===7.U,raw32(0).isNaN)
  val bn=Mux(request.double,rb(63,61)===7.U,raw32(1).isNaN)
  val az=Mux(request.double,ra(63,61)===0.U,raw32(0).isZero)
  val bz=Mux(request.double,rb(63,61)===0.U,raw32(1).isZero)
  val signA=FpBits.sign(request.a,request.double); val signB=FpBits.sign(request.b,request.double)
  val minimum=request.op===FpOp.min.U
  val chooseA=Mux(cmpEq,Mux(az&&bz,Mux(minimum,signA,!signA),true.B),Mux(minimum,cmpLt,cmpGt))
  val minmax=Mux(an&&bn,FpBits.canonical(request.double),Mux(an,request.b,Mux(bn,request.a,Mux(chooseA,request.a,request.b))))
  val sign=Mux(request.op===FpOp.sgnjx.U,signA^signB,Mux(request.op===FpOp.sgnjn.U,!signB,signB))
  val signMask=Mux(request.double,(BigInt(1)<<63).U(64.W),(BigInt(1)<<31).U(64.W))
  val signValue=(request.a & ~signMask) | Mux(sign,signMask,0.U)
  val classified=Mux(request.double,FpBits.classify(request.a,11,53),FpBits.classify(request.a(31,0),8,24))
  val compared=MuxLookup(request.op,false.B)(Seq(
    FpOp.eq.U->cmpEq,FpOp.ne.U-> !cmpEq,FpOp.lt.U->cmpLt,
    FpOp.le.U->(cmpLt||cmpEq),FpOp.gt.U->cmpGt,FpOp.ge.U->(cmpGt||cmpEq)))
  when(state===miscReply) {
    val data=Mux(request.op===FpOp.classify.U,classified.pad(64),
      Mux(request.op>=FpOp.sgnj.U,signValue,Mux(request.op<=FpOp.max.U,minmax,Cat(0.U(63.W),compared))))
    response.data:=Mux(request.double,data,data(31,0).pad(64))
    response.flags:=Mux(request.op>=FpOp.sgnj.U,0.U,cmpFlags)
    state:=reply
  }
  when(io.out.fire) { state:=idle }
  when(io.flush) { state:=idle }
}
