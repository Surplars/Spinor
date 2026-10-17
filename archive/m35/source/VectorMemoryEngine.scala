package vpu

import chisel3._
import chisel3.util._

class VectorMemoryStatus extends Bundle {
  val fault=Bool();val interrupted=Bool();val cause=UInt(6.W);val address=UInt(64.W);val element=UInt(8.W)
}
/** Unit-stride physical normal-RAM prototype. Uses the arithmetic core's
  * context port for per-element architectural updates and dedicated vstart commit port.
  * Memory instructions are irrevocable ROB-head operations: flush requests a
  * boundary stop and DOES NOT silently cancel completion or issued stores.
  */
class VectorMemoryEngine(regionBase:BigInt=BigInt("80000000",16),regionBytes:BigInt=BigInt(1)<<28) extends Module {
  require(regionBytes>=8 && (regionBytes&(regionBytes-1))==0 && regionBase%regionBytes==0)
  val io=IO(new Bundle {
    val stop=Input(Bool());val command=Flipped(Decoupled(new Command));val completion=Decoupled(new Completion)
    val status=Output(new VectorMemoryStatus);val busy=Output(Bool())
    val vl=Input(UInt(8.W));val vtype=Input(UInt(64.W));val vstart=Input(UInt(7.W))
    val context=Decoupled(new ContextAccess);val contextResult=Flipped(Valid(UInt(64.W)))
    val commit=Decoupled(UInt(7.W))
    val memoryRequest=Decoupled(new VpuMemoryRequest(VpuTLParams()))
    val memoryResponse=Flipped(Decoupled(new VpuMemoryResponse))
  })
  val Seq(idle,decode,validate,maskLow,maskLowWait,maskHigh,maskHighWait,checkElement,addressLow,addressHigh,
    checkAddress,readChunk,readChunkWait,sendMemory,waitMemory,writeChunk,writeChunkWait,writeStart,reply)=Enum(19)
  val state=RegInit(idle);val cmd=Reg(new Command);val length=Reg(UInt(8.W));val typ=Reg(UInt(64.W))
  val index=Reg(UInt(8.W));val width=Reg(UInt(2.W));val baseRegister=Reg(UInt(5.W));val store=Reg(Bool());val masked=Reg(Bool())
  val mask=Reg(UInt(128.W));val original=Reg(UInt(64.W));val result=Reg(UInt(64.W))
  // Reuse original as one write-through register-file chunk, never a whole group snapshot.
  val cachedValid=RegInit(false.B);val cachedAddress=Reg(UInt(6.W))
  val address=Reg(UInt(64.W));val addressCarry=Reg(Bool());val stopped=RegInit(false.B)
  val decodedBad=Reg(Bool());val illegal=Reg(Bool());val status=Reg(new VectorMemoryStatus);val nextStart=Reg(UInt(8.W));val finishAfterStart=Reg(Bool())
  val stop=stopped || io.stop
  io.busy:=state=/=idle;io.command.ready:=state===idle && !io.stop
  io.completion.valid:=state===reply;io.completion.bits:=0.U.asTypeOf(new Completion)
  io.completion.bits.token:=cmd.token;io.completion.bits.instruction:=cmd.instruction;io.completion.bits.illegal:=illegal
  io.status:=status
  io.context.valid:=state===maskLow || state===maskHigh || state===readChunk || (state===writeChunk && !stop)
  io.context.bits:=0.U.asTypeOf(new ContextAccess)
  val byteOffset=(index<<width)(6,0)
  // Compute the RF chunk address alongside the low memory address, before
  // checkAddress/readChunk. This cuts index -> shift/add -> shared RF access
  // without adding an element cycle or changing the write-through cache.
  val chunkAddress=Reg(UInt(6.W))
  val bitOffset=Cat(byteOffset(2,0),0.U(3.W))
  io.context.bits.address:=Mux(state===maskLow,0.U,Mux(state===maskHigh,1.U,chunkAddress))
  io.context.bits.write:=state===writeChunk;io.context.bits.data:=result
  io.commit.valid:=state===writeStart;io.commit.bits:=nextStart(6,0)
  io.memoryRequest.valid:=state===sendMemory
  io.memoryRequest.bits.address:=address;io.memoryRequest.bits.size:=width;io.memoryRequest.bits.write:=store
  io.memoryRequest.bits.data:=original>>bitOffset
  io.memoryRequest.bits.mask:=VecInit(Seq(1,3,15,255).map(_.U(8.W)))(width)
  io.memoryRequest.bits.token:=cmd.token;io.memoryRequest.bits.irrevocable:=true.B
  io.memoryResponse.ready:=state===waitMemory
  when(io.command.fire) {
    cmd:=io.command.bits;length:=io.vl;typ:=io.vtype;index:=io.vstart
    cachedValid:=false.B
    stopped:=false.B;illegal:=false.B;status:=0.U.asTypeOf(new VectorMemoryStatus);state:=decode
  }
  when(io.stop && state=/=idle) { stopped:=true.B }
  def setStart(value:UInt,finish:Bool):Unit={ nextStart:=value;finishAfterStart:=finish;state:=writeStart }
  def interrupt():Unit={ status.interrupted:=true.B;status.element:=index;setStart(index,true.B) }
  def fault(cause:UInt):Unit={ status.fault:=true.B;status.cause:=cause;status.address:=address;status.element:=index;setStart(index,true.B) }
  when(state===decode) {
    val inst=cmd.instruction;val f3=inst(14,12)
    val ew=MuxLookup(f3,0.U(2.W))(Seq(5.U->1.U,6.U->2.U,7.U->3.U))
    val lm=Mux(typ(2),typ(2,0).asSInt,typ(2,0).zext)
    val emul=lm+&ew.zext-typ(4,3).zext
    val group=Mux(emul>0.S,(1.U(4.W)<<emul.asUInt(1,0))(3,0),1.U(4.W))
    val vr=inst(11,7);val isStore=inst(6,0)==="h27".U
    val validOpcode=inst(6,0)==="h07".U || isStore
    val validWidth=f3===0.U || f3===5.U || f3===6.U || f3===7.U
    val bad= !validOpcode || !validWidth || typ(63) || typ(5,3)>3.U || emul<(-3).S || emul>3.S ||
      inst(31,26)=/=0.U || inst(24,20)=/=0.U || (vr&(group-1.U))=/=0.U ||
      (vr+&group)>32.U || (!inst(25) && vr===0.U)
    store:=isStore;masked:= !inst(25);baseRegister:=vr;width:=ew
    decodedBad:=bad;state:=validate
  }
  when(state===validate) {
    when(decodedBad) { illegal:=true.B;state:=reply }
      .elsewhen(index>=length) { setStart(0.U,true.B) }
      .otherwise { state:=maskLow }
  }
  when(state===maskLow && io.context.fire) { state:=maskLowWait }
  when(state===maskLowWait && io.contextResult.valid) { mask:=io.contextResult.bits;state:=maskHigh }
  when(state===maskHigh && io.context.fire) { state:=maskHighWait }
  when(state===maskHighWait && io.contextResult.valid) { mask:=Cat(io.contextResult.bits,mask(63,0));state:=checkElement }
  when(state===checkElement) {
    when(index>=length) { setStart(0.U,true.B) }
      .elsewhen(stop) { interrupt() }
      .elsewhen(masked && !mask(index(6,0))) { index:=index+1.U }
      .otherwise { state:=addressLow }
  }
  when(state===addressLow) {
    chunkAddress:=((baseRegister<<1)+byteOffset(6,3))(5,0)
    val sum=CarrySelect.add(cmd.scalar(31,0),(index<<width).pad(32),false.B)
    address:=Cat(cmd.scalar(63,32),sum(31,0));addressCarry:=sum(32);state:=addressHigh
  }
  when(state===addressHigh) { address:=Cat(ParallelIncrement(cmd.scalar(63,32),addressCarry),address(31,0));state:=checkAddress }
  when(state===checkAddress) {
    val alignment=VecInit(Seq(0,1,3,7).map(_.U(3.W)))(width)
    val regionMask=((BigInt(1)<<64)-1) ^ (regionBytes-1)
    when(stop) { interrupt() }
      .elsewhen((address(2,0)&alignment)=/=0.U) { fault(Mux(store,6.U,4.U)) }
      .elsewhen((address & regionMask.U(64.W))=/=regionBase.U) { fault(Mux(store,7.U,5.U)) }
      .otherwise { state:=Mux(cachedValid && cachedAddress===chunkAddress,sendMemory,readChunk) }
  }
  when(state===readChunk && io.context.fire) { state:=readChunkWait }
  when(state===readChunkWait && io.contextResult.valid) {
    original:=io.contextResult.bits;cachedAddress:=chunkAddress;cachedValid:=true.B
    when(stop) { interrupt() }.otherwise { state:=sendMemory }
  }
  when(io.memoryRequest.fire) { state:=waitMemory }
  when(io.memoryResponse.fire) {
    val response=io.memoryResponse.bits
    val bad=response.denied || response.corrupt || response.protocolError || response.localError || response.token=/=cmd.token
    when(bad) { fault(Mux(store,7.U,5.U)) }
      .elsewhen(store) {
        index:=index+1.U
        setStart(Mux(index+1.U>=length,0.U,index+1.U),index+1.U>=length)
      }.elsewhen(stop) { interrupt() }
      .otherwise {
        val fieldMask=VecInit(Seq(8,16,32,64).map(w=>((BigInt(1)<<w)-1).U(64.W)))(width)
        val positioned=(fieldMask<<bitOffset)(63,0)
        result:=(original & ~positioned) | ((response.data & fieldMask)<<bitOffset)(63,0);state:=writeChunk
      }
  }
  when(state===writeChunk) {
    when(stop) { interrupt() }.elsewhen(io.context.fire) { original:=result;state:=writeChunkWait }
  }
  when(state===writeChunkWait && io.contextResult.valid) {
    index:=index+1.U;setStart(Mux(index+1.U>=length,0.U,index+1.U),index+1.U>=length)
  }
  val commitStalled=RegNext(io.commit.valid && !io.commit.ready,false.B)
  val previousCommit=RegNext(io.commit.bits)
  when(commitStalled) {
    assert(io.commit.valid && io.commit.bits===previousCommit,"progress commit changed under backpressure")
  }
  when(io.commit.fire) {
    state:=Mux(finishAfterStart,reply,checkElement)
  }
  when(io.completion.fire) { state:=idle }
}

/** Current physical normal-RAM load/store top. Host must keep irrevocable
  * memory-command ownership until completion, including after a stop/flush.
  */
class LishiVpuMemory(regionBase:BigInt=BigInt("80000000",16),regionBytes:BigInt=BigInt(1)<<28,chunkBits:Int=32) extends Module {
  require(Set(16,32).contains(chunkBits))
  override def desiredName=if(chunkBits==16)"LishiVpuMemory16" else "LishiVpuMemory"
  val vpu=Module(new RamVector(chunkBits=chunkBits,enableFp=true,enableMemoryCommit=true));val engine=Module(new VectorMemoryEngine(regionBase,regionBytes))
  val bridge=Module(new TileLinkReservation)
  val io=IO(new Bundle {
    val core=chiselTypeOf(vpu.io);val tl=new VpuTileLinkMaster(VpuTLParams())
    val memoryStatus=Valid(new VectorMemoryStatus)
  })
  val memoryOpcode=io.core.command.bits.instruction(6,0)==="h07".U || io.core.command.bits.instruction(6,0)==="h27".U
  val busy=engine.io.busy
  val admit=vpu.io.command.ready && !vpu.io.contextResult.valid && !io.core.context.valid
  engine.io.command.valid:=io.core.command.valid && memoryOpcode && !busy && admit
  engine.io.command.bits:=io.core.command.bits
  io.core.command.ready:=Mux(memoryOpcode,engine.io.command.ready && admit,vpu.io.command.ready && !busy)
  vpu.io.command.valid:=io.core.command.valid && !memoryOpcode && !busy
  vpu.io.command.bits:=io.core.command.bits
  vpu.memoryCommit.get.valid:=engine.io.commit.valid && busy
  vpu.memoryCommit.get.bits:=engine.io.commit.bits
  engine.io.commit.ready:=vpu.memoryCommit.get.ready && busy
  vpu.io.completion.ready:=io.core.completion.ready && !busy
  io.core.completion.valid:=Mux(busy,engine.io.completion.valid,vpu.io.completion.valid)
  io.core.completion.bits:=Mux(busy,engine.io.completion.bits,vpu.io.completion.bits)
  engine.io.completion.ready:=io.core.completion.ready && busy
  vpu.io.context.valid:=Mux(busy,engine.io.context.valid,io.core.context.valid)
  vpu.io.context.bits:=Mux(busy,engine.io.context.bits,io.core.context.bits)
  engine.io.context.ready:=vpu.io.context.ready && busy
  engine.io.contextResult:=vpu.io.contextResult
  io.core.context.ready:=vpu.io.context.ready && !busy
  io.core.contextResult.valid:=vpu.io.contextResult.valid && !busy;io.core.contextResult.bits:=vpu.io.contextResult.bits
  engine.io.stop:=io.core.flush;vpu.io.flush:=io.core.flush && !busy
  engine.io.vl:=vpu.io.vl;engine.io.vtype:=vpu.io.vtype;engine.io.vstart:=vpu.io.vstart
  io.core.vl:=vpu.io.vl;io.core.vtype:=vpu.io.vtype;io.core.vstart:=vpu.io.vstart
  io.core.vxrm:=vpu.io.vxrm;io.core.vxsat:=vpu.io.vxsat;io.core.versions:=vpu.io.versions
  io.core.frm.get:=vpu.io.frm.get;io.core.fflags.get:=vpu.io.fflags.get
  io.core.busy:=vpu.io.busy || busy || bridge.io.busy
  bridge.io.request<>engine.io.memoryRequest;engine.io.memoryResponse<>bridge.io.response
  bridge.io.flush:=false.B;io.tl<>bridge.io.tl
  io.memoryStatus.valid:=engine.io.completion.valid && busy;io.memoryStatus.bits:=engine.io.status
}
