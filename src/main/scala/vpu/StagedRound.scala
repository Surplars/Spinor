
/*============================================================================

This Chisel source file is part of a pre-release version of the HardFloat IEEE
Floating-Point Arithmetic Package, by John R. Hauser (with some contributions
from Yunsup Lee and Andrew Waterman, mainly concerning testing).

Copyright 2010, 2011, 2012, 2013, 2014, 2015, 2016, 2017 The Regents of the
University of California.  All rights reserved.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:

 1. Redistributions of source code must retain the above copyright notice,
    this list of conditions, and the following disclaimer.

 2. Redistributions in binary form must reproduce the above copyright notice,
    this list of conditions, and the following disclaimer in the documentation
    and/or other materials provided with the distribution.

 3. Neither the name of the University nor the names of its contributors may
    be used to endorse or promote products derived from this software without
    specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE REGENTS AND CONTRIBUTORS "AS IS", AND ANY
EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE, ARE
DISCLAIMED.  IN NO EVENT SHALL THE REGENTS OR CONTRIBUTORS BE LIABLE FOR ANY
DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
(INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND
ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
(INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

=============================================================================*/

// Derived from HardFloat c1105e6 RoundAnyRawFNToRecFN.
// Modified: register adjusted inputs, mask, rounded significand, common result and output;
// replace increment with a balanced prefix. Inputs held by capacity-one owner.
package vpu

import chisel3._
import chisel3.util._
import hardfloat._
import hardfloat.consts._

class
    StagedRound(
        inExpWidth: Int,
        inSigWidth: Int,
        outExpWidth: Int,
        outSigWidth: Int,
        options: Int
    )
    extends Module
{
    override def desiredName = s"StagedRound_e${outExpWidth}_s${outSigWidth}"
    val io = IO(new Bundle {
        val start=Input(Bool());val flush=Input(Bool());val done=Output(Bool())
        val invalidExc  = Input(Bool())   // overrides 'infiniteExc' and 'in'
        val infiniteExc = Input(Bool())   // overrides 'in' except for 'in.sign'
        val in = Input(new RawFloat(inExpWidth, inSigWidth))
                                        // (allowed exponent range has limits)
        val roundingMode   = Input(UInt(3.W))
        val detectTininess = Input(UInt(1.W))
        val out = Output(Bits((outExpWidth + outSigWidth + 1).W))
        val exceptionFlags = Output(Bits(5.W))
    })

    //------------------------------------------------------------------------
    //------------------------------------------------------------------------
    val phase=RegInit(0.U(3.W))
    io.done := phase===6.U && !io.flush
    when(phase===0.U && io.start && !io.flush) { phase:=1.U }
    when(phase=/=0.U) { phase:=Mux(phase===6.U,0.U,phase+1.U) }
    when(io.flush) { phase:=0.U }
    val result=Reg(UInt((outExpWidth+outSigWidth+1).W))
    val flags=Reg(UInt(5.W))
    io.out:=result;io.exceptionFlags:=flags
    // Local 8-bit carry groups. The rounding decision is registered separately.
    def increment(x: UInt,carries: Vec[Bool]): UInt = {
        val pieces=(0 until x.getWidth by 8).zipWithIndex.map { case (lo,k)=>
            val hi=math.min(lo+7,x.getWidth-1)
            (x(hi,lo)+carries(k))(hi-lo,0)
        }
        Cat(pieces.reverse)
    }
    val sigMSBitAlwaysZero = ((options & flRoundOpt_sigMSBitAlwaysZero) != 0)
    val effectiveInSigWidth =
        if (sigMSBitAlwaysZero) inSigWidth else inSigWidth + 1
    val neverUnderflows =
        ((options &
              (flRoundOpt_neverUnderflows | flRoundOpt_subnormsAlwaysExact)
         ) != 0) ||
            (inExpWidth < outExpWidth)
    val neverOverflows =
        ((options & flRoundOpt_neverOverflows) != 0) ||
            (inExpWidth < outExpWidth)
    val outNaNExp = BigInt(7)<<(outExpWidth - 2)
    val outInfExp = BigInt(6)<<(outExpWidth - 2)
    val outMaxFiniteExp = outInfExp - 1
    val outMinNormExp = (BigInt(1)<<(outExpWidth - 1)) + 2
    val outMinNonzeroExp = outMinNormExp - outSigWidth + 1

    //------------------------------------------------------------------------
    //------------------------------------------------------------------------
    val roundingMode_near_even   = (io.roundingMode === round_near_even)
    val roundingMode_minMag      = (io.roundingMode === round_minMag)
    val roundingMode_min         = (io.roundingMode === round_min)
    val roundingMode_max         = (io.roundingMode === round_max)
    val roundingMode_near_maxMag = (io.roundingMode === round_near_maxMag)
    val roundingMode_odd         = (io.roundingMode === round_odd)

    val roundMagUp =
        (roundingMode_min && io.in.sign) || (roundingMode_max && ! io.in.sign)

    //------------------------------------------------------------------------
    //------------------------------------------------------------------------
    val sAdjustedExpComb =
        if (inExpWidth < outExpWidth)
            (io.in.sExp +&
                 ((BigInt(1)<<outExpWidth) - (BigInt(1)<<inExpWidth)).S
            )(outExpWidth, 0).zext
        else if (inExpWidth == outExpWidth)
            io.in.sExp
        else
            io.in.sExp +&
                ((BigInt(1)<<outExpWidth) - (BigInt(1)<<inExpWidth)).S
    val sAdjustedExp=Reg(chiselTypeOf(sAdjustedExpComb))
    when(phase===0.U && io.start) { sAdjustedExp:=sAdjustedExpComb }
    val adjustedSigComb =
        if (inSigWidth <= outSigWidth + 2)
            io.in.sig<<(outSigWidth - inSigWidth + 2)
        else
            (io.in.sig(inSigWidth, inSigWidth - outSigWidth - 1) ##
                io.in.sig(inSigWidth - outSigWidth - 2, 0).orR
            )
    val adjustedSig=Reg(chiselTypeOf(adjustedSigComb))
    when(phase===0.U && io.start) { adjustedSig:=adjustedSigComb }
    val doShiftSigDown1 =
        if (sigMSBitAlwaysZero) false.B else adjustedSig(outSigWidth + 2)

    val common_expOutComb   = Wire(UInt((outExpWidth + 1).W))
    val common_fractOutComb = Wire(UInt((outSigWidth - 1).W))
    val common_overflowComb       = Wire(Bool())
    val common_totalUnderflowComb = Wire(Bool())
    val common_underflowComb      = Wire(Bool())
    val common_inexactComb        = Wire(Bool())

    if (
        neverOverflows && neverUnderflows
            && (effectiveInSigWidth <= outSigWidth)
    ) {

        //--------------------------------------------------------------------
        //--------------------------------------------------------------------
        common_expOutComb := sAdjustedExp(outExpWidth, 0) + doShiftSigDown1
        common_fractOutComb :=
            Mux(doShiftSigDown1,
                adjustedSig(outSigWidth + 1, 3),
                adjustedSig(outSigWidth, 2)
            )
        common_overflowComb       := false.B
        common_totalUnderflowComb := false.B
        common_underflowComb      := false.B
        common_inexactComb        := false.B

    } else {

        //--------------------------------------------------------------------
        //--------------------------------------------------------------------
        val roundMaskComb =
            if (neverUnderflows)
                0.U(outSigWidth.W) ## doShiftSigDown1 ## 3.U(2.W)
            else
                (lowMask(
                        sAdjustedExp(outExpWidth, 0),
                        outMinNormExp - outSigWidth - 1,
                        outMinNormExp
                    ) | doShiftSigDown1) ##
                  3.U(2.W)

        val roundMask=Reg(chiselTypeOf(roundMaskComb))
        when(phase===1.U) { roundMask:=roundMaskComb }
        val shiftedRoundMask = 0.U(1.W) ## roundMask>>1
        val roundPosMask = ~shiftedRoundMask & roundMask
        val roundPosBitComb = (adjustedSig & roundPosMask).orR
        val anyRoundExtraComb = (adjustedSig & shiftedRoundMask).orR
        val anyRoundComb = roundPosBitComb || anyRoundExtraComb
        val roundPosBit=Reg(Bool());val anyRound=Reg(Bool())

        val roundIncr =
            ((roundingMode_near_even || roundingMode_near_maxMag) &&
                 roundPosBitComb) ||
                (roundMagUp && anyRoundComb)
        val incrementSelected=Reg(Bool())
        val incrementBase=Reg(UInt((outSigWidth+2).W))
        val incrementCarries=Reg(Vec((outSigWidth+9)/8,Bool()))
        val evenClearMask=Reg(UInt((outSigWidth+2).W))
        val unrounded=Reg(UInt((outSigWidth+2).W))
        when(phase===2.U) {
            roundPosBit:=roundPosBitComb;anyRound:=anyRoundComb
            incrementSelected:=roundIncr
            val base=Cat(0.U(1.W),(adjustedSig | roundMask)>>2)
            incrementBase:=base
            for((lo,k)<-(0 until outSigWidth+2 by 8).zipWithIndex) {
                incrementCarries(k):= (if(lo==0)true.B else base(lo-1,0).andR)
            }
            evenClearMask:=Mux(roundingMode_near_even && roundPosBitComb && !anyRoundExtraComb,roundMask>>1,0.U)
            unrounded:=(adjustedSig & ~roundMask)>>2 |
                Mux(roundingMode_odd && anyRoundComb,roundPosMask>>1,0.U)
        }
        val roundedSigComb: Bits =
            Mux(incrementSelected,increment(incrementBase,incrementCarries) & ~evenClearMask,unrounded)
val roundedSig=Reg(chiselTypeOf(roundedSigComb))
        when(phase===3.U) { roundedSig:=roundedSigComb }
//*** IF SIG WIDTH IS VERY NARROW, NEED TO ACCOUNT FOR ROUND-EVEN ZEROING
//***  M.S. BIT OF SUBNORMAL SIG?
        val sRoundedExp = sAdjustedExp +& (roundedSig>>outSigWidth).asUInt.zext

        common_expOutComb := sRoundedExp(outExpWidth, 0)
        common_fractOutComb :=
            Mux(doShiftSigDown1,
                roundedSig(outSigWidth - 1, 1),
                roundedSig(outSigWidth - 2, 0)
            )
        common_overflowComb :=
            (if (neverOverflows) false.B else
//*** REWRITE BASED ON BEFORE-ROUNDING EXPONENT?:
                 (sRoundedExp>>(outExpWidth - 1) >= 3.S))
        common_totalUnderflowComb :=
            (if (neverUnderflows) false.B else
//*** WOULD BE GOOD ENOUGH TO USE EXPONENT BEFORE ROUNDING?:
                 (sRoundedExp < outMinNonzeroExp.S))

        val unboundedRange_roundPosBit =
            Mux(doShiftSigDown1, adjustedSig(2), adjustedSig(1))
        val unboundedRange_anyRound =
            (doShiftSigDown1 && adjustedSig(2)) || adjustedSig(1, 0).orR
        val unboundedRange_roundIncr =
            ((roundingMode_near_even || roundingMode_near_maxMag) &&
                 unboundedRange_roundPosBit) ||
                (roundMagUp && unboundedRange_anyRound)
        val roundCarry =
            Mux(doShiftSigDown1,
                roundedSig(outSigWidth + 1),
                roundedSig(outSigWidth)
            )
        common_underflowComb :=
            (if (neverUnderflows) false.B else
                 common_totalUnderflowComb ||
//*** IF SIG WIDTH IS VERY NARROW, NEED TO ACCOUNT FOR ROUND-EVEN ZEROING
//***  M.S. BIT OF SUBNORMAL SIG?
                     (anyRound && ((sAdjustedExp>>outExpWidth) <= 0.S) &&
                          Mux(doShiftSigDown1, roundMask(3), roundMask(2)) &&
                          ! ((io.detectTininess === tininess_afterRounding) &&
                                 ! Mux(doShiftSigDown1,
                                       roundMask(4),
                                       roundMask(3)
                                   ) &&
                                 roundCarry && roundPosBit &&
                                 unboundedRange_roundIncr)))

        common_inexactComb := common_totalUnderflowComb || anyRound
    }

    // Separate exponent correction/classification from special-value packing.
    val common_expOut=Reg(chiselTypeOf(common_expOutComb))
    val common_fractOut=Reg(chiselTypeOf(common_fractOutComb))
    val common_overflow=Reg(chiselTypeOf(common_overflowComb))
    val common_totalUnderflow=Reg(chiselTypeOf(common_totalUnderflowComb))
    val common_underflow=Reg(chiselTypeOf(common_underflowComb))
    val common_inexact=Reg(chiselTypeOf(common_inexactComb))
    when(phase===4.U) {
        common_expOut:=common_expOutComb
        common_fractOut:=common_fractOutComb
        common_overflow:=common_overflowComb
        common_totalUnderflow:=common_totalUnderflowComb
        common_underflow:=common_underflowComb
        common_inexact:=common_inexactComb
    }

    //------------------------------------------------------------------------
    //------------------------------------------------------------------------
    val isNaNOut = io.invalidExc || io.in.isNaN
    val notNaN_isSpecialInfOut = io.infiniteExc || io.in.isInf
    val commonCase = ! isNaNOut && ! notNaN_isSpecialInfOut && ! io.in.isZero
    val overflow  = commonCase && common_overflow
    val underflow = commonCase && common_underflow
    val inexact = overflow || (commonCase && common_inexact)

    val overflow_roundMagUp =
        roundingMode_near_even || roundingMode_near_maxMag || roundMagUp
    val pegMinNonzeroMagOut =
        commonCase && common_totalUnderflow && (roundMagUp || roundingMode_odd)
    val pegMaxFiniteMagOut = overflow && ! overflow_roundMagUp
    val notNaN_isInfOut =
        notNaN_isSpecialInfOut || (overflow && overflow_roundMagUp)

    val signOut = Mux(isNaNOut, false.B, io.in.sign)
    val expOut =
        (common_expOut &
             ~Mux(io.in.isZero || common_totalUnderflow,
               (BigInt(7)<<(outExpWidth - 2)).U((outExpWidth + 1).W),
               0.U
              ) &
             ~Mux(pegMinNonzeroMagOut,
                  ~outMinNonzeroExp.U((outExpWidth + 1).W),
               0.U
              ) &
             ~Mux(pegMaxFiniteMagOut,
               (BigInt(1)<<(outExpWidth - 1)).U((outExpWidth + 1).W),
               0.U
              ) &
             ~Mux(notNaN_isInfOut,
               (BigInt(1)<<(outExpWidth - 2)).U((outExpWidth + 1).W),
               0.U
              )) |
            Mux(pegMinNonzeroMagOut,
              outMinNonzeroExp.U((outExpWidth + 1).W),
              0.U
            ) |
            Mux(pegMaxFiniteMagOut,
              outMaxFiniteExp.U((outExpWidth + 1).W),
              0.U
            ) |
            Mux(notNaN_isInfOut, outInfExp.U((outExpWidth + 1).W), 0.U) |
            Mux(isNaNOut,        outNaNExp.U((outExpWidth + 1).W), 0.U)
    val fractOut =
        Mux(isNaNOut || io.in.isZero || common_totalUnderflow,
            Mux(isNaNOut, (BigInt(1)<<(outSigWidth - 2)).U, 0.U),
            common_fractOut
        ) |
        Fill(outSigWidth - 1, pegMaxFiniteMagOut)

    when(phase===5.U) {
        result := signOut ## expOut ## fractOut
        flags := io.invalidExc ## io.infiniteExc ## overflow ## underflow ## inexact
    }
}

