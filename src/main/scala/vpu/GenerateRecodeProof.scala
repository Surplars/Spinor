package vpu

import chisel3._
import hardfloat._
import circt.stage.ChiselStage
import java.nio.file.{Files,Paths}

/** Verification-only miter against the pinned upstream combinational encoder.
  * Pipeline ownership/flush are checked separately by the numerical tests.
  */
class IeeeRecodeProof extends Module {
  val io=IO(new Bundle { val bits=Input(UInt(64.W));val mismatch=Output(Bool()) })
  val n32=Wire(UInt(5.W));val n64=Wire(UInt(6.W))
  n32:=countLeadingZeros(io.bits(22,0));n64:=countLeadingZeros(io.bits(51,0))
  io.mismatch:=(recFNFromFN(8,24,io.bits(31,0))=/=IeeeRecode(8,24,io.bits(31,0),n32)) ||
    (recFNFromFN(11,53,io.bits)=/=IeeeRecode(11,53,io.bits,n64))
}
object GenerateRecodeProof extends App {
  val path=Paths.get(args(0));Files.createDirectories(path.getParent)
  val rtl=ChiselStage.emitSystemVerilog(new IeeeRecodeProof,firtoolOpts=Array("-disable-all-randomization","-strip-debug-info"))
  // Chisel 7 appends layer files after FILE separators; SAT needs only the miter.
  val marker=rtl.indexOf("// ----- 8< ----- FILE ")
  Files.writeString(path,if(marker<0)rtl else rtl.take(marker))
}
