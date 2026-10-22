package vpu

import chisel3._
import chisel3.util._

/** Historical Milestone 1 experiment, not instantiated by production tops.
  * Real-encoding RVV integer subset, VLEN128/ELEN64/LMUL1.
  * Not full V or Zve: no FP, LSU, multiply/divide, widening, reductions,
  * permutations, fixed-point saturation, Zvbb, CSR instruction adapter yet.
  * One command in flight; up to 16 independent element requests are streamed
  * through the lane (one every two cycles when credits permit).
  * Operands are snapshotted; destination writes are atomic
  * at completion.fire. Flush discards the shadow and all pending lane work.
  * Mask/tail are always undisturbed (also legal when agnostic is requested).
  * Context port is for halted context save/restore, never concurrent with work.
  */
class VectorPrototype(split: Boolean = true, chunkBits: Int = 32, useRam: Boolean = true) extends Module {
  override def desiredName = if (split && !useRam) "VectorPrototypeFlops" else if (split && chunkBits == 16) "VectorPrototype16" else if (split) "VectorPrototype" else "VectorPrototypeBaseline"
  val io = IO(new Bundle {
    val flush = Input(Bool())
    val command = Flipped(Decoupled(new Command))
    val completion = Decoupled(new Completion)
    val context = Flipped(Decoupled(new ContextAccess))
    val contextResult = Valid(UInt(64.W))
    val vl = Output(UInt(5.W))
    val vtype = Output(UInt(64.W))
    val busy = Output(Bool())
  })
  val idle :: decode :: snapshot :: snapshotCapture :: prepare :: execute :: collect :: finish :: Nil = Enum(8)
  val state = RegInit(idle)
  // The unversioned experimental RF is written only by context access or the
  // final instruction commit. Full-register shadows keep computation private.
  val registers = Module(new VectorRegisterFile(useRam))
  registers.io.readEnable := false.B
  registers.io.readAddress := 0.U
  registers.io.writeEnable := false.B
  registers.io.writeAddress := 0.U
  registers.io.writeMask := 0.U
  registers.io.writeData := 0.U
  val snapshotPhase = Reg(UInt(2.W))
  val cmd = Reg(new Command)
  val vl = RegInit(0.U(5.W))
  val vtype = RegInit((BigInt(1)<<63).U(64.W))
  val sew = Reg(UInt(2.W))
  val operation = Reg(UInt(Op.width.W))
  val maskResult = Reg(Bool())
  val config = Reg(Bool())
  val nextVl = Reg(UInt(5.W))
  val nextVtype = Reg(UInt(64.W))
  val illegal = RegInit(false.B)
  // Snapshot sources, old destination and predicate before issuing any lane
  // request. These full-vector registers are specific to this early design.
  val left = Reg(UInt(128.W))
  val right = Reg(UInt(128.W))
  val shadow = Reg(UInt(128.W))
  val mask = Reg(UInt(16.W))
  val index = Reg(UInt(5.W))
  val elementA = Reg(UInt(64.W))
  val elementB = Reg(UInt(64.W))
  val active = Reg(Bool())
  val selected = Reg(Bool())
  val issuedElements = Reg(UInt(5.W))
  val completedElements = Reg(UInt(5.W))
  // Tagged element results may return while subsequent operands are prepared.
  // The collect state waits for all accepted requests before offering commit.
  val lane = Module(new IntegerLane(split,chunkBits))
  lane.io.flush := io.flush
  lane.io.in.valid := state === execute && active && !io.flush
  lane.io.in.bits.a := elementA
  lane.io.in.bits.b := elementB
  lane.io.in.bits.sew := sew
  lane.io.in.bits.op := operation
  lane.io.in.bits.select := selected
  lane.io.in.bits.tag := index
  lane.io.out.ready := (state === prepare || state === execute || state === collect) && !io.flush
  io.command.ready := state === idle && !io.context.valid && !io.flush
  io.completion.valid := state === finish && !io.flush
  io.completion.bits.token := cmd.token
  io.completion.bits.scalar := Mux(config && !illegal, nextVl, 0.U)
  io.completion.bits.writesScalar := config && cmd.instruction(11,7) =/= 0.U && !illegal
  io.completion.bits.illegal := illegal
  io.completion.bits.instruction := cmd.instruction
  io.busy := state =/= idle
  io.vl := vl
  io.vtype := vtype
  // Context has priority over a new command and is legal only while idle.
  // A half-register read/write is acknowledged one cycle after acceptance.
  io.context.ready := state === idle && !io.flush
  val ctxValid = RegInit(false.B)
  val ctxChunk = Reg(Bool())
  val ctxWrite = Reg(Bool())
  ctxValid := io.context.fire
  io.contextResult.valid := ctxValid
  io.contextResult.bits := Mux(ctxWrite,0.U,Mux(ctxChunk,registers.io.readData(127,64),registers.io.readData(63,0)))
  when(io.context.fire) {
    ctxChunk := io.context.bits.address(0)
    ctxWrite := io.context.bits.write
    registers.io.readEnable := !io.context.bits.write
    registers.io.readAddress := io.context.bits.address(5,1)
    registers.io.writeEnable := io.context.bits.write
    registers.io.writeAddress := io.context.bits.address(5,1)
    registers.io.writeMask := Mux(io.context.bits.address(0),2.U,1.U)
    registers.io.writeData := Fill(2,io.context.bits.data)
  }
  when(io.command.fire) { cmd := io.command.bits; state := decode }
  // Decode the original integer subset from the captured instruction. This
  // table describes the experiment, not the production ISA coverage table.
  val inst = cmd.instruction
  val f6 = inst(31,26)
  val f3 = inst(14,12)
  val vm = inst(25)
  val vv = f3 === 0.U
  val vx = f3 === 4.U
  val vi = f3 === 3.U
  val arithmeticForm = vv || vx || vi
  val decoded = WireDefault(0.U(Op.width.W))
  val supported = WireDefault(false.B)
  val comparison = WireDefault(false.B)
  def decodeOp(code: Int, op: Int, immediate: Boolean = true, compare: Boolean = false): Unit = {
    when(f6 === code.U && arithmeticForm && (immediate.B || !vi)) {
      decoded := op.U; supported := true.B; comparison := compare.B
    }
  }
  decodeOp(0x00,Op.add)
  decodeOp(0x02,Op.sub,false)
  decodeOp(0x09,Op.and)
  decodeOp(0x0a,Op.or)
  decodeOp(0x0b,Op.xor)
  decodeOp(0x25,Op.sll)
  decodeOp(0x28,Op.srl)
  decodeOp(0x29,Op.sra)
  decodeOp(0x04,Op.minu,false)
  decodeOp(0x05,Op.min,false)
  decodeOp(0x06,Op.maxu,false)
  decodeOp(0x07,Op.max,false)
  decodeOp(0x18,Op.eq,true,true)
  decodeOp(0x19,Op.ne,true,true)
  decodeOp(0x1a,Op.ltu,false,true)
  decodeOp(0x1b,Op.lt,false,true)
  decodeOp(0x1c,Op.leu,true,true)
  decodeOp(0x1d,Op.le,true,true)
  when(f6 === 0x17.U && arithmeticForm) {
    // vm=1 is vmv.v.*, whose vs2 field must be zero.
    supported := !vm || inst(24,20) === 0.U
    decoded := Mux(vm,Op.move.U,Op.merge.U)
  }
  when(state === decode) {
    // Configuration computes candidate VL/vtype, including vill for an
    // unsupported type. Architectural state changes only at completion.fire.
    config := f3 === 7.U && inst(6,0) === 0x57.U
    illegal := false.B
    when(inst(6,0) =/= 0x57.U) { illegal := true.B; state := finish }
      .elsewhen(f3 === 7.U) {
        val setivli = inst(31,30) === 3.U
        val setvli = !inst(31)
        val setvl = inst(31,25) === 0x40.U
        val t = Mux(setvl,cmd.scalar2,Mux(setivli,inst(29,20),inst(30,20)).pad(64))
        val legalType = t(63,8) === 0.U && t(5,3) <= 3.U && t(2,0) === 0.U
        val maxVl = 16.U(5.W) >> t(4,3)
        val avl = Mux(setivli,inst(19,15).pad(64),cmd.avl)
        nextVl := Mux(legalType,Mux(avl < maxVl,avl(4,0),maxVl),0.U)
        nextVtype := Mux(legalType,t,(BigInt(1)<<63).U(64.W))
        illegal := !(setvli || setivli || setvl)
        state := finish
      }.otherwise {
        // Masked non-mask destinations cannot overlap v0.
        val overlap = !vm && inst(11,7) === 0.U && !comparison
        when(vtype(63) || !supported || overlap) {
          illegal := true.B; state := finish
        }.otherwise {
          operation := decoded; maskResult := comparison; sew := vtype(4,3)
          snapshotPhase := 0.U
          issuedElements := 0.U
          completedElements := 0.U
          state := snapshot
        }
      }
  }
  // The synchronous RF requires separate request/capture states. Phases read
  // vs2, vs1, old vd, then v0; the default address zero selects the predicate.
  when(state === snapshot) {
    registers.io.readEnable := true.B
    registers.io.readAddress := MuxLookup(snapshotPhase,0.U)(Seq(
      0.U -> inst(24,20),1.U -> inst(19,15),2.U -> inst(11,7)))
    state := snapshotCapture
  }
  when(state === snapshotCapture) {
    switch(snapshotPhase) {
      is(0.U) { left := registers.io.readData }
      is(1.U) { right := registers.io.readData }
      is(2.U) { shadow := registers.io.readData }
      is(3.U) { mask := registers.io.readData(15,0) }
    }
    snapshotPhase := snapshotPhase+1.U
    index := 0.U
    state := Mux(snapshotPhase === 3.U,Mux(vl === 0.U,finish,prepare),snapshot)
  }
  // Separate the element-selection mux from arithmetic. Sources are snapshots,
  // including v0, so aliases never corrupt later source elements.
  when(state === prepare) {
    val offset = (index << (sew+&3.U))(6,0)
    val widthMask = VecInit(Seq(8,16,32,64).map(w => ((BigInt(1)<<w)-1).U(64.W)))(sew)
    elementA := (left >> offset)(63,0) & widthMask
    val immediate = Cat(Fill(59,inst(19)),inst(19,15))
    val shiftImmediate = inst(19,15).pad(64)
    val imm = Mux(operation === Op.sll.U || operation === Op.srl.U || operation === Op.sra.U,
      shiftImmediate,immediate)
    elementB := Mux(vv,(right >> offset)(63,0),Mux(vx,cmd.scalar,imm)) & widthMask
    val merge = operation === Op.merge.U
    active := vm || mask(index(3,0)) || merge
    selected := mask(index(3,0))
    state := execute
  }
  def advance(): Unit = {
    index := index+1.U
    state := Mux(index+1.U >= vl,collect,prepare)
  }
  when(state === execute) {
    when(!active) { advance() }
      .elsewhen(lane.io.in.fire) { advance() }
  }
  when(lane.io.in.fire) { issuedElements := issuedElements+1.U }
  // Result tags select the destination element or comparison bit within the
  // private shadow. Masked and tail bits retain the snapshotted old vd value.
  when(lane.io.out.fire) {
    val retiredIndex = lane.io.out.bits.tag(4,0)
    val offset = Mux(maskResult,retiredIndex,(retiredIndex << (sew+&3.U))(6,0))
    val bits = VecInit(Seq(8,16,32,64).map(w => ((BigInt(1)<<w)-1).U(128.W)))(sew)
    val writeMask = Mux(maskResult,1.U(128.W),bits) << offset
    val result = Mux(maskResult,lane.io.out.bits.data & 1.U,lane.io.out.bits.data)
    shadow := (shadow & ~writeMask(127,0)) | ((result.pad(128) << offset)(127,0) & writeMask(127,0))
    completedElements := completedElements+1.U
  }
  when(state === collect && completedElements === issuedElements) { state := finish }
  // One final write publishes the complete shadow. Illegal/cancelled work
  // never updates the RF; flush also invalidates the lane's pending requests.
  when(io.completion.fire) {
    when(!illegal) {
      when(config) { vl := nextVl; vtype := nextVtype }
        .elsewhen(vl =/= 0.U) {
          registers.io.writeEnable := true.B
          registers.io.writeAddress := inst(11,7)
          registers.io.writeMask := 3.U
          registers.io.writeData := shadow
        }
    }
    state := idle
  }
  when(io.flush) { state := idle; ctxValid := false.B }
}
