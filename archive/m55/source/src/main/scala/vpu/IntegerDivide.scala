package vpu

import chisel3._
import chisel3.util._

/** Capacity-one restoring divider. Each quotient bit takes four cycles;
  * the 65-bit trial subtraction is split into 32-bit and 33-bit stages.
  * Magnitude conversion and result sign correction are split at bit 32.
  */
class IntegerDivide extends Module {
  val io=IO(new Bundle {
    val flush=Input(Bool());val in=Flipped(Decoupled(new LaneRequest));val out=Decoupled(new LaneResponse)
  })
  val Seq(idle,aLow,aHigh,bLow,bHigh,load,shift,subtractLow,subtractHigh,choose,selectResult,signLow,signHigh,reply)=Enum(14)
  val state=RegInit(idle)
  val a=Reg(UInt(64.W));val b=Reg(UInt(64.W));val sew=Reg(UInt(2.W));val tag=Reg(UInt(8.W))
  val negativeA=Reg(Bool());val negativeB=Reg(Bool());val negativeQ=Reg(Bool());val remainderOp=Reg(Bool())
  val carry=Reg(Bool());val low=Reg(UInt(32.W));val difference=Reg(UInt(65.W));val accept=Reg(Bool())
  val q=Reg(UInt(64.W));val r=Reg(UInt(65.W));val remaining=Reg(UInt(7.W));val result=Reg(UInt(64.W))
  val masks=VecInit(Seq(8,16,32,64).map(w=>((BigInt(1)<<w)-1).U(64.W)))
  io.in.ready:=state===idle && !io.flush;io.out.valid:=state===reply && !io.flush
  io.out.bits.data:=result & masks(sew);io.out.bits.tag:=tag
  when(io.in.fire) {
    val aa=io.in.bits.a & masks(io.in.bits.sew);val bb=io.in.bits.b & masks(io.in.bits.sew)
    val signed=io.in.bits.op===Op.div.U || io.in.bits.op===Op.rem.U
    val sa=signed && VecInit(Seq(7,15,31,63).map(aa(_)))(io.in.bits.sew)
    val sb=signed && VecInit(Seq(7,15,31,63).map(bb(_)))(io.in.bits.sew)
    a:=aa;b:=bb;negativeA:=sa;negativeB:=sb;negativeQ:=(sa^sb) && bb.orR
    remainderOp:=io.in.bits.op===Op.rem.U || io.in.bits.op===Op.remu.U
    sew:=io.in.bits.sew;tag:=io.in.bits.tag;state:=aLow
  }
  // Four parallel 8-bit increments. Carry into each group is a prefix
  // reduction, rather than a serial 32-bit ripple after the sign XOR.
  def negateWord(x:UInt,negative:Bool,cin:Bool):UInt = {
    val flipped=x ^ Fill(32,negative)
    val words=(0 until 32 by 8).map { lo=>
      val carry=if(lo==0)cin else cin && flipped(lo-1,0).andR
      (flipped(lo+7,lo)+carry)(7,0)
    }
    Cat(cin && flipped.andR,Cat(words.reverse))
  }
  when(state===aLow) {
    val sum=negateWord(a(31,0),negativeA,negativeA)
    a:=Cat(a(63,32),sum(31,0));carry:=sum(32);state:=aHigh
  }
  when(state===aHigh) {
    val sum=negateWord(a(63,32),negativeA,carry)
    a:=Cat(sum(31,0),a(31,0)) & masks(sew);state:=bLow
  }
  when(state===bLow) {
    val sum=negateWord(b(31,0),negativeB,negativeB)
    b:=Cat(b(63,32),sum(31,0));carry:=sum(32);state:=bHigh
  }
  when(state===bHigh) {
    val sum=negateWord(b(63,32),negativeB,carry)
    b:=Cat(sum(31,0),b(31,0)) & masks(sew);state:=load
  }
  when(state===load) {
    q:=VecInit(Seq(8,16,32,64).map(w=>(a<<(64-w))(63,0)))(sew)
    r:=0.U;remaining:=VecInit(Seq(8,16,32,64).map(_.U(7.W)))(sew);state:=shift
  }
  when(state===shift) { r:=Cat(r(63,0),q(63));state:=subtractLow }
  when(state===subtractLow) {
    val sum=CarrySelect.add(r(31,0),(~b(31,0)).asUInt,true.B)
    low:=sum(31,0);carry:=sum(32);state:=subtractHigh
  }
  when(state===subtractHigh) {
    val sum=CarrySelect.add(r(64,32),(~Cat(false.B,b(63,32))).asUInt,carry)
    difference:=Cat(sum(32,0),low);accept:=sum(33);state:=choose
  }
  when(state===choose) {
    r:=Mux(accept,difference,r);q:=Cat(q(62,0),accept);remaining:=remaining-1.U
    state:=Mux(remaining===1.U,selectResult,shift)
  }
  when(state===selectResult) { result:=Mux(remainderOp,r(63,0),q);state:=signLow }
  val negative=Mux(remainderOp,negativeA,negativeQ)
  when(state===signLow) {
    val sum=negateWord(result(31,0),negative,negative)
    result:=Cat(result(63,32),sum(31,0));carry:=sum(32);state:=signHigh
  }
  when(state===signHigh) {
    val sum=negateWord(result(63,32),negative,carry)
    result:=Cat(sum(31,0),result(31,0));state:=reply
  }
  when(io.out.fire) { state:=idle }
  when(io.flush) { state:=idle }
}
