package vpu

/** Architectural widths shared by the public protocol and vector datapath.
  *
  * The host packs its instruction identity into the opaque 80-bit token and
  * must retain every bit through completion. VLEN and ELEN are implementation
  * constants; changing them requires register-file and scheduling changes in
  * addition to changing these declarations.
  */
object Parameters {
  val tokenBits = 80
  val vlen = 128
  val elen = 64
}
