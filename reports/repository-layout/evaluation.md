# Repository layout and comment maintenance

Hardware baseline: M61, commit `f8df80e9a1106e5d8cde16a19d4d4778f766cfb0`.

All 56 Scala files are grouped by responsibility. Their Scala code tokens
are unchanged; edits are comments, whitespace, and source locations. Public `vpu.*`
class names and Mill generation commands remain available. Every top-level declaration
has ScalaDoc; the maximum uncommented substantive-code span is 33 lines.
This is a maintenance convention, not a measure of functional correctness.

Eight complete generated SystemVerilog tops match the accepted M61 outputs byte for byte:
direct and isolated standard host, Deep host, standard standalone, and integer-deep.
The organization therefore adds no RTL change to those configurations. The existing
M61 numerical and conditional timing evidence keeps its original scope; this cleanup
does not claim a new simulation campaign or a new device timing result.

Retained M50–M61 receipts: 100,626 exact input/artifact bindings checked.
Original paths and hashes resolve through existing archives or the compressed M61
layout snapshot. Historical receipts and build artifacts were not rewritten.

The root Makefile now defaults to help. Historical recipes are explicit in
`scripts/legacy.mk`. Current helper paths and recursive source/notice discovery were
migrated. Python AST comparison of 72 migrated helpers confirms
only 110 source path literals and 8 recursive source searches changed.
All maintenance input hashes were re-read after verification to reject concurrent edits.
See [source map](../../src/README.md), [development conventions](../../docs/development.md),
and [verification instructions](../../docs/validation.md).

```sh
make check
make check-rtl       # requires retained M61 reference SV and Mill tools
make audit-evidence # requires retained historical tools/build artifacts
```
