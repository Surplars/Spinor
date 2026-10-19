package vpu

import circt.stage.ChiselStage

/** Production host-owned FCSR interface, independent of Orbital's Scala types. */
object GenerateHostGsim extends App {
  require(args.length==2,"Usage: output-directory top-name")
  val top=args(1)
  require(Set("SpinorHost","SpinorHostDeep").contains(top))
  ChiselStage.emitCHIRRTLFile(new SpinorVpu(BigInt(0),SpinorParams(
    aluStageBits=if(top=="SpinorHostDeep")16 else 32,hostFcsr=true)) {
    override def desiredName=top
  },Array("--target-dir",args(0)))
}
