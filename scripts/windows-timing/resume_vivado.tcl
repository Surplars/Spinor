# Report/export only: preserve the original routed implementation and clock.
set ::spinor_timing_library_only 1
source [file join [file dirname [file normalize [info script]]] run_vivado.tcl]
proc resume_main {} {
    global argv result_dir
    if {[llength $argv]!=5} {error "Use resume.ps1: checkpoint output_directory threads part export_dsp"}
    lassign $argv checkpoint result_dir threads part export
    set result_dir [file normalize $result_dir];file mkdir $result_dir
    if {![file isfile $checkpoint]} {error "Missing routed checkpoint"}
    if {![string is integer -strict $threads] || $threads<1 || $threads>32} {error "Invalid threads"}
    if {![regexp {^xczu15eg-[a-z0-9]+-2-[a-z]$} $part] || $export ni {0 1}} {error "Invalid part/export flag"}
    write_text [file join $result_dir tool-version.txt] [version]
    set_param general.maxThreads $threads
    open_checkpoint $checkpoint
    if {![string equal -nocase [get_property PART [current_design]] $part]} {error "Checkpoint part mismatch"}
    foreach port {clock io_core_command_valid io_core_context_valid io_monitor_a_valid io_tl_d_valid} {
        if {[llength [get_ports -quiet $port]]!=1} {error "Checkpoint missing Spinor public port: $port"}
    }
    set clock [get_clocks -quiet vpu_clk]
    if {[llength $clock]!=1} {error "Checkpoint clock missing"}
    set period [get_property PERIOD $clock]
    if {![string is double -strict $period] || $period<0.5 || $period>100} {error "Invalid checkpoint period"}
    write_text [file join $result_dir checkpoint-loaded.txt] "design=[current_design]\ncheckpoint=$checkpoint\nperiod_ns=$period\nimplementation_repeated=NO"
    finish_reports $period $part $export
}
if {[catch {resume_main} message options]} {
    puts stderr "FLOW FAILED: $message"
    if {$::result_dir ne "" && [file isdirectory $::result_dir]} {
        catch {write_text [file join $::result_dir flow-error.txt] "$message\n[dict get $options -errorinfo]"}
    }
    exit 1
}
exit 0
