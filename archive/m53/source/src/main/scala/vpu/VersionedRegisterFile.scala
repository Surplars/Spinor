package vpu

import chisel3._
import chisel3.util._

/** Two physical RAM versions per architectural vector register. A 32-bit map
  * is the sole committed version selector. Candidate writes never touch the
  * active copy. Commit XORs selected map bits atomically; abort needs no RAM
  * reset/clear. Caller copies old destination bytes before partial updates.
  * One synchronous read and one byte-enabled write; same-physical-row
  * read/write collisions are excluded by the client protocol.
  */
class VersionedRegisterFile(useRam: Boolean = true) extends Module {
  override def desiredName = if (useRam) "VersionedRegisterFileRam" else "VersionedRegisterFileFlops"
  val io = IO(new Bundle {
    val readEnable = Input(Bool())
    val readAddress = Input(UInt(5.W))
    val readCandidate = Input(Bool())
    val readData = Output(UInt(128.W))
    val writeEnable = Input(Bool())
    val writeAddress = Input(UInt(5.W))
    val writeCandidate = Input(Bool())
    val writeMask = Input(UInt(16.W))
    val writeData = Input(UInt(128.W))
    val commit = Input(Bool())
    val commitMask = Input(UInt(32.W))
    val versions = Output(UInt(32.W))
  })
  val committed = RegInit(0.U(32.W))
  when(io.commit) { committed := committed ^ io.commitMask }
  io.versions := committed
  val readPhysical = Cat(committed(io.readAddress) ^ io.readCandidate,io.readAddress)
  val writePhysical = Cat(committed(io.writeAddress) ^ io.writeCandidate,io.writeAddress)
  if (useRam) {
    val storage = SyncReadMem(64,Vec(16,UInt(8.W)))
    when(io.writeEnable) { storage.write(writePhysical,io.writeData.asTypeOf(Vec(16,UInt(8.W))),io.writeMask.asBools) }
    io.readData := storage.read(readPhysical,io.readEnable).asUInt
  } else {
    val storage = Reg(Vec(64,Vec(16,UInt(8.W))))
    val read = Reg(UInt(128.W))
    when(io.writeEnable) {
      for (b <- 0 until 16) {
        when(io.writeMask(b)) { storage(writePhysical)(b) := io.writeData(8*b+7,8*b) }
      }
    }
    when(io.readEnable) { read := storage(readPhysical).asUInt }
    io.readData := read
  }
}
