package vpu

import chisel3._
import chisel3.util._

/** Fixed seven-input truth functions replace signed add/subtract in LSU EMUL decode.
  * All inputs, including reserved LMULs and out-of-range EMULs, retain the old decode.
  * Validity of the architectural vtype itself remains a caller responsibility.
  */
object MemoryGeometry {
  def decode(t:UInt,eew:UInt):(UInt,Bool,Bool) = {
    require(eew.getWidth==2)
    val key=Cat(t(2,0),eew,t(4,3))
    def exponent(k:Int):Int = {
      val lm=(k>>4)&7
      (if(lm>=4)lm-8 else lm)+((k>>2)&3)-(k&3)
    }
    def table(f:Int=>Boolean):Bool = {
      val bits=(0 until 128).foldLeft(BigInt(0))((b,k)=>if(f(exponent(k)))b.setBit(k) else b)
      bits.U(128.W)(key)
    }
    val group=Cat((3 to 0 by -1).map(bit=>table(e=>(if(e>0)1<<(e&3) else 1)==(1<<bit))))
    (group,table(e=>e>= -3 && e<=3),table(_>=0))
  }
}
