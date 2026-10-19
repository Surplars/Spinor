package vpu

import chisel3._
import chisel3.util._

/** 32x128-bit VRF: one synchronous 128-bit read, one write address, two
  * independently enabled 64-bit banks. Exactly one writer, no reset/clear of
  * memory contents, and no simultaneous read/write are required by this user.
  * This intentionally avoids multiwrite emulation or read-port replication.
  * LUTRAM versus BRAM is a mapping decision; useRam does NOT promise BRAM.
  */
class VectorRegisterFile(useRam: Boolean = true) extends Module {
  override def desiredName = if (useRam) "VectorRegisterFileRam" else "VectorRegisterFileFlops"
  val io = IO(new Bundle {
    val readEnable = Input(Bool())
    val readAddress = Input(UInt(5.W))
    val readData = Output(UInt(128.W))
    val writeEnable = Input(Bool())
    val writeAddress = Input(UInt(5.W))
    val writeMask = Input(UInt(2.W))
    val writeData = Input(UInt(128.W))
  })
  val banks = for (bank <- 0 until 2) yield {
    if (useRam) {
      val memory = SyncReadMem(32,UInt(64.W))
      when(io.writeEnable && io.writeMask(bank)) {
        memory.write(io.writeAddress,io.writeData(64*bank+63,64*bank))
      }
      memory.read(io.readAddress,io.readEnable)
    } else {
      val memory = Reg(Vec(32,UInt(64.W)))
      val data = Reg(UInt(64.W))
      when(io.writeEnable && io.writeMask(bank)) {
        memory(io.writeAddress) := io.writeData(64*bank+63,64*bank)
      }
      when(io.readEnable) { data := memory(io.readAddress) }
      data
    }
  }
  io.readData := Cat(banks(1),banks(0))
}
