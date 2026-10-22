package vpu

import chisel3._
import chisel3.util._
import hardfloat._

/** Same-width conversions. Serial integer normalization avoids a 64-bit
  * absolute-value/LZC/barrel-shift/round chain. Capacity one, flushable.
  * A request, its rounding mode and tag remain owned until out.fire or flush.
  * The rounders and integer converters share that stable request; they do not
  * accept independent work. Results use the low 32 bits for single precision.
  */
class FloatingPointConvert extends Module {
  val io=IO(new Bundle {
    val flush=Input(Bool());val in=Flipped(Decoupled(new FpRequest));val out=Decoupled(new FpResponse)
  })
  val Seq(idle,absoluteLow,absoluteHigh,normalize,roundStart,roundWait,toIntRecode,toIntStart,toIntWait,reply,toIntPack)=Enum(11)
  val state=RegInit(idle);val req=Reg(new FpRequest);val response=Reg(new FpResponse)
  val magnitude=Reg(UInt(64.W));val negative=Reg(Bool());val carry=Reg(Bool());val leading=Reg(UInt(6.W))
  io.in.ready:=state===idle && !io.flush;io.out.valid:=state===reply && !io.flush;io.out.bits:=response
  val fromInt=req.op===FpOp.fromUInt.U || req.op===FpOp.fromInt.U
  val rtz=req.op===FpOp.toUIntRtz.U || req.op===FpOp.toIntRtz.U
  val mode=Mux(rtz,1.U,req.rounding)
  // Admission chooses the integer-normalization or recoded-float path. RTZ
  // opcodes carry their own rounding mode, independent of the requested frm.
  when(io.in.fire) {
    req:=io.in.bits;response:=0.U.asTypeOf(new FpResponse);response.tag:=io.in.bits.tag
    magnitude:=Mux(io.in.bits.double,io.in.bits.a,io.in.bits.a(31,0).pad(64));leading:=0.U
    negative:=io.in.bits.op===FpOp.fromInt.U && Mux(io.in.bits.double,io.in.bits.a(63),io.in.bits.a(31))
    val legal=io.in.bits.op>=FpOp.toUInt.U && io.in.bits.op<=FpOp.toIntRtz.U &&
      (io.in.bits.rounding<=4.U || io.in.bits.op>=FpOp.toUIntRtz.U)
    response.illegal:= !legal
    state:=Mux(!legal,reply,Mux(io.in.bits.op===FpOp.fromUInt.U || io.in.bits.op===FpOp.fromInt.U,absoluteLow,toIntRecode))
  }
  // Form the signed magnitude in two 32-bit carry stages before normalization.
  // This also represents the most-negative signed integer without overflow.
  when(state===absoluteLow) {
    val sum=CarrySelect.add(magnitude(31,0)^Fill(32,negative),0.U(32.W),negative)
    magnitude:=Cat(magnitude(63,32),sum(31,0));carry:=sum(32);state:=absoluteHigh
  }
  when(state===absoluteHigh) {
    val sum=CarrySelect.add(magnitude(63,32)^Fill(32,negative),0.U(32.W),carry)
    magnitude:=Mux(req.double,Cat(sum(31,0),magnitude(31,0)),magnitude(31,0).pad(64));state:=normalize
  }
  // Stop at zero or the leading one; leading records the exponent adjustment.
  when(state===normalize) {
    when(magnitude===0.U || magnitude(63)) { state:=roundStart }
      .otherwise { magnitude:=Cat(magnitude(62,0),false.B);leading:=leading+1.U }
  }
  // Round the integer magnitude directly to the requested floating precision.
  // Both helper instances finish before selecting data and exception flags.
  val raw=Wire(new RawFloat(7,64))
  raw.isNaN:=false.B;raw.isInf:=false.B;raw.isZero:=magnitude===0.U;raw.sign:=negative
  raw.sExp:=(191.U(9.W)-leading).asSInt;raw.sig:=magnitude
  val r32=Module(new StagedRound(7,64,8,24,0));val r64=Module(new StagedRound(7,64,11,53,0))
  for(r<-Seq(r32,r64)) {
    r.io.start:=state===roundStart && !io.flush;r.io.flush:=io.flush;r.io.in:=raw
    r.io.invalidExc:=false.B;r.io.infiniteExc:=false.B;r.io.roundingMode:=mode;r.io.detectTininess:=true.B
  }
  when(state===roundStart) { state:=roundWait }
  when(state===roundWait && r32.io.done && r64.io.done) {
    response.data:=Mux(req.double,fNFromRecFN(11,53,r64.io.out),fNFromRecFN(8,24,r32.io.out).pad(64))
    response.flags:=Mux(req.double,r64.io.exceptionFlags,r32.io.exceptionFlags);state:=reply
  }
  // Float-to-integer preparation separates leading-zero detection from IEEE
  // recoding. Helpers see the registered encoding throughout their operation.
  val t32=Module(new StagedFloatToInt(8,24,32));val t64=Module(new StagedFloatToInt(11,53,64))
  val rec32=Reg(UInt(33.W));val rec64=Reg(UInt(65.W))
  val norm32=Reg(UInt(5.W));val norm64=Reg(UInt(6.W))
  when(state===toIntRecode) {
    norm32:=countLeadingZeros(req.a(22,0));norm64:=countLeadingZeros(req.a(51,0));state:=toIntPack
  }
  when(state===toIntPack) {
    rec32:=IeeeRecode(8,24,req.a(31,0),norm32)
    rec64:=IeeeRecode(11,53,req.a,norm64);state:=toIntStart
  }
  t32.io.in:=rec32;t64.io.in:=rec64
  for(t<-Seq(t32,t64)) {
    t.io.start:=state===toIntStart && !io.flush;t.io.flush:=io.flush;t.io.roundingMode:=mode
    t.io.signedOut:=req.op===FpOp.toInt.U || req.op===FpOp.toIntRtz.U
  }
  when(state===toIntStart) { state:=toIntWait }
  when(state===toIntWait && t32.io.done && t64.io.done) {
    // HardFloat invalid and integer overflow both become RISC-V NV; NX retains
    // the helper's inexact bit. Integer conversion cannot raise DZ/OF/UF here.
    val flags=Mux(req.double,t64.io.intExceptionFlags,t32.io.intExceptionFlags)
    response.data:=Mux(req.double,t64.io.out,t32.io.out.pad(64))
    response.flags:=Cat(flags(2)||flags(1),0.U(3.W),flags(0));state:=reply
  }
  // A blocked reply holds the result; flush invalidates ownership immediately.
  when(io.out.fire) { state:=idle }
  when(io.flush) { state:=idle }
}
