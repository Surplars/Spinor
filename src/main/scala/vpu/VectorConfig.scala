package vpu

import chisel3._

/** Small Boolean forms for configuration decode; no pipeline state. */
object VectorConfig {
  def fractionalLegal(t:UInt):Bool = !t(2) ||
    (t(2,0)===5.U && !t(5,3).orR) ||
    (t(2,0)===6.U && !t(5,4).orR) ||
    (t(2,0)===7.U && !t(5) && !t(4,3).andR)
  def belowLimit(avl:UInt,limit:UInt):Bool = {
    require(avl.getWidth==64 && limit.getWidth==8)
    !avl(63,8).orR && avl(7,0)<limit
  }
}
