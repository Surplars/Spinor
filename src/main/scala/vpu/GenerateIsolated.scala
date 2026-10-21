package vpu

import circt.stage.ChiselStage
import java.nio.file.{Files,Paths}

/** Explicit new protocol; the legacy generator/top and their ABI are unchanged. */
object GenerateIsolated extends App {
  require(args.length%2==0,"Use --option value pairs")
  val pairs=args.grouped(2).map(x=>x(0)->x(1)).toSeq
  require(pairs.map(_._1).distinct.size==pairs.size,"Duplicate option")
  val opts=pairs.toMap
  require(opts.keySet.subsetOf(Set("--out","--name","--preset","--fcsr-owner","--format","--region-base","--region-bytes","--monitor-base")),"Unknown option")
  def num(s:String)=if(s.startsWith("0x"))BigInt(s.drop(2),16) else BigInt(s)
  val preset=opts.getOrElse("--preset","standard")
  val fcsr=opts.getOrElse("--fcsr-owner","standalone")
  require(Set("host","standalone").contains(fcsr),"Invalid FCSR owner")
  val cfg=SpinorParams.preset(preset).copy(hostFcsr=fcsr=="host",
    regionBase=opts.get("--region-base").map(num).getOrElse(BigInt("80000000",16)),
    regionBytes=opts.get("--region-bytes").map(num).getOrElse(BigInt(1)<<28))
  val base=opts.get("--monitor-base").map(num).getOrElse(BigInt(0))
  val top=opts.getOrElse("--name","SpinorIsolated")
  require(top.matches("[A-Za-z_][A-Za-z0-9_]*"),"Invalid top name")
  val format=opts.getOrElse("--format","sv")
  require(Set("sv","fir","both").contains(format),"Invalid format")
  val out=Paths.get(opts.getOrElse("--out","build/isolated"));Files.createDirectories(out)
  def make()=new SpinorIsolated(base,cfg) {override def desiredName=top}
  if(format!="sv") ChiselStage.emitCHIRRTLFile(make(),Array("--target-dir",out.toString))
  if(format!="fir") {
    val text=ChiselStage.emitSystemVerilog(make(),firtoolOpts=Array(
      "-disable-all-randomization","-strip-debug-info","--lowering-options=disallowLocalVariables,disallowPackedArrays"))
    val marker="(?m)^// ----- 8< ----- FILE \"([^\"]+)\" ----- 8< -----\\r?\\n".r
    val chunks=marker.findAllMatchIn(text).toSeq
    Files.writeString(out.resolve(top+".sv"),text.take(chunks.headOption.map(_.start).getOrElse(text.length)))
    for((m,i)<-chunks.zipWithIndex) {
      val p=out.resolve(m.group(1));Files.createDirectories(p.getParent)
      Files.writeString(p,text.substring(m.end,chunks.lift(i+1).map(_.start).getOrElse(text.length)))
    }
  }
  Files.writeString(out.resolve(top+".json"),s"""{
  "top":"$top", "preset":"$preset", "fcsr_owner":"$fcsr",
  "interface":"preview-grant-done-v1", "same_clock_only":true,
  "vlen":128, "elen":64, "lanes":1, "instruction_capacity":1,
  "physical_region_base":"0x${cfg.regionBase.toString(16)}", "physical_region_bytes":"0x${cfg.regionBytes.toString(16)}",
  "monitor_base":"0x${base.toString(16)}", "registered_tl":true,
  "grant_irrevocable":true, "device_timing_verified":false, "full_rvv":false
}
""")
}
