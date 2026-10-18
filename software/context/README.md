# Portable Spinor context images (M53)

`spinor_context.c` saves and restores VPU-owned architectural state through
callbacks on the existing public Command and context ports. It has no libc,
allocator, operating-system, native-struct-layout, or CPU-instruction dependency.
It works with all four current VLEN128/ELEN64 presets. The host adapter is still
responsible for transporting those ports and serializing access. This is not a
Linux job driver or an Orbital retirement implementation.

## API and ownership

Include `spinor_context.h`; compile and link `spinor_context.c` with the host
adapter. Set `features` to exactly `0` for Integer/IntegerDeep or
`SPINOR_CONTEXT_FP` for Standard/Deep. Configuration must come from the actual
target manifest/adapter; the caller cannot infer it from the image alone.

- `acquire(opaque, restoring)` must exclude CPU commands, debug access, other
  context operations, resets and configuration changes for the entire operation.
  It must wait for or reject active instructions, unconsumed completions and
  outstanding memory transactions. A nonzero return means busy and must leave
  any existing lease/recovery obligation intact.
- `read_chunk` and `write_chunk` use **chunk indices 0..63**, not byte addresses:
  `2*r` is v[r] bits63:0 and `2*r+1` is bits127:64. Transport these through the
  existing context port. Return zero only once the requested operation completes.
- `execute` transports the instruction, scalar, scalar2 and AVL fields to the
  public Command interface. It must check the completion identity and errors,
  wait for completion/bus drain, and return its scalar result. The helper uses
  CSR reads/writes and VSETVL; the encoded rd=x3 is only a completion destination
  inside this private command exchange, not permission to overwrite a live host
  GPR. It must not be submitted as an ordinary CPU instruction that retires x3.
- `release(opaque, valid=1)` certifies state safe for ordinary execution; the
  helper uses it after success or after rejecting a read-only save's metadata.
  `release(opaque, valid=0)` must retain ownership, mark the state uncertain and
  keep CPU/debug execution blocked. Errors can occur before or after a hardware
  operation took effect. A poisoned lease admits only a complete restore retry
  or a platform-coordinated reset, never a save or ordinary execution. Reacquire
  for recovery must also ensure any failed transaction is drained.

Restore validates the entire immutable source image before acquiring the
device. It writes all 64 chunks, restores VL/vtype via VSETVL with literal AVL,
then vcsr, optional fcsr, and **vstart last**. A device VLEN mismatch during
restore also poisons the lease: an earlier partial restore might already exist.
There is no whole-image rollback and no hardware mutex added by this library.
Host synchronization must cover every access path, including a second CPU or OS.

Save clears its destination before trying to acquire. Every unsuccessful save
leaves an invalid image; do not use the sole recovery image as a save destination.
Keep buffers separate from `ops` and adapter state, and keep the restore source
unchanged until the function returns. An application normally keeps a committed
image and saves into a separate staging buffer before publishing success.

The image includes all 32 vector registers, VL, vtype, vstart, vxrm/vxsat and
optional frm/fflags. vstart may exceed VL and is preserved. Reserved frm values
are preserved as CSR state; executing floating arithmetic with them remains
illegal. The image does not include host PC/GPRs, VS/FS, privilege state, RAM,
monitor counters, cache/TLB or outstanding requests. The host must handle those
separately and preserve program RAM, including irrevocable store prefixes.

## Image ABI 1

Exactly **576 bytes**, all integers little endian, no native C struct packing:

| Byte offset | Bytes | Meaning |
|---:|---:|---|
| 0 | 8 | ASCII `SPINCTX1` |
| 8 | 2 | ABI = 1 |
| 10 | 2 | Features: 0 or 1 (FP) |
| 12 | 4 | Total bytes = 576 |
| 16 | 2 | VLEN = 128 |
| 18 | 2 | ELEN = 64 |
| 20 | 2 | Register count = 32 |
| 22 | 2 | Chunk bytes = 8 |
| 24 | 8 | VL |
| 32 | 8 | vtype |
| 40 | 8 | vstart |
| 48 | 4 | vcsr, only bits2:0 |
| 52 | 4 | fcsr, only bits7:0; zero for integer targets |
| 56 | 4 | CRC32 |
| 60 | 4 | Reserved, must be zero |
| 64 | 512 | v0 low64, v0 high64, ... v31 low64, v31 high64 |

CRC32 is ISO-HDLC/IEEE: reflected polynomial `0xedb88320`, initial and final XOR
`0xffffffff`, covering all 576 bytes with bytes56..59 treated as zero. CRC detects
accidental corruption; it is not authentication. Geometry, feature flag, legal
SEW/LMUL, VL bounds, CSR widths, canonical vill and reserved fields are validated
independently. Images with different features/geometries require explicit
conversion; ABI1 is not a variable-VLEN format.

## Scalar host compilation

Context code must not use the vector/FPU state it is saving. Compile this file
with scalar-only target flags and keep that property when enabling LTO. The
tested Clang19 commands are:

```bash
clang-19 --target=riscv64-unknown-elf -march=rv64imac -mabi=lp64 \
  -std=c11 -O2 -ffreestanding -fno-builtin -fno-vectorize \
  -fno-slp-vectorize -Wall -Wextra -Werror -pedantic \
  -c software/context/spinor_context.c -o spinor-context-rv64.o
clang-19 --target=aarch64-none-elf -march=armv8-a -mgeneral-regs-only \
  -std=c11 -O2 -ffreestanding -fno-builtin -fno-vectorize \
  -fno-slp-vectorize -Wall -Wextra -Werror -pedantic \
  -c software/context/spinor_context.c -o spinor-context-arm64.o
```

These are freestanding compilation checks, not ARM/RISC-V target execution.
The cross-check verifies correct ELF machines and no undefined runtime symbols.
Real adapters must provide appropriate locking, completion transport, barriers,
timeout/drain/recovery and CPU architectural-state integration.

## Verification

Run `python3 scripts/verify_m53.py` in the established M52 environment. Tests link
the actual C library into a C++ host adapter that drives all four production
GSim tops through public ports. Independent Python byte images and continuations
check save/restore, register clobber by another task, masks, all legal geometry,
rounding/flags, and unit/segment load/store fault-prefix retry. Both before-effect
and after-effect errors are injected at every callback position. Native C
validation runs under ASan/UBSan, rejecting corrupted/malformed/truncated images
before device access. The host lease is a simulation adapter contract; it does
not prove a future CPU/OS adapter implements that contract correctly.
