#include "spinor_context.h"

static const uint64_t magic = UINT64_C(0x315854434e495053);
static uint64_t get_le(const uint8_t *p, unsigned n) {
    uint64_t value = 0;
    for (unsigned i = 0; i < n; ++i) value |= (uint64_t)p[i] << (8u * i);
    return value;
}
static void put_le(uint8_t *p, uint64_t value, unsigned n) {
    for (unsigned i = 0; i < n; ++i) p[i] = (uint8_t)(value >> (8u * i));
}
static uint32_t checksum(const uint8_t *p) {
    uint32_t crc = UINT32_MAX;
    for (unsigned i = 0; i < SPINOR_CONTEXT_BYTES; ++i) {
        const uint8_t byte = i >= 56 && i < 60 ? 0 : p[i];
        crc ^= byte;
        for (unsigned bit = 0; bit < 8; ++bit)
            crc = (crc >> 1) ^ (UINT32_C(0xedb88320) & (0u - (crc & 1u)));
    }
    return ~crc;
}
static int metadata(const uint8_t *p, uint32_t features) {
    const uint64_t vl = get_le(p + 24, 8), type = get_le(p + 32, 8);
    const unsigned sew = (unsigned)(type >> 3) & 7u, lm = (unsigned)type & 7u;
    if (get_le(p + 16, 2) != 128 || get_le(p + 18, 2) != 64 ||
        get_le(p + 20, 2) != 32 || get_le(p + 22, 2) != 8 ||
        get_le(p + 40, 8) > 127 || get_le(p + 48, 4) > 7 ||
        get_le(p + 52, 4) > 255 || (!features && get_le(p + 52, 4)))
        return SPINOR_CTX_GEOMETRY;
    if (type >> 63)
        return type == (UINT64_C(1) << 63) && vl == 0 ? SPINOR_CTX_OK : SPINOR_CTX_GEOMETRY;
    if (type > 255 || sew > 3 || lm == 4) return SPINOR_CTX_GEOMETRY;
    unsigned maximum = 16u >> sew;
    if (lm < 4) maximum <<= lm;
    else {
        /* Supported SEW cannot exceed ELEN * fractional LMUL. */
        if ((8u << sew) > (64u >> (8u - lm))) return SPINOR_CTX_GEOMETRY;
        maximum >>= 8u - lm;
    }
    return maximum && vl <= maximum ? SPINOR_CTX_OK : SPINOR_CTX_GEOMETRY;
}
int spinor_context_validate(const void *image, size_t bytes, uint32_t features) {
    const uint8_t *p = (const uint8_t *)image;
    if (!p || bytes != SPINOR_CONTEXT_BYTES || features > SPINOR_CONTEXT_FP)
        return SPINOR_CTX_ARGUMENT;
    if (get_le(p, 8) != magic || get_le(p + 8, 2) != SPINOR_CONTEXT_ABI ||
        get_le(p + 10, 2) != features || get_le(p + 12, 4) != SPINOR_CONTEXT_BYTES || get_le(p + 60, 4))
        return SPINOR_CTX_FORMAT;
    if (get_le(p + 56, 4) != checksum(p)) return SPINOR_CTX_CHECKSUM;
    return metadata(p, features);
}
static int operations(const struct spinor_context_ops *ops) {
    return ops && ops->features <= SPINOR_CONTEXT_FP && ops->acquire && ops->release &&
           ops->read_chunk && ops->write_chunk && ops->execute;
}
static int execute(const struct spinor_context_ops *ops, uint32_t instruction,
                   uint64_t scalar, uint64_t scalar2, uint64_t avl, uint64_t *result) {
    return ops->execute(ops->opaque, instruction, scalar, scalar2, avl, result);
}
static int read_csr(const struct spinor_context_ops *ops, unsigned address, uint64_t *value) {
    /* CSRRS rd=x3, rs1=x0: read without modifying CSR or vstart. */
    return execute(ops, (address << 20) | (2u << 12) | (3u << 7) | 0x73u, 0, 0, 0, value);
}
static int write_csr(const struct spinor_context_ops *ops, unsigned address, uint64_t value) {
    uint64_t ignored;
    return execute(ops, (address << 20) | (1u << 15) | (1u << 12) | 0x73u, value, 0, 0, &ignored);
}
int spinor_context_save(const struct spinor_context_ops *ops, void *image, size_t bytes) {
    uint8_t *p = (uint8_t *)image;
    uint64_t value;
    if (!operations(ops) || !p || bytes != SPINOR_CONTEXT_BYTES) return SPINOR_CTX_ARGUMENT;
    /* An interrupted/failed save must never leave an apparently valid image. */
    for (unsigned i = 0; i < SPINOR_CONTEXT_BYTES; ++i) p[i] = 0;
    if (ops->acquire(ops->opaque, 0)) return SPINOR_CTX_BUSY;
    if (read_csr(ops, 0xc22u, &value)) goto io_error;
    if (value != 16) { ops->release(ops->opaque, 1); return SPINOR_CTX_GEOMETRY; }
    put_le(p + 8, SPINOR_CONTEXT_ABI, 2); put_le(p + 10, ops->features, 2);
    put_le(p + 12, SPINOR_CONTEXT_BYTES, 4);
    put_le(p + 16, 128, 2); put_le(p + 18, 64, 2);
    put_le(p + 20, 32, 2); put_le(p + 22, 8, 2);
    const unsigned addresses[] = {0xc20u, 0xc21u, 0x008u, 0x00fu, 0x003u};
    const unsigned offsets[] = {24, 32, 40, 48, 52};
    for (unsigned i = 0; i < (ops->features ? 5u : 4u); ++i) {
        if (read_csr(ops, addresses[i], &value)) goto io_error;
        if ((i == 3 && value > 7) || (i == 4 && value > 255)) { ops->release(ops->opaque, 1); return SPINOR_CTX_GEOMETRY; }
        put_le(p + offsets[i], value, i < 3 ? 8 : 4);
    }
    if (metadata(p, ops->features)) { ops->release(ops->opaque, 1); return SPINOR_CTX_GEOMETRY; }
    for (unsigned i = 0; i < SPINOR_CONTEXT_CHUNKS; ++i) {
        if (ops->read_chunk(ops->opaque, i, &value)) goto io_error;
        put_le(p + 64 + 8u * i, value, 8);
    }
    put_le(p, magic, 8);
    put_le(p + 56, checksum(p), 4);
    ops->release(ops->opaque, 1);
    return SPINOR_CTX_OK;
io_error:
    put_le(p, 0, 8);
    ops->release(ops->opaque, 0);
    return SPINOR_CTX_IO;
}
int spinor_context_restore(const struct spinor_context_ops *ops, const void *image, size_t bytes) {
    const uint8_t *p = (const uint8_t *)image;
    uint64_t value;
    if (!operations(ops)) return SPINOR_CTX_ARGUMENT;
    const int valid = spinor_context_validate(image, bytes, ops->features);
    if (valid) return valid;
    if (ops->acquire(ops->opaque, 1)) return SPINOR_CTX_BUSY;
    if (read_csr(ops, 0xc22u, &value)) goto io_error;
    /* This may be a recovery attempt on an already poisoned lease. Even
     * though this call has not written state, it cannot certify that state. */
    if (value != 16) { ops->release(ops->opaque, 0); return SPINOR_CTX_GEOMETRY; }
    for (unsigned i = 0; i < SPINOR_CONTEXT_CHUNKS; ++i)
        if (ops->write_chunk(ops->opaque, i, get_le(p + 64 + 8u * i, 8))) goto io_error;
    /* VSETVL restores readonly VL/vtype through their architectural operation.
     * Nonzero rs1/rd gives literal AVL including zero, avoiding x0 AVL rules.
     */
    if (execute(ops, UINT32_C(0x8020f1d7), 0, get_le(p + 32, 8), get_le(p + 24, 8), &value)) goto io_error;
    if (value != get_le(p + 24, 8)) goto io_error;
    if (write_csr(ops, 0x00fu, get_le(p + 48, 4))) goto io_error;
    if (ops->features && write_csr(ops, 0x003u, get_le(p + 52, 4))) goto io_error;
    /* VSETVL clears vstart. Restore it last, including a fault's restart index. */
    if (write_csr(ops, 0x008u, get_le(p + 40, 8))) goto io_error;
    ops->release(ops->opaque, 1);
    return SPINOR_CTX_OK;
io_error:
    ops->release(ops->opaque, 0);
    return SPINOR_CTX_IO;
}
