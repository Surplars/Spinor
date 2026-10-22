package vpu

import chisel3._
import chisel3.util._

/** Adds LSU progress publication to the arithmetic core's versioned state.
  *
  * The inherited memoryCommit handshake publishes vstart. A simultaneous
  * memoryVl update publishes the VL reduction used by fault-only-first loads
  * on that same edge. The LSU must own the core exclusively while publishing
  * progress; a valid VL sideband alone cannot update architectural state.
  */
class MemoryRamVector(chunkBits:Int=32,enableFp:Boolean=true,hostFcsr:Boolean=false,stageOperands:Boolean=false)
    extends RamVector(chunkBits=chunkBits,enableFp=enableFp,enableMemoryCommit=true,stageControl=true,hostFcsr=hostFcsr,stageOperands=stageOperands) {
  val memoryVl=IO(Flipped(Valid(UInt(8.W))))
  // Keep VL trimming paired with the progress transaction even under backpressure.
  when(memoryVl.valid) {
    assert(memoryCommit.get.valid && !io.command.valid,"VL trim lacks exclusive memory progress ownership")
  }
  when(memoryCommit.get.fire && memoryVl.valid) {vl:=memoryVl.bits}
}
