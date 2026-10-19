"""Audit pinned ACT4 prerequisites without claiming generated or executed tests."""
import gzip
import json
import shutil
from m60_evidence import ROOT, sha


def main():
    pin = ROOT/'docs/references/m60-act-sources.json'; d = json.loads(pin.read_text())
    assert d['revision'] == '51c0ed49294c5797a59d0203517b14e1f5fe9656'
    assert not d['tests_executed'] and not d['elfs_generated'] and not d['tree_truncated']
    for rel, expected in d['sha256'].items(): assert sha(ROOT/rel) == expected, rel
    readme_path = ROOT/'docs/references/m60-act-README.md'
    text = readme_path.read_text()
    for phrase in ('ACT4 Framework', 'UDB configuration file', 'rvmodel_macros.h', 'Sail reference model', 'self-checking ELFs', 'version 0.16', 'LLVM/Clang 22'):
        assert phrase in text, phrase
    tree = json.loads(gzip.decompress((ROOT/'docs/references/m60-act-tree.json.gz').read_bytes()))
    assert not tree['truncated']
    paths = {item['path'] for item in tree['tree']}
    assert {'coverpoints/norm/Zvbb.yaml', 'coverpoints/norm/Zvfhmin.yaml', 'config/sail/sail-rv64-max-clang/test_config.yaml'} <= paths
    probes = {name:bool(shutil.which(name)) for name in ('make', 'uv', 'ruby', 'sail_riscv_sim')}
    # This is an intake contract, deliberately not an invented UDB schema or a
    # partial CPU implementation embedded in the VPU hardware.
    contract = dict(vector_target=dict(vlen=128, elen=64, xlen=64, base_v=True, zvfhmin=True, zvbb=True,
                                      zvkt_certified=False, fcsr_owner='HOST_FOR_NATIVE_CPU_STANDALONE_FOR_CURRENT_TESTS'),
                    runner_requirements=['full ELF scalar control-flow execution', 'vector/CSR dispatch to real VPU public ports',
                                         'matching Sail/UDB configuration', 'pass/fail console and termination hooks',
                                         'memory map and ordinary RAM service', 'explicit trap/VS/FS ownership by host model'],
                    hardware_scope='NO_SCALAR_CPU_PRIVILEGE_MMU_IMPLEMENTED_IN_VPU',
                    existing_elf_adapter='BOUNDED_COMPILER_KERNEL_ADAPTER_NOT_ACT4_RUNNER',
                    readiness='INTAKE_ONLY_NOT_READY_TO_EXECUTE_ACT4_ELFS')
    out = ROOT/'build/m60/act'; out.mkdir(parents=True, exist_ok=True)
    result = dict(status='PASS', scope='PINNED_UPSTREAM_INTAKE_ONLY', upstream_revision=d['revision'],
                  probes=probes, act4_elfs_generated=0, act4_tests_executed=0, contract=contract,
                  source_sha256={'scripts/m60_act_intake.py':sha(ROOT/'scripts/m60_act_intake.py')},
                  artifact_sha256={**d['sha256'], str(pin.relative_to(ROOT)):sha(pin)})
    (out/'results.json').write_text(json.dumps(result, indent=2)+'\n')
    print('PASS ACT4 intake; no ACT4 test execution claimed;', probes, flush=True)


if __name__ == '__main__': main()
