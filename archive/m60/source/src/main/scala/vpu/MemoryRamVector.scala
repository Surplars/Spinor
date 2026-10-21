package vpu

import chisel3._
import chisel3.util._

/** Memory-only VL metadata shares the existing atomic progress handshake.
  * The ordinary arithmetic RamVector and its generated interfaces stay unchanged.
  */
class MemoryRamVector(chunkBits:Int=32,enableFp:Boolean=true,hostFcsr:Boolean=false)
    extends RamVector(chunkBits=chunkBits,enableFp=enableFp,enableMemoryCommit=true,stageControl=true,hostFcsr=hostFcsr) {
  val memoryVl=IO(Flipped(Valid(UInt(8.W))))
  when(memoryVl.valid) {
    assert(memoryCommit.get.valid && !io.command.valid,"VL trim lacks exclusive memory progress ownership")
  }
  when(memoryCommit.get.fire && memoryVl.valid) {vl:=memoryVl.bits}
}
