package vpu

import chisel3._
import circt.stage.ChiselStage
import java.nio.file.{Files,Paths}

/** Versioned production exports for integration and reference comparison. */
object GenerateM56 extends App {
  require(args.length==2,"Usage: output-directory top-name")
  val out=Paths.get(args(0));Files.createDirectories(out)
  val top=args(1)
  val presets=Map("SpinorStandard"->"standard","SpinorDeep"->"deep",
    "SpinorInteger"->"integer","SpinorIntegerDeep"->"integer-deep")
  val host=top=="SpinorHost" || top=="SpinorHostDeep" || top=="LishiVpuMemoryHost"
  val cfg=if(host)SpinorParams(aluStageBits=if(top=="SpinorHostDeep")16 else 32,hostFcsr=true) else SpinorParams.preset(presets(top))
  val gen:()=>RawModule=if(top=="LishiVpuMemoryHost") ()=>new LishiVpuMemory(hostFcsr=true) {override def desiredName=top}
    else ()=>new SpinorVpu(BigInt(0),cfg) {override def desiredName=top}
  val text=ChiselStage.emitSystemVerilog(gen(),firtoolOpts=Array(
    "-disable-all-randomization","-strip-debug-info","--lowering-options=disallowLocalVariables,disallowPackedArrays"))
  val marker="(?m)^// ----- 8< ----- FILE \"([^\"]+)\" ----- 8< -----\\r?\\n".r
  val chunks=marker.findAllMatchIn(text).toSeq
  Files.writeString(out.resolve(top+".sv"),text.take(chunks.headOption.map(_.start).getOrElse(text.length)))
  for((m,i)<-chunks.zipWithIndex) {
    val p=out.resolve(m.group(1));Files.createDirectories(p.getParent)
    Files.writeString(p,text.substring(m.end,chunks.lift(i+1).map(_.start).getOrElse(text.length)))
  }
}
