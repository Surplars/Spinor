#ifndef SPINOR_CONTEXT_H
#define SPINOR_CONTEXT_H
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
#define SPINOR_CONTEXT_ABI 1u
#define SPINOR_CONTEXT_BYTES 576u
#define SPINOR_CONTEXT_FP 1u
#define SPINOR_CONTEXT_CHUNKS 64u

enum spinor_context_result {
    SPINOR_CTX_OK = 0,
    SPINOR_CTX_ARGUMENT = -1,
    SPINOR_CTX_FORMAT = -2,
    SPINOR_CTX_CHECKSUM = -3,
    SPINOR_CTX_GEOMETRY = -4,
    SPINOR_CTX_BUSY = -5,
    SPINOR_CTX_IO = -6
};

/* acquire must exclude CPU commands/debug/context and drain the VPU and bus.
 * A poisoned lease may only admit restore or a platform-coordinated reset.
 * release(valid=0) MUST keep execution blocked until recovery succeeds.
 * Callbacks return zero only after the operation has completed and drained.
 * execute transports public Command fields; its scalar result is private to
 * this context operation, never a write to an unrelated CPU register.
 */
struct spinor_context_ops {
    void *opaque;
    uint32_t features; /* Exactly 0 or SPINOR_CONTEXT_FP; VLEN128/ELEN64. */
    int (*acquire)(void *, int restoring);
    void (*release)(void *, int valid);
    int (*read_chunk)(void *, uint32_t address, uint64_t *data);
    int (*write_chunk)(void *, uint32_t address, uint64_t data);
    int (*execute)(void *, uint32_t instruction, uint64_t scalar,
                   uint64_t scalar2, uint64_t avl, uint64_t *result);
};

/* Fixed little-endian image, no native C struct layout or pointer fields.
 * Validation rejects malformed metadata/CRC before acquiring the device.
 * The caller keeps the source image immutable for the entire restore call.
 * A valid image contains VPU-owned state only, not CPU VS/FS/PC/privilege.
 */
int spinor_context_validate(const void *image, size_t bytes, uint32_t features);
int spinor_context_save(const struct spinor_context_ops *, void *image, size_t bytes);
int spinor_context_restore(const struct spinor_context_ops *, const void *image, size_t bytes);
#ifdef __cplusplus
}
#endif
#endif
