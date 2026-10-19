# M53 Windows timing handoff

Download [spinor-m53-timing-fix1.zip](spinor-m53-timing-fix1.zip), extract the whole archive,
and open PowerShell in the folder containing `run.ps1`. Set the installed Vivado
path in this command:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\run.ps1 -VivadoBat "D:\Xilinx\Vivado\2025.1\bin\vivado.bat"
```

If your original run failed with `invalid command name "redirect"`, **use
`resume.ps1` instead of starting over**:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\resume.ps1 -PreviousRun "D:\surplars\Downloads\spinor-m53-timing\runs\M53_Timing_20261019_144108_769"
```

It reads the installed Vivado path from the old run, validates the recorded RTL,
checkpoint part/public ports and saved clock, then regenerates reports and DSP
exports in a new directory. It never repeats synth/placement/routing, changes the
clock constraint, or rewrites the original checkpoint. `-VivadoBat` can override
the installed path. The [received local report](../reports/local-m53/evaluation.md)
already shows positive setup/hold slack; the failure was in the report wrapper.
The original ZIP is retained only for provenance and reproducing the diagnosed
failure. New users should use fix1.

The default target is **xczu15eg-ffvb1156-2-i, 3.333333ns (300MHz)**, standard FP
SpinorVpu. If the complete ordering code differs, pass `-Part` with the correct
ZU15EG -2 part. Vivado must include the Zynq UltraScale+ device support and license.
The RTL is pre-generated: Windows does not need Mill, Java, Chisel or the cloud tools.

The flow starts fresh: synth, opt, place, phys_opt, route, reports, checkpoints,
then DSP delay export. It never resumes an old checkpoint. Read the setup **and**
hold slack, route status, DRC and timing coverage. This is standalone OOC with
external IO delays and board clock location unspecified; it is not SoC timing
signoff, bitstream generation or post-route SDF simulation.

Upload the printed **report ZIP** even if timing is negative or implementation
fails. It contains timing/coverage/utilization/log/provenance files. Keep the
entire local `runs` directory: DCP, EDIF and DSP arc tables remain there and can
be packed with `pack_results.ps1 -RunDirectory ... -Full` later without rerunning.
DSP-export-only errors are recorded separately and do not hide completed STA.

The package pins the M53 source/RTL evidence and verifies input SHA256 before
starting. The new runner has passed Linux PowerShell 7 + Tcl mock tests for normal
completion, negative hold slack, missing timing paths, optional DSP failure,
partial-error report packing, repeat/full packing, invalid destinations and
modified-input rejection. Fix1 adds report-only resume tests, checkpoint part/
public-port mismatch rejection and strict rejection of unmodelled Tcl commands,
including the original `redirect` bug. The subsequently received
[actual Windows/Vivado resume](../reports/local-m53-resume/evaluation.md) completed
successfully with unchanged setup/hold timing and all 7 DSP exports locally
nonempty. The subsequently received [raw DSP tables](../reports/dsp-m53/evaluation.md)
have been audited and normalized into a reference database. They describe the
observed Vivado pipeline configurations; they are incompatible with the current
Yosys DSP register configuration and do not replace its full timing budget.

Cloud rebuild (requires established M53 artifacts):

```bash
python3 scripts/package_windows_timing.py
python3 tests/test_windows_timing_bundle.py
python3 scripts/verify_m53.py --check-only
```

The existing frozen M31 scripts and M50/M51/M52/M53 evidence are unchanged.
