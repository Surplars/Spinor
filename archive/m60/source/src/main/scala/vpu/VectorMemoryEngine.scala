package vpu

import chisel3._
import chisel3.util._

class VectorMemoryStatus extends Bundle {
  val fault=Bool();val interrupted=Bool();val cause=UInt(6.W);val address=UInt(64.W);val element=UInt(8.W)
}
/** Unit/constant-stride/indexed physical normal-RAM prototype. Uses the arithmetic core's
  * context port for per-element architectural updates and dedicated vstart commit port.
  * Memory instructions are irrevocable ROB-head operations: flush requests a
  * boundary stop and DOES NOT silently cancel completion or issued stores.
  */
class VectorMemoryEngine(regionBase:BigInt=BigInt("80000000",16),regionBytes:BigInt=BigInt(1)<<28,shortUnitAdder:Boolean=false) extends Module {
  require(regionBytes>=8 && (regionBytes&(regionBytes-1))==0 && regionBase%regionBytes==0)
  val io=IO(new Bundle {
    val stop=Input(Bool());val command=Flipped(Decoupled(new Command));val completion=Decoupled(new Completion)
    val status=Output(new VectorMemoryStatus);val busy=Output(Bool())
    val vl=Input(UInt(8.W));val vtype=Input(UInt(64.W));val vstart=Input(UInt(7.W))
    val context=Decoupled(new ContextAccess);val contextResult=Flipped(Valid(UInt(64.W)))
    val commit=Decoupled(UInt(7.W))
    val trim=Valid(UInt(8.W))
    val memoryRequest=Decoupled(new VpuMemoryRequest(VpuTLParams()))
    val memoryResponse=Flipped(Decoupled(new VpuMemoryResponse))
  })
  val states=Enum(if(shortUnitAdder)35 else 34)
  val addressMiddle=if(shortUnitAdder)states(34) else states(0)
  val Seq(idle,decode,validate,maskLow,maskLowWait,maskHigh,maskHighWait,checkElement,addressLow,addressHigh,
    checkAddress,readChunk,readChunkWait,sendMemory,waitMemory,writeChunk,writeChunkWait,writeStart,reply)=states.take(19)
  val Seq(strideSeek,strideAdd0,strideAdd1,strideAdd2,strideAdd3,indexValidate,indexRead,indexReadWait,indexExtract,specialDecode,specialValidate,segmentDecode,segmentSeek,segmentAdvance,segmentAlias)=states.slice(19,34)
  val state=RegInit(idle);val cmd=Reg(new Command);val length=Reg(UInt(8.W));val typ=Reg(UInt(64.W))
  val lastIndex=Reg(UInt(8.W));val index=Reg(UInt(8.W));val width=Reg(UInt(2.W));val baseRegister=Reg(UInt(5.W));val store=Reg(Bool());val masked=Reg(Bool())
  val mask=Reg(UInt(128.W));val original=Reg(UInt(64.W));val result=Reg(UInt(64.W))
  // Reuse original as one write-through register-file chunk, never a whole group snapshot.
  val cachedValid=RegInit(false.B);val cachedAddress=Reg(UInt(6.W))
  val address=Reg(UInt(64.W));val addressCarry=Reg(Bool());val stopped=RegInit(false.B)
  // The scalar base is invariant for the instruction. Capture the carry into
  // each high-address byte at decode, before the per-element address stages.
  // Separate 8-bit increments prevent LUT sharing from rebuilding a long
  // prefix chain through all 32 high bits, without adding an element cycle.
  val upperAddressPrefix=Reg(Vec(3,Bool()))
  val strided=Reg(Bool());val zeroStride=Reg(Bool());val seeking=Reg(Bool());val seek=Reg(UInt(7.W))
  // original is free until the first RF chunk read. Reuse it as the shifted
  // multiplicand for a bounded seven-bit vstart seek; no DSP or extra 64-bit bank.
  val indexed=Reg(Bool());val indexWidth=Reg(UInt(2.W))
  val dataAlignment=Reg(UInt(5.W));val indexAlignment=Reg(UInt(5.W));val indexIntegral=Reg(Bool())
  val indexChunk=Reg(UInt(6.W));val indexByte=Reg(UInt(3.W))
  // Normalize rs2=x0 on admission, keeping its zero-select off the sliced adder.
  val stride=cmd.scalar2
  // A segment contains several field groups, each rounded up to one RF register.
  // Only small cursors are added; the original 64-bit chunk remains the sole data cache.
  val segmented=Reg(Bool());val segmentLast=Reg(UInt(3.W));val segmentField=Reg(UInt(3.W))
  val segmentGroup=Reg(UInt(4.W));val segmentBytes=Reg(UInt(7.W));val unitOffset=Reg(UInt(13.W))
  // Modes 1/2 reuse the four-slice adder for a field step / segment rewind.
  // Rewind the field cursor before adding the original scalar stride, including zero stride.
  val segmentAdd=RegInit(0.U(2.W));val segmentBack=Reg(UInt(8.W))
  val faultOnlyFirst=Reg(Bool());val trimmed=RegInit(false.B)
  val fieldStep=(1.U(4.W)<<width)(3,0)
  // result is free once a field has committed. Reuse it for field deltas so
  // the ordinary stride operand does not acquire another mux before the adder.
  val addend=Mux(indexed || segmentAdd=/=0.U,result,Mux(seeking,original,stride))
  val decodedBad=Reg(Bool());val illegal=Reg(Bool());val status=Reg(new VectorMemoryStatus);val nextStart=RegInit(0.U(8.W));val finishAfterStart=Reg(Bool())
  val stop=stopped || io.stop
  val nextIndex=ParallelIncrement(index,true.B)
  val last=index===lastIndex
  io.busy:=state=/=idle;io.command.ready:=state===idle && !io.stop
  io.completion.valid:=state===reply;io.completion.bits:=0.U.asTypeOf(new Completion)
  io.completion.bits.token:=cmd.token;io.completion.bits.instruction:=cmd.instruction;io.completion.bits.illegal:=illegal
  io.status:=status
  io.context.valid:=state===maskLow || state===maskHigh || state===indexRead || state===readChunk || (state===writeChunk && !stop)
  io.context.bits:=0.U.asTypeOf(new ContextAccess)
  val byteOffset=(index<<width)(6,0)
  // Compute the RF chunk address alongside the low memory address, before
  // checkAddress/readChunk. This cuts index -> shift/add -> shared RF access
  // without adding an element cycle or changing the write-through cache.
  val chunkAddress=Reg(UInt(6.W))
  val bitOffset=Cat(byteOffset(2,0),0.U(3.W))
  io.context.bits.address:=Mux(state===maskLow,0.U,Mux(state===maskHigh,1.U,Mux(state===indexRead,indexChunk,chunkAddress)))
  io.context.bits.write:=state===writeChunk;io.context.bits.data:=result
  io.commit.valid:=state===writeStart;io.commit.bits:=nextStart(6,0)
  io.trim.valid:=state===writeStart && trimmed;io.trim.bits:=length
  io.memoryRequest.valid:=state===sendMemory
  io.memoryRequest.bits.address:=address;io.memoryRequest.bits.size:=width;io.memoryRequest.bits.write:=store
  io.memoryRequest.bits.data:=original>>bitOffset
  io.memoryRequest.bits.mask:=VecInit(Seq(1,3,15,255).map(_.U(8.W)))(width)
  io.memoryRequest.bits.token:=cmd.token;io.memoryRequest.bits.irrevocable:=true.B
  io.memoryResponse.ready:=state===waitMemory
  when(io.command.fire) {
    cmd:=io.command.bits;length:=io.vl;typ:=io.vtype;index:=io.vstart
    when(io.command.bits.instruction(27,26)===2.U && io.command.bits.instruction(24,20)===0.U) {
      cmd.scalar2:=0.U
    }
    cachedValid:=false.B;segmentAdd:=0.U;trimmed:=false.B;address:=io.command.bits.scalar
    stopped:=false.B;illegal:=false.B;status:=0.U.asTypeOf(new VectorMemoryStatus);state:=decode
  }
  when(io.stop && state=/=idle) { stopped:=true.B }
  def setStart(value:UInt,finish:Bool):Unit={ nextStart:=value;finishAfterStart:=finish;state:=writeStart }
  def interrupt():Unit={ status.interrupted:=true.B;status.element:=index;setStart(index,true.B) }
  def fault(cause:UInt):Unit={
    when(faultOnlyFirst && index=/=0.U) {
      // Absolute element index, including masked-off element zero / nonzero vstart.
      // Reuse length after the terminating fault; no separate VL data bank.
      length:=index;trimmed:=true.B;setStart(0.U,true.B)
    }.otherwise {
      status.fault:=true.B;status.cause:=cause;status.address:=address;status.element:=index;setStart(index,true.B)
    }
  }
  when(state===decode) {
    val inst=cmd.instruction;val f3=inst(14,12);lastIndex:=length-1.U
    for(byte<-1 until 4) { upperAddressPrefix(byte-1):=cmd.scalar(31+8*byte,32).andR }
    // For valid encodings (000/101/110/111), low bits are log2(bytes).
    // Decode validity separately so f3[2] does not gate the EMUL arithmetic.
    val ew=f3(1,0)
    val lm=Mux(typ(2),typ(2,0).asSInt,typ(2,0).zext)
    val (group,validEmul,integralEmul)=MemoryGeometry.decode(typ,ew)
    val vr=inst(11,7);val isStore=inst(6,0)==="h27".U
    val validOpcode=inst(6,0)==="h07".U || isStore
    val isFof= !isStore && inst(27,26)===0.U && inst(24,20)===16.U
    faultOnlyFirst:=isFof
    val validWidth=f3===0.U || f3===5.U || f3===6.U || f3===7.U
    val isStrided=inst(27,26)===2.U
    val isIndexed=inst(26)
    val dataGroup=Mux(isIndexed,Mux(lm>0.S,(1.U(4.W)<<lm.asUInt(1,0))(3,0),1.U(4.W)),group)
    val indexBase=inst(24,20)
    val bad= !validOpcode || !validWidth || typ(63) || typ(5,3)>3.U || !validEmul ||
      inst(28) || (!isStrided && !isIndexed && inst(24,20)=/=0.U && !isFof) || (vr&(dataGroup-1.U))=/=0.U ||
      (!inst(25) && vr===0.U) ||
      (isIndexed && ((indexBase&(group-1.U))=/=0.U ||
        (!inst(25) && indexBase===0.U) || typ(2,0)===4.U || !VectorConfig.fractionalLegal(typ)))
    // Treat a scalar-field FOF as a one-field segment too, sharing all vtype checks.
    val isSegment=isFof || (inst(31,29)=/=0.U && (isStrided || isIndexed || inst(24,20)===0.U))
    segmented:=isSegment;segmentLast:=inst(31,29);segmentField:=0.U;segmentGroup:=dataGroup
    store:=isStore;masked:= !inst(25);baseRegister:=vr;width:=Mux(isIndexed,typ(4,3),ew)
    indexed:=isIndexed;indexWidth:=ew;dataAlignment:=VectorConfig.countAlignment(dataGroup)
    indexAlignment:=VectorConfig.countAlignment(group);indexIntegral:=integralEmul
    strided:=isStrided;zeroStride:=inst(24,20)===0.U || cmd.scalar2===0.U
    seeking:=true.B;seek:=index(6,0);original:=Mux(inst(24,20)===0.U,0.U,cmd.scalar2)
    decodedBad:=bad
    // Keep special EVL/type handling off the existing EMUL decode chain.
    // These two setup states affect only mask and whole-register transfers.
    val special=inst(27,26)===0.U && (inst(24,20)===8.U || inst(24,20)===11.U)
    state:=Mux(special,specialDecode,Mux(isSegment,segmentDecode,validate))
  }
  when(state===segmentDecode) {
    val count=Cat(0.U(1.W),segmentLast)+1.U
    val span=MuxLookup(segmentGroup,(count<<3).pad(7))(Seq(1.U->count.pad(7),2.U->(count<<1).pad(7),4.U->(count<<2).pad(7)))
    decodedBad:=decodedBad || span>8.U || (baseRegister+&span)>32.U || typ(2,0)===4.U || !VectorConfig.fractionalLegal(typ)
    segmentBytes:=(count<<width)(6,0);segmentBack:=0.U(8.W)-(segmentLast<<width)
    unitOffset:=0.U
    // Stride seeking needs the original vstart bit counter. Unit segments use NF additions.
    when(indexed) {state:=segmentAlias}.elsewhen(strided) {state:=validate}
      .otherwise {seek:=count;state:=segmentSeek}
  }
  // Indexed segment loads forbid overlap with ANY data field, regardless of EEW.
  // Check one registered group per cycle, before reads/writes or the empty-VL exit.
  when(state===segmentAlias) {
    val overlap=VectorConfig.alignedGroupsOverlap(baseRegister,dataAlignment,cmd.instruction(24,20),indexAlignment)
    decodedBad:=decodedBad || (overlap && (!store || width=/=indexWidth))
    when(segmentField===segmentLast) {
      segmentField:=0.U;baseRegister:=cmd.instruction(11,7);state:=validate
    }.otherwise {segmentField:=segmentField+1.U;baseRegister:=baseRegister+segmentGroup}
  }
  // Bounded repeated addition positions the first segment at vstart. No multiplier
  // or wide combinational NF*index*EEW expression is placed on the address path.
  when(state===segmentSeek) {
    unitOffset:=unitOffset+(index<<width)
    seek:=seek-1.U
    when(seek===1.U || decodedBad) {state:=validate}
  }
  when(state===segmentAdvance) {
    when(!strided && !indexed) {unitOffset:=unitOffset+fieldStep}
    when(segmentField===segmentLast) {
      segmentField:=0.U;baseRegister:=cmd.instruction(11,7);index:=nextIndex
      setStart(Mux(last,0.U,nextIndex),last)
    }.otherwise {
      segmentField:=segmentField+1.U;baseRegister:=baseRegister+segmentGroup
      when(strided || indexed) {result:=fieldStep;segmentAdd:=1.U;state:=strideAdd0}.otherwise {state:=checkElement}
    }
  }
  when(state===specialDecode) {
    val inst=cmd.instruction;val whole=inst(24,20)===8.U;val nf=inst(31,29);val f3=inst(14,12)
    val ew=f3(1,0);val count=Cat(0.U(1.W),nf)+1.U
    val wholeLength=MuxLookup(ew,(count<<4).pad(8))(Seq(1.U->(count<<3).pad(8),2.U->(count<<2).pad(8),3.U->(count<<1).pad(8)))
    val maskLength=length(7,3)+&length(2,0).orR
    val validWidth=f3===0.U || f3===5.U || f3===6.U || f3===7.U
    val validCount=nf===0.U || nf===1.U || nf===3.U || nf===7.U
    val wholeBad= !validCount || (inst(11,7)&nf.pad(5))=/=0.U || !validWidth || (store && f3=/=0.U)
    val maskBad=nf=/=0.U || f3=/=0.U || typ(63) || typ(5,3)>3.U
    decodedBad:= !(inst(6,0)==="h07".U || store) || !inst(25) || inst(28) || Mux(whole,wholeBad,maskBad)
    length:=Mux(whole,wholeLength,maskLength.pad(8));width:=Mux(whole,ew,0.U)
    masked:=false.B;state:=specialValidate
  }
  when(state===specialValidate) {lastIndex:=length-1.U;state:=validate}
  when(state===validate) {
    when(decodedBad) { illegal:=true.B;state:=reply }
      .elsewhen(indexed && !segmented) {state:=indexValidate}
      .elsewhen(index>=length) { setStart(0.U,true.B) }
      .otherwise { state:=Mux(masked,maskLow,Mux(strided,strideSeek,checkElement)) }
  }
  // Check cross-width aliases from registered group geometry. The load rules
  // preserve unread index elements without snapshots, including restart.
  when(state===indexValidate) {
    val indexBase=cmd.instruction(24,20)
    val overlap=VectorConfig.alignedGroupsOverlap(baseRegister,dataAlignment,indexBase,indexAlignment)
    val legalLoadOverlap=width===indexWidth ||
      (width<indexWidth && baseRegister===indexBase) ||
      (width>indexWidth && indexIntegral && (baseRegister|dataAlignment)===(indexBase|indexAlignment))
    val badAlias=overlap && Mux(store,width=/=indexWidth,!legalLoadOverlap)
    when(badAlias) {illegal:=true.B;state:=reply}
      .elsewhen(index>=length) {setStart(0.U,true.B)}
      .otherwise {state:=Mux(masked,maskLow,checkElement)}
  }
  when(state===maskLow && io.context.fire) { state:=maskLowWait }
  when(state===maskLowWait && io.contextResult.valid) { mask:=io.contextResult.bits;state:=maskHigh }
  when(state===maskHigh && io.context.fire) { state:=maskHighWait }
  when(state===maskHighWait && io.contextResult.valid) { mask:=Cat(io.contextResult.bits,mask(63,0));state:=Mux(strided,strideSeek,checkElement) }
  when(state===checkElement) {
    when(index>=length) { setStart(0.U,true.B) }
      .elsewhen(stop) { interrupt() }
      .elsewhen(masked && !mask(index(6,0))) {
        index:=nextIndex;when(segmented && !strided && !indexed) {unitOffset:=unitOffset+segmentBytes};when(strided && !zeroStride && !last) {state:=strideAdd0}
      }
      .otherwise {
        when(!segmented) {unitOffset:=index<<width}
        when(strided || indexed) {chunkAddress:=((baseRegister<<1)+byteOffset(6,3))(5,0)}
        val offset=(index<<indexWidth)(6,0)
        indexChunk:=((cmd.instruction(24,20)<<1)+offset(6,3))(5,0);indexByte:=offset(2,0)
        state:=Mux(segmented && (strided || indexed) && segmentField=/=0.U,checkAddress,Mux(indexed,indexRead,Mux(strided,checkAddress,addressLow)))
      }
  }
  when(state===indexRead && io.context.fire) {state:=indexReadWait}
  when(state===indexReadWait && io.contextResult.valid) {result:=io.contextResult.bits;state:=indexExtract}
  when(state===indexExtract) {
    val shifted=result>>Cat(indexByte,0.U(3.W))
    result:=MuxLookup(indexWidth,shifted)(Seq(0.U->shifted(7,0).pad(64),1.U->shifted(15,0).pad(64),2.U->shifted(31,0).pad(64)))
    address:=cmd.scalar;state:=strideAdd0
  }
  when(state===strideSeek) {
    when(stop) {interrupt()}
      .elsewhen(seek===0.U || zeroStride) {seeking:=false.B;state:=checkElement}
      .elsewhen(seek(0)) {state:=strideAdd0}
      .otherwise {original:=Cat(original(62,0),false.B);seek:=seek>>1}
  }
  // Four fixed 16-bit additions keep negative strides and modulo-64-bit wrap
  // off a long combinational adder. The cursor stays stable while A or D stalls.
  for((phase,part)<-Seq(strideAdd0,strideAdd1,strideAdd2,strideAdd3).zipWithIndex) {
    when(state===phase) {
      val sum=if(shortUnitAdder) {
        val x=address(16*part+15,16*part);val y=addend(16*part+15,16*part)
        val carry=if(part==0)false.B else addressCarry
        val lo=CarrySelect.add(x(7,0),y(7,0),carry)
        val hi0=CarrySelect.add(x(15,8),y(15,8),false.B)
        val hi1=CarrySelect.add(x(15,8),y(15,8),true.B)
        Cat(Mux(lo(8),hi1,hi0),lo(7,0))
      } else CarrySelect.add(address(16*part+15,16*part),addend(16*part+15,16*part),if(part==0)false.B else addressCarry)
      val pieces=(0 until 4).reverse.map(k=>if(k==part)sum(15,0) else address(16*k+15,16*k))
      address:=Cat(pieces);addressCarry:=sum(16)
      if(part<3) {state:=Seq(strideAdd1,strideAdd2,strideAdd3)(part)}
      else {
        when(segmentAdd===1.U) {segmentAdd:=0.U;state:=checkElement}
          .elsewhen(segmentAdd===2.U) {segmentAdd:=0.U;state:=Mux(zeroStride,checkElement,strideAdd0)}
          .elsewhen(indexed) {state:=checkAddress}
          .elsewhen(seeking) {original:=Cat(original(62,0),false.B);seek:=seek>>1;state:=strideSeek}
          .otherwise {state:=checkElement}
      }
    }
  }
  when(state===addressLow) {
    chunkAddress:=((baseRegister<<1)+byteOffset(6,3))(5,0)
    if(shortUnitAdder) {
      // Reuse address/addressCarry across a separate middle-half stage. The
      // low add must not feed the high-prefix logic in the same cycle.
      val low=CarrySelect.add(cmd.scalar(15,0),unitOffset.pad(16),false.B)
      address:=Cat(cmd.scalar(63,16),low(15,0));addressCarry:=low(16);state:=addressMiddle
    } else {
      val sum=CarrySelect.add(cmd.scalar(31,0),unitOffset.pad(32),false.B)
      address:=Cat(cmd.scalar(63,32),sum(31,0));addressCarry:=sum(32);state:=addressHigh
    }
  }
  if(shortUnitAdder) {
    when(state===addressMiddle) {
      address:=Cat(cmd.scalar(63,32),ParallelIncrement(cmd.scalar(31,16),addressCarry),address(15,0))
      addressCarry:=addressCarry && cmd.scalar(31,16).andR;state:=addressHigh
    }
  }
  when(state===addressHigh) {
    val upperBytes=(0 until 4).map { byte =>
      val carry=if(byte==0)addressCarry else addressCarry && upperAddressPrefix(byte-1)
      ParallelIncrement(cmd.scalar(39+8*byte,32+8*byte),carry)
    }
    address:=Cat(Cat(upperBytes.reverse),address(31,0));state:=checkAddress
  }
  when(state===checkAddress) {
    val alignment=VecInit(Seq(0,1,3,7).map(_.U(3.W)))(width)
    val regionMask=((BigInt(1)<<64)-1) ^ (regionBytes-1)
    when(stop) { interrupt() }
      .elsewhen((address(2,0)&alignment)=/=0.U) { fault(Mux(store,6.U,4.U)) }
      .elsewhen((address & regionMask.U(64.W))=/=regionBase.U) { fault(Mux(store,7.U,5.U)) }
      .otherwise {
        // A naturally aligned 64-bit load replaces the whole RF chunk; no
        // read/modify/write source is needed. Keep Get payload deterministic.
        val fullLoad= !store && width===3.U
        when(fullLoad) {original:=0.U}
        state:=Mux(fullLoad || cachedValid && cachedAddress===chunkAddress,sendMemory,readChunk)
      }
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
        when(segmented) {state:=segmentAdvance}.otherwise {
          index:=nextIndex;setStart(Mux(last,0.U,nextIndex),last)
        }
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
    when(segmented) {state:=segmentAdvance}.otherwise {
      index:=nextIndex;setStart(Mux(last,0.U,nextIndex),last)
    }
  }
  val commitStalled=RegNext(io.commit.valid && !io.commit.ready,false.B)
  val previousCommit=RegNext(io.commit.bits)
  val previousTrim=RegNext(io.trim.valid,false.B);val previousLength=RegNext(io.trim.bits)
  when(commitStalled) {
    assert(io.commit.valid && io.commit.bits===previousCommit,"progress commit changed under backpressure")
    assert(io.trim.valid===previousTrim && (!io.trim.valid || io.trim.bits===previousLength),"VL trim changed under progress backpressure")
  }
  when(io.commit.fire) {
    when(finishAfterStart) {state:=reply}
      .elsewhen(strided && segmented) {result:=Cat(Fill(56,1.U(1.W)),segmentBack);segmentAdd:=2.U;state:=strideAdd0}
      .otherwise {state:=Mux(strided && !zeroStride,strideAdd0,checkElement)}
  }
  when(io.completion.fire) { state:=idle }
}

/** Current physical normal-RAM load/store top. Host must keep irrevocable
  * memory-command ownership until completion, including after a stop/flush.
  */
class LishiVpuMemory(regionBase:BigInt=BigInt("80000000",16),regionBytes:BigInt=BigInt(1)<<28,chunkBits:Int=32,enableFp:Boolean=true,hostFcsr:Boolean=false) extends Module {
  require(Set(16,32).contains(chunkBits))
  override def desiredName=if(chunkBits==16)"LishiVpuMemory16" else "LishiVpuMemory"
  val vpu=Module(new MemoryRamVector(chunkBits=chunkBits,enableFp=enableFp,hostFcsr=hostFcsr));val engine=Module(new VectorMemoryEngine(regionBase,regionBytes,shortUnitAdder=hostFcsr))
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
  vpu.memoryVl.valid:=engine.io.trim.valid && busy;vpu.memoryVl.bits:=engine.io.trim.bits
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
  if(enableFp) {io.core.frm.get:=vpu.io.frm.get;io.core.fflags.get:=vpu.io.fflags.get}
  if(hostFcsr) {
    vpu.io.fcsrHost.get.frm:=io.core.fcsrHost.get.frm
    vpu.io.fcsrHost.get.fflags:=io.core.fcsrHost.get.fflags
    io.core.fcsrHost.get.flags.valid:=vpu.io.fcsrHost.get.flags.valid && !busy
    io.core.fcsrHost.get.flags.bits:=Mux(!busy,vpu.io.fcsrHost.get.flags.bits,0.U)
  }
  io.core.busy:=vpu.io.busy || busy || bridge.io.busy
  bridge.io.request<>engine.io.memoryRequest;engine.io.memoryResponse<>bridge.io.response
  bridge.io.flush:=false.B;io.tl<>bridge.io.tl
  io.memoryStatus.valid:=engine.io.completion.valid && busy;io.memoryStatus.bits:=engine.io.status
}
