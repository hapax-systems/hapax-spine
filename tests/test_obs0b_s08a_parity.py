"""S08a offline helper boundaries, Council cef55b52 parity.

Receipt shape: S04 producer-shaped fixture. Pool locator: Council
 tests/shared/test_platform_capability_registry.py:836 (cef55b52).
Only synthetic wrappers/paths are used; helpers do not probe hosts. These
projections are not receipt admission; S08b owns the remaining consumer wiring.
"""
import copy
import itertools
from pathlib import Path

import pytest

from hapax.spine import platform_capability_registry as r
from hapax.spine.platform_capability_receipts import EvidenceStatus as Status, WrapperEvidence, PlatformCapabilityReceipt
from test_obs0b_s04_parity import payload, NOW
from test_obs0b_s07a_parity import REF, LABEL

POOL_LABEL = 'claude-subscription-quota-admission-claude-review-opus-pool-max-2-20260708t140000z.yaml'
POOL_REF = REF.replace(LABEL, POOL_LABEL).replace('route_id:claude.headless.full:', 'route_id:claude.review.opus:')
CAP = 'sanctioned_wrapper_missing_or_unreadable'
NONEXEC = 'sanctioned_wrapper_not_executable'


@pytest.fixture(autouse=True)
def offline(monkeypatch, tmp_path):
    import socket, subprocess
    def forbidden(*args, **kwargs): pytest.fail('unexpected network, host receipt read or subprocess')
    monkeypatch.setattr(socket.socket, 'connect', forbidden)
    monkeypatch.setattr(socket, 'create_connection', forbidden)
    monkeypatch.setattr(subprocess, 'Popen', forbidden)
    monkeypatch.setattr(r, 'load_platform_capability_receipts', forbidden)
    monkeypatch.setenv('HAPAX_PLATFORM_CAPABILITY_RECEIPT_DIR', 'none')
    monkeypatch.setenv('HAPAX_QUOTA_SPEND_LEDGER_LIVE', 'none')
    monkeypatch.setenv('HAPAX_SPINE_CONFIG_DIR', str(tmp_path/'config'))


def wrapper(exists=True, executable=True, sha256='a'*64, path='/fixture/route-wrapper'):
    return WrapperEvidence(path=path, exists=exists, executable=executable, sha256=sha256)


def receipt(*, routes=True):
    p = payload(current=routes)
    return PlatformCapabilityReceipt.model_validate(p)


@pytest.mark.parametrize('exists,executable,digest', list(itertools.product([False,True],[False,True],[None,'a'*64])))
def test_wrapper_dimensions(exists, executable, digest):
    w = wrapper(exists, executable, digest); before = w.model_dump_json()
    cap = [] if exists and executable and digest else (
        [NONEXEC, NONEXEC+':route-wrapper'] if exists and digest and not executable
        else [CAP, CAP+':route-wrapper'])
    res = [] if exists and executable and digest else (
        ['wrapper_not_executable'] if exists and not executable else ['wrapper_missing'])
    assert r._wrapper_capability_reason_codes(w) == cap
    assert r._wrapper_resource_reason_codes(w) == res
    assert r._wrapper_capability_refs(w) == ([f'local:{w.path}:sha256:{digest}'] if exists and executable and digest else [])
    assert r._wrapper_resource_refs(w) == [f'local:{w.path}:exists:{str(exists).lower()}',
                                          f'local:{w.path}:executable:{str(executable).lower()}']
    assert w.model_dump_json() == before


@pytest.mark.parametrize('path,label', [('/fixture/hapax wrapper!?','hapax-wrapper'),
    ('/fixture/a.b_c-d','a.b_c-d'), ('///','unknown-wrapper'), ('','unknown-wrapper'),
    ('relative/route-wrapper','route-wrapper'), ('/fixture/é','unknown-wrapper')])
def test_wrapper_label_is_stable_and_sanitized(path, label):
    assert r._wrapper_reason_label(wrapper(path=path)) == label


@pytest.mark.parametrize('reason,yes', [(CAP,True), (CAP+':x',True), (NONEXEC,True),
    (NONEXEC+':x',True), (CAP+'-x',False), ('prefix:'+CAP,False),
    ('wrapper_missing',False), ('cli_missing_or_unusable',False)])
def test_capability_reason_prefix_is_token_bounded(reason, yes):
    assert r._wrapper_capability_reason(reason) is yes


@pytest.mark.parametrize('route,selected', [('claude.review.opus','route-wrapper'),
    ('claude.headless.full','hapax-claude-reviewer'), ('','hapax-claude-reviewer'),
    (None,'hapax-claude-reviewer')])
def test_exact_route_wrapper_selection(route, selected):
    rec = receipt(); rec.route_wrappers['claude.review.opus'] = wrapper()
    assert Path(r._route_wrapper_for_receipt({'route_id':route}, rec).path).name == selected
    assert r._route_wrapper_for_receipt({}, rec) is rec.wrapper


@pytest.mark.parametrize('route_maps', [False,True])
@pytest.mark.parametrize('healthy', [False,True])
def test_route_reason_replacement_preserves_nonwrapper_reasons(route_maps, healthy):
    rec = receipt(routes=route_maps)
    rec.capability.reason_codes = ['cli_missing_or_unusable', CAP, CAP+':old', NONEXEC+':old', 'cli_missing_or_unusable']
    rec.resource.reason_codes = ['load_contract_held','wrapper_missing','wrapper_not_executable','load_contract_held']
    w = wrapper(executable=healthy)
    before = rec.model_dump_json()
    expected_cap = ['cli_missing_or_unusable'] + ([] if healthy else [NONEXEC,NONEXEC+':route-wrapper'])
    expected_res = ['load_contract_held'] + ([] if healthy else ['wrapper_not_executable'])
    assert r._route_receipt_capability_reason_codes(rec, w) == (expected_cap if route_maps else rec.capability.reason_codes)
    assert r._route_receipt_resource_reason_codes(rec, w) == (expected_res if route_maps else rec.resource.reason_codes)
    assert rec.model_dump_json() == before


@pytest.mark.parametrize('default', list(Status))
@pytest.mark.parametrize('reasons', [[],['held']])
def test_surface_status_retains_missing(default, reasons):
    expected = Status.OBSERVED if not reasons else Status.MISSING if default is Status.MISSING else Status.BLOCKED
    assert r._surface_status_from_reasons(default, reasons) is expected


@pytest.mark.parametrize('status', list(Status))
@pytest.mark.parametrize('blocker,where', [(None,'none'), ('capability_scores_asserted_not_measured','top'),
    ('capabilityio_measurement_absent','nested'), ('capabilityio_measurement_absent','top'),
    ('capability_scores_asserted_not_measured','nested'), ('unrelated','top')])
def test_only_observed_measured_scores_refresh(status, blocker, where):
    rec = receipt(); rec.capability.status = status
    route = {'blocked_reasons':[blocker] if where == 'top' else [], 'freshness':{'evidence':{'capability':{
        'blocked_reasons':[blocker] if where == 'nested' else []}}}}
    before = copy.deepcopy(route)
    assert r._receipt_measures_capability_scores(route, rec) is (status is Status.OBSERVED and blocker in {None,'unrelated'})
    assert route == before


def test_explicit_capability_status_overrides_receipt_status():
    rec = receipt(); rec.capability.status = Status.OBSERVED
    assert not r._receipt_measures_capability_scores({}, rec, capability_status=Status.BLOCKED)
    rec.capability.status = Status.BLOCKED
    assert r._receipt_measures_capability_scores({}, rec, capability_status=Status.OBSERVED)
    assert r._receipt_measures_capability_scores({'blocked_reasons':None}, rec, capability_status=Status.OBSERVED)


@pytest.mark.parametrize('raw,tokens', [(' A_B:C -- D\tE ', ('a','b','c','d','e')),
    ('',()), (' __ : -- ',()), ('aaa-b',('aaa','b')), ('quota::observed',('quota','observed'))])
def test_reference_tokens(raw, tokens):
    assert r._ref_tokens(raw) == tokens


@pytest.mark.parametrize('ref,suffix,yes', [('receipt:account_live-quota:observed','account-live-quota-observed',True),
    ('ACCOUNT_LIVE_QUOTA_OBSERVED',' account-live:quota observed ',True),
    ('receipt:not-account-live-quota-observed','account-live-quota-observed',True),
    ('receipt:account-live-quota-unobserved','account-live-quota-observed',False),
    ('receipt:account-live-quota-observed-extra','account-live-quota-observed',False),
    ('quota-observed','account-live-quota-observed',False), ('receipt:any','',False),
    ('','',False), ('a','__::--',False)])
def test_reference_suffix_matches_whole_token_tail(ref, suffix, yes):
    assert r._ref_has_token_suffix(ref,suffix) is yes


@pytest.mark.parametrize('pool', ['max-2','aa','a'*32])
@pytest.mark.parametrize('seconds', [False,True])
def test_pool_label_grammar(pool, seconds):
    label = POOL_LABEL.replace('pool-max-2','pool-'+pool)
    if not seconds: label = label.replace('t140000z','t1400z')
    assert r._receipt_label_pool(label) == pool
    assert r._admission_refs_name_pool([POOL_REF.replace(POOL_LABEL,label)],pool)


@pytest.mark.parametrize('label', [POOL_LABEL.replace('-pool-','-poolx-'),
    POOL_LABEL.replace('max-2','x'), POOL_LABEL.replace('max-2','a'*33),
    POOL_LABEL.replace('max-2','Max-2'), POOL_LABEL.replace('max-2','-max-2'),
    POOL_LABEL.replace('max-2','max-2-'), POOL_LABEL.replace('20260708','2026070'),
    POOL_LABEL.replace('t140000z','t140z'), POOL_LABEL.replace('.yaml','.json'),
    POOL_LABEL+'extra', POOL_LABEL+'\n', 'unrelated.yaml'])
def test_malformed_pool_labels_refuse(label):
    assert r._receipt_label_pool(label) is None
    assert not r._admission_refs_name_pool([POOL_REF.replace(POOL_LABEL,label)],'max-2')


def test_pool_requires_nonempty_all_matching_composites():
    assert not r._admission_refs_name_pool([], 'max-2')
    assert not r._admission_refs_name_pool(['fixture:quota'], 'max-2')
    assert r._admission_refs_name_pool([POOL_REF,'fixture:quota'], 'max-2')
    assert not r._admission_refs_name_pool([POOL_REF, POOL_REF.replace('pool-max-2','pool-max-1')], 'max-2')
    assert not r._admission_refs_name_pool([POOL_REF, REF], 'max-2')
    assert not r._admission_refs_name_pool(['prefix:'+POOL_REF], 'max-2')
    assert not r._admission_refs_name_pool([POOL_REF.replace('pool-max-2','pool-max-20')], 'max-2')
    assert r._admission_refs_name_pool(iter([POOL_REF,POOL_REF]), 'max-2')


def test_leftmost_pool_marker_prevents_double_pool_spoof():
    label = POOL_LABEL.replace('pool-max-2','pool-aa-pool-bb')
    assert r._receipt_label_pool(label) == 'aa-pool-bb'
    ref = POOL_REF.replace(POOL_LABEL,label)
    assert not r._admission_refs_name_pool([ref],'aa')
    assert not r._admission_refs_name_pool([ref],'bb')


BLOCKERS = {
    'agy.review.direct':'route_specific_quota_receipt_absent',
    'glmcp.review.direct':'glmcp_review_seat_receipt_admission_required',
    'claude.headless.full':'account_live_quota_receipt_absent',
    'claude.interactive.full':'account_live_quota_receipt_absent',
    'claude.review.opus':'claude_review_route_specific_quota_receipt_absent',
    'kimi.interactive.lane':'route_specific_quota_receipt_absent',
}


def test_declared_route_specific_blocker_map():
    assert r.ROUTE_SPECIFIC_QUOTA_ADMISSION_BLOCKERS == BLOCKERS


@pytest.mark.parametrize('route_id,cap_extra', [
    ('agy.review.direct','agy_review_seat_receipt_admission_required'),
    ('claude.review.opus','claude_review_seat_receipt_admission_required'),
    ('api.headless.provider_gateway','provider_gateway_evidence_absent'),
    ('glmcp.review.direct',None), ('kimi.interactive.lane',None),
    ('claude.headless.full',None), ('claude.interactive.full',None), ('unknown.route',None),
])
@pytest.mark.parametrize('pool', ['subscription_quota','api_paid_spend','bootstrap_budget'])
def test_removable_blockers_are_dimension_and_route_scoped(route_id, cap_extra, pool):
    route = {'route_id':route_id,'capacity_pool':pool}
    cap = {'fresh_capability_evidence_absent'} | ({cap_extra} if cap_extra else set())
    quota = set() if route_id in {'agy.review.direct','claude.review.opus'} else (
        {'quota_telemetry_unknown'} if route_id in {'claude.headless.full','claude.interactive.full'}
        else {'quota_telemetry_unknown','account_live_quota_receipt_absent'})
    unobs = {'quota_telemetry_unknown'}
    if route_id not in {'claude.headless.full','claude.interactive.full'}:
        unobs.add('account_live_quota_receipt_absent')
    if pool in {'api_paid_spend','bootstrap_budget'}: unobs.add('provider_budget_receipt_absent')
    assert r._capability_receipt_removable_reasons(route) == cap
    assert r._quota_receipt_removable_reasons(route) == quota
    assert r._quota_unobservable_removable_reasons(route) == unobs
    assert r._observed_quota_receipt_removable_reasons(route) == (set() if route_id == 'agy.review.direct' else unobs|quota)
    blocker = BLOCKERS.get(route_id)
    if blocker: assert blocker not in quota
    assert 'operator_hold' not in cap|quota|unobs


@pytest.mark.parametrize('configured', [None,'','0','none','None','false','False','  none  ','FALSE','/fixture/receipts'])
def test_receipt_directory_default_disable_and_override(monkeypatch, tmp_path, configured):
    default = tmp_path/'default-receipts'; monkeypatch.setattr(r,'DEFAULT_PLATFORM_CAPABILITY_RECEIPT_DIR',default)
    if configured is None: monkeypatch.delenv('HAPAX_PLATFORM_CAPABILITY_RECEIPT_DIR')
    else: monkeypatch.setenv('HAPAX_PLATFORM_CAPABILITY_RECEIPT_DIR',configured)
    expected = default if configured is None else None if configured.strip() in {'','0','none','None','false','False'} else Path(configured)
    assert r._receipt_dir_from_env() == expected
    assert not default.exists()


@pytest.mark.parametrize('configured', [None,'','0','none','None','false','False',' false ','FALSE','/fixture/ledger.json'])
def test_live_ledger_path_default_disable_and_override(monkeypatch, configured):
    if configured is None: monkeypatch.delenv('HAPAX_QUOTA_SPEND_LEDGER_LIVE')
    else: monkeypatch.setenv('HAPAX_QUOTA_SPEND_LEDGER_LIVE',configured)
    expected = None if not configured else Path('/dev/null/hapax-quota-spend-ledger-live-disabled.json') if configured.strip() in {'0','none','None','false','False'} else Path(configured)
    assert r._quota_spend_live_path_from_env() == expected


@pytest.mark.parametrize('name,var', [('_receipt_dir_from_env','HAPAX_PLATFORM_CAPABILITY_RECEIPT_DIR'),
    ('_quota_spend_live_path_from_env','HAPAX_QUOTA_SPEND_LEDGER_LIVE')])
def test_path_expansion_uses_declared_override(monkeypatch, tmp_path, name, var):
    monkeypatch.setenv(var, '~/fixture-binding')
    seen = []
    def expand(p): seen.append(p); return tmp_path/'expanded'
    monkeypatch.setattr(Path,'expanduser',expand)
    assert getattr(r,name)() == tmp_path/'expanded'
    assert seen == [Path('~/fixture-binding')]


def test_config_binding_and_explicit_paths_win_without_reading_host(monkeypatch, tmp_path):
    import json
    from test_obs0b_s03_parity import root
    explicit = tmp_path/'explicit.json'; explicit.write_text(json.dumps(root()))
    calls = []
    def loader(path, **kw): calls.append(path); return {}
    monkeypatch.setattr(r,'load_platform_capability_receipts',loader)
    monkeypatch.setenv('HAPAX_PLATFORM_CAPABILITY_RECEIPT_DIR',str(tmp_path/'env-receipts'))
    monkeypatch.delenv('HAPAX_SPINE_CONFIG_DIR')
    result = r.load_platform_capability_registry(explicit, receipt_dir=tmp_path/'explicit-receipts', now=NOW)
    assert len(result.routes) == 17 and calls == [tmp_path/'explicit-receipts']
    with pytest.raises(RuntimeError, match='HAPAX_SPINE_CONFIG_DIR'):
        r.load_platform_capability_registry()
    cfg = tmp_path/'config'; cfg.mkdir(); (cfg/'platform-capability-registry.json').write_text(explicit.read_text())
    monkeypatch.setenv('HAPAX_SPINE_CONFIG_DIR',str(cfg))
    r.load_platform_capability_registry(now=NOW)
    assert calls[-1] == tmp_path/'env-receipts'
    monkeypatch.delenv('HAPAX_PLATFORM_CAPABILITY_RECEIPT_DIR')
    monkeypatch.setattr(r,'DEFAULT_PLATFORM_CAPABILITY_RECEIPT_DIR',tmp_path/'default-receipts')
    r.load_platform_capability_registry(now=NOW)
    assert calls[-1] == tmp_path/'default-receipts'
    monkeypatch.setenv('HAPAX_PLATFORM_CAPABILITY_RECEIPT_DIR','none'); count = len(calls)
    r.load_platform_capability_registry(now=NOW)
    assert len(calls) == count

def _mutations():
    """Behavioral red / exact restore / green for each helper boundary below."""
    import ast, hashlib, json, os, subprocess, sys, tempfile
    path = Path(__file__).resolve().parents[1]/'src/hapax/spine/platform_capability_registry.py'
    assert Path(r.__file__).resolve() == path
    original = path.read_bytes(); source = original.decode(); lines = source.splitlines(keepends=True)
    nodes = {n.name:n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef)}
    nodes.update({n.targets[0].id:n for n in ast.parse(source).body if isinstance(n,ast.Assign) and isinstance(n.targets[0],ast.Name)})
    controls = []
    def change(fn, old, new):
        n = nodes[fn]; body = ''.join(lines[n.lineno-1:n.end_lineno])
        assert body.count(old) == 1, (fn,old)
        mutant = ''.join(lines[:n.lineno-1])+body.replace(old,new)+''.join(lines[n.end_lineno:])
        controls.append((fn+':'+old+' => '+new,mutant.encode()))
    for fn in ('_wrapper_capability_reason_codes','_wrapper_resource_reason_codes','_wrapper_capability_refs'):
        old = 'wrapper.exists and wrapper.executable and wrapper.sha256'
        for value in ('wrapper.exists','wrapper.executable','wrapper.sha256'):
            change(fn,old,old.replace(value,'True'))
    # The preceding healthy branch already discharges executable=True here.
    for value in ('wrapper.exists','wrapper.sha256'):
        old = 'wrapper.exists and wrapper.sha256 and not wrapper.executable'
        change('_wrapper_capability_reason_codes',old,old.replace(value,'True'))
    for value in ('wrapper.exists','not wrapper.executable'):
        old = 'wrapper.exists and not wrapper.executable'
        change('_wrapper_resource_reason_codes',old,old.replace(value,'True'))
    for fn in ('_route_receipt_capability_reason_codes','_route_receipt_resource_reason_codes'):
        change(fn,'if not receipt.route_wrappers:', 'if False:')
        change(fn,'list(dict.fromkeys([*receipt_reasons, *', 'list(dict.fromkeys([*')
        predicate = 'not _wrapper_capability_reason(reason)' if 'capability' in fn else 'reason not in _WRAPPER_RESOURCE_REASONS'
        change(fn,predicate,'True')
    # Fullmatch/search are equivalent for the composite regex's \A/\Z anchors.
    rules = {
        'ADMISSION_RECEIPT_POOL_RE': [('{0,30}[a-z0-9]', '{0,30}'), ('{0,30}', '{0,31}'),
            ('[a-z0-9][a-z0-9-]{0,30}[a-z0-9]', '[A-Za-z0-9][A-Za-z0-9-]{0,30}[A-Za-z0-9]'),
            (r'\d{8}t\d{4}', r'\d{7,8}t\d{3,4}')],
        '_wrapper_reason_label': [('re.sub(r"[^A-Za-z0-9_.-]+", "-", label).strip("-")','label'), ('or "unknown-wrapper"','or ""')],
        '_wrapper_capability_reason': [('reason == prefix','False'), ('reason.startswith(f"{prefix}:")','False'), ('f"{prefix}:"','prefix')],
        '_route_wrapper_for_receipt': [('receipt.route_wrappers.get(str(route_payload.get("route_id") or ""))','None')],
        '_wrapper_resource_refs': [('str(wrapper.exists).lower()','str(not wrapper.exists).lower()'), ('str(wrapper.executable).lower()','str(not wrapper.executable).lower()')],
        '_wrapper_capability_refs': [('sha256:{wrapper.sha256}','sha256:wrong')],
        '_surface_status_from_reasons': [('if not reason_codes:','if False:'), ('if default_status is EvidenceStatus.MISSING:','if False:')],
        '_ref_tokens': [('ref.strip().lower()','ref.strip()'), ('if token','if True')],
        '_ref_has_token_suffix': [('bool(suffix_tokens)','True'), ('ref_tokens[-len(suffix_tokens) :] == suffix_tokens','True')],
        '_admission_refs_name_pool': [('bool(labels)','True'), ('all(_receipt_label_pool','any(_receipt_label_pool'), ('_receipt_label_pool(label) == pool','True')],
        '_receipt_label_pool': [('label.partition("-pool-")','label.rpartition("-pool-")')],
        '_receipt_measures_capability_scores': [('(capability_status or receipt.capability.status)','receipt.capability.status'), ('is not EvidenceStatus.OBSERVED','is EvidenceStatus.MISSING'), ('capability_blockers | top_blockers','capability_blockers'), ('capability_blockers | top_blockers','top_blockers')],
    }
    for fn,pairs in rules.items():
        for old,new in pairs: change(fn,old,new)
    for fn in ('_quota_receipt_removable_reasons','_observed_quota_receipt_removable_reasons',
               '_capability_receipt_removable_reasons','_quota_unobservable_removable_reasons',
               '_receipt_dir_from_env','_quota_spend_live_path_from_env'):
        for n in ast.walk(nodes[fn]):
            if isinstance(n,ast.If):
                test = ast.get_source_segment(source,n.test)
                if fn == '_receipt_dir_from_env' and test == 'configured is None':
                    change(fn,'return DEFAULT_PLATFORM_CAPABILITY_RECEIPT_DIR','return Path("/fixture/wrong-default")')
                else: change(fn,test,'False')
    for fn in ('_receipt_dir_from_env','_quota_spend_live_path_from_env'):
        change(fn,'Path(configured).expanduser()','Path(configured)')
    change('_observed_quota_receipt_removable_reasons', '_quota_unobservable_removable_reasons(route_payload) |', 'set() |')
    def run(label):
        env = os.environ.copy(); env.pop('PYTHONPATH',None)
        with tempfile.TemporaryDirectory(prefix='s08a-pycache-') as cache:
            env['PYTHONPYCACHEPREFIX'] = cache
            result = subprocess.run([sys.executable,'-m','pytest','-q',str(Path(__file__).resolve())],
                cwd=path.parents[3],env=env,text=True,capture_output=True)
        output = result.stdout+result.stderr
        print(json.dumps({'phase':label,'exit':result.returncode}),flush=True)
        print(output,flush=True)
        if label.endswith(':red'): assert 'AssertionError' in output or 'DID NOT RAISE' in output, 'behavioral failure required'
        return result.returncode
    assert run('original-green') == 0
    for label,mutant in controls:
        try:
            assert path.read_bytes() == original and mutant != original
            print(json.dumps({'control':label,'mutant_sha256':hashlib.sha256(mutant).hexdigest()}),flush=True)
            path.write_bytes(mutant)
            assert run(label+':red') == 1
        finally: path.write_bytes(original)
        assert path.read_bytes() == original and run(label+':restored-green') == 0
    print(json.dumps({'controls':len(controls),'all_killed_and_restored':True,
                     'source_sha256':hashlib.sha256(original).hexdigest()}),flush=True)


if __name__ == '__main__':
    import sys
    if sys.argv[1:] == ['--mutation-controls']: _mutations()
    else: raise SystemExit('use --mutation-controls')
