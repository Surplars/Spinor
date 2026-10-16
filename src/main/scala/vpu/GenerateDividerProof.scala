package vpu

import chisel3._
import chisel3.util._
import _root_.circt.stage.ChiselStage
import java.nio.file.{Files,Paths}

/** Verification-only all-pattern identity for the production pure helper.
  * The unused DUT datapath is removed by flatten/opt before SAT.
  */
class DividerWordProof extends Module {
  val io=IO(new Bundle {
    val bits=Input(UInt(33.W));val other=Input(UInt(33.W));val negative=Input(Bool());val carry=Input(Bool());val mismatch=Output(Bool())
  })
  val dut=Module(new IntegerDivide)
  dut.io.flush:=false.B;dut.io.in.valid:=false.B
  dut.io.in.bits:=0.U.asTypeOf(new LaneRequest);dut.io.out.ready:=false.B
  val actual=dut.negateWord(io.bits(31,0),io.negative,io.carry)
  val expected=(io.bits(31,0) ^ Fill(32,io.negative))+&io.carry
  val mismatch=Seq(11,16,17,32,33).map { width =>
    val x=io.bits(width-1,0);val y=io.other(width-1,0)
    CarrySelect.add(x,y,io.carry)=/=(x+&y+io.carry)
  }.reduce(_ || _)
  io.mismatch:=(actual=/=expected) || mismatch

}
object GenerateDividerProof extends App {
  val path=Paths.get(args(0));Files.createDirectories(path.getParent)
  val rtl=ChiselStage.emitSystemVerilog(new DividerWordProof,firtoolOpts=Array("-disable-all-randomization","-strip-debug-info"))
  val marker=rtl.indexOf("// ----- 8< ----- FILE ")
  Files.writeString(path,if(marker<0)rtl else rtl.take(marker))
}
