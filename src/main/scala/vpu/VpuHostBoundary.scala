package vpu

import chisel3._
import chisel3.util._
import _root_.circt.stage.ChiselStage
import java.nio.file.{Files,Paths}

class VpuHostReply extends Bundle {
  val completion=new Completion
  val memory=Bool();val stopped=Bool();val exception=Bool()
  val cause=UInt(6.W);val tval=UInt(64.W);val rawMemoryCause=UInt(6.W);val element=UInt(8.W)
}
/** Same-clock, capacity-one irrevocable CPU retirement boundary. No CPU core
  * integration implied. Host token packing is opaque and always 80 bits.
  * reply.ready authorizes final VPU architectural commit and CPU retirement
  * (or fault/interrupt handling). Memory prefix commits are NOT rollbackable.
  */
class VpuHostBoundary extends Module {
  val io=IO(new Bundle {
    val headValid=Input(Bool());val headToken=Input(UInt(80.W))
    val olderMemoryDrained=Input(Bool());val olderFpDrained=Input(Bool())
    val stop=Input(Bool())
    val offer=Flipped(Decoupled(new Command));val reply=Decoupled(new VpuHostReply)
    val command=Decoupled(new Command);val completion=Flipped(Decoupled(new Completion))
    val memoryStatus=Flipped(Valid(new VectorMemoryStatus))
    val vpuFlush=Output(Bool());val active=Output(Bool());val protocolError=Output(Bool())
    val canceled=Valid(UInt(80.W))
  })
  val active=RegInit(false.B);val memory=Reg(Bool());val store=Reg(Bool())
  val token=Reg(UInt(80.W));val instruction=Reg(UInt(32.W));val poisoned=RegInit(false.B)
  val cancel=active && !memory && io.stop
  val identity=io.completion.bits.token===token && io.completion.bits.instruction===instruction
  val metadata=io.memoryStatus.valid===memory
  val malformed=(io.completion.valid && (!active || !identity || !metadata)) ||
    (io.memoryStatus.valid && !io.completion.valid)
  val eligible= !active && !poisoned && !malformed && !io.stop && io.headValid &&
    io.headToken===io.offer.bits.token && io.olderMemoryDrained && io.olderFpDrained
  io.command.valid:=io.offer.valid && eligible;io.command.bits:=io.offer.bits
  io.offer.ready:=io.command.ready && eligible
  io.reply.valid:=active && !poisoned && !malformed && !cancel && io.completion.valid
  io.reply.bits.completion:=io.completion.bits
  io.reply.bits.memory:=memory
  io.reply.bits.stopped:=memory && io.memoryStatus.bits.interrupted
  val illegal=io.completion.bits.illegal
  val memoryFault=memory && io.memoryStatus.bits.fault
  io.reply.bits.exception:=illegal || memoryFault
  // VectorMemoryEngine reports architectural physical causes: 4/5 load,
  // 6/7 store. Code 1 was an obsolete synthetic-peer convention.
  val misaligned=Mux(store,io.memoryStatus.bits.cause===6.U,io.memoryStatus.bits.cause===4.U)
  val memoryCause=Mux(misaligned,Mux(store,6.U,4.U),Mux(store,7.U,5.U))
  io.reply.bits.cause:=Mux(illegal,2.U,Mux(memoryFault,memoryCause,0.U))
  io.reply.bits.tval:=Mux(illegal,instruction.pad(64),Mux(memoryFault,io.memoryStatus.bits.address,0.U))
  io.reply.bits.rawMemoryCause:=Mux(memory,io.memoryStatus.bits.cause,0.U)
  io.reply.bits.element:=Mux(memory,io.memoryStatus.bits.element,0.U)
  when(illegal || memoryFault || io.reply.bits.stopped) {io.reply.bits.completion.writesScalar:=false.B}
  io.completion.ready:=active && !poisoned && !malformed && !cancel && metadata && io.reply.ready
  io.vpuFlush:=io.stop;io.active:=active;io.protocolError:=poisoned || malformed
  io.canceled.valid:=cancel;io.canceled.bits:=token
  when(io.command.fire) {
    active:=true.B;token:=io.offer.bits.token;instruction:=io.offer.bits.instruction
    memory:=io.offer.bits.instruction(6,0)==="h07".U || io.offer.bits.instruction(6,0)==="h27".U
    store:=io.offer.bits.instruction(6,0)==="h27".U
  }
  when(io.reply.fire || cancel) {active:=false.B}
  // Wrong/stale completions must not be consumed: completion.fire would
  // otherwise publish architectural VPU state with no matching CPU owner.
  when(malformed) {poisoned:=true.B}
}
object GenerateHostBoundary extends App {
  val p=Paths.get(args(0));Files.createDirectories(p.getParent)
  val text=ChiselStage.emitSystemVerilog(new VpuHostBoundary,firtoolOpts=Array(
    "-disable-all-randomization","-strip-debug-info","--lowering-options=disallowLocalVariables,disallowPackedArrays"))
  val marker="(?m)^// ----- 8< ----- FILE \"([^\"]+)\" ----- 8< -----\\r?\\n".r
  val chunks=marker.findAllMatchIn(text).toSeq
  Files.writeString(p,text.take(chunks.headOption.map(_.start).getOrElse(text.length)))
  for((m,i)<-chunks.zipWithIndex) {
    val part=p.getParent.resolve(m.group(1));Files.createDirectories(part.getParent)
    Files.writeString(part,text.substring(m.end,chunks.lift(i+1).map(_.start).getOrElse(text.length)))
  }
}
