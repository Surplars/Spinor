package vpu

import chisel3._
import chisel3.util._

/** Combinational carry-select at bit 16; callers provide pipeline registers.
  * Returns an extra carry bit above two equal-width unsigned operands.
  */
object CarrySelect {
  /** Compute x + y + cin, selecting a precomputed upper sum with the low carry. */
  def add(x:UInt,y:UInt,cin:Bool):UInt = {
    require(x.getWidth==y.getWidth)
    val width=x.getWidth
    def sum(a:UInt,b:UInt,c:Bool):UInt = {
      // Appending 1 and cin converts the extra low bit into the carry-in of
      // the original operands; discard that helper bit from the result.
      val extended=Cat(a,true.B)+&Cat(b,c)
      extended(a.getWidth+1,1)
    }
    if(width<=16) sum(x,y,cin) else {
      val lo=sum(x(15,0),y(15,0),cin)
      val hi0=x(width-1,16)+&y(width-1,16)
      val hi1=sum(x(width-1,16),y(width-1,16),true.B)
      Cat(Mux(lo(16),hi1,hi0),lo(15,0))
    }
  }
}
