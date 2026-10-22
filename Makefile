# Current development entry points. Historical milestone recipes live in
# scripts/legacy.mk and must use their matching source/tool snapshots.
.DEFAULT_GOAL := help
PYTHON ?= python3
PRESET ?= standard
FCSR_OWNER ?= standalone
RTL_OUT ?= build/current

.PHONY: help bootstrap compile rtl-direct rtl-isolated check check-rtl audit-evidence audit-retention
help:
	@printf '%s\n' 'Spinor development targets:' '  make bootstrap       Install pinned build tools' '  make compile         Compile all Chisel sources' '  make rtl-direct      Generate SpinorVpu' '  make rtl-isolated    Generate SpinorIsolated' '  make check           Check layout, comments, links and maintenance tests' '  make check-rtl       Also compare 8 generated tops with the M61 baseline' '  make audit-evidence  Audit retained M50-M61 evidence (needs build/tools)' 'Options: PRESET=standard|deep|integer|integer-deep FCSR_OWNER=standalone|host' 'Historical recipes: make -f scripts/legacy.mk <target>'
	@printf '%s\n' '  make audit-retention Verify compressed receipts and pinned Git originals'

bootstrap:
	$(PYTHON) scripts/bootstrap.py
compile:
	./mill Vpu.compile
rtl-direct:
	./mill Vpu.runMain vpu.GenerateConfigured --out "$(RTL_OUT)/direct" --name SpinorVpu --preset $(PRESET) --fcsr-owner $(FCSR_OWNER)
rtl-isolated:
	./mill Vpu.runMain vpu.GenerateIsolated --out "$(RTL_OUT)/isolated" --name SpinorIsolated --preset $(PRESET) --fcsr-owner $(FCSR_OWNER)
check:
	$(PYTHON) scripts/check_repository.py
	$(PYTHON) tests/test_repository_checks.py
	$(PYTHON) tests/test_retention.py
check-rtl:
	$(PYTHON) scripts/check_repository.py --rtl
audit-evidence:
	$(PYTHON) scripts/check_repository.py --evidence
audit-retention:
	$(PYTHON) scripts/retained_artifacts.py --verify
