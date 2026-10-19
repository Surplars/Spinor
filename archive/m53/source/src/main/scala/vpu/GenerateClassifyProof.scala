package vpu

import chisel3._
import hardfloat._
import _root_.circt.stage.ChiselStage
import java.nio.file.{Files,Paths}

/** All-pattern IEEE classification equivalence, including signaling NaNs. */
class ClassifyProof extends Module {
  val io=IO(new Bundle {
    val bits=Input(UInt(64.W));val mismatch=Output(Bool())
  })
  io.mismatch := (FpBits.classify(io.bits,11,53) =/=
    classifyRecFN(11,53,recFNFromFN(11,53,io.bits))) ||
    (FpBits.classify(io.bits(31,0),8,24) =/=
      classifyRecFN(8,24,recFNFromFN(8,24,io.bits(31,0))))
}
object GenerateClassifyProof extends App {
  val path=Paths.get(args(0));Files.createDirectories(path.getParent)
  val rtl=ChiselStage.emitSystemVerilog(new ClassifyProof,
    firtoolOpts=Array("-disable-all-randomization","-strip-debug-info"))
  val marker=rtl.indexOf("// ----- 8< ----- FILE ")
  Files.writeString(path,if(marker<0)rtl else rtl.take(marker))
}
