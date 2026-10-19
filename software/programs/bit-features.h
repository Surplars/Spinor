#ifndef SPINOR_BIT_FEATURES_H
#define SPINOR_BIT_FEATURES_H
#include <stddef.h>
#include <stdint.h>
/* Host must provide an enabled vector context and ordinary accessible buffers.
 * One uint32_t output per input; reversible bit transforms mixed with counts.
 * The fourth argument is both the excluded bit mask and rotate-left amount.
 */
void spinor_bit_features(uint32_t *dst,const uint32_t *src,size_t n,uint32_t exclude);
/* Zero-extend uint32_t to uint64_t, then shift by (amount & 63). */
void spinor_widen_shift(uint64_t *dst,const uint32_t *src,size_t n,uint64_t amount);
#endif
