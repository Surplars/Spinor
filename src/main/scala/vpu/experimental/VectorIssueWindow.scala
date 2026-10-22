package vpu

import chisel3._
import chisel3.util._
import _root_.circt.stage.ChiselStage
import java.nio.file.{Files,Paths}

/** Descriptor for the experimental scheduler; it contains no vector operands.
  * Read/write masks include every group member, v0 predicate and old vd source.
  * Configuration, CSR and memory commands must set the barrier bit.
  */
class WindowCommand extends Bundle {
  val reads=UInt(32.W);val writes=UInt(32.W)
  val unit=UInt(2.W);val barrier=Bool()
  val payload=UInt(128.W);val tag=UInt(8.W)
}
/** Experimental eight-slot scheduler, not connected to the production VPU.
  * At most one dispatch/issue/retire per cycle; registered issue selection has
  * II=2. Results remain private candidates until ordered retirement publishes
  * them. The external executor must cancel/drain all effects before flushAck
  * and must never send an older completion after that acknowledgement.
  */
class VectorIssueWindow extends Module {
  val io=IO(new Bundle {
    val flush=Input(Bool());val flushAck=Input(Bool())
    val command=Flipped(Decoupled(new WindowCommand))
    val unitReady=Input(UInt(4.W))
    val issue=Decoupled(new Bundle { val slot=UInt(3.W);val unit=UInt(2.W);val payload=UInt(128.W) })
    val complete=Flipped(Valid(new Bundle {val slot=UInt(3.W);val fault=Bool()}))
    val retire=Decoupled(new Bundle {val slot=UInt(3.W);val tag=UInt(8.W);val fault=Bool()})
    val draining=Output(Bool());val occupancy=Output(UInt(4.W))
  })
  // Physical slots form an in-order retirement ring. Dependency masks name
  // slots, so retirement must remove an edge before the same slot is reused.
  val valid=RegInit(VecInit(Seq.fill(8)(false.B)))
  val issued=Reg(Vec(8,Bool()));val done=Reg(Vec(8,Bool()));val faults=Reg(Vec(8,Bool()))
  val reads=Reg(Vec(8,UInt(32.W)));val writes=Reg(Vec(8,UInt(32.W)))
  val units=Reg(Vec(8,UInt(2.W)));val barriers=Reg(Vec(8,Bool()))
  val dependencies=Reg(Vec(8,UInt(8.W)))
  // Descriptors, not vector register contents. No full-vector FF snapshots.
  val descriptors=Mem(8,UInt(136.W))
  val head=RegInit(0.U(3.W));val tail=RegInit(0.U(3.W));val count=RegInit(0.U(4.W))
  val draining=RegInit(false.B)
  val held=RegInit(false.B);val selected=Reg(UInt(3.W))
  val faultPending=(0 until 8).map(i=>valid(i)&&done(i)&&faults(i)).reduce(_||_)
  val active= !io.flush && !draining
  io.draining:=draining;io.occupancy:=count
  io.command.ready:=active && !faultPending && count<8.U
  io.issue.valid:=held && active
  io.issue.bits.slot:=selected;io.issue.bits.unit:=units(selected)
  io.issue.bits.payload:=descriptors(selected)(127,0)
  io.retire.valid:=active && count=/=0.U && done(head)
  io.retire.bits.slot:=head;io.retire.bits.tag:=descriptors(head)(135,128)
  io.retire.bits.fault:=faults(head)
  // Conservatively retain RAW/WAR/WAW dependencies until retirement. This
  // needs no physical-register renaming, operand forwarding or bank snapshots.
  val eligible=Wire(Vec(8,Bool()))
  for(age<-0 until 8) {
    val slot=(head+age.U)(2,0)
    val blocked=(dependencies(slot)&valid.asUInt).orR
    eligible(age):=valid(slot) && !issued(slot) && !blocked && io.unitReady(units(slot))
  }
  when(active) {
    // Select the oldest eligible entry, then hold its descriptor until issue
    // handshakes. A registered selection avoids a priority encoder on payload.
    when(!held && !faultPending && eligible.asUInt.orR) {
      selected:=(head+PriorityEncoder(eligible.asUInt))(2,0);held:=true.B
    }
    when(io.issue.fire) { issued(selected):=true.B;held:=false.B }
    when(io.complete.valid) {
      assert(valid(io.complete.bits.slot)&&issued(io.complete.bits.slot)&& !done(io.complete.bits.slot),"completion has no live issued owner")
      done(io.complete.bits.slot):=true.B;faults(io.complete.bits.slot):=io.complete.bits.fault
    }
    // Only the head can retire. Simultaneous dispatch excludes the retiring
    // slot from its new hazards, while existing entries lose that same edge.
    when(io.retire.fire) {
      valid(head):=false.B;head:=head+1.U
      // Remove the edge before its physical slot can be reused by a younger
      // instruction. Keeping stale slot bits could create a false dependency.
      for(i<-0 until 8) {dependencies(i):=dependencies(i)& ~UIntToOH(head,8)}
    }
    when(io.command.fire) {
      valid(tail):=true.B;issued(tail):=false.B;done(tail):=false.B;faults(tail):=false.B
      reads(tail):=io.command.bits.reads;writes(tail):=io.command.bits.writes
      units(tail):=io.command.bits.unit;barriers(tail):=io.command.bits.barrier
      val hazards=VecInit((0 until 8).map { older=>
        valid(older) && (barriers(older) || io.command.bits.barrier ||
          (writes(older)&(io.command.bits.reads|io.command.bits.writes)).orR ||
          (reads(older)&io.command.bits.writes).orR)
      }).asUInt
      dependencies(tail):=hazards & ~Mux(io.retire.fire,UIntToOH(head,8),0.U(8.W))
      descriptors.write(tail,Cat(io.command.bits.tag,io.command.bits.payload));tail:=tail+1.U
    }
    when(io.command.fire =/= io.retire.fire) {count:=Mux(io.command.fire,count+1.U,count-1.U)}
  }
  // A fault is reported only at the head. Cancel younger work using the same
  // drain handshake as explicit flush, before any slot can be reused.
  when(io.flush || (io.retire.fire && io.retire.bits.fault)) {
    valid.foreach(_:=false.B);head:=0.U;tail:=0.U;count:=0.U;held:=false.B;draining:=true.B
  }.elsewhen(draining && io.flushAck) {draining:=false.B}
}
/** Export the isolated scheduling experiment for its dedicated testbench. */
object GenerateIssueWindow extends App {
  val p=Paths.get(args(0));Files.createDirectories(p.getParent)
  val text=ChiselStage.emitSystemVerilog(new VectorIssueWindow,firtoolOpts=Array(
    "-disable-all-randomization","-strip-debug-info","--lowering-options=disallowLocalVariables,disallowPackedArrays"))
  val marker=text.indexOf("// ----- 8< ----- FILE ")
  Files.writeString(p,if(marker<0)text else text.take(marker))
}
