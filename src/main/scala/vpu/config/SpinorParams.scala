package vpu

/** Elaboration-time choices for the public production tops.
  *
  * Presets select the FP implementation and integer ALU partition width.
  * Architectural VLEN/ELEN, lane count and monitor counter width remain fixed;
  * production variants always use the versioned RAM register file.
  *
  * @param regionBase base of the naturally aligned physical RAM window
  * @param regionBytes power-of-two size of that window, without address wrapping
  * @param hostFcsr select CPU-owned frm/fflags and per-instruction flag reporting
  */
case class SpinorParams(
  enableFp:Boolean=true,
  aluStageBits:Int=32,
  regionBase:BigInt=BigInt("80000000",16),
  regionBytes:BigInt=BigInt(1)<<28,
  monitorCounterBits:Int=32,
  vlen:Int=128,
  elen:Int=64,
  lanes:Int=1,
  hostFcsr:Boolean=false
) {
  // Reject unsupported architectural configurations before any RTL is emitted.
  require(!hostFcsr || enableFp,"Host FCSR mode requires the FP implementation")
  require(vlen==128 && elen==64,"This implementation supports VLEN128/ELEN64 only")
  require(lanes==1,"Multiple execution lanes are not implemented")
  require(Set(16,32).contains(aluStageBits),"ALU stage bits must be 16 or 32")
  require(monitorCounterBits==32,"Production monitor counters must be 32 bits")
  require(regionBase>=0 && regionBytes>=8 && (regionBytes&(regionBytes-1))==0 && regionBase%regionBytes==0)
  require(regionBase+regionBytes <= (BigInt(1)<<64),"Physical region exceeds address width")
}
/** Named resource/timing presets; these do not change ISA register capacity. */
object SpinorParams {
  val presets=Seq("standard","deep","integer","integer-deep")
  def preset(name:String):SpinorParams=name match {
    case "standard"=>SpinorParams()
    case "deep"=>SpinorParams(aluStageBits=16)
    case "integer"=>SpinorParams(enableFp=false)
    case "integer-deep"=>SpinorParams(enableFp=false,aluStageBits=16)
    case _=>throw new IllegalArgumentException("Unknown preset: "+name)
  }
}
