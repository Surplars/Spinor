.PHONY: verify-m27 package-m27
verify-m27:
	$(PYTHON) scripts/verify_m27.py
package-m27:
	$(PYTHON) scripts/package.py --milestone m27

.PHONY: verify-m26 package-m26
verify-m26:
	$(PYTHON) scripts/verify_m26.py
package-m26:
	$(PYTHON) scripts/package.py --milestone m26

PYTHON ?= python3

.PHONY: verify-m25 package-m25
verify-m25:
	$(PYTHON) scripts/verify_m25.py
package-m25:
	$(PYTHON) scripts/package.py --milestone m25

.PHONY: verify-m24 package-m24
verify-m24:
	$(PYTHON) scripts/verify_m24.py
package-m24:
	$(PYTHON) scripts/package.py --milestone m24

.PHONY: verify-m23 package-m23
verify-m23:
	$(PYTHON) scripts/verify_m23.py
package-m23:
	$(PYTHON) scripts/package.py --milestone m23

.PHONY: verify-m22 package-m22
verify-m22:
	$(PYTHON) scripts/verify_m22.py
package-m22:
	$(PYTHON) scripts/package.py --milestone m22

.PHONY: verify-m21 package-m21
verify-m21:
	$(PYTHON) scripts/verify_m21.py
package-m21:
	$(PYTHON) scripts/package.py --milestone m21

.PHONY: verify-m20 package-m20
verify-m20:
	$(PYTHON) scripts/verify_m20.py
package-m20:
	$(PYTHON) scripts/package.py --milestone m20

.PHONY: verify-m19 package-m19
verify-m19:
	$(PYTHON) scripts/verify_m19.py
package-m19:
	$(PYTHON) scripts/package.py --milestone m19

.PHONY: verify-m18 package-m18
verify-m18:
	$(PYTHON) scripts/verify_m18.py
package-m18:
	$(PYTHON) scripts/package.py --milestone m18

.PHONY: verify-m17 package-m17
verify-m17: rtl
	$(PYTHON) scripts/prove_classify.py
	$(PYTHON) scripts/prove_divider_word.py
	$(PYTHON) tests/test_lane.py
	$(PYTHON) tests/test_fp_lane.py
	$(PYTHON) tests/test_fp_lane.py --smoke
	$(PYTHON) tests/test_ram_vector.py --fp --multiply --divide
	$(PYTHON) tests/test_fp_vector.py --convert --multiply --divide
	$(PYTHON) tests/test_streaming.py
	$(PYTHON) tests/test_vector_memory.py
	$(PYTHON) tests/test_vector_memory.py --smoke
	$(PYTHON) tests/performance.py --baseline archive/m16/rtl/RamVectorFp.sv --current build/rtl/RamVectorFp.sv --baseline-label M16 --current-label M17 --output build/performance-m17-final
	$(PYTHON) scripts/synth.py LishiVpuMemory FloatingPointLane RamVectorFp
	$(PYTHON) scripts/path_depth.py LishiVpuMemory FloatingPointLane RamVectorFp
	$(PYTHON) tests/test_fp_lane.py --smoke --mapped
	$(PYTHON) tests/test_ram_vector.py --fp --multiply --divide --mapped-only
	$(PYTHON) tests/test_streaming.py --mapped
	$(PYTHON) tests/test_vector_memory.py --smoke --mapped
	$(PYTHON) scripts/cloud_budget.py --netlist archive/m16/synth-LishiVpuMemory/mapped.json --output build/timing-budget/m16-baseline
	$(PYTHON) scripts/cloud_budget.py --netlist build/synth/LishiVpuMemory/mapped.json --output build/timing-budget/m17
	$(PYTHON) scripts/report_m17.py
package-m17:
	$(PYTHON) scripts/package.py --milestone m17
TOPS := IntegerLaneBaseline IntegerLaneSplit IntegerLaneSplit16 VectorPrototype VectorPrototype16 VectorPrototypeFlops VectorPrototypeBram ValenceBoundary
PATH_TOPS := IntegerLaneBaseline IntegerLaneSplit IntegerLaneSplit16 VectorPrototype VectorPrototype16 VectorPrototypeFlops
M2_TOPS := RamVector RamVector16 RamVectorFlops RamVectorBram VersionedRegisterFileRam
LANE_TOPS := IntegerLaneBaseline IntegerLaneSplit IntegerLaneSplit16

.PHONY: bootstrap compile rtl test synth paths mapped-test report verify package
bootstrap:
	$(PYTHON) scripts/bootstrap.py
compile:
	./mill Vpu.compile
rtl:
	@mkdir -p tools
	./mill Vpu.runMain vpu.Generate $(CURDIR)/build/rtl > tools/mill-generate.log 2>&1
	@tail -n 6 tools/mill-generate.log
test: rtl
	$(PYTHON) tests/test_lane.py
	$(PYTHON) tests/test_vector.py
	$(PYTHON) tests/test_boundary.py
	$(PYTHON) tests/benchmark.py
synth: rtl
	$(PYTHON) scripts/synth.py $(TOPS)
paths: synth
	$(PYTHON) scripts/path_depth.py $(PATH_TOPS)
mapped-test: synth
	$(PYTHON) tests/test_vector.py --mapped-only
report: test paths mapped-test
	$(PYTHON) scripts/report.py
verify: report
package:
	$(PYTHON) scripts/package.py

.PHONY: m2-test m2-synth m2-paths m2-mapped-test reference-timing verify-m2 package-m2
m2-test: rtl
	$(PYTHON) tests/test_versioned_rf.py
	$(PYTHON) tests/test_ram_vector.py
	$(PYTHON) tests/benchmark.py --ram
m2-synth: rtl
	$(PYTHON) scripts/synth.py $(M2_TOPS) $(LANE_TOPS)
m2-paths: m2-synth
	$(PYTHON) scripts/path_depth.py RamVector RamVector16 RamVectorFlops VersionedRegisterFileRam $(LANE_TOPS)
m2-mapped-test: m2-synth m2-test
	$(PYTHON) tests/test_ram_vector.py --mapped-only
reference-timing: m2-synth
	$(PYTHON) tests/test_lane.py
	$(PYTHON) scripts/timing_reference.py
verify-m2: m2-test m2-paths m2-mapped-test reference-timing
	$(PYTHON) scripts/report_m2.py
package-m2:
	$(PYTHON) scripts/package.py --milestone m2

.PHONY: fp-bootstrap m3-test m3-synth m3-paths m3-mapped-test verify-m3 package-m3
fp-bootstrap:
	$(PYTHON) scripts/bootstrap_fp.py
m3-test: rtl fp-bootstrap
	$(PYTHON) scripts/record_tested_rtl.py
	$(PYTHON) tests/test_fp_lane.py
	$(PYTHON) tests/test_fp_vector.py
	$(PYTHON) tests/test_ram_vector.py --fp
m3-synth: rtl
	$(PYTHON) scripts/synth.py FloatingPointLane RamVectorFp RamVectorFpNoDsp
m3-paths: m3-synth
	$(PYTHON) scripts/path_depth.py FloatingPointLane RamVectorFp RamVectorFpNoDsp
m3-mapped-test: m3-test m3-synth
	$(PYTHON) tests/test_fp_vector.py --mapped
verify-m3: m3-test m3-paths m3-mapped-test
	$(PYTHON) scripts/report_m3.py
package-m3:
	$(PYTHON) scripts/package.py --milestone m3

.PHONY: m4-test m4-synth m4-paths m4-mapped-test rapidwright-probe verify-m4 package-m4
m4-test: rtl fp-bootstrap
	$(PYTHON) scripts/record_tested_rtl.py --milestone m4
	$(PYTHON) tests/test_fp_lane.py
	$(PYTHON) tests/test_fp_vector.py
	$(PYTHON) tests/test_ram_vector.py --fp
	$(PYTHON) tests/test_ram_vector.py
m4-synth: rtl
	$(PYTHON) scripts/synth.py FloatingPointLane RamVectorFp
m4-paths: m4-synth
	$(PYTHON) scripts/path_depth.py FloatingPointLane RamVectorFp
m4-mapped-test: m4-test m4-synth
	$(PYTHON) tests/test_fp_vector.py --mapped
rapidwright-probe:
	$(PYTHON) scripts/rapidwright_probe.py --device
verify-m4: m4-test m4-paths m4-mapped-test rapidwright-probe
	$(PYTHON) scripts/report_m4.py
package-m4:
	$(PYTHON) scripts/package.py --milestone m4

.PHONY: m5-test m5-synth m5-paths m5-mapped-test verify-m5 package-m5
m5-test: rtl fp-bootstrap
	$(PYTHON) scripts/record_tested_rtl.py --milestone m5
	$(PYTHON) tests/test_fp_vector.py
	$(PYTHON) tests/test_ram_vector.py --fp
	$(PYTHON) tests/test_ram_vector.py
m5-synth: rtl
	$(PYTHON) scripts/synth.py RamVectorFp
m5-paths: m5-synth
	$(PYTHON) scripts/path_depth.py RamVectorFp
	$(PYTHON) scripts/check_write_cone.py
m5-mapped-test: m5-test m5-synth
	$(PYTHON) tests/test_fp_vector.py --mapped
verify-m5: m5-test m5-paths m5-mapped-test
	$(PYTHON) scripts/report_m5.py
package-m5:
	$(PYTHON) scripts/package.py --milestone m5

.PHONY: windows-m5
windows-m5:
	$(PYTHON) scripts/windows_bundle.py

.PHONY: m6-test m6-synth m6-paths m6-mapped-test verify-m6 package-m6
m6-test: rtl fp-bootstrap
	$(PYTHON) tests/test_fp_vector.py --multiply
	$(PYTHON) tests/test_integer_multiply.py
	$(PYTHON) tests/test_integer_multiply_latency.py
	$(PYTHON) tests/test_ram_vector.py --multiply
	$(PYTHON) tests/test_ram_vector.py --fp --multiply
	$(PYTHON) tests/test_fp_vector.py
m6-synth: rtl
	$(PYTHON) scripts/synth.py IntegerMultiply RamVectorFp
m6-paths: m6-synth
	$(PYTHON) scripts/path_depth.py IntegerMultiply RamVectorFp
	$(PYTHON) scripts/check_write_cone.py
m6-mapped-test: m6-test m6-synth
	$(PYTHON) tests/test_integer_multiply.py --mapped
	$(PYTHON) tests/test_ram_vector.py --mapped-only --fp --multiply
verify-m6: m6-test m6-paths m6-mapped-test
	$(PYTHON) scripts/report_m6.py
package-m6:
	$(PYTHON) scripts/package.py --milestone m6

.PHONY: m7-test m7-synth m7-paths m7-mapped-test verify-m7 package-m7
m7-test: rtl fp-bootstrap
	$(PYTHON) tests/test_integer_divide.py
	$(PYTHON) tests/test_integer_divide_latency.py
	$(PYTHON) tests/test_ram_vector.py --fp --divide --multiply
	$(PYTHON) tests/test_ram_vector.py --divide --multiply
	$(PYTHON) tests/test_ram_vector.py --fp --divide --divide-smoke
	$(PYTHON) tests/test_fp_vector.py --multiply --divide
m7-synth: rtl
	$(PYTHON) scripts/synth.py IntegerDivide RamVectorFp
m7-paths: m7-synth
	$(PYTHON) scripts/path_depth.py IntegerDivide RamVectorFp
	$(PYTHON) scripts/check_write_cone.py
m7-mapped-test: m7-test m7-synth
	$(PYTHON) tests/test_integer_divide.py --mapped
	$(PYTHON) tests/test_ram_vector.py --mapped-only --fp --divide --divide-smoke
verify-m7: m7-test m7-paths m7-mapped-test
	$(PYTHON) scripts/report_m7.py
package-m7:
	$(PYTHON) scripts/package.py --milestone m7

.PHONY: m8-test m8-synth m8-paths m8-mapped-test performance verify-m8 package-m8
m8-test: rtl fp-bootstrap
	$(PYTHON) tests/test_ram_vector.py --fp --divide --multiply
	$(PYTHON) tests/test_ram_vector.py --divide --multiply
	$(PYTHON) tests/test_ram_vector.py --fp --divide --divide-smoke
	$(PYTHON) tests/test_fp_vector.py --multiply --divide
	$(PYTHON) tests/test_streaming.py
m8-synth: rtl
	$(PYTHON) scripts/synth.py RamVectorFp
m8-paths: m8-synth
	$(PYTHON) scripts/path_depth.py RamVectorFp
	$(PYTHON) scripts/check_write_cone.py
m8-mapped-test: m8-test m8-synth
	$(PYTHON) tests/test_streaming.py --mapped
	$(PYTHON) tests/test_ram_vector.py --mapped-only --fp --divide --divide-smoke
performance: rtl
	$(PYTHON) tests/performance.py
	$(PYTHON) scripts/performance_report.py
verify-m8: m8-test m8-paths m8-mapped-test performance
	$(PYTHON) scripts/report_m8.py
package-m8:
	$(PYTHON) scripts/package.py --milestone m8

.PHONY: m9-test m9-synth m9-paths m9-mapped-test verify-m9 package-m9
m9-test: rtl fp-bootstrap
	$(PYTHON) tests/test_fp_convert.py
	$(PYTHON) tests/test_fp_convert.py --lane
	$(PYTHON) tests/test_fp_lane.py
	$(PYTHON) tests/test_fp_vector.py --convert --multiply --divide
	$(PYTHON) tests/test_ram_vector.py --fp --divide --multiply
	$(PYTHON) tests/test_streaming.py
	$(PYTHON) tests/test_tilelink.py
	$(PYTHON) tests/test_tilelink.py --wrapper
m9-synth: rtl
	$(PYTHON) scripts/synth.py FloatingPointConvert TileLinkReservation RamVectorFp
m9-paths: m9-synth
	$(PYTHON) scripts/path_depth.py FloatingPointConvert TileLinkReservation RamVectorFp
	$(PYTHON) scripts/check_write_cone.py
m9-mapped-test: m9-test m9-synth
	$(PYTHON) tests/test_fp_convert.py --mapped
	$(PYTHON) tests/test_tilelink.py --mapped
verify-m9: m9-test m9-paths m9-mapped-test
	$(PYTHON) scripts/report_m9.py
package-m9:
	$(PYTHON) scripts/package.py --milestone m9

.PHONY: m10-test m10-synth m10-paths m10-mapped-test verify-m10 package-m10
m10-test: rtl
	$(PYTHON) tests/test_vector_memory.py
	$(PYTHON) tests/test_vector_memory.py --smoke
m10-synth: rtl
	$(PYTHON) scripts/synth.py VectorMemoryEngine LishiVpuMemory
m10-paths: m10-synth
	$(PYTHON) scripts/path_depth.py VectorMemoryEngine LishiVpuMemory
m10-mapped-test: m10-test m10-synth
	$(PYTHON) tests/test_vector_memory.py --smoke --mapped
verify-m10: m10-test m10-paths m10-mapped-test
	$(PYTHON) scripts/memory_performance.py
	$(PYTHON) scripts/report_m10.py
package-m10:
	$(PYTHON) scripts/package.py --milestone m10

.PHONY: m11-test m11-synth m11-paths m11-mapped-test verify-m11 package-m11
m11-test: rtl
	$(PYTHON) tests/test_vector_memory.py
	$(PYTHON) tests/test_vector_memory.py --smoke
m11-synth: rtl
	$(PYTHON) scripts/synth.py VectorMemoryEngine LishiVpuMemory
m11-paths: m11-synth
	$(PYTHON) scripts/path_depth.py VectorMemoryEngine LishiVpuMemory
m11-mapped-test: m11-test m11-synth
	$(PYTHON) tests/test_vector_memory.py --smoke --mapped
verify-m11: m11-test m11-paths m11-mapped-test
	$(PYTHON) scripts/memory_performance.py --milestone m11
	$(PYTHON) scripts/report_m11.py
package-m11:
	$(PYTHON) scripts/package.py --milestone m11

.PHONY: m12-test m12-synth m12-paths m12-mapped-test verify-m12 package-m12
m12-test: rtl
	$(PYTHON) tests/test_vector_memory.py
	$(PYTHON) tests/test_vector_memory.py --smoke
m12-synth: rtl
	$(PYTHON) scripts/synth.py VectorMemoryEngine LishiVpuMemory
m12-paths: m12-synth
	$(PYTHON) scripts/path_depth.py VectorMemoryEngine LishiVpuMemory
m12-mapped-test: m12-test m12-synth
	$(PYTHON) tests/test_vector_memory.py --smoke --mapped
verify-m12: m12-test m12-paths m12-mapped-test
	$(PYTHON) scripts/memory_performance.py --milestone m12
	$(PYTHON) scripts/report_m12.py
package-m12:
	$(PYTHON) scripts/package.py --milestone m12

.PHONY: m13-test m13-synth m13-paths m13-mapped-test m13-budget verify-m13 package-m13
m13-test: rtl fp-bootstrap
	$(PYTHON) tests/test_fp_lane.py
	$(PYTHON) tests/test_fp_lane.py --smoke
	$(PYTHON) tests/test_fp_convert.py --lane
	$(PYTHON) tests/test_fp_vector.py --convert --multiply --divide
	$(PYTHON) tests/test_vector_memory.py
	$(PYTHON) tests/test_vector_memory.py --smoke
m13-synth: rtl
	$(PYTHON) scripts/synth.py FloatingPointLane LishiVpuMemory
m13-paths: m13-synth
	$(PYTHON) scripts/path_depth.py FloatingPointLane LishiVpuMemory
m13-mapped-test: m13-test m13-synth
	$(PYTHON) tests/test_fp_lane.py --smoke --mapped
	$(PYTHON) tests/test_vector_memory.py --smoke --mapped
m13-budget: m13-paths rapidwright-probe
	$(PYTHON) tests/test_cloud_budget.py
	$(PYTHON) scripts/cloud_budget.py --netlist archive/m12/synth-LishiVpuMemory/mapped.json --output build/timing-budget/m12
	$(PYTHON) scripts/cloud_budget.py --netlist build/synth/LishiVpuMemory/mapped.json --output build/timing-budget/m13
verify-m13: m13-test m13-paths m13-mapped-test m13-budget
	$(PYTHON) scripts/memory_performance.py --milestone m13
	$(PYTHON) scripts/report_m13.py
package-m13:
	$(PYTHON) scripts/package.py --milestone m13

.PHONY: m14-test m14-proof m14-synth m14-paths m14-mapped-test m14-budget verify-m14 package-m14
m14-test: rtl fp-bootstrap
	$(PYTHON) tests/test_integer_multiply.py
	$(PYTHON) tests/test_integer_multiply_latency.py
	$(PYTHON) tests/test_fp_convert.py
	$(PYTHON) tests/test_fp_convert.py --lane
	$(PYTHON) tests/test_fp_lane.py
	$(PYTHON) tests/test_fp_lane.py --smoke
	$(PYTHON) tests/test_fp_vector.py --convert --multiply --divide
	$(PYTHON) tests/test_ram_vector.py --fp --multiply --divide
	$(PYTHON) tests/test_vector_memory.py
	$(PYTHON) tests/test_vector_memory.py --smoke
m14-proof: rtl
	$(PYTHON) scripts/prove_recode.py
m14-synth: rtl
	$(PYTHON) scripts/synth.py IntegerMultiply FloatingPointConvert FloatingPointLane LishiVpuMemory
m14-paths: m14-synth
	$(PYTHON) scripts/path_depth.py IntegerMultiply FloatingPointConvert FloatingPointLane LishiVpuMemory
m14-mapped-test: m14-test m14-synth
	$(PYTHON) tests/test_integer_multiply.py --mapped
	$(PYTHON) tests/test_fp_convert.py --mapped
	$(PYTHON) tests/test_fp_lane.py --smoke --mapped
	$(PYTHON) tests/test_vector_memory.py --smoke --mapped
m14-budget: m14-paths rapidwright-probe
	$(PYTHON) tests/test_cloud_budget.py
	$(PYTHON) scripts/cloud_budget.py --netlist archive/m13/synth-LishiVpuMemory/mapped.json --output build/timing-budget/m13-baseline
	$(PYTHON) scripts/cloud_budget.py --netlist build/synth/LishiVpuMemory/mapped.json --output build/timing-budget/m14
verify-m14: m14-test m14-proof m14-paths m14-mapped-test m14-budget
	$(PYTHON) scripts/memory_performance.py --milestone m14
	$(PYTHON) scripts/report_m14.py
package-m14:
	$(PYTHON) scripts/package.py --milestone m14

.PHONY: m15-test m15-proof m15-synth m15-paths m15-mapped-test m15-budget verify-m15 package-m15
m15-test: rtl fp-bootstrap
	$(PYTHON) tests/test_integer_divide.py
	$(PYTHON) tests/test_integer_multiply.py
	$(PYTHON) tests/test_integer_multiply_latency.py
	$(PYTHON) tests/test_fp_convert.py
	$(PYTHON) tests/test_fp_convert.py --lane
	$(PYTHON) tests/test_fp_lane.py
	$(PYTHON) tests/test_fp_lane.py --smoke
	$(PYTHON) tests/test_fp_vector.py --convert --multiply --divide
	$(PYTHON) tests/test_ram_vector.py --fp --multiply --divide
	$(PYTHON) tests/test_vector_memory.py
	$(PYTHON) tests/test_vector_memory.py --smoke
m15-proof: rtl
	$(PYTHON) scripts/prove_divider_word.py
	$(PYTHON) scripts/prove_recode.py
m15-synth: rtl
	$(PYTHON) scripts/synth.py IntegerDivide IntegerMultiply FloatingPointConvert FloatingPointLane LishiVpuMemory
m15-paths: m15-synth
	$(PYTHON) scripts/path_depth.py IntegerDivide IntegerMultiply FloatingPointConvert FloatingPointLane LishiVpuMemory
m15-mapped-test: m15-test m15-synth
	$(PYTHON) tests/test_integer_divide.py --mapped
	$(PYTHON) tests/test_integer_multiply.py --mapped
	$(PYTHON) tests/test_fp_convert.py --mapped
	$(PYTHON) tests/test_fp_lane.py --smoke --mapped
	$(PYTHON) tests/test_vector_memory.py --smoke --mapped
m15-budget: m15-paths rapidwright-probe
	$(PYTHON) tests/test_cloud_budget.py
	$(PYTHON) scripts/cloud_budget.py --netlist archive/m14/synth-LishiVpuMemory/mapped.json --output build/timing-budget/m14-baseline
	$(PYTHON) scripts/cloud_budget.py --netlist build/synth/LishiVpuMemory/mapped.json --output build/timing-budget/m15
verify-m15: m15-test m15-proof m15-paths m15-mapped-test m15-budget
	$(PYTHON) scripts/memory_performance.py --milestone m15
	$(PYTHON) scripts/report_m15.py
package-m15:
	$(PYTHON) scripts/package.py --milestone m15

.PHONY: m16-test m16-proof m16-synth m16-paths m16-mapped-test m16-budget verify-m16 package-m16
m16-test: rtl fp-bootstrap
	$(PYTHON) tests/test_ram_vector.py
	$(PYTHON) tests/test_integer_divide.py
	$(PYTHON) tests/test_integer_multiply.py
	$(PYTHON) tests/test_integer_multiply_latency.py
	$(PYTHON) tests/test_fp_convert.py
	$(PYTHON) tests/test_fp_convert.py --lane
	$(PYTHON) tests/test_fp_lane.py
	$(PYTHON) tests/test_fp_lane.py --smoke
	$(PYTHON) tests/test_fp_vector.py --convert --multiply --divide
	$(PYTHON) tests/test_ram_vector.py --fp --multiply --divide
	$(PYTHON) tests/test_vector_memory.py
	$(PYTHON) tests/test_vector_memory.py --smoke
m16-proof: rtl
	$(PYTHON) scripts/prove_increment.py
	$(PYTHON) scripts/prove_divider_word.py
	$(PYTHON) scripts/prove_recode.py
m16-synth: rtl
	$(PYTHON) scripts/synth.py VectorMemoryEngine IntegerDivide IntegerMultiply FloatingPointConvert FloatingPointLane LishiVpuMemory
m16-paths: m16-synth
	$(PYTHON) scripts/path_depth.py VectorMemoryEngine IntegerDivide IntegerMultiply FloatingPointConvert FloatingPointLane LishiVpuMemory
m16-mapped-test: m16-test m16-synth
	$(PYTHON) tests/test_integer_divide.py --mapped
	$(PYTHON) tests/test_integer_multiply.py --mapped
	$(PYTHON) tests/test_fp_convert.py --mapped
	$(PYTHON) tests/test_fp_lane.py --smoke --mapped
	$(PYTHON) tests/test_vector_memory.py --smoke --mapped
m16-budget: m16-paths rapidwright-probe
	$(PYTHON) tests/test_cloud_budget.py
	$(PYTHON) scripts/cloud_budget.py --netlist archive/m15/synth-LishiVpuMemory/mapped.json --output build/timing-budget/m15-baseline
	$(PYTHON) scripts/cloud_budget.py --netlist build/synth/LishiVpuMemory/mapped.json --output build/timing-budget/m16
verify-m16: m16-test m16-proof m16-paths m16-mapped-test m16-budget
	$(PYTHON) scripts/memory_performance.py --milestone m16
	$(PYTHON) scripts/report_m16.py
package-m16:
	$(PYTHON) scripts/package.py --milestone m16

.PHONY: verify-m28 package-m28
verify-m28:
	$(PYTHON) scripts/verify_m28.py
package-m28:
	$(PYTHON) scripts/package.py --milestone m28

.PHONY: verify-m29 package-m29
verify-m29:
	$(PYTHON) scripts/verify_m29.py
package-m29:
	$(PYTHON) scripts/package.py --milestone m29

.PHONY: verify-m30 package-m30
verify-m30:
	$(PYTHON) scripts/verify_m30.py
package-m30:
	$(PYTHON) scripts/package.py --milestone m30

.PHONY: verify-m31 package-m31 windows-m31
verify-m31:
	$(PYTHON) scripts/verify_m31.py
package-m31:
	$(PYTHON) scripts/package.py --milestone m31
windows-m31:
	$(PYTHON) scripts/windows_current_bundle.py

.PHONY: verify-m32 package-m32
verify-m32:
	$(PYTHON) scripts/verify_m32.py
package-m32:
	$(PYTHON) scripts/package.py --milestone m32

.PHONY: verify-m33 package-m33
verify-m33:
	$(PYTHON) scripts/verify_m33.py
package-m33:
	$(PYTHON) scripts/package.py --milestone m33

.PHONY: verify-m34 package-m34
verify-m34:
	$(PYTHON) scripts/verify_m34.py
package-m34:
	$(PYTHON) scripts/package.py --milestone m34

.PHONY: verify-m35 package-m35
verify-m35:
	$(PYTHON) scripts/verify_m35.py
package-m35:
	$(PYTHON) scripts/package.py --milestone m35

.PHONY: verify-m36 package-m36
verify-m36:
	$(PYTHON) scripts/verify_m36.py
package-m36:
	$(PYTHON) scripts/package.py --milestone m36
