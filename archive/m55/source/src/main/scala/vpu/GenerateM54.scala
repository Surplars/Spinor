package vpu

import circt.stage.ChiselStage
import java.nio.file.{Files,Paths}

/** Isolated milestone exports preserve the accepted M53 RTL and model inputs. */
object GenerateM54 extends App {
  require(args.length==2,"Usage: output-directory top-name")
  val out=Paths.get(args(0));Files.createDirectories(out)
  val name=args(1)
  val gen:()=>chisel3.RawModule=name match {
    case "FloatingPointConvertResize" => ()=>new FloatingPointConvertResize
    case "RamVectorFp" => ()=>new RamVector(enableFp=true)
    case "RamVectorFp16" => ()=>new RamVector(chunkBits=16,enableFp=true)
    case "LishiVpuMemory" => ()=>new LishiVpuMemory
    case "SpinorVpu" => ()=>new SpinorVpu
    case _ => throw new IllegalArgumentException("Unsupported isolated top: "+name)
  }
  val text=ChiselStage.emitSystemVerilog(gen(),firtoolOpts=Array(
    "-disable-all-randomization","-strip-debug-info","--lowering-options=disallowLocalVariables,disallowPackedArrays"))
  val marker="(?m)^// ----- 8< ----- FILE \"([^\"]+)\" ----- 8< -----\\r?\\n".r
  val chunks=marker.findAllMatchIn(text).toSeq
  Files.writeString(out.resolve(name+".sv"),text.take(chunks.headOption.map(_.start).getOrElse(text.length)))
  for((m,i)<-chunks.zipWithIndex) {
    val p=out.resolve(m.group(1));Files.createDirectories(p.getParent)
    Files.writeString(p,text.substring(m.end,chunks.lift(i+1).map(_.start).getOrElse(text.length)))
  }
}
