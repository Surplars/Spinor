
/*============================================================================

This Chisel source file is part of a pre-release version of the HardFloat IEEE
Floating-Point Arithmetic Package, by John R. Hauser (with some contributions
from Yunsup Lee and Andrew Waterman, mainly concerning testing).

Copyright 2017 SiFive, Inc.  All rights reserved.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:

 1. Redistributions of source code must retain the above copyright notice,
    this list of conditions, and the following disclaimer.

 2. Redistributions in binary form must reproduce the above copyright notice,
    this list of conditions, and the following disclaimer in the documentation
    and/or other materials provided with the distribution.

 3. Neither the name of SiFive nor the names of its contributors may
    be used to endorse or promote products derived from this software without
    specific prior written permission.

THIS SOFTWARE IS PROVIDED BY SIFIVE AND CONTRIBUTORS "AS IS", AND ANY
EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE, ARE
DISCLAIMED.  IN NO EVENT SHALL SIFIVE OR CONTRIBUTORS BE LIABLE FOR ANY
DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
(INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND
ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
(INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

=============================================================================*/

/*

s = sigWidth
c_i = newBit

Division:
width of a is (s+2)

Normal
------

(qi + ci * 2^(-i))*b <= a
q0 = 0
r0 = a

q(i+1) = qi + ci*2^(-i)
ri = a - qi*b
r(i+1) = a - q(i+1)*b
       = a - qi*b - ci*2^(-i)*b
r(i+1) = ri - ci*2^(-i)*b
ci = ri >= 2^(-i)*b
summary_i = ri != 0

i = 0 to s+1

(s+1)th bit plus summary_(i+1) gives enough information for rounding
If (a < b), then we need to calculate (s+2)th bit and summary_(i+1)
because we need s bits ignoring the leading zero. (This is skipCycle2
part of Hauser's code.)

Hauser
------
sig_i = qi
rem_i = 2^(i-2)*ri
cycle_i = s+3-i

sig_0 = 0
rem_0 = a/4
cycle_0 = s+3
bit_0 = 2^0 (= 2^(s+1), since we represent a, b and q with (s+2) bits)

sig(i+1) = sig(i) + ci*bit_i
rem(i+1) = 2rem_i - ci*b/2
ci = 2rem_i >= b/2
bit_i = 2^-i (=2^(cycle_i-2), since we represent a, b and q with (s+2) bits)
cycle(i+1) = cycle_i-1
summary_1 = a <> b
summary(i+1) = if ci then 2rem_i-b/2 <> 0 else summary_i, i <> 0

Proof:
2^i*r(i+1) = 2^i*ri - ci*b. Qed

ci = 2^i*ri >= b. Qed

summary(i+1) = if ci then rem(i+1) else summary_i, i <> 0
Now, note that all of ck's cannot be 0, since that means
a is 0. So when you traverse through a chain of 0 ck's,
from the end,
eventually, you reach a non-zero cj. That is exactly the
value of ri as the reminder remains the same. When all ck's
are 0 except c0 (which must be 1) then summary_1 is set
correctly according
to r1 = a-b != 0. So summary(i+1) is always set correctly
according to r(i+1)



Square root:
width of a is (s+1)

Normal
------
(xi + ci*2^(-i))^2 <= a
xi^2 + ci*2^(-i)*(2xi+ci*2^(-i)) <= a

x0 = 0
x(i+1) = xi + ci*2^(-i)
ri = a - xi^2
r(i+1) = a - x(i+1)^2
       = a - (xi^2 + ci*2^(-i)*(2xi+ci*2^(-i)))
       = ri - ci*2^(-i)*(2xi+ci*2^(-i))
       = ri - ci*2^(-i)*(2xi+2^(-i))  // ci is always 0 or 1
ci = ri >= 2^(-i)*(2xi + 2^(-i))
summary_i = ri != 0


i = 0 to s+1

For odd expression, do 2 steps initially.

(s+1)th bit plus summary_(i+1) gives enough information for rounding.

Hauser
------

sig_i = xi
rem_i = ri*2^(i-1)
cycle_i = s+2-i
bit_i = 2^(-i) (= 2^(s-i) = 2^(cycle_i-2) in terms of bit representation)

sig_0 = 0
rem_0 = a/2
cycle_0 = s+2
bit_0 = 1 (= 2^s in terms of bit representation)

sig(i+1) = sig_i + ci * bit_i
rem(i+1) = 2rem_i - ci*(2sig_i + bit_i)
ci = 2*sig_i + bit_i <= 2*rem_i
bit_i = 2^(cycle_i-2) (in terms of bit representation)
cycle(i+1) = cycle_i-1
summary_1 = a - (2^s) (in terms of bit representation) 
summary(i+1) = if ci then rem(i+1) <> 0 else summary_i, i <> 0


Proof:
ci = 2*sig_i + bit_i <= 2*rem_i
ci = 2xi + 2^(-i) <= ri*2^i. Qed

sig(i+1) = sig_i + ci * bit_i
x(i+1) = xi + ci*2^(-i). Qed

rem(i+1) = 2rem_i - ci*(2sig_i + bit_i)
r(i+1)*2^i = ri*2^i - ci*(2xi + 2^(-i))
r(i+1) = ri - ci*2^(-i)*(2xi + 2^(-i)). Qed

Same argument as before for summary.


------------------------------
Note that all registers are updated normally until cycle == 2.
At cycle == 2, rem is not updated, but all other registers are updated normally.
But, cycle == 1 does not read rem to calculate anything (note that final summary
is calculated using the values at cycle = 2).

*/

// Derived from HardFloat c1105e6 DivSqrtRawFN_small, options=0.
// Modified: latch each request; stage recurrence input/subtract/commit.
// Numerical state advances every five cycles. Original source retained.
package vpu

import chisel3._
import chisel3.util._
import hardfloat._
import hardfloat.consts._

/** Capacity-one binary64 divide/square-root recurrence from HardFloat.
  * inValid && inReady captures the raw operands, operation and rounding mode.
  * Each numerical step spans five phases: select, capture trial operands,
  * subtract low word, subtract high word, commit recurrence state.
  * Completion is a one-cycle rawOutValid pulse with no response backpressure;
  * the owning lane must capture it and perform final rounding. This helper
  * has no flush port: its parent combines cancellation into the local reset.
  */
class
    StagedDivSqrt(expWidth: Int = 11, sigWidth: Int = 53)
    extends Module
{
    override def desiredName = "StagedDivSqrt"
    require(expWidth == 11 && sigWidth == 53)
    val options = 0
    val io = IO(new Bundle {
        // Request is accepted only on inValid && inReady.
        val inReady        = Output(Bool())
        val inValid        = Input(Bool())
        val sqrtOp         = Input(Bool())
        val a              = Input(new RawFloat(expWidth, sigWidth))
        val b              = Input(new RawFloat(expWidth, sigWidth))
        val roundingMode   = Input(UInt(3.W))
        // Pulse outputs carry the unrounded result and its captured mode.
        val rawOutValid_div  = Output(Bool())
        val rawOutValid_sqrt = Output(Bool())
        val roundingModeOut  = Output(UInt(3.W))
        val invalidExc       = Output(Bool())
        val infiniteExc      = Output(Bool())
        val rawOut = Output(new RawFloat(expWidth, sigWidth + 2))
    })

    // cycleNum tracks numerical precision work; phase tracks the five-cycle
    // implementation schedule. Only commit advances the numerical recurrence.
    val cycleNum       = RegInit(0.U(log2Ceil(sigWidth + 3).W))
    val inReady        = RegInit(true.B)  // <-> (cycleNum <= 1)
    val rawOutValid    = RegInit(false.B) // <-> (cycleNum === 1)
    val phase = RegInit(0.U(3.W))
    val first = RegInit(false.B)
    val inputA = Reg(new RawFloat(expWidth,sigWidth))
    val inputB = Reg(new RawFloat(expWidth,sigWidth))
    val inputSqrt = Reg(Bool())
    val inputRounding = Reg(UInt(3.W))
    val accept = io.inValid && io.inReady
    val commit = phase === 4.U
    // A result is a one-cycle pulse; numerical state advances only at commit.
    rawOutValid := false.B
    when (phase === 0.U) {
        when (cycleNum === 1.U) { cycleNum := 0.U }
        .elsewhen (accept || !inReady) {
            first := accept
            when (accept) {
                inputA := io.a; inputB := io.b
                inputSqrt := io.sqrtOp; inputRounding := io.roundingMode
            }
            phase := 1.U
        }
    }


    // Classification and operation metadata belong to the accepted request
    // and remain paired with its quotient/root until the completion pulse.
    val sqrtOp_Z       = Reg(Bool())
    val majorExc_Z     = Reg(Bool())
    // Keep the exceptional classes separate for the raw-result interface.
    val isNaN_Z        = Reg(Bool())
    val isInf_Z        = Reg(Bool())
    val isZero_Z       = Reg(Bool())
    val sign_Z         = Reg(Bool())
    val sExp_Z         = Reg(SInt((expWidth + 2).W))
    val fractB_Z       = Reg(UInt(sigWidth.W))
    val roundingMode_Z = Reg(UInt(3.W))

    /*------------------------------------------------------------------------
    | (The most-significant and least-significant bits of 'rem_Z' are needed
    | only for square roots.)
    *------------------------------------------------------------------------*/
    val rem_Z          = Reg(UInt((sigWidth + 2).W))
    val notZeroRem_Z   = Reg(Bool())
    val sigX_Z         = Reg(UInt((sigWidth + 2).W))

    // Special cases bypass iterative precision work after the entry commit.
    // Keep invalid and divide-by-zero distinctions for the destination rounder.
    val rawA_S = inputA
    val rawB_S = inputB

    val notSigNaNIn_invalidExc_S_div =
        (rawA_S.isZero && rawB_S.isZero) || (rawA_S.isInf && rawB_S.isInf)
    val notSigNaNIn_invalidExc_S_sqrt =
        ! rawA_S.isNaN && ! rawA_S.isZero && rawA_S.sign
    val majorExc_S =
        Mux(inputSqrt,
            isSigNaNRawFloat(rawA_S) || notSigNaNIn_invalidExc_S_sqrt,
            isSigNaNRawFloat(rawA_S) || isSigNaNRawFloat(rawB_S) ||
                notSigNaNIn_invalidExc_S_div ||
                (! rawA_S.isNaN && ! rawA_S.isInf && rawB_S.isZero)
        )
    val isNaN_S =
        Mux(inputSqrt,
            rawA_S.isNaN || notSigNaNIn_invalidExc_S_sqrt,
            rawA_S.isNaN || rawB_S.isNaN || notSigNaNIn_invalidExc_S_div
        )
    val isInf_S  = Mux(inputSqrt, rawA_S.isInf,  rawA_S.isInf || rawB_S.isZero)
    val isZero_S = Mux(inputSqrt, rawA_S.isZero, rawA_S.isZero || rawB_S.isInf)
    val sign_S = rawA_S.sign ^ (! inputSqrt && rawB_S.sign)

    val specialCaseA_S = rawA_S.isNaN || rawA_S.isInf || rawA_S.isZero
    val specialCaseB_S = rawB_S.isNaN || rawB_S.isInf || rawB_S.isZero
    val normalCase_S_div = ! specialCaseA_S && ! specialCaseB_S
    val normalCase_S_sqrt = ! specialCaseA_S && ! rawA_S.sign
    val normalCase_S = Mux(inputSqrt, normalCase_S_sqrt, normalCase_S_div)

    // Divide subtracts exponents; sqrt halves the exponent at entry. Bound the
    // divide exponent before storing it in the fixed-width recurrence metadata.
    val sExpQuot_S_div =
        rawA_S.sExp +&
            Cat(rawB_S.sExp(expWidth), ~rawB_S.sExp(expWidth - 1, 0)).asSInt
    val sSatExpQuot_S_div =
        Cat(Mux(((BigInt(7)<<(expWidth - 2)).S <= sExpQuot_S_div),
                6.U,
                sExpQuot_S_div(expWidth + 1, expWidth - 2)
            ),
            sExpQuot_S_div(expWidth - 3, 0)
        ).asSInt

    val evenSqrt_S = inputSqrt && ! rawA_S.sExp(0)
    val oddSqrt_S  = inputSqrt &&   rawA_S.sExp(0)

    // Select the initial precision count and optional final-bit skip using the
    // original HardFloat recurrence. options=0 disables its two-bit variant.
    val idle = cycleNum === 0.U
    val entering = first && commit
    val entering_normalCase = entering && normalCase_S

    val processTwoBits = cycleNum >= 3.U && ((options & divSqrtOpt_twoBitsPerCycle) != 0).B
    val skipCycle2 = cycleNum === 3.U && sigX_Z(sigWidth + 1) && ((options & divSqrtOpt_twoBitsPerCycle) == 0).B

    when (commit && (! idle || entering)) {
        def computeCycleNum(f: UInt => UInt): UInt = {
            Mux(entering & ! normalCase_S, f(1.U), 0.U) |
            Mux(entering_normalCase,
                Mux(inputSqrt,
                    Mux(rawA_S.sExp(0), f(sigWidth.U), f((sigWidth + 1).U)),
                    f((sigWidth + 2).U)
                ),
                0.U
            ) |
            Mux(! entering && ! skipCycle2, f(cycleNum - Mux(processTwoBits, 2.U, 1.U)), 0.U) |
            Mux(skipCycle2, f(1.U), 0.U)
        }

        inReady := computeCycleNum(_ <= 1.U).asBool
        rawOutValid := computeCycleNum(_ === 1.U).asBool
        cycleNum := computeCycleNum(x => x)
    }

    io.inReady := inReady && phase === 0.U && cycleNum === 0.U

    // Entry commit freezes metadata; later commits update only the iterative
    // divisor/root trial term and numerical registers owned by this operation.
    when (commit && entering) {
        sqrtOp_Z   := inputSqrt
        majorExc_Z := majorExc_S
        isNaN_Z    := isNaN_S
        isInf_Z    := isInf_S
        isZero_Z   := isZero_S
        sign_Z     := sign_S
        sExp_Z :=
            Mux(inputSqrt,
                (rawA_S.sExp>>1) +& (BigInt(1)<<(expWidth - 1)).S,
                sSatExpQuot_S_div
            )
        roundingMode_Z := inputRounding
    }
    when (commit && (entering || ! inReady && sqrtOp_Z)) {
        fractB_Z :=
            Mux(inReady && ! inputSqrt,                       rawB_S.sig(sigWidth - 2, 0)<<1, 0.U) |
            Mux(inReady && inputSqrt && rawA_S.sExp(0),       (BigInt(1)<<(sigWidth - 2)).U,  0.U) |
            Mux(inReady && inputSqrt && ! rawA_S.sExp(0),     (BigInt(1)<<(sigWidth - 1)).U,  0.U) |
            Mux(! inReady /* sqrtOp_Z */ && processTwoBits,   fractB_Z>>2,                    0.U) |
            Mux(! inReady /* sqrtOp_Z */ && ! processTwoBits, fractB_Z>>1,                    0.U)
    }

    // Build the next trial remainder from the captured input on entry, or the
    // previous remainder afterwards. Square-root parity changes the first trial.
    val rem =
        Mux(inReady && ! oddSqrt_S, rawA_S.sig<<1, 0.U) |
        Mux(inReady && oddSqrt_S,
            Cat(rawA_S.sig(sigWidth - 1, sigWidth - 2) - 1.U,
                rawA_S.sig(sigWidth - 3, 0)<<3
            ),
            0.U
        ) |
        Mux(! inReady, rem_Z<<1, 0.U)
    val bitMask = (1.U<<cycleNum)(sigWidth + 2, 0)>>2
    val trialTerm =
        Mux(inReady && ! inputSqrt,  rawB_S.sig<<1,                 0.U) |
        Mux(inReady && evenSqrt_S,   (BigInt(1)<<sigWidth).U,       0.U) |
        Mux(inReady && oddSqrt_S,    (BigInt(5)<<(sigWidth - 1)).U, 0.U) |
        Mux(! inReady,               fractB_Z,                      0.U) |
        Mux(! inReady && ! sqrtOp_Z, 1.U << sigWidth,               0.U) |
        Mux(! inReady &&   sqrtOp_Z, sigX_Z<<1,                     0.U)
    // Registered 32-bit low subtraction, then upper subtraction with carry.
    val subtractionWidth = sigWidth + 5
    val savedRem = Reg(UInt(subtractionWidth.W))
    val savedTerm = Reg(UInt(subtractionWidth.W))
    val low = Reg(UInt(32.W))
    val carryLow = Reg(Bool())
    val trialRem = Reg(SInt(subtractionWidth.W))
    when (phase === 1.U) {
        savedRem := rem; savedTerm := trialTerm; phase := 2.U
    }
    when (phase === 2.U) {
        val sum = CarrySelect.add(savedRem(31,0),~savedTerm(31,0),true.B)
        low := sum(31,0); carryLow := sum(32); phase := 3.U
    }
    when (phase === 3.U) {
        val sum = CarrySelect.add(savedRem(subtractionWidth-1,32),~savedTerm(subtractionWidth-1,32),carryLow)
        trialRem := Cat(sum(subtractionWidth-33,0),low).asSInt
        phase := 4.U
    }
    when (phase === 4.U) { phase := 0.U }
    val newBit = (0.S <= trialRem)

    // A nonnegative trial chooses the new quotient/root bit. The zero summary
    // survives rejected subtractions and becomes the final sticky information.
    val nextRem_Z = Mux(newBit, trialRem.asUInt, savedRem)(sigWidth + 1, 0)
    val rem2 = nextRem_Z<<1
    val trialTerm2_newBit0 = Mux(sqrtOp_Z, fractB_Z>>1 | sigX_Z<<1, fractB_Z | (1.U << sigWidth))
    val trialTerm2_newBit1 = trialTerm2_newBit0 | Mux(sqrtOp_Z, fractB_Z<<1, 0.U)
    val trialRem2 =
        Mux(newBit,
            (trialRem<<1) - trialTerm2_newBit1.zext,
            (rem_Z<<2)(sigWidth+2, 0).zext - trialTerm2_newBit0.zext)
    val newBit2 = (0.S <= trialRem2)
    val nextNotZeroRem_Z = Mux(inReady || newBit, trialRem =/= 0.S, notZeroRem_Z)
    val nextNotZeroRem_Z_2 = // <-> Mux(newBit2, trialRem2 =/= 0.S, nextNotZeroRem_Z)
        processTwoBits && newBit && (0.S < (trialRem<<1) - trialTerm2_newBit1.zext) ||
        processTwoBits && !newBit && (0.S < (rem_Z<<2)(sigWidth+2, 0).zext - trialTerm2_newBit0.zext) ||
        !(processTwoBits && newBit2) && nextNotZeroRem_Z
    val nextRem_Z_2 =
        Mux(processTwoBits && newBit2,  trialRem2.asUInt(sigWidth + 1, 0), 0.U) |
        Mux(processTwoBits && !newBit2, rem2(sigWidth + 1, 0),               0.U) |
        Mux(!processTwoBits,            nextRem_Z,                           0.U)

    // Publish one recurrence step atomically after both subtract stages finish.
    when (commit && (entering || ! inReady)) {
        notZeroRem_Z := nextNotZeroRem_Z_2
        rem_Z := nextRem_Z_2
        sigX_Z :=
            Mux(inReady && ! inputSqrt,    newBit<<(sigWidth + 1),  0.U) |
            Mux(inReady &&   inputSqrt,    (BigInt(1)<<sigWidth).U, 0.U) |
            Mux(inReady && oddSqrt_S,      newBit<<(sigWidth - 1),  0.U) |
            Mux(! inReady,                 sigX_Z,                  0.U) |
            Mux(! inReady && newBit,       bitMask,                 0.U) |
            Mux(processTwoBits && newBit2, bitMask>>1,              0.U)
    }

    // The result is still unrounded: append the remainder summary to sigX_Z
    // and let the lane choose destination precision and exception packing.
    io.rawOutValid_div  := rawOutValid && ! sqrtOp_Z
    io.rawOutValid_sqrt := rawOutValid &&   sqrtOp_Z
    io.roundingModeOut  := roundingMode_Z
    io.invalidExc    := majorExc_Z &&   isNaN_Z
    io.infiniteExc   := majorExc_Z && ! isNaN_Z
    io.rawOut.isNaN  := isNaN_Z
    io.rawOut.isInf  := isInf_Z
    io.rawOut.isZero := isZero_Z
    io.rawOut.sign   := sign_Z
    io.rawOut.sExp   := sExp_Z
    io.rawOut.sig    := sigX_Z<<1 | notZeroRem_Z

}

