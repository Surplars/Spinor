package vpu

import circt.stage.ChiselStage

/** Emit CHIRRTL for simulation of a direct production preset.
  * Arguments are output-directory, preset and top-name. This wrapper only
  * chooses elaboration parameters; the simulator drives the normal public IO.
  */
object GenerateGsim extends App {
  require(args.length == 3, "Usage: output-directory preset top-name")
  val top = args(2)
  require(top.matches("[A-Za-z_][A-Za-z0-9_]*"))
  ChiselStage.emitCHIRRTLFile(
    new SpinorVpu(BigInt(0), SpinorParams.preset(args(1))) {
      override def desiredName = top
    }, Array("--target-dir", args(0)))
}
