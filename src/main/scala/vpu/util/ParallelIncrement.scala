package vpu

import chisel3._
import chisel3.util._

/** Exact modulo increment. Each bit's carry is a prefix reduction, with no
  * serial carry chain and no additional register or pipeline cycle.
  */
object ParallelIncrement {
  /** Preserve x when disabled; otherwise wrap modulo 2^x.getWidth. */
  def apply(x:UInt,enable:Bool):UInt = VecInit((0 until x.getWidth).map { bit =>
    x(bit) ^ (enable && (if(bit==0)true.B else x(bit-1,0).andR))
  }).asUInt
}
