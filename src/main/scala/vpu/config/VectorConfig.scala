package vpu

import chisel3._

/** Combinational configuration predicates for the fixed VLEN128/ELEN64 core.
  * Callers retain responsibility for reserved encodings and aligned bases.
  * Group helpers use low-bit alignment masks, not register counts.
  */
object VectorConfig {
  /** Fractional LMUL must provide storage for at least one configured element. */
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
  /** Convert a legal physical count (1/2/4/8) to its low-bit alignment mask. */
  def countAlignment(count:UInt):UInt = {
    require(count.getWidth==4) // one-hot 1/2/4/8; caller rejects count=0
    chisel3.util.Cat(0.U(2.W),count(3),count(3,2).orR,count(3,1).orR)
  }
  // Double-width source groups for narrowing. Valid LMULs 0/1/2 map to
  // EMUL 2/4/8; fractional LMULs occupy one physical register. The caller
  // rejects LMUL=m8 and invalid encodings before any source access.
  def narrowAlignment(lmul:UInt):UInt = {
    require(lmul.getWidth==3)
    Mux(lmul(2),0.U(5.W),
      chisel3.util.Cat(0.U(2.W),lmul(1),lmul(1)||lmul(0),true.B))
  }
  // log2 of the physical register count after doubling LMUL; m8 is rejected.
  def doubleGroupLog(lmul:UInt):UInt = {
    require(lmul.getWidth==3)
    Mux(lmul(2),0.U(2.W),chisel3.util.Cat(lmul(1)^lmul(0),!lmul(0)))
  }
  /** Aligned power-of-two groups overlap iff their larger-group prefixes match. */
  def alignedGroupsOverlap(a:UInt,aa:UInt,b:UInt,ba:UInt):Bool = {
    val alignment=aa|ba
    (a & ~alignment)===(b & ~alignment)
  }
  /** Test membership after the caller has checked that base is aligned. */
  def alignedGroupContains(address:UInt,base:UInt,alignment:UInt):Bool = {
    require(address.getWidth==5 && base.getWidth==5 && alignment.getWidth==5)
    (address & ~alignment)===base
  }
  /** Unsigned 64-bit AVL comparison with an eight-bit architectural limit. */
  def belowLimit(avl:UInt,limit:UInt):Bool = {
    require(avl.getWidth==64 && limit.getWidth==8)
    // Two-bit comparisons and equality compose as a balanced LUT tree, rather
    // than a carry comparator feeding gather/control. The independent SAT
    // miter checks all 64-bit values and all 8-bit limits.
    val pairs=(0 until 4).map { k=>
      val a=avl(2*k+1,2*k);val b=limit(2*k+1,2*k)
      ((!a(1) && b(1)) || ((a(1)===b(1)) && !a(0) && b(0)), a===b)
    }
    val low=pairs(1)._1 || (pairs(1)._2 && pairs(0)._1)
    val high=pairs(3)._1 || (pairs(3)._2 && pairs(2)._1)
    !avl(63,8).orR && (high || (pairs(3)._2 && pairs(2)._2 && low))
  }
}
