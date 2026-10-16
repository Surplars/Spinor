package vpu

import chisel3._

/** Small Boolean forms for configuration decode; no pipeline state. */
object VectorConfig {
  def fractionalLegal(t:UInt):Bool = !t(2) ||
    (t(2,0)===5.U && !t(5,3).orR) ||
    (t(2,0)===6.U && !t(5,4).orR) ||
    (t(2,0)===7.U && !t(5) && !t(4,3).andR)
  // Base alignment is checked by the caller. Physical groups have power-of-two
  // sizes, so membership does not require an end-address adder/comparator.
  def groupAlignment(log:UInt):UInt = {
    require(log.getWidth==2)
    chisel3.util.Cat(0.U(2.W),log.andR,log(1),log.orR)
  }
  def countAlignment(count:UInt):UInt = {
    require(count.getWidth==4) // one-hot 1/2/4/8; caller rejects count=0
    chisel3.util.Cat(0.U(2.W),count(3),count(3,2).orR,count(3,1).orR)
  }
  def alignedGroupsOverlap(a:UInt,aa:UInt,b:UInt,ba:UInt):Bool = {
    val alignment=aa|ba
    (a & ~alignment)===(b & ~alignment)
  }
  def alignedGroupContains(address:UInt,base:UInt,alignment:UInt):Bool = {
    require(address.getWidth==5 && base.getWidth==5 && alignment.getWidth==5)
    (address & ~alignment)===base
  }
  def belowLimit(avl:UInt,limit:UInt):Bool = {
    require(avl.getWidth==64 && limit.getWidth==8)
    !avl(63,8).orR && avl(7,0)<limit
  }
}
