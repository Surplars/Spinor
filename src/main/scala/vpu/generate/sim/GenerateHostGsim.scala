package vpu

import circt.stage.ChiselStage

/** Emit direct production CHIRRTL with host-owned architectural FCSR.
  * The two accepted names select 32-bit or 16-bit ALU carry segments; both
  * expose the generic public interface without importing a scalar CPU's types.
  */
object GenerateHostGsim extends App {
  require(args.length==2,"Usage: output-directory top-name")
  val top=args(1)
  require(Set("SpinorHost","SpinorHostDeep").contains(top))
  ChiselStage.emitCHIRRTLFile(new SpinorVpu(BigInt(0),SpinorParams(
    aluStageBits=if(top=="SpinorHostDeep")16 else 32,hostFcsr=true)) {
    override def desiredName=top
  },Array("--target-dir",args(0)))
}
