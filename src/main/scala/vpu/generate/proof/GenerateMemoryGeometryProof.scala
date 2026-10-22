package vpu

import chisel3._
import chisel3.util._
import _root_.circt.stage.ChiselStage
import java.nio.file.{Files,Paths}

/** Independent arithmetic reference for every seven-bit geometry key and RF base. */
class MemoryGeometryProof extends Module {
  val io=IO(new Bundle {val key=Input(UInt(7.W));val base=Input(UInt(5.W));val ok=Output(Bool())})
  // Treat encoded LMUL as a signed logarithm and derive EMUL arithmetically.
  // This reference is independent of the production Boolean truth functions.
  val lm=io.key(6,4).asSInt;val ew=io.key(3,2);val sew=io.key(1,0)
  val t=Cat(0.U(59.W),sew,io.key(6,4))
  val (group,valid,integral)=MemoryGeometry.decode(t,ew)
  val emul=lm+&ew.zext-sew.zext
  val reference=Mux(emul>0.S,(1.U(4.W)<<emul.asUInt(1,0))(3,0),1.U(4.W))
  val misaligned=(io.base&(group-1.U))=/=0.U
  val oldBad=misaligned || (io.base+&group)>32.U
  io.ok:=group===reference && valid===(emul>=(-3).S && emul<=3.S) && integral===(emul>=0.S) && misaligned===oldBad
}
/** Emit the geometry miter; ok must hold for every geometry key and RF base. */
object GenerateMemoryGeometryProof extends App {
  val out=Paths.get(args.headOption.getOrElse("build/memory-geometry-proof"));Files.createDirectories(out)
  val rtl=ChiselStage.emitSystemVerilog(new MemoryGeometryProof,firtoolOpts=Array(
    "-disable-all-randomization","-strip-debug-info","--strip-fir-debug-info","--lowering-options=disallowLocalVariables,disallowPackedArrays"))
  val marker=rtl.indexOf("// ----- 8< ----- FILE ")
  Files.writeString(out.resolve("MemoryGeometryProof.sv"),if(marker<0)rtl else rtl.take(marker))
}
