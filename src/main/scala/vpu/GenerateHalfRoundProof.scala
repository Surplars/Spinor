package vpu

import chisel3._
import hardfloat._
import _root_.circt.stage.ChiselStage
import java.nio.file.{Files,Paths}

/** One held arbitrary raw input, all mode/special bits, explicit done witness. */
class HalfRoundProof extends Module {
  val io=IO(new Bundle {
    val sig=Input(UInt(65.W));val exp=Input(SInt(13.W));val special=Input(UInt(6.W))
    val mode=Input(UInt(3.W));val tininess=Input(Bool());val mismatch=Output(Bool())
  })
  val phase=RegInit(0.U(4.W));phase:=phase+1.U
  val raw=Reg(new RawFloat(11,64));val mode=Reg(UInt(3.W));val special=Reg(UInt(2.W));val tiny=Reg(Bool())
  when(phase===0.U) {
    raw.sig:=io.sig;raw.sExp:=io.exp;raw.sign:=io.special(0)
    raw.isNaN:=io.special(1);raw.isInf:=io.special(2);raw.isZero:=io.special(3)
    special:=io.special(5,4);mode:=io.mode;tiny:=io.tininess
  }
  val dut=Module(new StagedRound(11,64,5,11,0))
  val reference=Module(new RoundAnyRawFNToRecFN(11,64,5,11,0))
  dut.io.start:=phase===1.U;dut.io.flush:=false.B
  dut.io.in:=raw;reference.io.in:=raw
  dut.io.invalidExc:=special(1);reference.io.invalidExc:=special(1)
  dut.io.infiniteExc:=special(0);reference.io.infiniteExc:=special(0)
  dut.io.roundingMode:=mode;reference.io.roundingMode:=mode
  dut.io.detectTininess:=tiny;reference.io.detectTininess:=tiny
  val seen=RegInit(false.B);when(dut.io.done){seen:=true.B}
  io.mismatch:=(dut.io.done && (dut.io.out=/=reference.io.out || dut.io.exceptionFlags=/=reference.io.exceptionFlags)) ||
    (phase>=8.U && !seen)
}
object GenerateHalfRoundProof extends App {
  val path=Paths.get(args(0));Files.createDirectories(path.getParent)
  val rtl=ChiselStage.emitSystemVerilog(new HalfRoundProof,firtoolOpts=Array(
    "-disable-all-randomization","-strip-debug-info","--lowering-options=disallowLocalVariables,disallowPackedArrays"))
  val marker=rtl.indexOf("// ----- 8< ----- FILE ")
  Files.writeString(path,if(marker<0)rtl else rtl.take(marker))
}
