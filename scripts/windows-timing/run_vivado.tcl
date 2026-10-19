# M53 current RTL, fresh standalone OOC implementation. Never opens old DCPs.
set ::bundle_root [file dirname [file normalize [info script]]]
set ::result_dir ""
proc write_text {path value} {set f [open $path w];puts $f $value;close $f}
proc export_dsp {} {
    global bundle_root result_dir
    set dsps [get_cells -hier -filter {REF_NAME == DSP48E2}]
    set f [open [file join $result_dir dsp-configurations.txt] w]
    foreach dsp $dsps {
        puts $f "DSP $dsp"
        foreach prop {AREG BREG MREG PREG ACASCREG BCASCREG ADREG CREG DREG ALUMODEREG CARRYINREG CARRYINSELREG INMODEREG OPMODEREG USE_MULT USE_SIMD} {
            puts $f "$prop=[get_property $prop $dsp]"
        }
    }
    close $f
    if {[llength $dsps]==0} {error "No DSP48E2 inferred; inspect utilization"}
    # Upstream exporter needs property_list in global scope.
    uplevel #0 [list source [file join $bundle_root dump_all_dsp_delay.tcl]]
    set dir [file join $result_dir dsp_delay];file mkdir $dir
    set old [pwd];cd $dir
    set failed [catch {dump_all_dsp_delay} message options];cd $old
    if {$failed} {return -options $options $message}
    set coverage ""
    foreach dsp $dsps {
        set p [file join $dir "[string map {/ -} $dsp].txt"];set rows 0
        if {[file isfile $p]} {
            set f [open $p r]
            while {[gets $f line]>=0} {
                set line [string trim $line]
                if {$line ne "" && ![string match "#*" $line]} {incr rows}
            }
            close $f
        }
        append coverage "[file tail $p] timing_rows=$rows\n"
        write_text [file join $result_dir dsp-export-coverage.txt] $coverage
        if {$rows==0} {error "Empty/missing DSP delay export: $p"}
    }
}
proc main {} {
    global argv bundle_root result_dir
    if {[llength $argv]!=5} {error "Use run.ps1: period_ns output_directory threads part export_dsp"}
    lassign $argv period result_dir threads part export
    if {![string is double -strict $period] || $period<0.5 || $period>100} {error "Invalid period"}
    if {![string is integer -strict $threads] || $threads<1 || $threads>32} {error "Invalid threads"}
    if {![regexp {^xczu15eg-[a-z0-9]+-2-[a-z]$} $part]} {error "Expected complete ZU15EG -2 part"}
    if {$export ni {0 1}} {error "Invalid DSP export flag"}
    set result_dir [file normalize $result_dir];file mkdir $result_dir
    write_text [file join $result_dir tool-version.txt] [version]
    if {[llength [get_parts -quiet $part]]!=1} {error "Install Zynq UltraScale+ device support for $part"}
    create_project -in_memory -part $part
    set_param general.maxThreads $threads
    read_verilog -sv [file join $bundle_root rtl SpinorVpu.sv]
    set xdc [file join $result_dir clock.xdc]
    write_text $xdc [format {create_clock -name vpu_clk -period %.6f [get_ports clock]} $period]
    read_xdc $xdc
    synth_design -top SpinorVpu -part $part -mode out_of_context
    if {[llength [get_ports -quiet clock]]!=1 || [llength [get_clocks -quiet vpu_clk]]!=1} {error "Missing clock constraint"}
    report_utilization -file [file join $result_dir utilization_synth.rpt]
    write_checkpoint -force [file join $result_dir synth.dcp]
    opt_design
    place_design
    write_checkpoint -force [file join $result_dir placed.dcp]
    report_timing_summary -delay_type min_max -report_unconstrained -max_paths 20 -file [file join $result_dir timing_placed.rpt]
    phys_opt_design
    route_design
    # Preserve physical evidence before optional DSP extraction.
    write_checkpoint -force [file join $result_dir routed.dcp]
    finish_reports $period $part $export
}
proc finish_reports {period part export} {
    global result_dir
    write_edif -force [file join $result_dir routed.edf]
    write_xdc -force [file join $result_dir constraints.xdc]
    report_route_status -file [file join $result_dir route_status.rpt]
    report_utilization -file [file join $result_dir utilization_routed.rpt]
    report_utilization -hierarchical -file [file join $result_dir utilization_hierarchical.rpt]
    report_clocks -file [file join $result_dir clocks.rpt]
    report_drc -file [file join $result_dir drc.rpt]
    report_timing_summary -delay_type min_max -report_unconstrained -max_paths 30 -file [file join $result_dir timing_routed.rpt]
    report_timing -delay_type max -max_paths 50 -path_type full_clock_expanded -file [file join $result_dir setup_paths.rpt]
    report_timing -delay_type min -max_paths 30 -path_type full_clock_expanded -file [file join $result_dir hold_paths.rpt]
    # Vivado does not implement the Synopsys-style `redirect` command.
    # Log the native command and retain the check section already emitted by
    # report_timing_summary, without guessing unsupported output flags.
    check_timing -verbose
    set f [open [file join $result_dir timing_routed.rpt] r];set body [read $f];close $f
    set begin [string first "check_timing report" $body]
    set end [string first "| Design Timing Summary" $body [expr {max(0,$begin)}]]
    if {$begin>=0 && $end>$begin} {
        write_text [file join $result_dir check_timing.rpt] [string range $body $begin [expr {$end-1}]]
    } else {
        write_text [file join $result_dir check_timing.rpt] "See check_timing output in vivado.log and timing_routed.rpt."
    }
    set setup [get_timing_paths -quiet -delay_type max -max_paths 1]
    set hold [get_timing_paths -quiet -delay_type min -max_paths 1]
    if {[llength $setup]==0 || [llength $hold]==0} {error "Missing setup or hold paths"}
    set wns [get_property SLACK $setup];set whs [get_property SLACK $hold]
    set summary [list "milestone=M53" "top=SpinorVpu" "part=$part" "period_ns=$period" \
        "setup_slack_ns=$wns" "hold_slack_ns=$whs" "standalone_setup_hold_nonnegative=[expr {$wns>=0 && $whs>=0}]" \
        "scope=Standalone OOC; inspect unconstrained IO, check_timing, DRC and routing coverage" \
        "board_clock_location=UNSPECIFIED" "SoC_timing_signoff=NOT_EVALUATED" \
        "post_route_SDF_simulation=NOT_RUN" "DSP_export_status=SKIPPED"]
    write_text [file join $result_dir run-summary.txt] [join $summary "\n"]
    if {$export} {
        # DSP extraction must not invalidate or hide completed STA reports.
        if {[catch {export_dsp} message options]} {
            write_text [file join $result_dir dsp-export-error.txt] "$message\n[dict get $options -errorinfo]"
            set dsp_status "ERROR_SEE_dsp-export-error.txt"
            puts "WARNING: DSP export failed; routed timing reports remain valid: $message"
        } else {set dsp_status "NONEMPTY_FILES_ARC_COMPLETENESS_UNVERIFIED"}
        set summary [lreplace $summary end end "DSP_export_status=$dsp_status"]
        write_text [file join $result_dir run-summary.txt] [join $summary "\n"]
    }
    puts "DONE: M53 routed reports; inspect $result_dir"
}
if {![info exists ::spinor_timing_library_only]} {
    if {[catch {main} message options]} {
        puts stderr "FLOW FAILED: $message"
        if {$::result_dir ne "" && [file isdirectory $::result_dir]} {
            catch {write_text [file join $::result_dir flow-error.txt] "$message\n[dict get $options -errorinfo]"}
        }
        exit 1
    }
    exit 0
}
