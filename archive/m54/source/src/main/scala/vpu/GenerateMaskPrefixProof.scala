package vpu

import chisel3._
import chisel3.util._
import _root_.circt.stage.ChiselStage
import java.nio.file.{Files,Paths}

/** Arithmetic first-bit oracle is independent of the production prefix ORs. */
class MaskPrefixProof extends Module {
  val io=IO(new Bundle {
    val source=Input(UInt(8.W));val seen=Input(Bool());val mode=Input(UInt(2.W))
    val mismatch=Output(Bool())
  })
  val first=io.source & (0.U(8.W)-io.source)
  val before=(first-1.U)(7,0)
  val expected=Mux(io.seen,0.U,MuxLookup(io.mode,0.U(8.W))(Seq(
    1.U->before,2.U->first,3.U->(before | first))))
  io.mismatch:=MaskPrefixByte(io.source,io.seen,io.mode)=/=expected
}
object GenerateMaskPrefixProof extends App {
  val path=Paths.get(args(0));Files.createDirectories(path.getParent)
  val rtl=ChiselStage.emitSystemVerilog(new MaskPrefixProof,firtoolOpts=Array("-disable-all-randomization","-strip-debug-info"))
  val marker=rtl.indexOf("// ----- 8< ----- FILE ")
  Files.writeString(path,if(marker<0)rtl else rtl.take(marker))
}
