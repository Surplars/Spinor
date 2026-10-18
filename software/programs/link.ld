OUTPUT_ARCH(riscv)
SECTIONS {
  . = 0x80000000;
  .text : { *(.text*) }
  .rodata : { *(.rodata*) }
  .data : { *(.sdata*) *(.data*) }
  .bss : { *(.sbss*) *(.bss*) *(COMMON) }
  /DISCARD/ : { *(.comment) *(.eh_frame*) *(.riscv.attributes) }
}
