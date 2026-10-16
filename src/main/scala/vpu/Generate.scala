package vpu

import circt.stage.ChiselStage
import java.nio.file.{Files, Paths}

object Generate extends App {
  val out = if (args.nonEmpty) args(0) else sys.env.get("MILL_WORKSPACE_ROOT").map(_+"/build/rtl").getOrElse("build/rtl")
  Files.createDirectories(Paths.get(out))
  // The string emitter bundles layer files with FILE separators in Chisel 7.
  // Materialize every file instead of concatenating includes into the main RTL.
  def writeBundle(name: String, text: String): Unit = {
    val marker = "(?m)^// ----- 8< ----- FILE \"([^\"]+)\" ----- 8< -----\\r?\\n".r
    val matches = marker.findAllMatchIn(text).toSeq
    Files.writeString(Paths.get(out,s"$name.sv"),text.take(matches.headOption.map(_.start).getOrElse(text.length)))
    for ((m,i) <- matches.zipWithIndex) {
      val path = Paths.get(out,m.group(1))
      Files.createDirectories(path.getParent)
      Files.writeString(path,text.substring(m.end,matches.lift(i+1).map(_.start).getOrElse(text.length)))
    }
  }
  for (split <- Seq(false, true)) {
    val name = if (split) "IntegerLaneSplit" else "IntegerLaneBaseline"
    val sv = ChiselStage.emitSystemVerilog(new IntegerLane(split), firtoolOpts = Array(
      "-disable-all-randomization", "-strip-debug-info", "--strip-fir-debug-info", "--lowering-options=disallowLocalVariables,disallowPackedArrays"))
    writeBundle(name,sv)
    val topName = if (split) "VectorPrototype" else "VectorPrototypeBaseline"
    val top = ChiselStage.emitSystemVerilog(new VectorPrototype(split), firtoolOpts = Array(
      "-disable-all-randomization", "-strip-debug-info", "--lowering-options=disallowLocalVariables,disallowPackedArrays"))
    writeBundle(topName,top)
  }
  val cut16 = ChiselStage.emitSystemVerilog(new IntegerLane(true,16), firtoolOpts = Array(
    "-disable-all-randomization", "-strip-debug-info", "--lowering-options=disallowLocalVariables,disallowPackedArrays"))
  writeBundle("IntegerLaneSplit16",cut16)
  val top16 = ChiselStage.emitSystemVerilog(new VectorPrototype(true,16), firtoolOpts = Array(
    "-disable-all-randomization", "-strip-debug-info", "--lowering-options=disallowLocalVariables,disallowPackedArrays"))
  writeBundle("VectorPrototype16",top16)
  val flops = ChiselStage.emitSystemVerilog(new VectorPrototype(true,32,false), firtoolOpts = Array(
    "-disable-all-randomization", "-strip-debug-info", "--lowering-options=disallowLocalVariables,disallowPackedArrays"))
  writeBundle("VectorPrototypeFlops",flops)
  val boundary = ChiselStage.emitSystemVerilog(new ValenceBoundary, firtoolOpts = Array(
    "-disable-all-randomization", "-strip-debug-info", "--lowering-options=disallowLocalVariables,disallowPackedArrays"))
  writeBundle("ValenceBoundary",boundary)
  for ((name,ram,cut) <- Seq(("RamVector",true,32),("RamVector16",true,16),("RamVectorFlops",false,32))) {
    val text = ChiselStage.emitSystemVerilog(new RamVector(ram,cut),firtoolOpts=Array(
      "-disable-all-randomization","-strip-debug-info","--lowering-options=disallowLocalVariables,disallowPackedArrays"))
    writeBundle(name,text)
  }
  val vrf = ChiselStage.emitSystemVerilog(new VersionedRegisterFile,firtoolOpts=Array(
    "-disable-all-randomization","-strip-debug-info","--lowering-options=disallowLocalVariables,disallowPackedArrays"))
  writeBundle("VersionedRegisterFileRam",vrf)
  val div = ChiselStage.emitSystemVerilog(new IntegerDivide,firtoolOpts=Array(
    "-disable-all-randomization","-strip-debug-info","--lowering-options=disallowLocalVariables,disallowPackedArrays"))
  writeBundle("IntegerDivide",div)
  val mul = ChiselStage.emitSystemVerilog(new IntegerMultiply,firtoolOpts=Array(
    "-disable-all-randomization","-strip-debug-info","--lowering-options=disallowLocalVariables,disallowPackedArrays"))
  writeBundle("IntegerMultiply",mul)
  val memory = ChiselStage.emitSystemVerilog(new LishiVpuMemory,firtoolOpts=Array(
    "-disable-all-randomization","-strip-debug-info","--lowering-options=disallowLocalVariables,disallowPackedArrays"))
  writeBundle("LishiVpuMemory",memory)
  val engine = ChiselStage.emitSystemVerilog(new VectorMemoryEngine,firtoolOpts=Array(
    "-disable-all-randomization","-strip-debug-info","--lowering-options=disallowLocalVariables,disallowPackedArrays"))
  writeBundle("VectorMemoryEngine",engine)
  val tl = ChiselStage.emitSystemVerilog(new TileLinkReservation,firtoolOpts=Array(
    "-disable-all-randomization","-strip-debug-info","--lowering-options=disallowLocalVariables,disallowPackedArrays"))
  writeBundle("TileLinkReservation",tl)
  val reserved = ChiselStage.emitSystemVerilog(new LishiVpuTileLinkReserved,firtoolOpts=Array(
    "-disable-all-randomization","-strip-debug-info","--lowering-options=disallowLocalVariables,disallowPackedArrays"))
  writeBundle("LishiVpuTileLinkReserved",reserved)
  val convert = ChiselStage.emitSystemVerilog(new FloatingPointConvert,firtoolOpts=Array(
    "-disable-all-randomization","-strip-debug-info","--lowering-options=disallowLocalVariables,disallowPackedArrays"))
  writeBundle("FloatingPointConvert",convert)
  val fp = ChiselStage.emitSystemVerilog(new FloatingPointLane,firtoolOpts=Array(
    "-disable-all-randomization","-strip-debug-info","--lowering-options=disallowLocalVariables,disallowPackedArrays"))
  writeBundle("FloatingPointLane",fp)
  val fpVector = ChiselStage.emitSystemVerilog(new RamVector(enableFp=true),firtoolOpts=Array(
    "-disable-all-randomization","-strip-debug-info","--lowering-options=disallowLocalVariables,disallowPackedArrays"))
  writeBundle("RamVectorFp",fpVector)
  val candidate = ChiselStage.emitSystemVerilog(new RamVector(chunkBits=16,enableFp=true),firtoolOpts=Array(
    "-disable-all-randomization","-strip-debug-info","--lowering-options=disallowLocalVariables,disallowPackedArrays"))
  writeBundle("RamVectorFp16",candidate)
  val candidateMemory = ChiselStage.emitSystemVerilog(new LishiVpuMemory(chunkBits=16),firtoolOpts=Array(
    "-disable-all-randomization","-strip-debug-info","--lowering-options=disallowLocalVariables,disallowPackedArrays"))
  writeBundle("LishiVpuMemory16",candidateMemory)
  writeBundle("SpinorVpu",ChiselStage.emitSystemVerilog(new SpinorVpu,firtoolOpts=Array(
    "-disable-all-randomization","-strip-debug-info","--lowering-options=disallowLocalVariables,disallowPackedArrays")))
  writeBundle("VpuHostBoundary",ChiselStage.emitSystemVerilog(new VpuHostBoundary,firtoolOpts=Array(
    "-disable-all-randomization","-strip-debug-info","--lowering-options=disallowLocalVariables,disallowPackedArrays")))

}
