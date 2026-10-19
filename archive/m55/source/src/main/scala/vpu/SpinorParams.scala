package vpu

/** Elaborated implementation choices. VLEN/ELEN and lane count are currently
  * fixed: unsupported architectural sizes fail instead of silently truncating.
  * Production variants always use the versioned RAM register file.
  */
case class SpinorParams(
  enableFp:Boolean=true,
  aluStageBits:Int=32,
  regionBase:BigInt=BigInt("80000000",16),
  regionBytes:BigInt=BigInt(1)<<28,
  monitorCounterBits:Int=32,
  vlen:Int=128,
  elen:Int=64,
  lanes:Int=1
) {
  require(vlen==128 && elen==64,"This implementation supports VLEN128/ELEN64 only")
  require(lanes==1,"Multiple execution lanes are not implemented")
  require(Set(16,32).contains(aluStageBits),"ALU stage bits must be 16 or 32")
  require(monitorCounterBits==32,"Production monitor counters must be 32 bits")
  require(regionBase>=0 && regionBytes>=8 && (regionBytes&(regionBytes-1))==0 && regionBase%regionBytes==0)
  require(regionBase+regionBytes <= (BigInt(1)<<64),"Physical region exceeds address width")
}
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
