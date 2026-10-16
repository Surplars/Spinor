# Standalone M4 evaluation. No board pinout, CPU integration or bitstream.
set ::bundle_root [file dirname [file normalize [info script]]]
set ::result_dir ""

proc write_text {path text} {
    set handle [open $path w]
    puts $handle $text
    close $handle
}

proc main {} {
    global argv bundle_root result_dir
    if {[llength $argv] != 4} {
        error "Expected arguments: period_ns output_directory thread_count checkpoint_or_dash; use run.ps1"
    }
    lassign $argv period result_dir threads checkpoint
    if {![string is double -strict $period] || $period <= 0} {error "Invalid clock period"}
    if {![string is integer -strict $threads] || $threads < 1} {error "Invalid thread count"}
    set result_dir [file normalize $result_dir]
    file mkdir $result_dir
    set part xczu15eg-ffvb1156-2-i
    set top RamVectorFp
    set rtl [file join $bundle_root rtl RamVectorFp.sv]
    if {[llength [get_parts -quiet $part]] != 1} {
        error "Target part $part is unavailable. Install Zynq UltraScale+ device support."
    }
    write_text [file join $result_dir tool-version.txt] [version]
    set_param general.maxThreads $threads

    if {$checkpoint eq "-"} {
        read_verilog -sv $rtl
        set clock_xdc [file join $result_dir clock.xdc]
        write_text $clock_xdc [format {create_clock -name vpu_clk -period %.6f [get_ports clock]} $period]
        read_xdc $clock_xdc
        synth_design -top $top -part $part -mode out_of_context
        if {[llength [get_ports -quiet clock]] != 1} {error "Expected exactly one top-level clock port"}
        if {[llength [get_clocks -quiet vpu_clk]] != 1} {error "Clock constraint was not applied"}
        report_utilization -file [file join $result_dir utilization_synth.rpt]
        write_checkpoint -force [file join $result_dir synth.dcp]
        write_edif -force [file join $result_dir synth.edf]
        opt_design
        place_design
        write_checkpoint -force [file join $result_dir placed.dcp]
        write_edif -force [file join $result_dir placed.edf]
        report_timing_summary -delay_type min_max -report_unconstrained -max_paths 10 \
            -file [file join $result_dir timing_placed.rpt]
        route_design
        set run_mode FULL_OOC_FLOW
    } else {
        if {![file isfile $checkpoint]} {error "Resume checkpoint does not exist: $checkpoint"}
        open_checkpoint $checkpoint
        if {[get_property PART [current_design]] ne $part} {error "Checkpoint target part does not match $part"}
        # After open_checkpoint, NAME identifies the in-memory design/session;
        # it is not a reliable RTL module-name check. PowerShell validates Top
        # in dcp.xml before launch. Check the actual boundary here as well.
        puts "CHECKPOINT_SESSION_NAME: [get_property NAME [current_design]]"
        foreach required_port {clock reset io_flush io_command_valid io_command_ready \
                               io_completion_valid io_completion_ready io_context_valid \
                               io_context_ready io_contextResult_valid io_busy} {
            if {[llength [get_ports -quiet $required_port]] != 1} {
                error "Checkpoint does not expose expected VPU port: $required_port"
            }
        }
        set clk [get_clocks -quiet vpu_clk]
        if {[llength $clk] != 1} {error "Resume checkpoint must have one vpu_clk constraint"}
        if {abs([get_property PERIOD $clk] - $period) > 0.000001} {
            error "Resume period differs from the checkpoint; do not relabel a routed DCP with another frequency"
        }
        # Resume only: preserve the existing clock constraints and routing.
        # No synthesis, optimization, placement or routing is performed here.
        set run_mode RESUME_ROUTED_DCP
    }
    write_xdc -force [file join $result_dir constraints.xdc]
    write_checkpoint -force [file join $result_dir routed.dcp]
    # A DCP's embedded EDIF may be unreadable by RapidWright. Its official
    # write_rw_checkpoint helper exports this sibling .edf in the same way.
    write_edif -force [file join $result_dir routed.edf]
    report_route_status -file [file join $result_dir route_status.rpt]
    report_utilization -file [file join $result_dir utilization_routed.rpt]
    report_utilization -hierarchical -file [file join $result_dir utilization_hierarchical.rpt]
    report_clocks -file [file join $result_dir clocks.rpt]
    report_timing_summary -delay_type min_max -report_unconstrained -max_paths 20 \
        -file [file join $result_dir timing_routed.rpt]
    report_timing -delay_type max -max_paths 20 -path_type full_clock_expanded \
        -file [file join $result_dir setup_paths.rpt]
    report_timing -delay_type min -max_paths 20 -path_type full_clock_expanded \
        -file [file join $result_dir hold_paths.rpt]
    # Vivado does not provide the Synopsys-style redirect command. The full
    # check_timing section is already saved by report_timing_summary above;
    # print its verbose form to vivado.log as well.
    check_timing -verbose
    set clock_source_note "UNSPECIFIED: actual clock delay/skew not fully modeled"
    set source_site [get_property HD.CLK_SRC [get_ports clock]]
    if {$source_site ne ""} {set clock_source_note "HD.CLK_SRC=$source_site; inspect clock assumptions"}

    set setup_path [get_timing_paths -quiet -delay_type max -max_paths 1]
    set hold_path [get_timing_paths -quiet -delay_type min -max_paths 1]
    if {[llength $setup_path] == 0 || [llength $hold_path] == 0} {
        error "No setup or hold timing paths were found; inspect clocks and timing reports"
    }
    set setup_slack [get_property SLACK $setup_path]
    set hold_slack [get_property SLACK $hold_path]
    set dsps [get_cells -hier -filter {REF_NAME == DSP48E2}]
    set summary [list \
        "target=$part" \
        "top=$top" \
        "vivado=[version -short]" \
        "period_ns=$period" \
        "nominal_frequency_MHz=[expr {1000.0 / $period}]" \
        "DSP48E2_count=[llength $dsps]" \
        "worst_timed_setup_slack_ns=$setup_slack" \
        "worst_timed_hold_slack_ns=$hold_slack" \
        "scope=Standalone OOC; host IO delays unspecified; no board or CPU timing claim" \
        "DSP_export_checkpoint=routed.dcp" \
        "run_mode=$run_mode" \
        "clock_source_model=$clock_source_note" \
        "DSP_export_status=NOT_STARTED"]
    write_text [file join $result_dir run-summary.txt] [join $summary "\n"]
    if {[llength $dsps] == 0} {error "No DSP48E2 cells remain in this Vivado implementation"}

    # Preserve the DSP configurations with the corresponding checkpoint.
    set cfg [open [file join $result_dir dsp-configurations.txt] w]
    foreach dsp $dsps {
        puts $cfg "DSP $dsp"
        foreach prop {AREG BREG MREG PREG ACASCREG BCASCREG ADREG CREG DREG \
                      ALUMODEREG CARRYINREG CARRYINSELREG INMODEREG OPMODEREG USE_MULT USE_SIMD} {
            puts $cfg "$prop=[get_property $prop $dsp]"
        }
        puts $cfg ""
    }
    close $cfg

    set dsp_dir [file join $result_dir dsp_delay]
    file mkdir $dsp_dir
    # The upstream script defines property_list and references ::property_list
    # while declaring a default argument. It must be sourced at global scope.
    uplevel #0 [list source [file join $bundle_root dump_all_dsp_delay.tcl]]
    set previous_dir [pwd]
    cd $dsp_dir
    set dump_failed [catch {dump_all_dsp_delay} dump_message dump_options]
    cd $previous_dir
    if {$dump_failed} {return -options $dump_options $dump_message}

    set coverage [open [file join $result_dir dsp-export-coverage.txt] w]
    set invalid 0
    foreach dsp $dsps {
        set filename "[string map {/ -} $dsp].txt"
        set path [file join $dsp_dir $filename]
        set arc_count 0
        if {[file exists $path]} {
            set fh [open $path r]
            while {[gets $fh line] >= 0} {
                set trimmed [string trim $line]
                if {$trimmed ne "" && ![string match "#*" $trimmed]} {incr arc_count}
            }
            close $fh
        }
        puts $coverage "$filename timing_rows=$arc_count"
        if {$arc_count == 0} {incr invalid}
    }
    close $coverage
    if {$invalid > 0} {
        error "$invalid DSP files contain no timing rows; routed DCP and reports were retained"
    }
    set summary [lreplace $summary end end "DSP_export_status=EXPORTED_NONEMPTY_FILES"]
    lappend summary "DSP_file_coverage_note=Nonempty files do not establish complete coverage of every active arc"
    write_text [file join $result_dir run-summary.txt] [join $summary "\n"]
    puts "DONE: checkpoints, timing reports, and DSP export are in $result_dir"
}

if {[catch {main} message options]} {
    puts stderr "FLOW FAILED: $message"
    if {$::result_dir ne "" && [file isdirectory $::result_dir]} {
        catch {write_text [file join $::result_dir flow-error.txt] \
            "$message\n\n[dict get $options -errorinfo]"}
    }
    exit 1
}
exit 0
