package vpu

import chisel3._
import chisel3.util._

/** Capacity-one integer multiplier, one reused unsigned 16x16 product.
  * Each partial product is registered, aligned, then added in four 32-bit
  * steps. Signed high products use two separately staged modular corrections.
  * Small area is deliberate; this is not a one-element-per-cycle multiplier.
  */
class IntegerMultiply extends Module {
  val io=IO(new Bundle {
    val flush=Input(Bool());val in=Flipped(Decoupled(new LaneRequest));val out=Decoupled(new LaneResponse)
  })
  val Seq(idle,multiply,align,accumulate,extract,correctLow,correctHigh,reply)=Enum(8)
  val state=RegInit(idle)
  val a=Reg(UInt(64.W));val b=Reg(UInt(64.W));val sew=Reg(UInt(2.W));val op=Reg(UInt(Op.width.W))
  val tag=Reg(UInt(8.W));val signA=Reg(Bool());val signB=Reg(Bool())
  val i=Reg(UInt(2.W));val j=Reg(UInt(2.W));val limit=Reg(UInt(2.W));val word=Reg(UInt(2.W))
  val product=Reg(UInt(32.W));val term=Reg(Vec(4,UInt(32.W)));val acc=Reg(Vec(4,UInt(32.W)))
  val carry=Reg(Bool());val result=Reg(UInt(64.W));val correction=Reg(UInt(64.W));val second=Reg(Bool())
  val masks=VecInit(Seq(8,16,32,64).map(w=>((BigInt(1)<<w)-1).U(64.W)))
  io.in.ready:=state===idle && !io.flush
  io.out.valid:=state===reply && !io.flush
  io.out.bits.data:=result & masks(sew);io.out.bits.tag:=tag
  when(io.in.fire) {
    a:=io.in.bits.a & masks(io.in.bits.sew);b:=io.in.bits.b & masks(io.in.bits.sew)
    sew:=io.in.bits.sew;op:=io.in.bits.op;tag:=io.in.bits.tag
    val sa=VecInit(Seq(7,15,31,63).map(io.in.bits.a(_)))(io.in.bits.sew)
    val sb=VecInit(Seq(7,15,31,63).map(io.in.bits.b(_)))(io.in.bits.sew)
    signA:=sa && (io.in.bits.op===Op.mulh.U || io.in.bits.op===Op.mulhsu.U)
    signB:=sb && io.in.bits.op===Op.mulh.U
    limit:=MuxLookup(io.in.bits.sew,0.U)(Seq(2.U->1.U,3.U->3.U))
    i:=0.U;j:=0.U;acc.foreach(_:=0.U);state:=multiply
  }
  val aWords=VecInit((0 until 4).map(k=>a(16*k+15,16*k)))
  val bWords=VecInit((0 until 4).map(k=>b(16*k+15,16*k)))
  when(state===multiply) { product:=aWords(i)*bWords(j);state:=align }
  when(state===align) {
    val shifted=(product.pad(128)<<Cat(i+&j,0.U(4.W)))(127,0)
    for(k<-0 until 4)term(k):=shifted(32*k+31,32*k)
    word:=0.U;carry:=false.B;state:=accumulate
  }
  // Rotate banks instead of putting a dynamic 4:1 read/write mux around
  // the carry chain. Four steps restore canonical word order.
  def addCarry(x:UInt,y:UInt,cin:Bool):UInt = CarrySelect.add(x,y,cin)
  when(state===accumulate) {
    val sum=addCarry(acc(0),term(0),carry)
    for(k<-0 until 3) { acc(k):=acc(k+1);term(k):=term(k+1) }
    acc(3):=sum(31,0);term(3):=term(0);carry:=sum(32)
    when(word===3.U) {
      when(j===limit) {
        j:=0.U
        when(i===limit) { state:=extract }.otherwise { i:=i+1.U;state:=multiply }
      }.otherwise { j:=j+1.U;state:=multiply }
    }.otherwise { word:=word+1.U }
  }
  when(state===extract) {
    val full=acc.asUInt
    val high=VecInit(Seq(8,16,32,64).map(w=>full(2*w-1,w).pad(64)))(sew)
    result:=Mux(op===Op.mul.U,full(63,0),high)
    correction:=Mux(signA,b,0.U);carry:=true.B;second:=false.B
    state:=Mux(op===Op.mul.U,reply,correctLow)
  }
  when(state===correctLow) {
    val sum=addCarry(result(31,0),(~correction(31,0)).asUInt,carry)
    result:=Cat(result(63,32),sum(31,0));carry:=sum(32);state:=correctHigh
  }
  when(state===correctHigh) {
    val sum=addCarry(result(63,32),(~correction(63,32)).asUInt,carry)
    result:=Cat(sum(31,0),result(31,0))
    when(second) { state:=reply }.otherwise {
      correction:=Mux(signB,a,0.U);carry:=true.B;second:=true.B;state:=correctLow
    }
  }
  when(io.out.fire) { state:=idle }
  when(io.flush) { state:=idle }
}
