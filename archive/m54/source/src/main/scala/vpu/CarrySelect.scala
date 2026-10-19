package vpu

import chisel3._
import chisel3.util._

/** Combinational carry-select at 16 bits. No extra pipeline cycle. */
object CarrySelect {
  def add(x:UInt,y:UInt,cin:Bool):UInt = {
    require(x.getWidth==y.getWidth)
    val width=x.getWidth
    def sum(a:UInt,b:UInt,c:Bool):UInt = {
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
