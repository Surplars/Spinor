package vpu

import chisel3._
import chisel3.util._

/** Fixed-latency arithmetic pipeline, unstalled II=1. Split configurations
  * reserve output FIFO credit at launch; arithmetic registers never stall.
  * This removes a global enable from the high-frequency data pipeline.
  * Baseline retains global stalling for an explicit comparison.
  * Operates on ONE element per request, NOT packed SIMD sub-elements.
  * Split variants pipeline carry at configurable 16/32-bit boundaries. Shifts have
  * three registered radix-4 levels (2+2+2 shift-control bits).
  */
class IntegerLane(val split: Boolean = true, val chunkBits: Int = 32) extends Module {
  require(Set(16,32).contains(chunkBits))
  val io = IO(new Bundle {
    val flush = Input(Bool())
    val in = Flipped(Decoupled(new LaneRequest))
    val out = Decoupled(new LaneResponse)
  })
  override def desiredName = if (split && chunkBits == 16) "IntegerLaneSplit16" else if (split) "IntegerLaneSplit" else "IntegerLaneBaseline"
  private val chunks = 64/chunkBits
  private val arithmeticEnd = math.max(chunks,3)
  val latency = if (split) arithmeticEnd+3 else 2
  val valid = RegInit(VecInit(Seq.fill(latency)(false.B)))
  val payload = Reg(Vec(latency, new LaneRequest))
  val enable = if (split) true.B else !valid.last || io.out.ready
  val pipelineOutput = Wire(new LaneResponse)
  pipelineOutput.tag := payload.last.tag
  if (split) {
    val capacity = latency+2
    val credits = RegInit(0.U(log2Ceil(capacity+1).W))
    val queue = withReset(reset.asBool || io.flush) {
      Module(new Queue(new LaneResponse,capacity,pipe=false,flow=false))
    }
    io.in.ready := credits < capacity.U && !io.flush
    queue.io.enq.valid := valid.last && !io.flush
    queue.io.enq.bits := pipelineOutput
    io.out.valid := queue.io.deq.valid && !io.flush
    io.out.bits := queue.io.deq.bits
    queue.io.deq.ready := io.out.ready && !io.flush
    when(io.in.fire =/= io.out.fire) {
      credits := Mux(io.in.fire,credits+1.U,credits-1.U)
    }
    when(io.flush) { credits := 0.U }
  } else {
    io.in.ready := enable && !io.flush
    io.out.valid := valid.last && !io.flush
    io.out.bits := pipelineOutput
  }
  val masks = Seq(8, 16, 32, 64).map(w => ((BigInt(1) << w) - 1).U(64.W))
  val inputMask = VecInit(masks)(io.in.bits.sew)
  val normalized = WireDefault(io.in.bits)
  normalized.a := io.in.bits.a & inputMask
  normalized.b := io.in.bits.b & inputMask
  val values = Reg(Vec(latency, UInt(64.W)))
  val signedLess = Reg(Vec(latency, Bool()))
  val unsignedLess = Reg(Vec(latency, Bool()))
  val equal = Reg(Vec(latency, Bool()))
  def sign(v: UInt, sew: UInt): Bool = VecInit(Seq(7,15,31,63).map(i => v(i)))(sew)
  def isSubtract(op: UInt): Bool = op === Op.sub.U
  def signed64(v: UInt, sew: UInt): UInt = MuxLookup(sew, v)(Seq(
    0.U -> Cat(Fill(56,v(7)),v(7,0)),
    1.U -> Cat(Fill(48,v(15)),v(15,0)),
    2.U -> Cat(Fill(32,v(31)),v(31,0))))
  val shift = Reg(Vec(latency, UInt(64.W)))
  val sums = Reg(Vec(latency, UInt(64.W)))
  val carries = Reg(Vec(latency, Bool()))
  val comparePrefix = Reg(Vec(latency, UInt(4.W)))
  val compareEqual = Reg(UInt(4.W))
  when(enable) {
      valid(0) := io.in.fire
      payload(0) := normalized
      for (i <- 1 until latency) {
        valid(i) := valid(i-1)
        payload(i) := payload(i-1)
      }
      if (split) {
        sums(0) := 0.U
        carries(0) := isSubtract(normalized.op)
        // Prefix partial comparisons, four local 16-bit comparators.
        comparePrefix(0) := VecInit((0 until 4).map(i =>
          normalized.a(16*i+15,16*i) < normalized.b(16*i+15,16*i))).asUInt
        compareEqual := VecInit((0 until 4).map(i =>
          normalized.a(16*i+15,16*i) === normalized.b(16*i+15,16*i))).asUInt
        equal(0) := normalized.a === normalized.b
        for (i <- 1 to chunks) {
          val p = payload(i-1)
          val lo = (i-1)*chunkBits
          val bx = p.b(lo+chunkBits-1,lo) ^ Fill(chunkBits,isSubtract(p.op))
          val part = CarrySelect.add(p.a(lo+chunkBits-1,lo),bx,carries(i-1))
          val keep = ((BigInt(1)<<64)-1) ^ (((BigInt(1)<<chunkBits)-1)<<lo)
          sums(i) := (sums(i-1) & keep.U(64.W)) | (part(chunkBits-1,0).pad(64) << lo)(63,0)
          carries(i) := part(chunkBits)
        }
        for (i <- chunks+1 to arithmeticEnd) { sums(i) := sums(i-1) }
        // Compare is deliberately outside the carry pipeline and registered.
        val lt = comparePrefix(0)
        val ce = compareEqual
        val less = lt(3) || (ce(3) && lt(2)) || (ce(3,2).andR && lt(1)) || (ce(3,1).andR && lt(0))
        unsignedLess(1) := less
        signedLess(1) := Mux(sign(payload(0).a,payload(0).sew) ^ sign(payload(0).b,payload(0).sew),
          sign(payload(0).a,payload(0).sew), less)
        equal(1) := equal(0)
        for (i <- 2 until latency) {
          unsignedLess(i) := unsignedLess(i-1)
          signedLess(i) := signedLess(i-1)
          equal(i) := equal(i-1)
        }
        val p0 = payload(0)
        val shamtMask = VecInit(Seq(7,15,31,63).map(_.U(6.W)))(p0.sew)
        val amounts = p0.b(5,0) & shamtMask
        val sh = Mux(p0.op === Op.sra.U, signed64(p0.a,p0.sew), p0.a)
        def shiftLevel(v: UInt, p: LaneRequest, amount: UInt): UInt = {
          Mux(p.op === Op.sll.U, (v << amount)(63,0),
            Mux(p.op === Op.sra.U, (v.asSInt >> amount).asUInt, v >> amount))
        }
        shift(1) := shiftLevel(sh,p0,amounts(1,0))
        for (i <- 2 to 3) {
          val p = payload(i-1)
          val m = VecInit(Seq(7,15,31,63).map(_.U(6.W)))(p.sew)
          val a = p.b(5,0) & m
          shift(i) := shiftLevel(shift(i-1),p,Cat(a(2*i-1,2*i-2),0.U((2*i-2).W)))
        }
        for (i <- 4 to arithmeticEnd) { shift(i) := shift(i-1) }
        // Select results only after arithmetic has completed.
        val p = payload(arithmeticEnd)
        val result = WireDefault(0.U(64.W))
        switch(p.op) {
          is(Op.add.U,Op.sub.U) { result := sums(arithmeticEnd) }
          is(Op.and.U) { result := p.a & p.b }
          is(Op.or.U) { result := p.a | p.b }
          is(Op.xor.U) { result := p.a ^ p.b }
          is(Op.sll.U,Op.srl.U,Op.sra.U) { result := shift(arithmeticEnd) }
          is(Op.min.U) { result := Mux(signedLess(arithmeticEnd),p.a,p.b) }
          is(Op.minu.U) { result := Mux(unsignedLess(arithmeticEnd),p.a,p.b) }
          is(Op.max.U) { result := Mux(signedLess(arithmeticEnd),p.b,p.a) }
          is(Op.maxu.U) { result := Mux(unsignedLess(arithmeticEnd),p.b,p.a) }
          is(Op.eq.U) { result := equal(arithmeticEnd) }
          is(Op.ne.U) { result := !equal(arithmeticEnd) }
          is(Op.lt.U) { result := signedLess(arithmeticEnd) }
          is(Op.ltu.U) { result := unsignedLess(arithmeticEnd) }
          is(Op.le.U) { result := signedLess(arithmeticEnd) || equal(arithmeticEnd) }
          is(Op.leu.U) { result := unsignedLess(arithmeticEnd) || equal(arithmeticEnd) }
          is(Op.move.U) { result := p.b }
          is(Op.merge.U) { result := Mux(p.select,p.b,p.a) }
        }
        values(arithmeticEnd+1) := result & VecInit(masks)(p.sew)
        values(arithmeticEnd+2) := values(arithmeticEnd+1)
      } else {
        val p = payload(0)
        val sl = signed64(p.a,p.sew).asSInt < signed64(p.b,p.sew).asSInt
        val ul = p.a < p.b
        val eq = p.a === p.b
        val amt = p.b(5,0) & VecInit(Seq(7,15,31,63).map(_.U(6.W)))(p.sew)
        val result = WireDefault(0.U(64.W))
        switch(p.op) {
          is(Op.add.U) { result := p.a+p.b }
          is(Op.sub.U) { result := p.a-p.b }
          is(Op.and.U) { result := p.a&p.b }
          is(Op.or.U) { result := p.a|p.b }
          is(Op.xor.U) { result := p.a^p.b }
          is(Op.sll.U) { result := (p.a << amt)(63,0) }
          is(Op.srl.U) { result := p.a >> amt }
          is(Op.sra.U) { result := (signed64(p.a,p.sew).asSInt >> amt).asUInt }
          is(Op.min.U) { result := Mux(sl,p.a,p.b) }
          is(Op.minu.U) { result := Mux(ul,p.a,p.b) }
          is(Op.max.U) { result := Mux(sl,p.b,p.a) }
          is(Op.maxu.U) { result := Mux(ul,p.b,p.a) }
          is(Op.eq.U) { result := eq }
          is(Op.ne.U) { result := !eq }
          is(Op.lt.U) { result := sl }
          is(Op.ltu.U) { result := ul }
          is(Op.le.U) { result := sl || eq }
          is(Op.leu.U) { result := ul || eq }
          is(Op.move.U) { result := p.b }
          is(Op.merge.U) { result := Mux(p.select,p.b,p.a) }
        }
        values(1) := result & VecInit(masks)(p.sew)
      }
    }
  // Flush only validity/control. Unconditional split datapath updates avoid
  // reintroducing a thousand-load global flush clock-enable.
  when(io.flush) { valid.foreach(_ := false.B) }
  pipelineOutput.data := values.last
}
