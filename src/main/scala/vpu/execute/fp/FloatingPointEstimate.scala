package vpu

import chisel3._
import chisel3.util._

/** RVV 1.0 reciprocal/reciprocal-square-root seven-bit estimates.
  * One owner; byte/bit normalization, registered table lookup, exponent and pack
  * stages. Tables are small constant ROMs; no DSP and no architectural snapshots.
  * The reply is held until out.fire; flush cancels computation and reply.
  */
class FloatingPointEstimate extends Module {
  val io=IO(new Bundle {
    val flush=Input(Bool());val in=Flipped(Decoupled(new FpRequest));val out=Decoupled(new FpResponse)
  })
  val Seq(idle,normalize,lookup,exponentStage,pack,reply)=Enum(6)
  val state=RegInit(idle);val response=Reg(new FpResponse)
  val double=Reg(Bool());val reciprocal=Reg(Bool());val sign=Reg(Bool());val rounding=Reg(UInt(3.W))
  val significand=Reg(UInt(64.W));val exponent=Reg(SInt(13.W));val outputExponent=Reg(SInt(13.W))
  val estimate=Reg(UInt(7.W))
  io.in.ready:=state===idle && !io.flush;io.out.valid:=state===reply && !io.flush;io.out.bits:=response
  // Classify the original IEEE encoding before normalization. NaNs, signed
  // zero, infinities and negative rsqrt inputs complete without a ROM access.
  when(io.in.fire) {
    val x=io.in.bits.a;val d=io.in.bits.double;val rec=io.in.bits.op===30.U
    val e=Mux(d,x(62,52),x(30,23).pad(11));val f=Mux(d,x(51,0),Cat(x(22,0),0.U(29.W)))
    val sg=Mux(d,x(63),x(31));val special=Mux(d,e===2047.U,e===255.U)
    val nan=special && f.orR;val inf=special && !f.orR;val zero= !e.orR && !f.orR
    val invalid=nan && !f(51) || !rec && sg && !zero && !nan
    val illegal= !(io.in.bits.op===30.U || io.in.bits.op===31.U) || rec && io.in.bits.rounding>4.U
    double:=d;reciprocal:=rec;sign:=sg;rounding:=io.in.bits.rounding
    significand:=Cat(e.orR,f,0.U(11.W));exponent:=Mux(e.orR,e,1.U).zext
    response:=0.U.asTypeOf(new FpResponse);response.tag:=io.in.bits.tag;response.illegal:=illegal
    val infinity=Mux(d,"h7ff0000000000000".U(64.W),"h7f800000".U(64.W))
    val signBit=Mux(d,Cat(sg,0.U(63.W)),Cat(0.U(32.W),sg,0.U(31.W)))
    when(nan || invalid) {response.data:=Mux(d,"h7ff8000000000000".U,"h7fc00000".U);response.flags:=Mux(invalid,16.U,0.U)}
      .elsewhen(zero) {response.data:=signBit|infinity;response.flags:=8.U}
      .elsewhen(inf) {response.data:=signBit}
    when(illegal) {response.data:=0.U;response.flags:=0.U}
    state:=Mux(illegal || nan || invalid || zero || inf,reply,normalize)
  }
  // Subnormal inputs shift into the leading-one position of normal inputs.
  // Decrementing exponent preserves the value while skipping eight zero bits.
  when(state===normalize) {
    when(significand(63)) {state:=lookup}
      .elsewhen(!significand(63,56).orR) {significand:=Cat(significand(55,0),0.U(8.W));exponent:=exponent-8.S}
      .otherwise {significand:=Cat(significand(62,0),false.B);exponent:=exponent-1.S}
  }
  // RVV estimate-table entries are indexed by leading fraction bits; rsqrt
  // additionally uses exponent parity. Registration isolates lookup from pack.
  val reciprocalTable=VecInit(Seq(127,125,123,121,119,117,116,114,112,110,109,107,105,104,102,100,99,97,96,94,93,91,90,88,87,85,84,83,81,80,79,77,76,75,74,72,71,70,69,68,66,65,64,63,62,61,60,59,58,57,56,55,54,53,52,51,50,49,48,47,46,45,44,43,42,41,40,40,39,38,37,36,35,35,34,33,32,31,31,30,29,28,28,27,26,25,25,24,23,23,22,21,21,20,19,19,18,17,17,16,15,15,14,14,13,12,12,11,11,10,9,9,8,8,7,7,6,5,5,4,4,3,3,2,2,1,1,0).map(_.U(7.W)))
  val rsqrtTable=VecInit(Seq(52,51,50,48,47,46,44,43,42,41,40,39,38,36,35,34,33,32,31,30,30,29,28,27,26,25,24,23,23,22,21,20,19,19,18,17,16,16,15,14,14,13,12,12,11,10,10,9,9,8,7,7,6,6,5,4,4,3,3,2,2,1,1,0,127,125,123,121,119,118,116,114,113,111,109,108,106,105,103,102,100,99,97,96,95,93,92,91,90,88,87,86,85,84,83,82,80,79,78,77,76,75,74,73,72,71,70,70,69,68,67,66,65,64,63,63,62,61,60,59,59,58,57,56,56,55,54,53).map(_.U(7.W)))
  when(state===lookup) {
    estimate:=Mux(reciprocal,reciprocalTable(significand(62,56)),rsqrtTable(Cat(exponent(0),significand(62,57))))
    state:=exponentStage
  }
  // Work in biased exponents so both precisions share the same small adder.
  when(state===exponentStage) {
    val bias=Mux(double,1023.S(13.W),127.S(13.W))
    outputExponent:=Mux(reciprocal,(bias<<1)-1.S-exponent,((bias<<1)+bias-1.S-exponent)>>1)
    state:=pack
  }
  // Reciprocal overflow observes the rounding mode. Tiny results place the
  // leading one into the fraction; only overflow contributes OF and NX here.
  when(state===pack) {
    val overflow=reciprocal && outputExponent>Mux(double,2046.S,254.S)
    val finite=rounding===1.U || rounding===2.U && !sign || rounding===3.U && sign
    val expBits=Mux(outputExponent<=0.S,0.U,outputExponent.asUInt)
    val fraction=Cat(estimate,0.U(45.W))
    val denormal=Mux(outputExponent===0.S,Cat(1.U(1.W),fraction)>>1,Cat(1.U(1.W),fraction)>>2)
    val frac=Mux(outputExponent<=0.S,denormal(51,0),fraction)
    val normal=Mux(double,Cat(sign,expBits(10,0),frac),Cat(0.U(32.W),sign,expBits(7,0),frac(51,29)))
    val infinity=Mux(double,Cat(sign,"h7ff0000000000000".U(63.W)),Cat(0.U(32.W),sign,"h7f800000".U(31.W)))
    val maxFinite=Mux(double,Cat(sign,"h7fefffffffffffff".U(63.W)),Cat(0.U(32.W),sign,"h7f7fffff".U(31.W)))
    response.data:=Mux(overflow,Mux(finite,maxFinite,infinity),normal)
    response.flags:=Mux(overflow,5.U,0.U);state:=reply
  }
  when(io.out.fire) {state:=idle}
  when(io.flush) {state:=idle}
}
