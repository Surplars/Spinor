package vpu

import chisel3._
import chisel3.util._
import hardfloat._

/** Shared same-width and cross-width conversions. Serial integer normalization avoids a 64-bit
  * absolute-value/LZC/barrel-shift/round chain. Capacity one, flushable.
  * widthMode is captured with the request: 0 selects its ordinary width,
  * 1/2 select 32-to-64/64-to-32, and 5/6 select 16-to-32/32-to-16.
  * Helpers use this captured mode throughout the operation.
  */
class FloatingPointConvertResize extends Module {
  val io=IO(new Bundle {
    val widthMode=Input(UInt(3.W))
    val flush=Input(Bool());val in=Flipped(Decoupled(new FpRequest));val out=Decoupled(new FpResponse)
  })
  val Seq(idle,absoluteLow,absoluteHigh,normalize,roundStart,roundWait,toIntRecode,toIntStart,toIntWait,reply,toIntPack)=Enum(11)
  val state=RegInit(idle);val req=Reg(new FpRequest);val response=Reg(new FpResponse)
  val magnitude=Reg(UInt(64.W));val negative=Reg(Bool());val carry=Reg(Bool());val leading=Reg(UInt(6.W))
  io.in.ready:=state===idle && !io.flush;io.out.valid:=state===reply && !io.flush;io.out.bits:=response
  // Source and destination width differ for resizing. req.double selects the
  // destination container; widths determines which input bits are meaningful.
  val widths=Reg(UInt(3.W))
  val sourceDouble=Mux(widths===0.U,req.double,widths===2.U)
  val floatCast=req.op===FpOp.convertFloat.U || req.op===FpOp.convertOdd.U
  val fromInt=req.op===FpOp.fromUInt.U || req.op===FpOp.fromInt.U
  val rtz=req.op===FpOp.toUIntRtz.U || req.op===FpOp.toIntRtz.U
  val mode=Mux(req.op===FpOp.convertOdd.U,6.U,Mux(rtz,1.U,req.rounding))
  // Reject unsupported width/op combinations before starting any helper. The
  // integer-RTZ and float round-to-odd opcodes override the dynamic mode.
  when(io.in.fire) {
    req:=io.in.bits;widths:=io.widthMode;response:=0.U.asTypeOf(new FpResponse);response.tag:=io.in.bits.tag
    val inputDouble=Mux(io.widthMode===0.U,io.in.bits.double,io.widthMode===2.U)
    val small=io.widthMode===5.U
    val smallInt=Mux(io.in.bits.op===FpOp.fromInt.U,Cat(Fill(16,io.in.bits.a(15)),io.in.bits.a(15,0)),io.in.bits.a(15,0).pad(32))
    magnitude:=Mux(inputDouble,io.in.bits.a,Mux(small,smallInt,io.in.bits.a(31,0)).pad(64));leading:=0.U
    negative:=io.in.bits.op===FpOp.fromInt.U && Mux(inputDouble,io.in.bits.a(63),Mux(small,io.in.bits.a(15),io.in.bits.a(31)))
    val integerOp=io.in.bits.op>=FpOp.toUInt.U && io.in.bits.op<=FpOp.toIntRtz.U
    val cast=io.in.bits.op===FpOp.convertFloat.U || io.in.bits.op===FpOp.convertOdd.U
    val fixedRm=io.in.bits.op===FpOp.toUIntRtz.U || io.in.bits.op===FpOp.toIntRtz.U || io.in.bits.op===FpOp.convertOdd.U
    val smallLegal=io.widthMode===5.U && (io.in.bits.op===FpOp.fromUInt.U || io.in.bits.op===FpOp.fromInt.U || io.in.bits.op===FpOp.convertFloat.U) ||
      io.widthMode===6.U && (io.in.bits.op===FpOp.toUInt.U || io.in.bits.op===FpOp.toInt.U || io.in.bits.op===FpOp.toUIntRtz.U || io.in.bits.op===FpOp.toIntRtz.U || io.in.bits.op===FpOp.convertFloat.U)
    val widthLegal=(io.widthMode<=2.U && (io.widthMode===0.U || io.in.bits.double===(io.widthMode===1.U)) || smallLegal && !io.in.bits.double) &&
      (!cast || io.widthMode===1.U || io.widthMode===2.U || smallLegal) && (io.in.bits.op=/=FpOp.convertOdd.U || io.widthMode===2.U)
    val legal=(integerOp || cast) && widthLegal && (io.in.bits.rounding<=4.U || fixedRm)
    response.illegal:= !legal
    state:=Mux(!legal,reply,Mux(io.in.bits.op===FpOp.fromUInt.U || io.in.bits.op===FpOp.fromInt.U,absoluteLow,toIntRecode))
  }
  // Absolute value is split across words. Source-width placement below makes
  // the subsequent normalization independent of the 16/32/64-bit input size.
  when(state===absoluteLow) {
    val sum=CarrySelect.add(magnitude(31,0)^Fill(32,negative),0.U(32.W),negative)
    magnitude:=Cat(magnitude(63,32),sum(31,0));carry:=sum(32);state:=absoluteHigh
  }
  when(state===absoluteHigh) {
    val sum=CarrySelect.add(magnitude(63,32)^Fill(32,negative),0.U(32.W),carry)
    // Place the effective integer MSB at bit 63 before normalization.
    // Absolute value has already been taken at its source width.
    magnitude:=Mux(sourceDouble,Cat(sum(31,0),magnitude(31,0)),
      Mux(widths===5.U,Cat(magnitude(15,0),0.U(48.W)),Cat(magnitude(31,0),0.U(32.W))))
    leading:=Mux(sourceDouble,0.U,Mux(widths===5.U,48.U,32.U));state:=normalize
  }
  // Skip zero bytes before shifting individual bits; leading preserves the
  // original integer exponent despite this variable-latency normalization.
  when(state===normalize) {
    when(magnitude===0.U || magnitude(63)) { state:=roundStart }
      .elsewhen(!magnitude(63,56).orR) { magnitude:=Cat(magnitude(55,0),0.U(8.W));leading:=leading+8.U }
      .otherwise { magnitude:=Cat(magnitude(62,0),false.B);leading:=leading+1.U }
  }
  // Exact recoded widening supplies a common binary64-sized source. Integer
  // and floating conversions round once, directly to the selected output size.
  val rec64=Reg(UInt(65.W))
  val raw=Wire(new RawFloat(11,64))
  raw.isNaN:=false.B;raw.isInf:=false.B;raw.isZero:=magnitude===0.U;raw.sign:=negative
  raw.sExp:=(2111.U(13.W)-leading).asSInt;raw.sig:=magnitude
  val r16=Module(new StagedRound(11,64,5,11,0))
  val r32=Module(new StagedRound(11,64,8,24,0));val r64=Module(new StagedRound(11,64,11,53,0))
  for(r<-Seq(r16,r32,r64)) {
    r.io.start:=(state===roundStart || state===toIntStart && floatCast) && !io.flush;r.io.flush:=io.flush
    r.io.in:=Mux(floatCast,resizeRawFloat(11,64,rawFloatFromRecFN(11,53,rec64)),raw)
    r.io.invalidExc:=floatCast && isSigNaNRawFloat(rawFloatFromRecFN(11,53,rec64));r.io.infiniteExc:=false.B;r.io.roundingMode:=mode;r.io.detectTininess:=true.B
  }
  when(state===roundStart) { state:=roundWait }
  when(state===roundWait && r16.io.done && r32.io.done && r64.io.done) {
    val half=floatCast && widths===6.U
    response.data:=Mux(half,fNFromRecFN(5,11,r16.io.out).pad(64),
      Mux(req.double,fNFromRecFN(11,53,r64.io.out),fNFromRecFN(8,24,r32.io.out).pad(64)))
    response.flags:=Mux(half,r16.io.exceptionFlags,Mux(req.double,r64.io.exceptionFlags,r32.io.exceptionFlags));state:=reply
  }
  // One integer conversion datapath selects 16-, 32- or 64-bit bounds and
  // exception values. Narrow results are zero-padded into the response word.
  val t64=Module(new StagedFloatToInt(11,53,64,flexible=true))
  t64.io.narrow.get:=Mux(widths===6.U,2.U,Mux(req.double,0.U,1.U))

  val raw16=Reg(new RawFloat(5,11));val raw32=Reg(new RawFloat(8,24));val norm64=Reg(UInt(6.W))
  when(state===toIntRecode) {
    raw16:=rawFloatFromFN(5,11,req.a(15,0))
    raw32:=FpBits.raw32(req.a);norm64:=countLeadingZeros(req.a(51,0));state:=toIntPack
  }
  when(state===toIntPack) {
    // Exact recoded widening keeps subnormals, NaN payload and signaling bit.
    // Final rounding/quieting happens only at the selected output precision.
    val exact=Mux(floatCast && widths===5.U,FpBits.wideRecRaw(raw16),FpBits.wideRecRaw(raw32))
    rec64:=Mux(sourceDouble,IeeeRecode(11,53,req.a,norm64),exact);state:=toIntStart
  }
  t64.io.in:=rec64
  for(t<-Seq(t64)) {
    t.io.start:=state===toIntStart && !floatCast && !io.flush;t.io.flush:=io.flush;t.io.roundingMode:=mode
    t.io.signedOut:=req.op===FpOp.toInt.U || req.op===FpOp.toIntRtz.U
  }
  when(state===toIntStart) { state:=Mux(floatCast,roundWait,toIntWait) }
  when(state===toIntWait && t64.io.done) {
    // The public fflags packet merges integer invalid/overflow into NV.
    val flags=t64.io.intExceptionFlags
    response.data:=t64.io.out
    response.flags:=Cat(flags(2)||flags(1),0.U(3.W),flags(0));state:=reply
  }
  // Reply data remains registered under backpressure; flush discards the owner.
  when(io.out.fire) { state:=idle }
  when(io.flush) { state:=idle }
}
