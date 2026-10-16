# Pinned HardFloat numerical hardware

Repository: https://github.com/ucb-bar/berkeley-hardfloat

Revision: `c1105e6ac6a0dd90fc80893efc4830ab609005d3`.
The 18 sources were copied from the pinned Valence checkout without changes;
their SHA-256 values and provenance are in `../fp-dependencies.json`.
Source copyright notices and `../licenses/berkeley-hardfloat.LICENSE` apply.

The inherited unsigned alignment-distance patch and the formatting differences
from upstream are recorded in that manifest and `patches/`. These 18 pinned files
remain unchanged. They compile with Scala 2.13.18 / Chisel
7.16.0 under Mill; this independent VPU project uses Icarus, not Valence's
scalar-core simulator or wrappers.

`FloatingPointLane.scala` provides resource sharing, staged product/aligned
addition, exact FP32 widening, direct raw-result rounding, RISC-V adaptation,
tags, backpressure and cancellation. These wrappers do not constitute a
separate floating-point numerical oracle. Tests use pinned Berkeley SoftFloat
with independent known-answer anchors; no upstream HardFloat testbench is used.

M4 adds derived `src/main/scala/vpu/StagedFmaPre.scala`, `StagedFmaPost.scala`,
`StagedRound.scala`, and `StagedDivSqrt.scala`. They retain the upstream BSD
notice and identify their modifications: register boundaries, split shifts,
balanced-prefix increments and multi-cycle split subtraction. They are derived
hardware, not independently authored numerical reference models.
FP timing remains unqualified; functional checks do not establish device Fmax.
