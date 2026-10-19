package vpu

import chisel3._
import chisel3.util._

/** Three registered local reductions. Inputs are already masked to one SEW.
  * Circular shifts repeat the element to 64 bits once, so every radix-4
  * level is independent of SEW. No 64-bit variable shifter/count chain.
  */
class BitManipPipeline extends Module {
  val io = IO(new Bundle {
    val in = Input(new LaneRequest)
    val result = Output(UInt(64.W))
  })
  val a=io.in.a;val sew=io.in.sew
  val mask=VecInit(Seq(7,15,31,63).map(_.U(6.W)))(sew)
  val amount=io.in.b(5,0)&mask
  val right=Mux(io.in.op===Op.rol.U,(-amount)(5,0)&mask,amount)
  val repeated=MuxLookup(sew,a)(Seq(0.U->Fill(8,a(7,0)),1.U->Fill(4,a(15,0)),2.U->Fill(2,a(31,0))))
  val r1=RegNext(MuxLookup(right(1,0),repeated)((1 to 3).map(i=>i.U->Cat(repeated(i-1,0),repeated(63,i)))))
  val amount1=RegNext(right);val amount2=RegNext(amount1)
  val r2=RegNext(MuxLookup(amount1(3,2),r1)((1 to 3).map(i=>i.U->Cat(r1(4*i-1,0),r1(63,4*i)))))
  val r3=RegNext(MuxLookup(amount2(5,4),r2)((1 to 3).map(i=>i.U->Cat(r2(16*i-1,0),r2(63,16*i)))))

  // Pad inactive low bits with ones: an all-zero SEW counts exactly SEW.
  val aligned=MuxLookup(sew,a)(Seq(0.U->Cat(a(7,0),0.U(56.W)),
    1.U->Cat(a(15,0),0.U(48.W)),2.U->Cat(a(31,0),0.U(32.W))))
  val padding=VecInit(Seq(56,48,32,0).map(n=>((BigInt(1)<<n)-1).U(64.W)))(sew)
  val countInput=Mux(io.in.op===Op.ctz.U,Reverse(a),aligned)|padding
  val counts=RegNext(VecInit((0 until 8).map(i=> {
    val byte=countInput(63-8*i,56-8*i)
    Mux(byte.orR,PriorityEncoder(Reverse(byte)).pad(4),8.U(4.W))
  })))
  def join(hi:UInt,lo:UInt,span:Int):UInt=Mux(hi===span.U,span.U+&lo,hi.pad(lo.getWidth+1))
  val counts2=RegNext(VecInit((0 until 4).map(i=>join(counts(2*i),counts(2*i+1),8))))
  val counts3=RegNext(VecInit((0 until 2).map(i=>join(counts2(2*i),counts2(2*i+1),16))))
  val count=join(counts3(0),counts3(1),32)
  val pops=RegNext(VecInit((0 until 8).map(i=>PopCount(a(8*i+7,8*i)))))
  val pops2=RegNext(VecInit((0 until 4).map(i=>pops(2*i)+&pops(2*i+1))))
  val pops3=RegNext(VecInit((0 until 2).map(i=>pops2(2*i)+&pops2(2*i+1))))
  val population=pops3(0)+&pops3(1)

  val brev8=Cat((0 until 8).reverse.map(i=>Reverse(a(8*i+7,8*i))))
  val reversed=MuxLookup(sew,Reverse(a))(Seq(0.U->Reverse(a(7,0)).pad(64),
    1.U->Reverse(a(15,0)).pad(64),2.U->Reverse(a(31,0)).pad(64)))
  val swapped=MuxLookup(sew,Cat((0 until 8).map(i=>a(8*i+7,8*i))))(Seq(
    0.U->a,1.U->Cat(a(7,0),a(15,8)).pad(64),
    2.U->Cat((0 until 4).map(i=>a(8*i+7,8*i))).pad(64)))
  val bitValue=Mux(io.in.op===Op.brev8.U,brev8,Mux(io.in.op===Op.brev.U,reversed,swapped))
  val bits3=ShiftRegister(bitValue,3)
  val op3=ShiftRegister(io.in.op,3)
  io.result:=MuxLookup(op3,bits3)(Seq(Op.rol.U->r3,Op.ror.U->r3,
    Op.clz.U->count.pad(64),Op.ctz.U->count.pad(64),Op.cpop.U->population.pad(64)))
}
