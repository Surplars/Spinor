package vpu

import chisel3._
import chisel3.util._

/** Serialized byte arithmetic and three radix-4 shift stages. No architectural
  * state, no vector-sized snapshot, and no dependency on the ordinary II=1 ALU.
  * Modes 0..3: adc/sbc/madc/msbc; 4..7: saturating add/sub u/s;
  * 8..11: averaging add/sub u/s; 12/13: rounding logical/arithmetic right shift.
  */
class FixedPointLane extends Module {
  val io=IO(new Bundle {
    val flush=Input(Bool())
    val in=Flipped(Decoupled(new Bundle {
      val a=UInt(64.W);val b=UInt(64.W);val sew=UInt(2.W)
      val mode=UInt(4.W);val rounding=UInt(2.W);val carry=Bool();val tag=UInt(8.W)
    }))
    val out=Decoupled(new Bundle {val data=UInt(64.W);val saturated=Bool();val tag=UInt(8.W)})
  })
  val Seq(idle,arithmetic,analyze,shift0,shift1,shift2,round,done)=Enum(8)
  val state=RegInit(idle);val mode=Reg(UInt(4.W));val rounding=Reg(UInt(2.W))
  val sew=Reg(UInt(2.W));val tag=Reg(UInt(8.W));val byte=Reg(UInt(3.W));val last=Reg(UInt(3.W))
  val a=Reg(UInt(64.W));val b=Reg(UInt(64.W));val sum=Reg(Vec(8,UInt(8.W)))
  val carry=Reg(Bool());val subtract=Reg(Bool());val secondPass=Reg(Bool())
  val signA=Reg(Bool());val signB=Reg(Bool());val signResult=Reg(Bool())
  val data=Reg(UInt(64.W));val saturated=Reg(Bool())
  val shifted=Reg(UInt(65.W));val amount=Reg(UInt(6.W));val sticky=Reg(Bool())
  val mask=VecInit(Seq(8,16,32,64).map(n=>((BigInt(1)<<n)-1).U(64.W)))(sew)
  io.in.ready:=state===idle && !io.flush
  io.out.valid:=state===done && !io.flush
  io.out.bits.data:=data;io.out.bits.saturated:=saturated;io.out.bits.tag:=tag
  when(io.in.fire) {
    val p=io.in.bits
    val sub=p.mode===1.U || p.mode===3.U || p.mode===6.U || p.mode===7.U || p.mode===10.U || p.mode===11.U
    val inputMask=VecInit(Seq(8,16,32,64).map(n=>((BigInt(1)<<n)-1).U(64.W)))(p.sew)
    mode:=p.mode;rounding:=p.rounding;sew:=p.sew;tag:=p.tag
    a:=p.a&inputMask;b:=p.b&inputMask;byte:=0.U;last:=VecInit(Seq(0,1,3,7).map(_.U(3.W)))(p.sew)
    subtract:=sub;carry:=Mux(sub,!p.carry,p.carry);secondPass:=false.B;saturated:=false.B
    sum.foreach(_:=0.U)
    amount:=p.b(5,0)&VecInit(Seq(7,15,31,63).map(_.U(6.W)))(p.sew)
    val signedA=MuxLookup(p.sew,p.a)(Seq(
      0.U->Cat(Fill(56,p.a(7)),p.a(7,0)),1.U->Cat(Fill(48,p.a(15)),p.a(15,0)),2.U->Cat(Fill(32,p.a(31)),p.a(31,0))))
    shifted:=Cat(Mux(p.mode===13.U,signedA,p.a&inputMask),0.U(1.W));sticky:=false.B
    state:=Mux(p.mode>=12.U,shift0,arithmetic)
  }
  when(state===arithmetic) {
    val part=CarrySelect.add(a(7,0),b(7,0)^Fill(8,subtract),carry)
    sum(byte):=part(7,0);carry:=part(8);a:=a>>8;b:=b>>8;byte:=byte+1.U
    when(byte===last) {
      signA:=a(7);signB:=b(7);signResult:=part(7)
      state:=Mux(secondPass,done,analyze)
    }
    when(secondPass) {data:=Cat((0 until 8).reverse.map(i=>Mux(byte===i.U,part(7,0),sum(i))))&mask}
  }
  def increment(guard:Bool,tail:Bool,lsb:Bool):Bool = MuxLookup(rounding,false.B)(Seq(
    0.U->guard,1.U->(guard && (tail || lsb)),3.U->(!lsb && (guard || tail))))
  when(state===analyze) {
    val raw=sum.asUInt&mask
    data:=raw;state:=done
    when(mode<4.U) {when(mode(1)) {data:=Mux(subtract,!carry,carry)}}
    .elsewhen(mode<8.U) {
      val signedOverflow=((signA ^ signB)===subtract) && (signResult=/=signA)
      val overflow=Mux(mode(0),signedOverflow,Mux(subtract,!carry,carry))
      val maxSigned=mask>>1
      val limit=Mux(mode(0),Mux(signA,mask^maxSigned,maxSigned),Mux(subtract,0.U,mask))
      data:=Mux(overflow,limit,raw);saturated:=overflow
    }.otherwise {
      // Exact SEW+1 sum/difference, then shift and round before truncation.
      val signedTop=Mux(signA ^ signB,Mux(subtract,signA,signResult),Mux(subtract,signResult,signA))
      val top=Mux(mode(0),signedTop,Mux(subtract,!carry,carry))
      val average=MuxLookup(sew,Cat(top,raw(63,1)))(Seq(
        0.U->Cat(top,raw(7,1)).pad(64),1.U->Cat(top,raw(15,1)).pad(64),2.U->Cat(top,raw(31,1)).pad(64)))
      a:=average;b:=0.U;subtract:=false.B;carry:=increment(raw(0),false.B,raw(1))
      byte:=0.U;secondPass:=true.B;state:=arithmetic
    }
  }
  def shiftStage(bits:UInt,next:UInt,scale:Int):Unit = {
    val choices=(0 until 4).map { k =>
      val distance=k*scale
      val value=if(distance==0)shifted else Mux(mode===13.U,(shifted.asSInt>>distance).pad(65).asUInt,shifted>>distance)
      val lost=if(distance==0)false.B else shifted(distance-1,0).orR
      k.U->Cat(sticky || lost,value.pad(65))
    }
    val result=MuxLookup(bits,Cat(sticky,shifted))(choices)
    shifted:=result(64,0);sticky:=result(65);state:=next
  }
  when(state===shift0) {shiftStage(amount(1,0),shift1,1)}
  when(state===shift1) {shiftStage(amount(3,2),shift2,4)}
  when(state===shift2) {shiftStage(amount(5,4),round,16)}
  when(state===round) {
    a:=shifted(64,1)&mask;b:=0.U;subtract:=false.B
    carry:=increment(shifted(0),sticky,shifted(1));byte:=0.U;secondPass:=true.B;state:=arithmetic
  }
  when(io.out.fire) {state:=idle}
  when(io.flush) {state:=idle}
}
