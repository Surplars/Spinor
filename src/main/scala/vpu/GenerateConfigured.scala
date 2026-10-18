package vpu

import chisel3._
import circt.stage.ChiselStage
import java.nio.file.{Files,Paths}

/** Mill entry point for an inspectable, standalone configured production top. */
object GenerateConfigured extends App {
  require(args.length%2==0,"Use --option value pairs")
  val pairs=args.grouped(2).map(x=>x(0)->x(1)).toSeq
  require(pairs.map(_._1).distinct.size==pairs.size,"Duplicate option")
  val opts=pairs.toMap
  val allowed=Set("--out","--name","--preset","--fp","--alu-stage-bits","--region-base","--region-bytes","--monitor-base","--vlen","--elen","--lanes")
  require(opts.keySet.subsetOf(allowed),"Unknown option: "+(opts.keySet--allowed).mkString(","))
  def number(s:String):BigInt=if(s.startsWith("0x"))BigInt(s.drop(2),16) else BigInt(s)
  val preset=opts.getOrElse("--preset","standard")
  val initial=SpinorParams.preset(preset)
  val cfg=initial.copy(
    enableFp=opts.get("--fp").map {case "true"=>true;case "false"=>false;case _=>throw new IllegalArgumentException("--fp must be true or false")}.getOrElse(initial.enableFp),
    aluStageBits=opts.get("--alu-stage-bits").map(_.toInt).getOrElse(initial.aluStageBits),
    regionBase=opts.get("--region-base").map(number).getOrElse(initial.regionBase),
    regionBytes=opts.get("--region-bytes").map(number).getOrElse(initial.regionBytes),
    vlen=opts.get("--vlen").map(_.toInt).getOrElse(128),elen=opts.get("--elen").map(_.toInt).getOrElse(64),lanes=opts.get("--lanes").map(_.toInt).getOrElse(1))
  val base=opts.get("--monitor-base").map(number).getOrElse(BigInt(0))
  require(base>=0 && base<(BigInt(1)<<64) && base%4096==0,"Monitor base must be aligned to 4 KiB")
  val top=opts.getOrElse("--name","SpinorVpu")
  require(top.matches("[A-Za-z_][A-Za-z0-9_]*"),"Invalid Verilog top name")
  val out=Paths.get(opts.getOrElse("--out","build/configured"));Files.createDirectories(out)
  val text=ChiselStage.emitSystemVerilog(new SpinorVpu(base,cfg) {override def desiredName=top},firtoolOpts=Array(
    "-disable-all-randomization","-strip-debug-info","--lowering-options=disallowLocalVariables,disallowPackedArrays"))
  val marker="(?m)^// ----- 8< ----- FILE \"([^\"]+)\" ----- 8< -----\\r?\\n".r
  val chunks=marker.findAllMatchIn(text).toSeq
  Files.writeString(out.resolve(top+".sv"),text.take(chunks.headOption.map(_.start).getOrElse(text.length)))
  for((m,i)<-chunks.zipWithIndex) {val p=out.resolve(m.group(1));Files.createDirectories(p.getParent);Files.writeString(p,text.substring(m.end,chunks.lift(i+1).map(_.start).getOrElse(text.length)))}
  val caps=if(cfg.enableFp)BigInt("ffffffff",16) else BigInt("ffffffff",16).clearBit(2).clearBit(3).clearBit(15).clearBit(17)
  Files.writeString(out.resolve(top+".json"),s"""{
  "top":"$top", "preset":"$preset", "vlen":${cfg.vlen}, "elen":${cfg.elen}, "lanes":${cfg.lanes},
  "instruction_capacity":1, "architectural_vrf_bytes":512, "vrf":"versioned-ram",
  "alu_stage_bits":${cfg.aluStageBits}, "fp32_fp64":${cfg.enableFp}, "has_fp_csr_ports":${cfg.enableFp},
  "physical_region_base":"0x${cfg.regionBase.toString(16)}", "physical_region_bytes":"0x${cfg.regionBytes.toString(16)}",
  "monitor_base":"0x${base.toString(16)}", "monitor_implementation":"0x4601", "monitor_abi":"1.0", "monitor_caps":"0x${caps.toString(16)}",
  "device_timing_verified":false, "full_rvv":false
}
""")
}
