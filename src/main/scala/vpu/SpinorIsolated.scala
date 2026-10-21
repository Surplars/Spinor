package vpu

import chisel3._
import chisel3.util._

/** One-entry, non-flowing, non-pipelined link. Both valid/data and reverse
  * ready terminate at registers. No cancellation of accepted transactions.
  */
class RegisteredLink[T <: Data](gen:T) extends Module {
  val io=IO(new Bundle {val in=Flipped(Decoupled(gen));val out=Decoupled(gen)})
  val full=RegInit(false.B);val data=Reg(gen)
  io.in.ready:= !full;io.out.valid:=full;io.out.bits:=data
  when(io.in.fire) {data:=io.in.bits;full:=true.B}
  when(io.out.fire) {full:=false.B}
}

class IsolatedState extends Bundle {
  val vl=UInt(8.W);val vtype=UInt(64.W);val vstart=UInt(7.W)
  val vxrm=UInt(2.W);val vxsat=Bool();val frm=UInt(3.W);val fflags=UInt(5.W)
}
class IsolatedResult extends Bundle {
  val reply=new VpuHostReply
  val flagsValid=Bool();val flags=UInt(5.W)
}
class IsolatedDone extends Bundle {
  val result=new IsolatedResult
  val state=new IsolatedState
}
class IsolatedFcsr extends Bundle {val frm=UInt(3.W);val fflags=UInt(5.W)}

/** Same-clock registered SoC boundary. The CPU offers only irrevocable work.
  * preview is NOT completion: grant authorizes a later local completion.fire;
  * done acknowledges publication. After grant the CPU must retain ownership
  * and defer interrupts/recovery until done.fire. No younger work may pass it.
  * This intentionally does not implement the old single-edge reply protocol.
  */
class SpinorIsolated(monitorBase:BigInt=0,config:SpinorParams=SpinorParams()) extends Module {
  val core=Module(new SpinorVpu(monitorBase,config,retimeMemory=true))
  val io=IO(new Bundle {
    val offer=Flipped(Decoupled(new Command))
    val preview=Valid(new IsolatedResult)
    val grant=Flipped(Decoupled(UInt(80.W)))
    val done=Decoupled(new IsolatedDone)
    val stop=Input(Bool());val canceled=Valid(UInt(80.W))
    val busy=Output(Bool());val protocolError=Output(Bool())
    val contextMode=Input(Bool())
    val context=Flipped(Decoupled(new ContextAccess));val contextResult=Decoupled(UInt(64.W))
    val fcsrHost=if(config.hostFcsr)Some(Input(new IsolatedFcsr)) else None
    val status=Valid(new IsolatedState)
    val tl=new VpuTileLinkMaster(VpuTLParams())
    val monitor=Flipped(new VpuTileLinkMaster(VpuTLParams()))
  })
  val Seq(idle,dispatch,waiting,prepared,authorizing,commit,published,ack,cancel,
    contextSend,contextWait,contextReply,poison)=Enum(13)
  val state=RegInit(idle)
  val owner=Reg(new Command);val grantToken=Reg(UInt(80.W))
  val memory=owner.instruction(6,0)==="h07".U || owner.instruction(6,0)==="h27".U
  val store=owner.instruction(6,0)==="h27".U
  // The same immutable packet serves preview and done. Keep it until done.fire
  // instead of copying another wide completion register at publication.
  val result=Reg(new IsolatedResult);val finishedState=Reg(new IsolatedState)
  val contextRequest=Reg(new ContextAccess);val contextData=Reg(UInt(64.W))
  val contextMode=RegNext(io.contextMode,false.B);val stop=RegNext(io.stop,false.B)
  val stopPending=RegInit(false.B)
  val stopping=stop || stopPending
  io.offer.ready:=state===idle && !contextMode && !stop
  io.context.ready:=state===idle && contextMode && !stop
  io.preview.valid:=state===prepared;io.preview.bits:=result
  io.grant.ready:=state===prepared
  io.done.valid:=state===ack;io.done.bits.result:=result;io.done.bits.state:=finishedState
  io.canceled.valid:=state===cancel;io.canceled.bits:=owner.token
  io.contextResult.valid:=state===contextReply;io.contextResult.bits:=contextData
  io.busy:=state=/=idle;io.protocolError:=state===poison

  val observed=Wire(new IsolatedState)
  observed.vl:=core.io.core.vl;observed.vtype:=core.io.core.vtype
  observed.vstart:=core.io.core.vstart;observed.vxrm:=core.io.core.vxrm
  observed.vxsat:=core.io.core.vxsat
  observed.frm:=core.io.core.frm.getOrElse(0.U)
  observed.fflags:=core.io.core.fflags.getOrElse(0.U)
  val status=RegInit(0.U.asTypeOf(new IsolatedState));status:=observed
  io.status.bits:=status;io.status.valid:=RegNext(!reset.asBool,false.B)

  if(config.hostFcsr) {
    val committedFrm=RegNext(io.fcsrHost.get.frm,0.U)
    val committedFlags=RegNext(io.fcsrHost.get.fflags,0.U)
    // State observation belongs to the host, including during context access
    // before any offer has initialized the independent execution snapshot.
    observed.frm:=committedFrm
    val executionFrm=Reg(UInt(3.W))
    when(io.offer.fire) {executionFrm:=io.fcsrHost.get.frm}
    core.io.core.fcsrHost.get.frm:=Mux(state===idle,committedFrm,executionFrm)
    core.io.core.fcsrHost.get.fflags:=committedFlags
  }
  core.io.core.command.valid:=state===dispatch && (memory || !stopping)
  core.io.core.command.bits:=owner
  core.io.core.context.valid:=state===contextSend
  core.io.core.context.bits:=contextRequest
  // Stop before grant may cancel arithmetic, but never discard a memory
  // owner or a buffered bus beat. Once grant is accepted it cannot be revoked.
  core.io.core.flush:=state===cancel || ((state===waiting || state===prepared) && memory && stopping)

  val identity=core.io.core.completion.bits.token===owner.token &&
    core.io.core.completion.bits.instruction===owner.instruction
  val metadata=core.io.memoryStatus.valid===memory
  val matches=identity && metadata
  val awaiting=state===waiting || state===prepared || state===authorizing || state===commit
  val unchanged=WireDefault(false.B)
  val malformed=(core.io.core.completion.valid && (!awaiting || !matches)) ||
    (core.io.memoryStatus.valid && !core.io.core.completion.valid)
  core.io.core.completion.ready:=state===commit && matches && !malformed && unchanged

  val snapshot=Wire(new IsolatedResult)
  snapshot:=0.U.asTypeOf(new IsolatedResult)
  snapshot.reply.completion:=core.io.core.completion.bits
  snapshot.reply.memory:=memory
  snapshot.reply.stopped:=memory && core.io.memoryStatus.bits.interrupted
  val illegal=core.io.core.completion.bits.illegal
  val fault=memory && core.io.memoryStatus.bits.fault
  val misaligned=Mux(store,core.io.memoryStatus.bits.cause===6.U,core.io.memoryStatus.bits.cause===4.U)
  snapshot.reply.exception:=illegal || fault
  snapshot.reply.cause:=Mux(illegal,2.U,Mux(fault,Mux(misaligned,Mux(store,6.U,4.U),Mux(store,7.U,5.U)),0.U))
  snapshot.reply.tval:=Mux(illegal,owner.instruction.pad(64),Mux(fault,core.io.memoryStatus.bits.address,0.U))
  snapshot.reply.rawMemoryCause:=Mux(memory,core.io.memoryStatus.bits.cause,0.U)
  snapshot.reply.element:=Mux(memory,core.io.memoryStatus.bits.element,0.U)
  when(illegal || fault || snapshot.reply.stopped) {snapshot.reply.completion.writesScalar:=false.B}
  if(config.hostFcsr) {
    snapshot.flagsValid:=core.io.core.fcsrHost.get.flags.valid
    snapshot.flags:=core.io.core.fcsrHost.get.flags.bits
  }
  unchanged:=snapshot.asUInt===result.asUInt

  when(state===idle) {stopPending:=false.B}
  when((state===dispatch || state===waiting || state===prepared) && stop) {stopPending:=true.B}
  when(io.offer.fire) {
    owner:=io.offer.bits
    state:=dispatch
  }
  when(io.context.fire) {contextRequest:=io.context.bits;state:=contextSend}
  when(state===dispatch) {
    when(!memory && stopping) {state:=cancel}
      .elsewhen(core.io.core.command.fire) {state:=waiting}
  }
  when(state===waiting) {
    when(!memory && stopping) {state:=cancel}
      .elsewhen(core.io.core.completion.valid && matches) {result:=snapshot;state:=prepared}
  }
  when(state===prepared) {
    // grant wins a coincident stop: it is an irrevocable publication lease.
    when(io.grant.fire) {
      grantToken:=io.grant.bits;state:=authorizing
    }.elsewhen(!memory && stopping) {state:=cancel}
  }
  // Compare only captured tokens. The external CPU token never enters a wide
  // comparator ahead of the boundary register.
  when(state===authorizing) {state:=Mux(grantToken===owner.token,commit,poison)}
  when(state===commit) {
    // Refuse to consume a core which changed a previously captured result.
    when(!core.io.core.completion.valid || snapshot.asUInt=/=result.asUInt) {state:=poison}
    when(core.io.core.completion.fire) {state:=published}
  }
  when(state===published) {finishedState:=observed;state:=ack}
  when(io.done.fire || state===cancel) {state:=idle}
  when(core.io.core.context.fire) {state:=contextWait}
  when(state===contextWait && core.io.core.contextResult.valid) {contextData:=core.io.core.contextResult.bits;state:=contextReply}
  when(io.contextResult.fire) {state:=idle}
  when(malformed) {state:=poison}

  // All four TL directions cross a non-flowing register. No flush here:
  // the LSU must see the final response and own all externally issued stores.
  val ramA=Module(new RegisteredLink(new VpuTLA(VpuTLParams())))
  val ramD=Module(new RegisteredLink(new VpuTLD(VpuTLParams())))
  ramA.io.in<>core.io.tl.a;io.tl.a<>ramA.io.out
  ramD.io.in<>io.tl.d;core.io.tl.d<>ramD.io.out
  val monitorA=Module(new RegisteredLink(new VpuTLA(VpuTLParams())))
  val monitorControl=Module(new RegisteredLink(new VpuTLA(VpuTLParams())))
  val monitorD=Module(new RegisteredLink(new VpuTLD(VpuTLParams())))
  monitorA.io.in<>io.monitor.a
  monitorControl.io.in.valid:=monitorA.io.out.valid
  monitorA.io.out.ready:=monitorControl.io.in.ready
  monitorControl.io.in.bits:=monitorA.io.out.bits
  // A control write can only mean 0/1/2. Preserve high-bit rejection in a
  // separate pipeline stage instead of a 64-bit <=2 carry chain inside the
  // monitor. For 32-bit writes the unused upper data half remains ignored.
  val ma=monitorA.io.out.bits
  val write=ma.opcode===0.U || ma.opcode===1.U
  val high=Mux(ma.size===2.U,ma.data(31,2).orR,ma.data(63,2).orR)
  monitorControl.io.in.bits.data:=ma.data(1,0).pad(64)
  monitorControl.io.in.bits.param:=ma.param | (write && high).asUInt
  core.io.monitor.a<>monitorControl.io.out
  monitorD.io.in<>core.io.monitor.d;io.monitor.d<>monitorD.io.out
}
