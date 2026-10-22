package vpu

import chisel3._
import hardfloat._
import _root_.circt.stage.ChiselStage
import java.nio.file.{Files,Paths}

/** Arbitrary recoded bits, including noncanonical encodings, and arbitrary
  * enabled captures/holds. Compare with the pinned combinational decoder.
  */
class UnrecodeProof extends Module {
  val io=IO(new Bundle {
    val bits=Input(UInt(65.W));val capture=Input(Bool());val mismatch=Output(Bool())
  })
  // Ignore uninitialized output until the first enabled capture. Thereafter
  // both reference and DUT must retain their last result when capture is low.
  val valid=RegInit(false.B)
  when(io.capture) {valid:=true.B}
  val errors=for((e,s)<-Seq((8,24),(11,53)))yield {
    val dut=Module(new StagedIeeeUnrecode(e,s))
    dut.io.in:=io.bits(e+s,0);dut.io.capture:=io.capture
    val reference=Reg(UInt((e+s).W))
    when(io.capture) {reference:=fNFromRecFN(e,s,io.bits(e+s,0))}
    valid && dut.io.out=/=reference
  }
  io.mismatch:=errors.reduce(_||_)
}
/** Emit the enabled-capture recoded-to-IEEE equivalence miter. */
object GenerateUnrecodeProof extends App {
  val path=Paths.get(args(0));Files.createDirectories(path.getParent)
  val rtl=ChiselStage.emitSystemVerilog(new UnrecodeProof,firtoolOpts=Array("-disable-all-randomization","-strip-debug-info","--lowering-options=disallowLocalVariables,disallowPackedArrays"))
  val marker=rtl.indexOf("// ----- 8< ----- FILE ")
  Files.writeString(path,if(marker<0)rtl else rtl.take(marker))
}
