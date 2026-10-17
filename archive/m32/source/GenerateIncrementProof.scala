package vpu

import chisel3._
import chisel3.util._
import _root_.circt.stage.ChiselStage
import java.nio.file.{Files,Paths}

class IncrementProof extends Module {
  val io=IO(new Bundle {
    val bits=Input(UInt(109.W));val enable=Input(Bool())
    val base=Input(UInt(64.W));val index=Input(UInt(8.W));val eewLog2=Input(UInt(2.W))
    val mismatch=Output(Bool())
  })
  val increments=Seq(5,8,32,55,109).map { width =>
    val x=io.bits(width-1,0)
    ParallelIncrement(x,io.enable)=/=(x+io.enable)
  }.reduce(_ || _)
  val offset=(io.index<<io.eewLog2).pad(32)
  val low=CarrySelect.add(io.base(31,0),offset,false.B)
  val address=Cat(ParallelIncrement(io.base(63,32),low(32)),low(31,0))
  val t=io.bits(63,0)
  val fractionalReference=t(2,0)<=3.U || (t(2,0)>=5.U && t(5,3)<=(t(2,0)-5.U))
  val configMismatch=(VectorConfig.fractionalLegal(t)=/=fractionalReference) ||
    (VectorConfig.belowLimit(io.base,io.bits(7,0))=/=(io.base<io.bits(7,0).pad(64)))
  val groupLog=io.eewLog2
  val count=(1.U(4.W)<<groupLog)(3,0)
  val alignment=VectorConfig.groupAlignment(groupLog)
  val base=io.bits(4,0);val address5=io.bits(9,5)
  val groupMismatch=(base & alignment)===0.U &&
    (VectorConfig.alignedGroupContains(address5,base,alignment)=/=(address5>=base && address5<(base+&count)))
  val logB=io.bits(11,10)
  val countB=(1.U(4.W)<<logB)(3,0);val alignB=VectorConfig.groupAlignment(logB)
  val aligned=(base & alignment)===0.U && (address5 & alignB)===0.U
  val overlapMismatch=aligned &&
    (VectorConfig.alignedGroupsOverlap(base,alignment,address5,alignB)=/=
      (base<(address5+&countB) && address5<(base+&count)))
  // Widening overlap: aligned narrower source must end at destination end.
  // Cover every pair of 5-bit bases and power-of-two physical group sizes.
  val highPartMismatch=aligned && countB<count &&
    (((base^address5)===(alignment^alignB))=/=((base+&count)===(address5+&countB)))
  val alignmentMismatch=(alignment=/=(count-1.U).pad(5)) ||
    (VectorConfig.countAlignment(count)=/=alignment)
  val endMismatch=(base & alignment)===0.U && (base+&count)>32.U
  val lmul=io.bits(14,12)
  val narrowCount=MuxLookup(lmul,1.U(5.W))(Seq(0.U->2.U,1.U->4.U,2.U->8.U))
  val narrowValid=lmul<=2.U || lmul>=5.U
  val narrowMismatch=narrowValid && VectorConfig.narrowAlignment(lmul)=/=(narrowCount-1.U)
  io.mismatch:=narrowMismatch || highPartMismatch || overlapMismatch || alignmentMismatch || endMismatch || groupMismatch || increments || (address=/=(io.base+offset.pad(64))) || configMismatch
}
object GenerateIncrementProof extends App {
  val path=Paths.get(args(0));Files.createDirectories(path.getParent)
  val rtl=ChiselStage.emitSystemVerilog(new IncrementProof,firtoolOpts=Array("-disable-all-randomization","-strip-debug-info"))
  val marker=rtl.indexOf("// ----- 8< ----- FILE ")
  Files.writeString(path,if(marker<0)rtl else rtl.take(marker))
}
