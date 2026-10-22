package vpu

import chisel3._
import chisel3.util._
import hardfloat._
import _root_.circt.stage.ChiselStage
import java.nio.file.{Files,Paths}

/** Bounded all-input check: hold one arbitrary raw input through each rounder.
  * No CPU assumptions. A sticky done check prevents a vacuous data comparison.
  */
class RoundProof extends Module {
  val io=IO(new Bundle {
    val sig=Input(UInt(65.W));val exp=Input(SInt(13.W));val special=Input(UInt(6.W))
    val mode=Input(UInt(3.W));val tininess=Input(Bool());val mismatch=Output(Bool())
  })
  // The bounded proof starts from reset. Capture one arbitrary transaction
  // before start, then keep all raw and rounding controls stable for each DUT.
  val phase=RegInit(0.U(4.W));phase:=phase+1.U
  val errors=for((ie,is,oe,os)<-Seq((11,55,8,24),(11,55,11,53),(7,64,8,24),(7,64,11,53)))yield {
    val raw=Reg(new RawFloat(ie,is));val mode=Reg(UInt(3.W));val special=Reg(UInt(2.W));val tiny=Reg(Bool())
    when(phase===0.U) {
      raw.sig:=io.sig;raw.sExp:=io.exp;raw.sign:=io.special(0)
      raw.isNaN:=io.special(1);raw.isInf:=io.special(2);raw.isZero:=io.special(3)
      special:=io.special(5,4);mode:=io.mode;tiny:=io.tininess
    }
    val dut=Module(new StagedRound(ie,is,oe,os,0))
    val reference=Module(new RoundAnyRawFNToRecFN(ie,is,oe,os,0))
    dut.io.start:=phase===1.U;dut.io.flush:=false.B
    dut.io.in:=raw;reference.io.in:=raw
    dut.io.invalidExc:=special(1);reference.io.invalidExc:=special(1)
    dut.io.infiniteExc:=special(0);reference.io.infiniteExc:=special(0)
    dut.io.roundingMode:=mode;reference.io.roundingMode:=mode
    dut.io.detectTininess:=tiny;reference.io.detectTininess:=tiny
    // Numerical equality alone would be vacuous without an observed done.
    val seen=RegInit(false.B);when(dut.io.done) {seen:=true.B}
    (dut.io.done && (dut.io.out=/=reference.io.out || dut.io.exceptionFlags=/=reference.io.exceptionFlags)) ||
      (phase>=8.U && !seen)
  }
  io.mismatch:=errors.reduce(_||_)
}
/** Emit the multi-format held-input rounder miter for bounded checking. */
object GenerateRoundProof extends App {
  val path=Paths.get(args(0));Files.createDirectories(path.getParent)
  val rtl=ChiselStage.emitSystemVerilog(new RoundProof,firtoolOpts=Array("-disable-all-randomization","-strip-debug-info","--lowering-options=disallowLocalVariables,disallowPackedArrays"))
  val marker=rtl.indexOf("// ----- 8< ----- FILE ")
  Files.writeString(path,if(marker<0)rtl else rtl.take(marker))
}
