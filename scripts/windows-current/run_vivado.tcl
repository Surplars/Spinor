# M31 fresh RTL simulation and standalone OOC implementation.
set ::bundle_root [file dirname [file normalize [info script]]]
set ::result_dir ""
proc write_text {path value} {
    set f [open $path w];puts $f $value;close $f
}
proc simulate_case {name top rtl tb pass_marker part} {
    global bundle_root result_dir
    set dir [file join $result_dir simulation $name]
    file mkdir $dir
    set project_name spinor_$name
    create_project -force $project_name [file join $dir project] -part $part
    add_files -norecurse [file join $bundle_root rtl $rtl]
    add_files -fileset sim_1 -norecurse [file join $bundle_root tb $tb]
    set_property top tb [get_filesets sim_1]
    set_property verilog_define [list TOP=$top] [get_filesets sim_1]
    set_property xsim.simulate.runtime 0ns [get_filesets sim_1]
    update_compile_order -fileset sources_1
    update_compile_order -fileset sim_1
    launch_simulation -simset sim_1 -mode behavioral
    # Focused port waves; do not log the whole datapath or every RAM word.
    log_wave /tb/clock /tb/reset /tb/cycles
    log_wave /tb/dut/*
    run all
    close_sim
    set log_dir [file join $dir project ${project_name}.sim sim_1 behav xsim]
    set success 0
    set combined ""
    foreach p [glob -nocomplain -directory $log_dir *.log] {
        set f [open $p r];set value [read $f];close $f
        append combined "\n=== [file tail $p] ===\n$value"
        if {[string first $pass_marker $value]>=0} {set success 1}
        if {[regexp -nocase {Fatal:|FATAL:|\$fatal|ERROR:} $value]} {
            error "XSim reported an error in $name: $p"
        }
    }
    write_text [file join $dir simulation-logs.txt] $combined
    if {!$success} {error "XSim $name did not produce its self-check PASS marker; inspect nested simulation logs"}
    write_text [file join $dir result.txt] "PASS $name: $pass_marker"
    close_project
}
proc implement {period threads part} {
    global bundle_root result_dir
    create_project -in_memory -part $part
    set_param general.maxThreads $threads
    read_verilog -sv [file join $bundle_root rtl SpinorVpu.sv]
    set xdc [file join $result_dir clock.xdc]
    write_text $xdc [format {create_clock -name vpu_clk -period %.6f [get_ports clock]} $period]
    read_xdc $xdc
    synth_design -top SpinorVpu -part $part -mode out_of_context
    if {[llength [get_ports -quiet clock]]!=1 || [llength [get_clocks -quiet vpu_clk]]!=1} {error "Clock constraint missing"}
    report_utilization -file [file join $result_dir utilization_synth.rpt]
    write_checkpoint -force [file join $result_dir synth.dcp]
    opt_design
    place_design
    write_checkpoint -force [file join $result_dir placed.dcp]
    report_timing_summary -delay_type min_max -report_unconstrained -max_paths 20 -file [file join $result_dir timing_placed.rpt]
    phys_opt_design
    route_design
    write_checkpoint -force [file join $result_dir routed.dcp]
    write_edif -force [file join $result_dir routed.edf]
    write_xdc -force [file join $result_dir constraints.xdc]
    report_route_status -file [file join $result_dir route_status.rpt]
    report_utilization -file [file join $result_dir utilization_routed.rpt]
    report_utilization -hierarchical -file [file join $result_dir utilization_hierarchical.rpt]
    report_clocks -file [file join $result_dir clocks.rpt]
    report_timing_summary -delay_type min_max -report_unconstrained -max_paths 20 -file [file join $result_dir timing_routed.rpt]
    report_timing -delay_type max -max_paths 30 -path_type full_clock_expanded -file [file join $result_dir setup_paths.rpt]
    report_timing -delay_type min -max_paths 30 -path_type full_clock_expanded -file [file join $result_dir hold_paths.rpt]
    check_timing -verbose
    set setup [get_timing_paths -quiet -delay_type max -max_paths 1]
    set hold [get_timing_paths -quiet -delay_type min -max_paths 1]
    if {[llength $setup]==0 || [llength $hold]==0} {error "Missing setup or hold timing paths"}
    set dsps [get_cells -hier -filter {REF_NAME == DSP48E2}]
    set summary [list "top=SpinorVpu" "milestone=M31" "part=$part" "period_ns=$period" \
        "setup_slack_ns=[get_property SLACK $setup]" "hold_slack_ns=[get_property SLACK $hold]" \
        "DSP48E2_count=[llength $dsps]" "DSP_export_status=NOT_STARTED" \
        "scope=Standalone OOC; IO delays and HD.CLK_SRC unspecified; inspect coverage and route status" \
        "post_route_SDF_simulation=NOT_RUN" "RTL_functional_simulation=See simulation/*/result.txt if Mode All"]
    write_text [file join $result_dir run-summary.txt] [join $summary "\n"]
    # Retain configuration and arc delays bound to this fresh DCP and EDIF.
    set f [open [file join $result_dir dsp-configurations.txt] w]
    foreach dsp $dsps {
        puts $f "DSP $dsp"
        foreach prop {AREG BREG MREG PREG ACASCREG BCASCREG ADREG CREG DREG ALUMODEREG CARRYINREG CARRYINSELREG INMODEREG OPMODEREG USE_MULT USE_SIMD} {
            puts $f "$prop=[get_property $prop $dsp]"
        }
    }
    close $f
    if {[llength $dsps]==0} {error "No DSP48E2 remains; inspect inference before using DSP reference data"}
    set dsp_dir [file join $result_dir dsp_delay];file mkdir $dsp_dir
    # Upstream requires its property_list in global scope.
    uplevel #0 [list source [file join $bundle_root dump_all_dsp_delay.tcl]]
    set old [pwd];cd $dsp_dir
    set failed [catch {dump_all_dsp_delay} message options];cd $old
    if {$failed} {return -options $options $message}
    set coverage ""
    foreach dsp $dsps {
        set p [file join $dsp_dir "[string map {/ -} $dsp].txt"]
        set rows 0
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
    set i [lsearch -exact $summary DSP_export_status=NOT_STARTED]
    set summary [lreplace $summary $i $i DSP_export_status=NONEMPTY_FILES_ARC_COMPLETENESS_UNVERIFIED]
    write_text [file join $result_dir run-summary.txt] [join $summary "\n"]
}
proc main {} {
    global argv bundle_root result_dir
    if {[llength $argv]!=4} {error "Use run.ps1: mode period_ns output_directory threads"}
    lassign $argv mode period result_dir threads
    if {$mode ni {All Rtl Implement}} {error "Invalid mode"}
    if {![string is double -strict $period] || $period<0.5 || $period>100} {error "Invalid period"}
    if {![string is integer -strict $threads] || $threads<1 || $threads>32} {error "Invalid threads"}
    set result_dir [file normalize $result_dir];file mkdir $result_dir
    set part xczu15eg-ffvb1156-2-i
    write_text [file join $result_dir tool-version.txt] [version]
    if {[llength [get_parts -quiet $part]]!=1} {error "Install Zynq UltraScale+ device support for $part"}
    if {$mode in {All Rtl}} {
        simulate_case extensions RamVectorFp RamVectorFp.sv integer-extensions.sv {PASS integer-extensions commands=} $part
        simulate_case integration SpinorVpu SpinorVpu.sv spinor-integration.sv {PASS vector-memory} $part
        # Integration also has an independent concurrent monitor oracle.
        set f [open [file join $result_dir simulation integration simulation-logs.txt] r];set logs [read $f];close $f
        if {[string first {PASS monitored-mmio} $logs]<0} {error "Monitor self-check did not finish"}
    }
    if {$mode in {All Implement}} {implement $period $threads $part} else {
        write_text [file join $result_dir run-summary.txt] "RTL_self_checks=PASS\nimplementation=NOT_RUN\npost_route_SDF_simulation=NOT_RUN\npasses_300MHz=UNKNOWN"
    }
    puts "DONE: M31 $mode; inspect $result_dir"
}
if {[catch {main} message options]} {
    puts stderr "FLOW FAILED: $message"
    if {$::result_dir ne "" && [file isdirectory $::result_dir]} {
        catch {write_text [file join $::result_dir flow-error.txt] "$message\n\n[dict get $options -errorinfo]"}
    }
    exit 1
}
exit 0
