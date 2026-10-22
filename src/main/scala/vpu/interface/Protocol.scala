package vpu

import chisel3._
import chisel3.util._

/** Host instruction and scalar operands, independent of CPU implementation types.
  *
  * The host offers only an irrevocable instruction at its retirement boundary,
  * after older scalar memory operations have drained. The opaque token keeps
  * that instruction's identity intact through cancellation or completion.
  */
class Command extends Bundle {
  val instruction = UInt(32.W)
  val scalar = UInt(64.W) // integer/CSR operand, NaN-boxed FLEN64 operand, or physical memory base
  val scalar2 = UInt(64.W) // vsetvl vtype source or strided-memory byte stride
  val avl = UInt(64.W) // AVL operand; the configuration decoder handles the vset x0 cases
  val token = UInt(Parameters.tokenBits.W) // host owns index/tag/epoch packing
}

/** Exclusive context access to one 64-bit half of an architectural vector register.
  * The caller must drain instruction ownership before using this port. Context
  * access writes the architectural copy, rather than an arithmetic candidate.
  */
class ContextAccess extends Bundle {
  val address = UInt(6.W) // {vector-register[4:0], 64-bit chunk}
  val write = Bool()
  val data = UInt(64.W)
}

/** Core result held until its completion handshake authorizes final publication.
  * scalar is meaningful only when writesScalar is asserted. Memory fault and
  * stop metadata travel alongside this packet and are combined by the boundary.
  */
class Completion extends Bundle {
  val token = UInt(Parameters.tokenBits.W)
  val scalar = UInt(64.W)
  val writesScalar = Bool()
  val illegal = Bool()
  val instruction = UInt(32.W)
}

/** Core-side interface for CPU-owned architectural FCSR.
  *
  * The core snapshots frm on command.fire. flags reports only the current
  * instruction's contribution, not an already merged architectural value.
  * The host merges it when accepting completion; SpinorIsolated retains the
  * contribution until its external done handshake. This port cannot write CPU
  * state by itself.
  */
class FcsrHostPort extends Bundle {
  val frm = Input(UInt(3.W))
  val fflags = Input(UInt(5.W))
  val flags = Valid(UInt(5.W))
}

/** Internal lane operation IDs; these are distinct from instruction encodings. */
object Op {
  val add = 0; val sub = 1; val and = 2; val or = 3; val xor = 4
  val sll = 5; val srl = 6; val sra = 7
  val min = 8; val minu = 9; val max = 10; val maxu = 11
  val eq = 12; val ne = 13; val lt = 14; val ltu = 15; val le = 16; val leu = 17
  val move = 18; val merge = 19
  val mul = 20; val divu = 21; val div = 22; val remu = 23; val rem = 24
  val mulh = 25; val mulhu = 26; val mulhsu = 27
  val fractionalMul = 28
  val andn = 29; val brev8 = 30; val brev = 31; val rev8 = 32
  val clz = 33; val ctz = 34; val cpop = 35; val rol = 36; val ror = 37
  val width = 6
}

/** One prepared element operation. The issuer applies the required width/sign
  * adjustments and carries the element index in tag for ordered writeback.
  */
class LaneRequest extends Bundle {
  val a = UInt(64.W) // prepared vs2 element or instruction-specific first operand
  val b = UInt(64.W) // prepared vs1, scalar, immediate, or accumulator operand
  val sew = UInt(2.W) // log2(SEW/8)
  val op = UInt(Op.width.W)
  val select = Bool() // per-element merge/mask selection
  val tag = UInt(8.W) // returned unchanged to identify the destination element
}

/** Element result with the request's identity retained through lane latency. */
class LaneResponse extends Bundle {
  val data = UInt(64.W)
  val tag = UInt(8.W)
}
