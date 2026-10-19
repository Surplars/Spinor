package vpu

import chisel3._
import chisel3.util._

case class VpuTLParams(addressBits:Int=64,dataBits:Int=64,sourceBits:Int=4,sinkBits:Int=1,sizeBits:Int=3) {
  require(addressBits>=32 && dataBits==64 && sourceBits>=1 && sinkBits>=1 && sizeBits>=2)
}
class VpuTLA(p:VpuTLParams) extends Bundle {
  val opcode=UInt(3.W);val param=UInt(3.W);val size=UInt(p.sizeBits.W);val source=UInt(p.sourceBits.W)
  val address=UInt(p.addressBits.W);val mask=UInt(8.W);val data=UInt(64.W);val corrupt=Bool()
}
class VpuTLD(p:VpuTLParams) extends Bundle {
  val opcode=UInt(3.W);val param=UInt(3.W);val size=UInt(p.sizeBits.W);val source=UInt(p.sourceBits.W)
  val sink=UInt(p.sinkBits.W);val denied=Bool();val data=UInt(64.W);val corrupt=Bool()
}
class VpuTileLinkMaster(p:VpuTLParams) extends Bundle {
  val a=Decoupled(new VpuTLA(p));val d=Flipped(Decoupled(new VpuTLD(p)))
}
/** Physical, naturally aligned, single-beat transfer. Data and byte mask are
  * right justified. Stores require irrevocable permission before acceptance.
  * This is a future LSU boundary, not a vector instruction/translation engine.
  */
class VpuMemoryRequest(p:VpuTLParams) extends Bundle {
  val address=UInt(p.addressBits.W);val size=UInt(p.sizeBits.W);val write=Bool()
  val data=UInt(64.W);val mask=UInt(8.W);val token=UInt(80.W);val irrevocable=Bool()
}
class VpuMemoryResponse extends Bundle {
  val data=UInt(64.W);val token=UInt(80.W)
  val denied=Bool();val corrupt=Bool();val protocolError=Bool();val localError=Bool()
}
/** One source ID, one outstanding transfer. Published A is held through flush;
  * killed traffic drains D before source reuse. Does not undo a store.
  */
class TileLinkReservation(p:VpuTLParams=VpuTLParams()) extends Module {
  val io=IO(new Bundle {
    val flush=Input(Bool());val request=Flipped(Decoupled(new VpuMemoryRequest(p)))
    val response=Decoupled(new VpuMemoryResponse);val tl=new VpuTileLinkMaster(p);val busy=Output(Bool())
  })
  val Seq(idle,send,waitD,reply)=Enum(4);val state=RegInit(idle)
  val request=Reg(new VpuMemoryRequest(p));val channel=Reg(new VpuTLA(p))
  val response=Reg(new VpuMemoryResponse);val killed=RegInit(false.B)
  io.request.ready:=state===idle && !io.flush;io.busy:=state=/=idle
  io.response.valid:=state===reply && !io.flush;io.response.bits:=response
  io.tl.a.valid:=state===send;io.tl.a.bits:=channel
  io.tl.d.ready:=state===waitD || (state===send && io.tl.a.ready)
  when(io.request.fire) {
    val in=io.request.bits
    val natural=MuxLookup(in.size,0.U(8.W))(Seq(0.U->1.U,1.U->3.U,2.U->15.U,3.U->255.U))
    val alignment=MuxLookup(in.size,7.U(3.W))(Seq(0.U->0.U,1.U->1.U,2.U->3.U,3.U->7.U))
    val invalid=in.size>3.U || (in.address(2,0)&alignment)=/=0.U ||
      (in.write && (!in.irrevocable || !in.mask.orR || (in.mask & ~natural).orR))
    request:=in;killed:=false.B;response:=0.U.asTypeOf(new VpuMemoryResponse);response.token:=in.token
    channel.opcode:=Mux(in.write,Mux(in.mask===natural,0.U,1.U),4.U)
    channel.param:=0.U;channel.size:=in.size;channel.source:=0.U;channel.address:=in.address
    channel.mask:=(Mux(in.write,in.mask,natural)<<in.address(2,0))(7,0)
    channel.data:=(in.data<<Cat(in.address(2,0),0.U(3.W)))(63,0);channel.corrupt:=false.B
    when(invalid) { response.localError:=true.B;state:=reply }.otherwise { state:=send }
  }
  when(io.tl.a.fire) { state:=waitD }
  when(io.tl.d.fire) {
    val d=io.tl.d.bits
    val dataMask=VecInit(Seq(8,16,32,64).map(w=>((BigInt(1)<<w)-1).U(64.W)))(request.size(1,0))
    response.data:=Mux(request.write,0.U,(d.data>>Cat(request.address(2,0),0.U(3.W))) & dataMask);response.token:=request.token
    response.denied:=d.denied;response.corrupt:=d.corrupt
    response.protocolError:=d.source=/=0.U || d.size=/=request.size || d.param=/=0.U ||
      d.opcode=/=Mux(request.write,0.U,1.U)
    response.localError:=false.B
    state:=Mux(killed || io.flush,idle,reply)
  }
  when(io.response.fire) { state:=idle }
  when(io.flush) {
    when(state===send || state===waitD) { killed:=true.B }
    when(state===reply) { state:=idle }
  }
}
/** Reservation wrapper. Arithmetic command ports retain their semantics.
  * memoryRequest is externally driven until the vector LSU is implemented.
  */
class LishiVpuTileLinkReserved extends Module {
  val vpu=Module(new RamVector(enableFp=true));val bridge=Module(new TileLinkReservation)
  val io=IO(new Bundle {
    val core=chiselTypeOf(vpu.io)
    val memoryRequest=Flipped(Decoupled(new VpuMemoryRequest(VpuTLParams())))
    val memoryResponse=Decoupled(new VpuMemoryResponse);val tl=new VpuTileLinkMaster(VpuTLParams())
    val memoryBusy=Output(Bool())
  })
  vpu.io<>io.core;bridge.io.flush:=io.core.flush
  bridge.io.request<>io.memoryRequest;io.memoryResponse<>bridge.io.response
  io.tl<>bridge.io.tl;io.memoryBusy:=bridge.io.busy
}
