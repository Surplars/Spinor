package vpu

import chisel3._
import chisel3.util._

class ValenceOffer(robBits: Int, tagBits: Int) extends Bundle {
  val index = UInt(robBits.W)
  val tag = UInt(tagBits.W)
  val instruction = UInt(32.W)
  val scalar = UInt(64.W)
  val scalar2 = UInt(64.W)
  val avl = UInt(64.W)
}

class ValenceReply(robBits: Int, tagBits: Int) extends Bundle {
  val index = UInt(robBits.W)
  val tag = UInt(tagBits.W)
  val data = UInt(64.W)
  val writesScalar = Bool()
  val exception = Bool()
  val cause = UInt(64.W)
  val tval = UInt(64.W)
}

/** SAME-CLOCK candidate boundary for Valence's default 32-entry ROB and
  * 64-bit allocation tag. This is not wired into the evolving scalar core.
  * Launch only at irrevocable head after scalar memory/FP work drains. A
  * single owner is retained through result backpressure. Stale replies are
  * consumed and discarded, never routed to a reused ROB slot.
  * Host must keep ownership until reply.fire, including interrupt/recovery.
  */
class ValenceBoundary(robBits: Int = 5, tagBits: Int = 64) extends Module {
  require(robBits+tagBits <= Parameters.tokenBits)
  val io = IO(new Bundle {
    val flush = Input(Bool())
    val headValid = Input(Bool())
    val headIndex = Input(UInt(robBits.W))
    val headTag = Input(UInt(tagBits.W))
    val olderMemoryDrained = Input(Bool())
    val olderFpDrained = Input(Bool())
    val offer = Flipped(Decoupled(new ValenceOffer(robBits,tagBits)))
    val reply = Decoupled(new ValenceReply(robBits,tagBits))
    val command = Decoupled(new Command)
    val completion = Flipped(Decoupled(new Completion))
    val active = Output(Bool())
    val discarded = Output(Bool())
  })
  val active = RegInit(false.B)
  val owner = Reg(UInt(Parameters.tokenBits.W))
  val packed = Cat(io.offer.bits.tag,io.offer.bits.index).pad(Parameters.tokenBits)
  val eligible = io.headValid && io.offer.bits.index === io.headIndex && io.offer.bits.tag === io.headTag &&
    io.olderMemoryDrained && io.olderFpDrained && !active && !io.flush
  io.command.valid := io.offer.valid && eligible
  io.command.bits.instruction := io.offer.bits.instruction
  io.command.bits.scalar := io.offer.bits.scalar
  io.command.bits.scalar2 := io.offer.bits.scalar2
  io.command.bits.avl := io.offer.bits.avl
  io.command.bits.token := packed
  io.offer.ready := io.command.ready && eligible
  val matches = active && io.completion.bits.token === owner
  io.reply.valid := io.completion.valid && matches && !io.flush
  io.reply.bits.index := owner(robBits-1,0)
  io.reply.bits.tag := owner(tagBits+robBits-1,robBits)
  io.reply.bits.data := io.completion.bits.scalar
  io.reply.bits.writesScalar := io.completion.bits.writesScalar && !io.completion.bits.illegal
  io.reply.bits.exception := io.completion.bits.illegal
  io.reply.bits.cause := Mux(io.completion.bits.illegal,2.U,0.U)
  io.reply.bits.tval := Mux(io.completion.bits.illegal,io.completion.bits.instruction.pad(64),0.U)
  io.completion.ready := !io.flush && Mux(matches,io.reply.ready,true.B)
  io.discarded := io.completion.fire && !matches
  io.active := active
  when(io.command.fire) { owner := packed; active := true.B }
  when(io.reply.fire || io.flush) { active := false.B }
}
