package vpu

import chisel3._
import chisel3.util._

/** Balanced binary tree, identical to HardFloat countLeadingZeros including zero.
  * Pad at the least-significant end so non-power-of-two widths need no subtract.
  */
object BalancedLeadingZeros {
  /** Return the leading-zero index; all-zero inputs saturate at width - 1. */
  def apply(x:UInt):UInt = {
    val size=1<<log2Ceil(x.getWidth)
    def tree(v:UInt):(Bool,UInt) = {
      // The Boolean marks an entirely zero subtree. The count selects the
      // low subtree only when every higher-priority bit was zero.
      val n=v.getWidth
      if(n==2) (!v.orR,(!v(1)).asUInt) else {
        val (hz,hc)=tree(v(n-1,n/2));val (lz,lc)=tree(v(n/2-1,0))
        (hz && lz,Cat(hz,Mux(hz,lc,hc)))
      }
    }
    if(size==1) 0.U(1.W) else {
      val padded=if(size==x.getWidth)x else Cat(x,0.U((size-x.getWidth).W))
      val (zero,count)=tree(padded)
      // PriorityEncoder's default is the final index when every input is zero.
      Mux(zero,(x.getWidth-1).U,count)
    }
  }
}
