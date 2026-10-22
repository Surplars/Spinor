package vpu

import chisel3._
import chisel3.util._

/** Combinational LSU EMUL geometry from LMUL, memory EEW and configured SEW.
  * Seven-input truth tables keep signed exponent arithmetic off the decode path.
  * The caller must separately validate architectural VTYPE, including reserved LMUL.
  */
object MemoryGeometry {
  /** Return (occupied register count, EMUL in [1/8, 8], EMUL at least one).
    * Fractional groups occupy one physical register; eew is log2(bytes).
    */
  def decode(t:UInt,eew:UInt):(UInt,Bool,Bool) = {
    require(eew.getWidth==2)
    val key=Cat(t(2,0),eew,t(4,3))
    // This arithmetic runs during elaboration. Only the lookup tables and key
    // selection become hardware, including deterministic values for invalid keys.
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
