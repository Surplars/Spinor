package vpu

import chisel3._
import chisel3.util._

/** Byte-aligned 64-bit window, zero-filled above a 128-bit RAM word.
  * The caller registers a one-hot byte selector in the RAM request stage.
  */
object PackedElementRead {
  def apply(data:UInt,select:UInt):UInt = {
    require(data.getWidth==128 && select.getWidth==16)
    Mux1H((0 until 16).map { byte =>
      select(byte) -> data(math.min(127,byte*8+63),byte*8).pad(64)
    })
  }
}
