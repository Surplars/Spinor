package vpu

import circt.stage.ChiselStage

/** Simulation-only export of the unchanged public production module. */
object GenerateGsim extends App {
  require(args.length == 3, "Usage: output-directory preset top-name")
  val top = args(2)
  require(top.matches("[A-Za-z_][A-Za-z0-9_]*"))
  ChiselStage.emitCHIRRTLFile(
    new SpinorVpu(BigInt(0), SpinorParams.preset(args(1))) {
      override def desiredName = top
    }, Array("--target-dir", args(0)))
}
