package vpu

import chisel3._
import chisel3.util._

/** RAM-first candidate. VLEN128/ELEN64, m1/m2/m4/m8/mf2/mf4/mf8.
  * Architectural data and uncommitted results reside in versioned RAM.
  * A single 128-bit mask cache and scalar element staging are independent of
  * LMUL; there are no full-group FF snapshots. Basic integer data operations may overlap elements; other units remain serial.
  * Completing non-faulting arithmetic atomically flips destination versions.
  * Shared FP32/FP64 lane with same-width integer conversions. NOT full RVV: LSU,
  * widening/narrowing conversions, reduction FP and remaining integer groups absent.
  */
class RamVector(useRam: Boolean = true, chunkBits: Int = 32, enableFp: Boolean = false, enableMemoryCommit: Boolean = false) extends Module {
  override def desiredName = if(enableMemoryCommit) (if(chunkBits==16) "RamVectorFpMemory16" else "RamVectorFpMemory") else if(enableFp) (if(chunkBits==16) "RamVectorFp16" else "RamVectorFp") else if (!useRam) "RamVectorFlops" else if (chunkBits==16) "RamVector16" else "RamVector"
  val io = IO(new Bundle {
    val flush = Input(Bool())
    val command = Flipped(Decoupled(new Command))
    val completion = Decoupled(new Completion)
    val context = Flipped(Decoupled(new ContextAccess))
    val contextResult = Valid(UInt(64.W))
    val vl = Output(UInt(8.W))
    val vtype = Output(UInt(64.W))
    val vstart = Output(UInt(7.W))
    val vxrm = Output(UInt(2.W))
    val vxsat = Output(Bool())
    val versions = Output(UInt(32.W))
    val frm = if(enableFp) Some(Output(UInt(3.W))) else None
    val fflags = if(enableFp) Some(Output(UInt(5.W))) else None
    val busy = Output(Bool())
  })
  val memoryCommit = if(enableMemoryCommit) Some(IO(Flipped(Decoupled(UInt(7.W))))) else None
  val states=Enum(if(enableFp)24 else 21)
  val Seq(idle, decode, copyRead, copyWrite, maskRead, maskCapture, dispatch,
    readA, captureA, readB, captureB, launch, awaitResult, maskOldRead, maskWrite, finish) = states.take(16)
  val readC=if(enableFp)states(16) else idle
  val captureC=if(enableFp)states(17) else idle
  val checkVector=if(enableFp)states(18) else idle
  val reductionSeedRead=states(if(enableFp)19 else 16)
  val reductionSeedCapture=states(if(enableFp)20 else 17)
  val reductionWrite=states(if(enableFp)21 else 18)
  val scalarRead=states(if(enableFp)22 else 19)
  val scalarCapture=states(if(enableFp)23 else 20)
  val state = RegInit(idle)
  val command = Reg(new Command)
  val vl = RegInit(0.U(8.W))
  val vtype = RegInit((BigInt(1)<<63).U(64.W))
  val vstart = RegInit(0.U(7.W))
  val vxrm = RegInit(0.U(2.W))
  val vxsat = RegInit(false.B)
  val frm=if(enableFp)RegInit(0.U(3.W)) else WireDefault(0.U(3.W))
  val fflags=if(enableFp)RegInit(0.U(5.W)) else WireDefault(0.U(5.W))
  val fp=if(enableFp)RegInit(false.B) else WireDefault(false.B)
  val fpOp=Reg(UInt(5.W)); val fpDestMultiply=Reg(Bool()); val fpReverse=Reg(Bool())
  val fpFlags=if(enableFp)RegInit(0.U(5.W)) else WireDefault(0.U(5.W))
  val c=Reg(UInt(64.W))
  io.frm.foreach(x=>x:=frm); io.fflags.foreach(x=>x:=fflags)
  val illegal = Reg(Bool())
  val kind = Reg(UInt(2.W)) // 0 arithmetic, 1 vset, 2 CSR
  val scalarResult = Reg(UInt(64.W))
  val scalarWrite = Reg(Bool())
  val nextVl = Reg(UInt(8.W))
  val nextVtype = Reg(UInt(64.W))
  val csrWrite = Reg(Bool())
  val csrData = Reg(UInt(64.W))
  val index = Reg(UInt(8.W))
  val sew = Reg(UInt(2.W))
  val op = Reg(UInt(Op.width.W))
  val comparison = Reg(Bool())
  val destinationCount = Reg(UInt(4.W))
  val commitMask = Reg(UInt(32.W))
  val hasElements = Reg(Bool())
  val copyIndex = Reg(UInt(4.W))
  val mask = Reg(UInt(128.W))
  val sourceOffset = Reg(UInt(3.W))
  val bitOffset = Reg(UInt(7.W))
  val destination = Reg(UInt(5.W))
  val byteMask = Reg(UInt(16.W))
  val a = Reg(UInt(64.W))
  val b = Reg(UInt(64.W))
  val resultBit = Reg(Bool())
  val outstanding = RegInit(0.U(5.W))
  val reduction=RegInit(false.B)
  val maskLogic=RegInit(false.B)
  val scalarMove=RegInit(0.U(2.W)) // 0 ordinary, 1 vmv.x.s, 2 vmv.s.x
  val maskScalar=RegInit(false.B) // vcpop.m / vfirst.m, no vector destination
  val reductionAccumulator=Reg(UInt(64.W)) // one scalar element, never a group snapshot
  val streaming = WireDefault(false.B)
  val rf = Module(new VersionedRegisterFile(useRam))
  rf.io.readEnable := false.B; rf.io.readAddress := 0.U; rf.io.readCandidate := false.B
  val writeEnable = WireDefault(false.B)
  val writeAddress = WireDefault(0.U(5.W))
  val writeCandidate = WireDefault(false.B)
  val writeData = WireDefault(0.U(128.W))
  val writeMask = WireDefault(0.U(16.W))
  val writePending = if(enableFp) RegInit(false.B) else WireDefault(false.B)
  rf.io.commit := false.B; rf.io.commitMask := commitMask
  io.versions := rf.io.versions
  io.vl := vl; io.vtype := vtype; io.vstart := vstart; io.vxrm := vxrm; io.vxsat := vxsat
  io.busy := state =/= idle
  io.command.ready := state === idle && !io.context.valid && !writePending && !io.flush
  io.context.ready := state === idle && !writePending && !io.flush
  memoryCommit.foreach { port =>
    port.ready := state === idle && !writePending && !io.context.valid && !io.command.valid && !io.flush
    when(port.fire) {
      assert(!io.contextResult.valid,"memory progress overlaps context response")
      vstart := port.bits
    }
  }
  val contextValid = RegNext(io.context.fire,false.B)
  val contextWrite = Reg(Bool())
  val contextChunk = Reg(Bool())
  io.contextResult.valid := contextValid && !io.flush
  io.contextResult.bits := Mux(contextWrite,0.U,Mux(contextChunk,rf.io.readData(127,64),rf.io.readData(63,0)))
  when(io.context.fire) {
    contextWrite := io.context.bits.write; contextChunk := io.context.bits.address(0)
    rf.io.readEnable := !io.context.bits.write
    rf.io.readAddress := io.context.bits.address(5,1)
    writeEnable := io.context.bits.write
    writeAddress := io.context.bits.address(5,1)
    writeData := Fill(2,io.context.bits.data)
    writeMask := Mux(io.context.bits.address(0),"hff00".U,"h00ff".U)
  }
  io.completion.valid := state === finish && !writePending && !io.flush
  io.completion.bits.token := command.token
  io.completion.bits.instruction := command.instruction
  io.completion.bits.scalar := Mux(illegal,0.U,scalarResult)
  io.completion.bits.writesScalar := scalarWrite && !illegal
  io.completion.bits.illegal := illegal
  when(io.command.fire) { command := io.command.bits; state := decode }
  val inst = command.instruction
  val f3 = inst(14,12); val f6 = inst(31,26)
  val vd = inst(11,7); val vs2 = inst(24,20); val vs1 = inst(19,15)
  val vm = inst(25)
  val vv = f3 === 0.U; val vx = f3 === 4.U; val vi = f3 === 3.U
  val fpVV=enableFp.B && f3===1.U; val fpVF=enableFp.B && f3===5.U
  val fpUnary=fpVV && (f6===0x13.U || f6===0x12.U)
  val mulVV=f3===2.U; val mulVX=f3===6.U
  val reductionEncoding=mulVV && f6<=7.U
  val maskLogicEncoding=mulVV && f6>=0x18.U && f6<=0x1f.U
  val scalarReadEncoding=mulVV && f6===0x10.U && vm && vs1===0.U
  val scalarWriteEncoding=mulVX && f6===0x10.U && vm && vs2===0.U
  val maskScalarEncoding=mulVV && f6===0x10.U && (vs1===16.U || vs1===17.U)
  val scalarMoveEncoding=Mux(scalarReadEncoding,1.U(2.W),Mux(scalarWriteEncoding,2.U(2.W),0.U(2.W)))
  val vectorSource1=(vv || mulVV || (fpVV && !fpUnary)) && !reductionEncoding
  val fpSupported=WireDefault(false.B)
  val fpDecoded=WireDefault(0.U(5.W)); val fpMask=WireDefault(false.B)
  if(enableFp) {
    def entryFp(code: Int, operation: Int, mask: Boolean=false, scalarOnly: Boolean=false): Unit = {
      when(f6===code.U && (fpVF || (fpVV && !scalarOnly.B))) {
        fpSupported:=true.B; fpDecoded:=operation.U; fpMask:=mask.B
      }
    }
    entryFp(0x00,FpOp.add); entryFp(0x02,FpOp.sub)
    entryFp(0x04,FpOp.min); entryFp(0x06,FpOp.max)
    entryFp(0x08,FpOp.sgnj); entryFp(0x09,FpOp.sgnjn); entryFp(0x0a,FpOp.sgnjx)
    entryFp(0x18,FpOp.eq,true); entryFp(0x19,FpOp.le,true)
    entryFp(0x1b,FpOp.lt,true); entryFp(0x1c,FpOp.ne,true)
    entryFp(0x1d,FpOp.gt,true,true); entryFp(0x1f,FpOp.ge,true,true)
    entryFp(0x20,FpOp.div); entryFp(0x21,FpOp.div,false,true)
    entryFp(0x24,FpOp.mul); entryFp(0x27,FpOp.sub,false,true)
    for (base<-Seq(0x28,0x2c)) {
      entryFp(base,FpOp.fma); entryFp(base+1,FpOp.fnmadd)
      entryFp(base+2,FpOp.fmsub); entryFp(base+3,FpOp.fnmsub)
    }
    when(fpVV && f6===0x13.U && (vs1===0.U || vs1===16.U)) {
      fpSupported:=true.B; fpDecoded:=Mux(vs1===0.U,FpOp.sqrt.U,FpOp.classify.U)
    }
  }
    if(enableFp) {
      for((sub,operation)<-Seq((0,FpOp.toUInt),(1,FpOp.toInt),(2,FpOp.fromUInt),(3,FpOp.fromInt),(6,FpOp.toUIntRtz),(7,FpOp.toIntRtz))) {
        when(fpVV && f6===0x12.U && vs1===sub.U) { fpSupported:=true.B;fpDecoded:=operation.U }
      }
    }
  val decodedOp = WireDefault(0.U(Op.width.W))
  val supported = WireDefault(false.B)
  val decodedMask = WireDefault(false.B)
  def entry(code: Int, operation: Int, immediate: Boolean = true, producesMask: Boolean = false): Unit = {
    when(f6 === code.U && (vv || vx || vi) && (immediate.B || !vi)) {
      decodedOp := operation.U; supported := true.B; decodedMask := producesMask.B
    }
  }
  entry(0x00,Op.add); entry(0x02,Op.sub,false)
  entry(0x09,Op.and); entry(0x0a,Op.or); entry(0x0b,Op.xor)
  entry(0x25,Op.sll); entry(0x28,Op.srl); entry(0x29,Op.sra)
  entry(0x04,Op.minu,false); entry(0x05,Op.min,false)
  entry(0x06,Op.maxu,false); entry(0x07,Op.max,false)
  entry(0x18,Op.eq,true,true); entry(0x19,Op.ne,true,true)
  entry(0x1a,Op.ltu,false,true); entry(0x1b,Op.lt,false,true)
  entry(0x1c,Op.leu,true,true); entry(0x1d,Op.le,true,true)
  when(f6 === 0x17.U && (vv || vx || vi)) {
    supported := !vm || vs2 === 0.U
    decodedOp := Mux(vm,Op.move.U,Op.merge.U)
  }
  for((code,operation)<-Seq((0x20,Op.divu),(0x21,Op.div),(0x22,Op.remu),(0x23,Op.rem),(0x25,Op.mul),(0x27,Op.mulh),(0x24,Op.mulhu),(0x26,Op.mulhsu))) {
    when(f6===code.U && (mulVV || mulVX)) { supported:=true.B;decodedOp:=operation.U }
  }
  when(reductionEncoding) {
    supported:=true.B
    decodedOp:=MuxLookup(f6,Op.add.U)(Seq(0.U->Op.add.U,1.U->Op.and.U,
      2.U->Op.or.U,3.U->Op.xor.U,4.U->Op.minu.U,5.U->Op.min.U,
      6.U->Op.maxu.U,7.U->Op.max.U))
  }
  when(maskLogicEncoding) {
    supported:=vm;decodedMask:=true.B
    decodedOp:=MuxLookup(f6,Op.and.U)(Seq(
      0x1a.U->Op.or.U,0x1b.U->Op.xor.U,0x1c.U->Op.or.U,
      0x1e.U->Op.or.U,0x1f.U->Op.xor.U))
  }
  when(scalarReadEncoding || scalarWriteEncoding) {supported:=true.B;decodedOp:=Op.move.U}
  when(maskScalarEncoding) {supported:=true.B;decodedOp:=Op.move.U}
  val producesMask=Mux(fpSupported,fpMask,decodedMask)
  // Register decode before alignment/overlap/permission checks in the FP top.
  val selectedOp=if(enableFp)Reg(UInt(Op.width.W)) else decodedOp
  val selectedFpOp=Reg(UInt(5.W))
  val selectedFp=if(enableFp)Reg(Bool()) else fpSupported
  val selectedMask=if(enableFp)Reg(Bool()) else producesMask
  val selectedSupported=if(enableFp)Reg(Bool()) else (supported||fpSupported)
  val selectedReduction=if(enableFp)Reg(Bool()) else reductionEncoding
  val selectedMaskLogic=if(enableFp)Reg(Bool()) else maskLogicEncoding
  val selectedScalarMove=if(enableFp)Reg(UInt(2.W)) else scalarMoveEncoding
  val selectedMaskScalar=if(enableFp)Reg(Bool()) else maskScalarEncoding
  def maxVl(t: UInt): UInt = {
    val base = 16.U(8.W) >> t(4,3)
    MuxLookup(t(2,0),0.U(8.W))(Seq(
      0.U -> base,1.U -> (base<<1)(7,0),2.U -> (base<<2)(7,0),3.U -> (base<<3)(7,0),
      5.U -> (base>>3),6.U -> (base>>2),7.U -> (base>>1)))
  }
  val groupLog = Mux(vtype(2,0) <= 3.U,vtype(1,0),0.U(2.W))
  val groupCount = (1.U(4.W)<<groupLog)(3,0)
  val alignment = (groupCount-1.U).pad(5)
  val sourceGroupEnd2 = vs2+&groupCount
  val sourceGroupEnd1 = vs1+&groupCount
  // Mask destinations have EEW=1: overlap may only use the lowest register
  // of a wider source group (generic narrowing-overlap rule).
  val badMaskOverlap = selectedMask && !selectedMaskLogic && ((vd > vs2 && vd < sourceGroupEnd2) ||
    (vectorSource1 && vd > vs1 && vd < sourceGroupEnd1))
  def validateVector(): Unit = {
    val needsVs2 = selectedFp || selectedOp =/= Op.move.U
    val singleRegister=selectedMaskLogic || selectedScalarMove=/=0.U || selectedMaskScalar
    val misaligned = !singleRegister && ((needsVs2 && (vs2&alignment) =/= 0.U) || (vectorSource1 && (vs1&alignment) =/= 0.U) ||
      (!selectedMask && !selectedReduction && (vd&alignment) =/= 0.U))
    val fpIllegal=selectedFp && (vtype(4,3)<2.U || (frm>4.U && selectedFpOp=/=FpOp.toUIntRtz.U && selectedFpOp=/=FpOp.toIntRtz.U))
    when(vtype(63) || !selectedSupported || fpIllegal || misaligned || badMaskOverlap ||
      (!vm && !selectedMask && !selectedReduction && !selectedMaskScalar && vd === 0.U) ||
      ((selectedReduction || selectedMaskScalar) && vstart=/=0.U)) {
      illegal := true.B; state := finish
    }.otherwise {
      sew := Mux(selectedMaskLogic,0.U,vtype(4,3)); op := selectedOp; comparison := selectedMask
      reduction:=selectedReduction
      maskLogic:=selectedMaskLogic;scalarMove:=selectedScalarMove
      maskScalar:=selectedMaskScalar
      if(enableFp) {
        fp:=selectedFp; fpOp:=selectedFpOp
        fpDestMultiply:=f6>=0x28.U && f6<=0x2b.U
        fpReverse:=fpVF && (f6===0x21.U || f6===0x27.U)
      }
      destinationCount := Mux(selectedMask || selectedReduction || singleRegister,1.U,groupCount)
      val maskBase = Mux(selectedMask || selectedReduction || singleRegister,1.U(32.W),MuxLookup(groupLog,1.U(32.W))(Seq(
        1.U -> 3.U(32.W),2.U -> 15.U(32.W),3.U -> 255.U(32.W))))
      commitMask := (maskBase<<vd)(31,0)
      copyIndex := 0.U; index := vstart
      hasElements := vl =/= 0.U && vstart < vl && selectedScalarMove=/=1.U && !selectedMaskScalar
      scalarWrite:=(selectedScalarMove===1.U || selectedMaskScalar) && vd=/=0.U
      when(selectedMaskScalar) {scalarResult:=Mux(vs1===17.U,"hffffffffffffffff".U,0.U)}
      state := Mux(selectedMaskScalar,Mux(vl===0.U,finish,maskRead),
        Mux(selectedScalarMove===1.U,scalarRead,Mux(vl === 0.U || vstart >= vl,finish,copyRead)))
    }
  }
  when(state === decode) {
    illegal := false.B; scalarResult := 0.U; scalarWrite := false.B; kind := 0.U
    hasElements := false.B; csrWrite := false.B
    if(enableFp) { fpFlags:=0.U }
    when(inst(6,0) === 0x73.U) {
      kind := 2.U
      val address = inst(31,20)
      val old = WireDefault(0.U(64.W))
      val known = WireDefault(true.B)
      switch(address) {
        is(0x008.U) { old := vstart }
        is(0x009.U) { old := vxsat }
        is(0x00a.U) { old := vxrm }
        is(0x00f.U) { old := Cat(vxrm,vxsat) }
        is(0xc20.U) { old := vl }
        is(0xc21.U) { old := vtype }
        is(0xc22.U) { old := 16.U }
      }
      if(enableFp) {
        switch(address) {
          is(0x001.U) { old:=fflags }
          is(0x002.U) { old:=frm }
          is(0x003.U) { old:=Cat(frm,fflags) }
        }
      }
      known := (Seq(0x008,0x009,0x00a,0x00f,0xc20,0xc21,0xc22)++
        (if(enableFp)Seq(0x001,0x002,0x003) else Seq.empty)).map(x => address === x.U).reduce(_||_)
      val action = f3(1,0)
      val source = Mux(f3(2),vs1.pad(64),command.scalar)
      val write = action === 1.U || (vs1 =/= 0.U && action =/= 0.U)
      csrWrite := write
      csrData := MuxLookup(action,source)(Seq(2.U -> (old|source),3.U -> (old & ~source)))
      scalarResult := old; scalarWrite := vd =/= 0.U
      illegal := !known || action === 0.U || (write && address(11,10) === 3.U)
      state := finish
    }.elsewhen(inst(6,0) =/= 0x57.U) {
      illegal := true.B; state := finish
    }.elsewhen(f3 === 7.U) {
      kind := 1.U
      val setvl = inst(31,25) === 0x40.U
      val setivli = inst(31,30) === 3.U
      val setvli = !inst(31)
      val t = Mux(setvl,command.scalar2,Mux(setivli,inst(29,20),inst(30,20)).pad(64))
      val fractionalLegal = VectorConfig.fractionalLegal(t)
      val keepVl = !setivli && vs1 === 0.U && vd === 0.U
      val legal = t(63,8) === 0.U && t(5,3) <= 3.U && fractionalLegal &&
        (!keepVl || (!vtype(63) && maxVl(t) === maxVl(vtype)))
      val avl = Mux(setivli,vs1.pad(64),Mux(vs1 === 0.U,Mux(vd === 0.U,vl.pad(64),"hffffffffffffffff".U),command.avl))
      val maximum=maxVl(t)
      val length = Mux(VectorConfig.belowLimit(avl,maximum),avl(7,0),maximum)
      nextVl := Mux(legal,length,0.U)
      nextVtype := Mux(legal,t,(BigInt(1)<<63).U(64.W))
      scalarResult := Mux(legal,length,0.U); scalarWrite := vd =/= 0.U
      illegal := !(setvl || setivli || setvli)
      state := finish
    }.otherwise {
      if(enableFp) {
        selectedOp:=decodedOp;selectedFpOp:=fpDecoded;selectedFp:=fpSupported
        selectedMask:=producesMask;selectedSupported:=supported||fpSupported
        selectedReduction:=reductionEncoding
        selectedMaskLogic:=maskLogicEncoding;selectedScalarMove:=scalarMoveEncoding
        selectedMaskScalar:=maskScalarEncoding
        state:=checkVector
      } else {
        validateVector()
      }
    }
  }
  if(enableFp) { when(state===checkVector) { validateVector() } }
  when(state === copyRead) {
    rf.io.readEnable := true.B; rf.io.readAddress := (vd+copyIndex)(4,0)
    state := copyWrite
  }
  when(state === copyWrite) {
    writeEnable := true.B; writeAddress := (vd+copyIndex)(4,0)
    writeCandidate := true.B; writeData := rf.io.readData; writeMask := "hffff".U
    copyIndex := copyIndex+1.U
    state := Mux(copyIndex+1.U >= destinationCount,Mux(scalarMove===2.U,reductionWrite,maskRead),copyRead)
  }
  when(state === maskRead) {
    rf.io.readEnable := true.B; rf.io.readAddress := 0.U; state := maskCapture
  }
  when(state === maskCapture) { mask := rf.io.readData; state := Mux(reduction,reductionSeedRead,dispatch) }
  when(state === dispatch) {
    when(index >= vl) { state := Mux(reduction,reductionWrite,Mux(streaming && outstanding=/=0.U,awaitResult,finish)) }
      .elsewhen(!vm && !mask(index(6,0)) && (fp || op =/= Op.merge.U)) { index := index+1.U }
      .otherwise {
        val offset = (index<<sew)(6,0)
        sourceOffset := Mux(maskLogic || maskScalar,0.U,offset(6,4))
        bitOffset := Mux(maskLogic || maskScalar,index(6,0),Cat(offset(3,0),0.U(3.W)))
        destination := Mux(comparison,vd,(vd+offset(6,4))(4,0))
        val widthMask = VecInit(Seq(1,3,15,255).map(_.U(16.W)))(sew)
        byteMask := (widthMask<<offset(3,0))(15,0)
        state := readA
      }
  }
  val elementMask = VecInit(Seq(8,16,32,64).map(w => ((BigInt(1)<<w)-1).U(64.W)))(sew)
  when(state===scalarRead) {rf.io.readEnable:=true.B;rf.io.readAddress:=vs2;state:=scalarCapture}
  when(state===scalarCapture) {
    val value=rf.io.readData(63,0)
    scalarResult:=MuxLookup(sew,value)(Seq(
      0.U->Cat(Fill(56,value(7)),value(7,0)),
      1.U->Cat(Fill(48,value(15)),value(15,0)),
      2.U->Cat(Fill(32,value(31)),value(31,0))))
    state:=finish
  }
  when(state===reductionSeedRead) {
    rf.io.readEnable:=true.B;rf.io.readAddress:=vs1;state:=reductionSeedCapture
  }
  when(state===reductionSeedCapture) {
    reductionAccumulator:=rf.io.readData(63,0)&elementMask;state:=dispatch
  }
  when(state===reductionWrite) {
    writeEnable:=true.B;writeCandidate:=true.B;writeAddress:=vd
    writeMask:=VecInit(Seq(1,3,15,255).map(_.U(16.W)))(sew)
    writeData:=Mux(scalarMove===2.U,command.scalar,reductionAccumulator).pad(128);state:=finish
  }
  when(state === readA) {
    rf.io.readEnable := true.B; rf.io.readAddress := (vs2+sourceOffset)(4,0); state := captureA
  }
  when(state === captureA) {
    val value=(rf.io.readData>>bitOffset)(63,0)
    a := Mux(maskLogic,value(0).asUInt,value&elementMask)
    val immediate = Cat(Fill(59,vs1(4)),vs1)
    val isShift = op === Op.sll.U || op === Op.srl.U || op === Op.sra.U
    val fpScalar=Mux(sew===2.U && !command.scalar(63,32).andR,"h7fc00000".U,command.scalar)
    b := Mux(reduction,reductionAccumulator,Mux(fp,fpScalar,Mux(vx || mulVX,command.scalar,Mux(isShift,vs1.pad(64),immediate))))&elementMask
    val fused=fp && fpOp>=FpOp.fma.U && fpOp<=FpOp.fnmadd.U
    state := Mux(vectorSource1,readB,Mux(fused,readC,launch))
    when(maskScalar) {
      index:=index+1.U;state:=dispatch
      when(value(0)) {
        when(vs1===17.U) {scalarResult:=index;state:=finish}
          .otherwise {scalarResult:=(scalarResult(7,0)+1.U)(7,0)}
      }
    }
  }
  when(state === readB) {
    rf.io.readEnable := true.B; rf.io.readAddress := (vs1+sourceOffset)(4,0); state := captureB
  }
  when(state === captureB) {
    val value=(rf.io.readData>>bitOffset)(63,0)
    b := Mux(maskLogic,(value(0) ^ (f6===0x18.U || f6===0x1c.U)).asUInt,value&elementMask)
    state := Mux(fp && fpOp>=FpOp.fma.U && fpOp<=FpOp.fnmadd.U,readC,launch)
  }
  if(enableFp) {
    when(state===readC) {
      rf.io.readEnable:=true.B; rf.io.readAddress:=(vd+sourceOffset)(4,0); state:=captureC
    }
    when(state===captureC) { c:=(rf.io.readData>>bitOffset)(63,0)&elementMask; state:=launch }
  }
  val lane = Module(new IntegerLane(true,chunkBits))
  lane.io.flush := io.flush
  val isMul=op===Op.mul.U || op===Op.mulh.U || op===Op.mulhu.U || op===Op.mulhsu.U
  val isDiv=op===Op.div.U || op===Op.divu.U || op===Op.rem.U || op===Op.remu.U
  lane.io.in.valid := state === launch && !fp && !isMul && !isDiv && !io.flush
  lane.io.in.bits.a := a; lane.io.in.bits.b := b; lane.io.in.bits.sew := sew
  lane.io.in.bits.op := op; lane.io.in.bits.select := mask(index(6,0)); lane.io.in.bits.tag := index
  streaming := !fp && !comparison && !isMul && !isDiv && !reduction
  val streamActive=state===dispatch || state===readA || state===captureA || state===readB || state===captureB || state===launch || state===awaitResult
  lane.io.out.ready := (Mux(streaming,streamActive,state===awaitResult)) && !fp && !isMul && !isDiv && !io.flush
  when(lane.io.in.fire) {
    when(streaming) { index:=index+1.U;state:=dispatch }.otherwise { state:=awaitResult }
  }
  when(streaming && (lane.io.in.fire =/= lane.io.out.fire)) {
    outstanding:=Mux(lane.io.in.fire,outstanding+1.U,outstanding-1.U)
  }
  when(streaming && state===awaitResult && outstanding===0.U) { state:=finish }
  when(lane.io.out.fire && streaming) { assert(outstanding=/=0.U,"integer response without owner") }
  when(io.completion.valid) { assert(outstanding===0.U,"completion before element drain") }
  val multiplier=Module(new IntegerMultiply)
  multiplier.io.flush:=io.flush;multiplier.io.in.bits:=lane.io.in.bits
  multiplier.io.in.valid:=state===launch && !fp && isMul && !io.flush
  multiplier.io.out.ready:=state===awaitResult && !fp && isMul && !io.flush
  when(multiplier.io.in.fire) { state:=awaitResult }
  val divider=Module(new IntegerDivide)
  divider.io.flush:=io.flush;divider.io.in.bits:=lane.io.in.bits
  divider.io.in.valid:=state===launch && !fp && isDiv && !io.flush
  divider.io.out.ready:=state===awaitResult && !fp && isDiv && !io.flush
  when(divider.io.in.fire) { state:=awaitResult }
  val integerFire=Mux(isDiv,divider.io.out.fire,Mux(isMul,multiplier.io.out.fire,lane.io.out.fire))
  val integerData=Mux(isDiv,divider.io.out.bits.data,Mux(isMul,multiplier.io.out.bits.data,lane.io.out.bits.data))
  val resultFire=WireDefault(integerFire)
  val resultData=WireDefault(integerData)
  if(enableFp) {
    val unit=Module(new FloatingPointLane)
    unit.io.flush:=io.flush
    unit.io.in.valid:=state===launch && fp && !io.flush
    unit.io.in.bits.a:=Mux(fpReverse,b,Mux(fpDestMultiply,c,a))
    unit.io.in.bits.b:=Mux(fpReverse,a,b)
    unit.io.in.bits.c:=Mux(fpDestMultiply,a,c)
    unit.io.in.bits.op:=fpOp; unit.io.in.bits.double:=sew===3.U
    unit.io.in.bits.rounding:=frm; unit.io.in.bits.tag:=index
    unit.io.out.ready:=state===awaitResult && fp && !io.flush
    when(unit.io.in.fire) { state:=awaitResult }
    when(unit.io.out.fire) {
      fpFlags:=fpFlags | unit.io.out.bits.flags
      when(unit.io.out.bits.illegal) { illegal:=true.B; state:=finish }
    }
    resultFire:=Mux(fp,unit.io.out.fire && !unit.io.out.bits.illegal,integerFire)
    resultData:=Mux(fp,unit.io.out.bits.data,integerData)
  }
  when(resultFire) {
    when(reduction) {reductionAccumulator:=resultData;index:=index+1.U;state:=dispatch}
      .elsewhen(comparison) { resultBit := resultData(0) ^ (maskLogic && f6>=0x1d.U); state := maskOldRead }
      .otherwise {
        writeEnable := true.B; writeAddress := destination; writeCandidate := true.B
        val retiredOffset=(lane.io.out.bits.tag<<sew)(6,0)
        val retiredBits=Cat(retiredOffset(3,0),0.U(3.W))
        val retiredMask=(VecInit(Seq(1,3,15,255).map(_.U(16.W)))(sew)<<retiredOffset(3,0))(15,0)
        writeAddress:=Mux(streaming,(vd+retiredOffset(6,4))(4,0),destination)
        writeMask := Mux(streaming,retiredMask,byteMask)
        writeData := (resultData.pad(128)<<Mux(streaming,retiredBits,bitOffset))(127,0)
        when(!streaming) { index := index+1.U; state := dispatch }
      }
  }
  when(state === maskOldRead) {
    rf.io.readEnable := true.B; rf.io.readAddress := vd; rf.io.readCandidate := true.B; state := maskWrite
  }
  when(state === maskWrite) {
    val oldByte = (rf.io.readData>>Cat(index(6,3),0.U(3.W)))(7,0)
    val bit = (1.U(8.W)<<index(2,0))(7,0)
    val newByte = (oldByte & ~bit) | Mux(resultBit,bit,0.U)
    writeEnable := true.B; writeAddress := vd; writeCandidate := true.B
    writeMask := (1.U(16.W)<<index(6,3))(15,0); writeData := Fill(16,newByte)
    index := index+1.U; state := dispatch
  }
  when(io.completion.fire) {
    when(!illegal) {
      when(kind === 1.U) { vl := nextVl; vtype := nextVtype; vstart := 0.U }
        .elsewhen(kind === 2.U) {
          when(csrWrite) {
            switch(inst(31,20)) {
              is(0x008.U) { vstart := csrData(6,0) }
              is(0x009.U) { vxsat := csrData(0) }
              is(0x00a.U) { vxrm := csrData(1,0) }
              is(0x00f.U) { vxrm := csrData(2,1); vxsat := csrData(0) }
            }
            if(enableFp) {
              switch(inst(31,20)) {
                is(0x001.U) { fflags:=csrData(4,0) }
                is(0x002.U) { frm:=csrData(2,0) }
                is(0x003.U) { frm:=csrData(7,5); fflags:=csrData(4,0) }
              }
            }
          }
        }.otherwise {
          when(hasElements) { rf.io.commit := true.B }
          if(enableFp) { when(fp) { fflags:=fflags | fpFlags } }
          vstart := 0.U
        }
    }
    state := idle
  }
  when(io.flush) {
    outstanding:=0.U
    state := idle
    writeEnable := false.B
    rf.io.commit := false.B
  }
  if(enableFp) {
    // M5: break result-ready/state -> RAM address and read/modify/write paths.
    // Candidate writes can be discarded on flush. Context writes bypass this
    // stage so their architectural effect still occurs on context.fire.
    val stagedAddress = Reg(UInt(5.W))
    val stagedMask = Reg(UInt(16.W))
    val stagedData = Reg(UInt(128.W))
    val enqueueWrite = writeEnable && writeCandidate && !io.flush
    writePending := enqueueWrite
    when(enqueueWrite) {
      stagedAddress := writeAddress
      stagedMask := writeMask
      stagedData := writeData
    }
    val contextWriteNow = io.context.fire && io.context.bits.write
    rf.io.writeEnable := (writePending && !io.flush) || contextWriteNow
    // Use context IO fields directly: selecting the shared write-request mux
    // here would leave a combinational path from unit.out.ready/state to RAM.
    rf.io.writeAddress := Mux(contextWriteNow,io.context.bits.address(5,1),stagedAddress)
    rf.io.writeCandidate := !contextWriteNow
    rf.io.writeMask := Mux(contextWriteNow,Mux(io.context.bits.address(0),"hff00".U,"h00ff".U),stagedMask)
    rf.io.writeData := Mux(contextWriteNow,Fill(2,io.context.bits.data),stagedData)
    when(writePending) {
      assert(!contextWriteNow,"context write collided with pending candidate")
      assert(!rf.io.commit,"version commit preceded candidate write drain")
    }
  } else {
    rf.io.writeEnable := writeEnable
    rf.io.writeAddress := writeAddress
    rf.io.writeCandidate := writeCandidate
    rf.io.writeMask := writeMask
    rf.io.writeData := writeData
  }
}
