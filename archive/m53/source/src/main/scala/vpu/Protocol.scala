package vpu

import chisel3._
import chisel3.util._

/** Deliberately independent of Valence's changing Scala/ROB types.
  * The host may issue ONLY an irrevocable ROB-head instruction, with older
  * scalar memory operations drained. No speculative architectural writes.
  */
class Command extends Bundle {
  val instruction = UInt(32.W)
  val scalar = UInt(64.W) // vx: integer x-register; vf: FLEN64 NaN-boxed f-register
  val scalar2 = UInt(64.W) // vtype source for vsetvl
  val avl = UInt(64.W) // nonzero-rs1 AVL; M2/M3 decode x0 rules, M1 needs resolved AVL
  val token = UInt(Parameters.tokenBits.W) // host owns index/tag/epoch packing
}

class ContextAccess extends Bundle {
  val address = UInt(6.W) // {vector-register[4:0], 64-bit chunk}
  val write = Bool()
  val data = UInt(64.W)
}

class Completion extends Bundle {
  val token = UInt(Parameters.tokenBits.W)
  val scalar = UInt(64.W)
  val writesScalar = Bool()
  val illegal = Bool()
  val instruction = UInt(32.W)
}

object Op {
  val add = 0; val sub = 1; val and = 2; val or = 3; val xor = 4
  val sll = 5; val srl = 6; val sra = 7
  val min = 8; val minu = 9; val max = 10; val maxu = 11
  val eq = 12; val ne = 13; val lt = 14; val ltu = 15; val le = 16; val leu = 17
  val move = 18; val merge = 19
  val mul = 20; val divu = 21; val div = 22; val remu = 23; val rem = 24
  val mulh = 25; val mulhu = 26; val mulhsu = 27
  val fractionalMul = 28
  val width = 5
}

class LaneRequest extends Bundle {
  val a = UInt(64.W) // vs2 element, zero extended
  val b = UInt(64.W) // vs1 / scalar / sign-extended immediate element
  val sew = UInt(2.W) // log2(SEW/8)
  val op = UInt(Op.width.W)
  val select = Bool()
  val tag = UInt(8.W)
}

class LaneResponse extends Bundle {
  val data = UInt(64.W)
  val tag = UInt(8.W)
}
