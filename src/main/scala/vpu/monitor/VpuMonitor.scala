package vpu

import chisel3._
import chisel3.util._
import _root_.circt.stage.ChiselStage
import java.nio.file.{Files,Paths}

/** Same-clock observations sampled by the passive MMIO monitor.
  * events contains one-cycle counting conditions in ABI order; busy/ownership
  * are levels. error captures the accompanying diagnostic fields on that edge.
  */
class MonitorSignals extends Bundle {
  val events=UInt(13.W)
  val busy=Bool();val memoryOwned=Bool();val tlPending=Bool();val owned=Bool()
  val vtype=UInt(64.W);val config=UInt(32.W)
  val error=Bool();val cause=UInt(16.W);val address=UInt(64.W);val token=UInt(80.W);val element=UInt(8.W)
}
/** Passive 4 KiB MMIO monitor with live observations and coherent snapshots.
  *
  * Production counters are 32-bit modular values; the eight-bit configuration
  * exists for wrap tests. Snapshot and clear commands affect telemetry only.
  * Reads return one held TileLink D beat; unsupported accesses are denied.
  * The monitor shares the VPU clock/reset and provides no interrupt or CDC.
  */
class VpuMonitor(base:BigInt=0,counterBits:Int=32,enableFp:Boolean=true,hostFcsr:Boolean=false) extends Module {
  require(base>=0 && base<(BigInt(1)<<64) && base%4096==0)
  require(counterBits==8 || counterBits==32)
  override def desiredName=if(counterBits==8)"VpuMonitorTiny" else "VpuMonitor"
  val io=IO(new Bundle {val signals=Input(new MonitorSignals);val mmio=Flipped(new VpuTileLinkMaster(VpuTLParams()))})
  // Live event counters continue while software reads the frozen snapshot bank.
  val live=RegInit(VecInit(Seq.fill(13)(0.U(counterBits.W))))
  // Exact lookahead: predict the next stored all-ones value on each increment.
  // Overflow still asserts on the wrapping event; no telemetry cycle is added.
  val wrapNext=RegInit(VecInit(Seq.fill(13)(false.B)))
  val snap=RegInit(VecInit(Seq.fill(13)(0.U(counterBits.W))))
  val snapshotValid=RegInit(false.B);val sequence=RegInit(0.U(32.W))
  val overflow=RegInit(false.B);val errorSticky=RegInit(false.B)
  // The sticky flag records that an error occurred; these fields describe the
  // most recent error, not the first error since clear.
  val cause=RegInit(0.U(16.W));val address=RegInit(0.U(64.W));val token=RegInit(0.U(80.W));val element=RegInit(0.U(8.W))
  val snapStatus=RegInit(0.U(64.W));val snapVtype=RegInit(0.U(64.W));val snapConfig=RegInit(0.U(32.W))
  val snapCause=RegInit(0.U(16.W));val snapAddress=RegInit(0.U(64.W));val snapToken=RegInit(0.U(80.W));val snapElement=RegInit(0.U(8.W))
  val status=Cat(0.U(56.W),errorSticky,overflow,true.B,snapshotValid,io.signals.owned,io.signals.tlPending,io.signals.memoryOwned,io.signals.busy)
  for(i<-0 until 13) {when(io.signals.events(i)) {
    live(i):=ParallelIncrement(live(i),true.B)
    wrapNext(i):=live(i)===((BigInt(1)<<counterBits)-2).U
  }}
  when((0 until 13).map(i=>io.signals.events(i)&&wrapNext(i)).reduce(_||_)) {overflow:=true.B}
  when(io.signals.error) {errorSticky:=true.B;cause:=io.signals.cause;address:=io.signals.address;token:=io.signals.token;element:=io.signals.element}
  // A one-entry response register preserves source/data/denied under D stalls.
  // No new A is accepted until the prior response has left this register.
  val pending=RegInit(false.B);val response=Reg(new VpuTLD(VpuTLParams()))
  io.mmio.a.ready:= !pending;io.mmio.d.valid:=pending;io.mmio.d.bits:=response
  when(io.mmio.d.fire) {pending:=false.B}
  val a=io.mmio.a.bits
  val read=a.opcode===4.U;val write=a.opcode===0.U || a.opcode===1.U
  val index=a.address(11,3)
  val data=WireDefault(0.U(64.W));val known=WireDefault(true.B)
  // ABI words 0..15 describe capabilities and live state. Words 48..54 and
  // the separate counter range below expose the most recent snapshot.
  switch(index) {
    is(0.U) {data:="h4c495348".U} // LISH
    is(1.U) {data:="h00010000".U} // ABI major 1, minor 0
    is(2.U) {data:=(if(hostFcsr)"h00005602".U else "h00005501".U)} // explicit FCSR ownership; ABI v1
    is(3.U) {data:=(if(enableFp)BigInt("ffffffff",16) else BigInt("ffffffff",16).clearBit(2).clearBit(3).clearBit(15).clearBit(17)).U} // bits 0..29 retained; 30 vsmul, 31 vnclip[u]
    is(4.U) {data:=Cat(1.U(16.W),32.U(16.W),64.U(16.W),128.U(16.W))}
    is(5.U) {data:=Cat(0.U(24.W),8.U(8.W),512.U(32.W))} // architectural bytes, max LMUL
    is(6.U) {data:=counterBits.U}
    is(7.U) {data:=status}
    is(8.U) {data:=0.U} // control pulses
    is(9.U) {data:=sequence}
    is(10.U) {data:=Cat(0.U(40.W),element,cause)}
    is(11.U) {data:=address}
    is(12.U) {data:=token(63,0)}
    is(13.U) {data:=token(79,64)}
    is(14.U) {data:=io.signals.vtype}
    is(15.U) {data:=io.signals.config}
    // Frozen status/error words must be read with the same snapshot sequence.
    is(48.U) {data:=snapStatus}
    is(49.U) {data:=snapVtype}
    is(50.U) {data:=snapConfig}
    is(51.U) {data:=Cat(0.U(40.W),snapElement,snapCause)}
    is(52.U) {data:=snapAddress}
    is(53.U) {data:=snapToken(63,0)}
    is(54.U) {data:=snapToken(79,64)}
  }
  val fixed=(index<=15.U) || (index>=48.U && index<=54.U)
  val counter=index>=32.U && index<45.U
  when(counter) {data:=snap((index-32.U)(3,0))}
  known:=fixed || counter
  // Enforce the configured window, natural alignment and exact byte lanes.
  // Control writes are limited to the low 32-bit or full 64-bit control word;
  // a 32-bit write intentionally ignores the unused upper data half.
  val natural=VecInit(Seq(1,3,15,255).map(_.U(8.W)))(a.size(1,0))
  val alignment=VecInit(Seq(0,1,3,7).map(_.U(3.W)))(a.size(1,0))
  val expectedMask=(natural<<a.address(2,0))(7,0)
  val validBus=a.address(63,12)===(base>>12).U && a.size<=3.U && a.param===0.U && !a.corrupt &&
    (a.address(2,0)&alignment)===0.U && a.mask===expectedMask
  val controlData=Mux(a.size===2.U,a.data(31,0).pad(64),a.data)
  val controlWrite=write && index===8.U && a.address(2,0)===0.U && a.size>=2.U && controlData<=2.U
  val allowed=validBus && ((read && known) || controlWrite)
  when(io.mmio.a.fire) {
    pending:=true.B;response:=0.U.asTypeOf(response)
    // Denied AMOs still need AccessAckData, not a Put acknowledgement.
    response.opcode:=Mux(read || a.opcode===2.U || a.opcode===3.U,1.U,Mux(a.opcode===5.U,2.U,0.U))
    response.size:=a.size;response.source:=a.source
    response.denied:= !allowed;response.data:=Mux(read && allowed,data,0.U)
    // Snapshot captures values before this edge's live event increments. The
    // sequence advances on snapshot only, allowing software to detect changes.
    when(allowed && controlWrite && controlData===1.U) {
      snap:=live;sequence:=ParallelIncrement(sequence,true.B);snapshotValid:=true.B
      snapStatus:=status;snapVtype:=io.signals.vtype;snapConfig:=io.signals.config
      snapCause:=cause;snapAddress:=address;snapToken:=token;snapElement:=element
    }
    // Explicit monitor clear wins over this edge's events, including errors.
    // Neither clear nor snapshot touches the vector core or outstanding memory.
    when(allowed && controlWrite && controlData===2.U) {
      live.foreach(_:=0.U);wrapNext.foreach(_:=false.B);snap.foreach(_:=0.U);snapshotValid:=false.B;overflow:=false.B;errorSticky:=false.B
      cause:=0.U;address:=0.U;token:=0.U;element:=0.U
      snapStatus:=0.U;snapVtype:=0.U;snapConfig:=0.U;snapCause:=0.U;snapAddress:=0.U;snapToken:=0.U;snapElement:=0.U
    }
  }
}

/** Connects the production memory core to an independent telemetry slave.
  *
  * Datapath TL remains the physical RAM master. Events describe the inner core
  * handshakes; under SpinorIsolated, completion can precede outer done.fire.
  * Software must distinguish these counters from CPU retirement and from the
  * isolated wrapper's owner/busy state.
  */
class LishiVpuMonitored(monitorBase:BigInt=0,config:SpinorParams=SpinorParams(),retimeMemory:Boolean=false) extends Module {
  val vpu=Module(new LishiVpuMemory(config.regionBase,config.regionBytes,config.aluStageBits,config.enableFp,config.hostFcsr,retimeMemory));val monitor=Module(new VpuMonitor(monitorBase,config.monitorCounterBits,config.enableFp,config.hostFcsr))
  val io=IO(new Bundle {
    val core=chiselTypeOf(vpu.io.core);val tl=new VpuTileLinkMaster(VpuTLParams())
    val memoryStatus=Valid(new VectorMemoryStatus);val monitor=Flipped(new VpuTileLinkMaster(VpuTLParams()))
  })
  vpu.io.core<>io.core;io.tl<>vpu.io.tl;io.memoryStatus<>vpu.io.memoryStatus
  monitor.io.mmio<>io.monitor
  // Arithmetic flush releases the inner owner; memory retains ownership until
  // its stopped/faulted/normal completion drains the architectural prefix.
  val owned=RegInit(false.B);val memoryOwned=RegInit(false.B);val tlPending=RegInit(false.B)
  val accept=io.core.command.fire;val complete=io.core.completion.fire
  val cancel=owned && !memoryOwned && io.core.flush
  when(complete || cancel) {owned:=false.B;memoryOwned:=false.B}
  when(accept) {owned:=true.B;memoryOwned:=io.core.command.bits.instruction(6,0)==="h07".U || io.core.command.bits.instruction(6,0)==="h27".U}
  when(io.tl.a.fire =/= io.tl.d.fire) {tlPending:=io.tl.a.fire}
  val memoryDone=complete && io.memoryStatus.valid
  val fault=memoryDone && io.memoryStatus.bits.fault
  val illegal=complete && io.core.completion.bits.illegal
  // ABI counter order: cycles, busy, memory-owned, accepted, completed,
  // canceled, illegal, memory-fault, memory-stopped, TL A, TL D,
  // command-backpressure cycles, completion-backpressure cycles.
  val s=monitor.io.signals
  s.events:=VecInit(Seq(true.B,io.core.busy,owned&&memoryOwned,accept,complete,cancel,illegal,fault,
    memoryDone&&io.memoryStatus.bits.interrupted,io.tl.a.fire,io.tl.d.fire,
    io.core.command.valid && !io.core.command.ready,io.core.completion.valid && !io.core.completion.ready)).asUInt
  s.busy:=io.core.busy;s.memoryOwned:=owned&&memoryOwned;s.tlPending:=tlPending;s.owned:=owned
  s.vtype:=io.core.vtype
  // This word observes the inner core's current state, not a CPU context image.
  // Host-owned FCSR fields follow the sidebands currently supplied to that core.
  s.config:=Cat(0.U(6.W),io.core.fflags.getOrElse(0.U(5.W)),io.core.frm.getOrElse(0.U(3.W)),io.core.vxsat,io.core.vxrm,io.core.vstart,io.core.vl)
  s.error:=fault||illegal;s.cause:=Mux(illegal,"h100".U,io.memoryStatus.bits.cause)
  s.address:=Mux(fault,io.memoryStatus.bits.address,0.U);s.token:=io.core.completion.bits.token
  s.element:=Mux(fault,io.memoryStatus.bits.element,0.U)
}
/** Emit standalone monitor test variants and monitored public/compatibility tops. */
object GenerateMonitor extends App {
  val out=Paths.get(args(0));Files.createDirectories(out)
  val base=if(args.length>1)BigInt(args(1).stripPrefix("0x"),16) else BigInt(0)
  for((name,gen)<-Seq[(String,()=>RawModule)](
    "VpuMonitor"->(()=>new VpuMonitor(base)),"VpuMonitorTiny"->(()=>new VpuMonitor(base,counterBits=8)),
    "LishiVpuMonitored"->(()=>new LishiVpuMonitored(base)),
    "SpinorVpu"->(()=>new SpinorVpu(base)))) {
    val text=ChiselStage.emitSystemVerilog(gen(),firtoolOpts=Array("-disable-all-randomization","-strip-debug-info","--lowering-options=disallowLocalVariables,disallowPackedArrays"))
    val marker="(?m)^// ----- 8< ----- FILE \"([^\"]+)\" ----- 8< -----\\r?\\n".r
    val chunks=marker.findAllMatchIn(text).toSeq
    Files.writeString(out.resolve(name+".sv"),text.take(chunks.headOption.map(_.start).getOrElse(text.length)))
    for((m,i)<-chunks.zipWithIndex) {val p=out.resolve(m.group(1));Files.createDirectories(p.getParent);Files.writeString(p,text.substring(m.end,chunks.lift(i+1).map(_.start).getOrElse(text.length)))}
  }
}
