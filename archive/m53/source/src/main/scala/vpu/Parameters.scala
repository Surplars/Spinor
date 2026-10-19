package vpu

/** VLEN/ELEN are fixed for the first milestone. Token width covers Valence's
  * default 64-bit allocation tag plus ROB index, without truncating ownership.
  */
object Parameters {
  val tokenBits = 80
  val vlen = 128
  val elen = 64
}

