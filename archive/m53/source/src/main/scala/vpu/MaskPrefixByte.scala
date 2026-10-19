package vpu

import chisel3._
import chisel3.util._

/** Eight active source bits, with one carry flag between bytes. No wide scan.
  * mode follows the RVV vs1 selector: 1 before, 2 only, 3 including first.
  * Source bits must already be filtered by VL and the execution predicate.
  */
object MaskPrefixByte {
  def apply(source:UInt,seen:Bool,mode:UInt):UInt = {
    require(source.getWidth==8)
    VecInit((0 until 8).map { i =>
      val earlier=if(i==0)seen else seen || source(i-1,0).orR
      !earlier && MuxLookup(mode,false.B)(Seq(
        1.U-> !source(i),2.U->source(i),3.U->true.B))
    }).asUInt
  }
}
