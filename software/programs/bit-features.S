/* Ordinary-RAM, VLEN-independent strip-mining. See bit-features.h. */
.text
.p2align 2
.globl spinor_bit_features
.type spinor_bit_features,@function
spinor_bit_features:
  beqz a2, 2f
1:
  vsetvli t0, a2, e32, m1, tu, mu
  vle32.v v16, (a1)
  vandn.vx v16, v16, a3
  vbrev8.v v8, v16
  vrev8.v v9, v16
  vbrev.v v10, v16
  vclz.v v11, v16
  vctz.v v12, v16
  vcpop.v v13, v16
  vrol.vx v8, v8, a3
  vror.vi v9, v9, 13
  vxor.vv v8, v8, v9
  vxor.vv v8, v8, v10
  vadd.vv v8, v8, v11
  vadd.vv v8, v8, v12
  vadd.vv v8, v8, v13
  vse32.v v8, (a0)
  slli t1, t0, 2
  add a0, a0, t1
  add a1, a1, t1
  sub a2, a2, t0
  bnez a2, 1b
2:
  ret
.size spinor_bit_features, .-spinor_bit_features

.globl spinor_widen_shift
.type spinor_widen_shift,@function
spinor_widen_shift:
  beqz a2, 2f
1:
  vsetvli t0, a2, e32, m1, tu, mu
  vle32.v v16, (a1)
  vwsll.vx v8, v16, a3
  vsetvli zero, t0, e64, m2, tu, mu
  vse64.v v8, (a0)
  slli t1, t0, 2
  add a1, a1, t1
  slli t1, t0, 3
  add a0, a0, t1
  sub a2, a2, t0
  bnez a2, 1b
2:
  ret
.size spinor_widen_shift, .-spinor_widen_shift
