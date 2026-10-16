# M6 integer multiply and cloud screening

M6 adds `vmul`, `vmulh`, `vmulhu`, `vmulhsu` in OPMVV (`funct3=010`) and OPMVX (`funct3=110`) forms, at SEW 8/16/32/64 and all 22 supported legal SEW/LMUL combinations. `vmulhsu` treats vs2 as signed and vs1/scalar as unsigned. Existing masks, vstart, tail-undisturbed behavior, overlapping source/destination groups, atomic version-map commit, completion backpressure and flush apply. This does not add widening multiply, multiply-accumulate, divide or remainder.

`IntegerMultiply` is capacity one and shares one unsigned 16×16 multiply. It registers the product, registers the aligned 128-bit term, then accumulates four 32-bit words over four cycles. There are 1/1/4/16 partial products for SEW 8/16/32/64. High signed results subtract b when a is negative, then a when b is negative, modulo SEW; each correction uses separate low/high 32-bit cycles. Data registers retain their contents on flush; only ownership/state is canceled. No result is visible until the operation completes. This design favors area and short arithmetic chains over throughput.

Expected latency from the accepting edge to visible output is 7/7/25/97 cycles for low multiply and 11/11/29/101 for high multiply; these exclude parent vector fetch/write/commit and backpressure. The multiplier does not accept another request while busy or holding a response.

Use `make verify-m6` for Chisel generation, RTL arithmetic/vector/FP regressions, Yosys mapping, cell-hop analysis, write-cone audit, mapped multiplier and mapped vector multiplication checks. Independent Python arbitrary-precision multiplication supplies expected results. Mapped tests include the pinned unmodified public DSP48E2 functional model; it supplies functional behavior, not calibrated -2 delays.

Cloud timing workflow for an existing matched Vivado result directory:

```bash
python3 scripts/cloud_timing_screen.py --results /path/to/results \
  --label M5 --output build/rapidwright/m5-screen
```

This verifies the export hashes, builds the RapidWright graph, compares exported critical paths and saves a SHA receipt. The matching DCP, readable EDIF and DSP tables must describe the same implementation. The cached pinned RapidWright JAR/device database and JDK are required. Changed RTL must first pass functional and structural screening; the old routed graph cannot provide its new placement or routed delays. M5's local timing result is a baseline, not an M6 timing result. M6 does not require another Windows run as part of this delivery, and the existing `windows-m5` target still explicitly builds only frozen M5 inputs.
