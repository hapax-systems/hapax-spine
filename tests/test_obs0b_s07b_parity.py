"""S07b offline Council cef55b52 parity. AGY_REF/model fields come from
Council tests/shared/test_quota_spend_ledger.py and config/platform-capability-
registry.json. Kimi/negative locators are synthetic. Snapshot clocks are separate
from locator grammar; model binding grants neither admission nor paid authority.
"""
import copy
from datetime import timedelta
import hashlib
import json
from pathlib import Path

import pytest

from hapax.spine import quota_spend_ledger as q
from test_obs0b_s05_parity import payload, snapshot, paid
from test_obs0b_s06_parity import NOW, reference, ledger as payg_ledger, snapshot as payg_snapshot
from test_obs0b_s07a_parity import REF as CLAUDE_REF, NOW as CLAUDE_NOW, HASHED_IGNORED

State = q.SubscriptionQuotaState
route_state = q.subscription_quota_state_for_route
WRITER = 'scripts/hapax-quota-telemetry-writer'
AGY_REF = ('relay-receipt:agy-quota-admission.yaml:witness:agy-gemini31pro-smoke-witness:'
           'supported_tool:hapax-agy-reviewer:model:gemini-4-argon:'
           'observed_at:2026-05-17T07:59:00Z:fresh_until:2026-05-17T08:05:00Z')
KIMI_REF = ('relay-receipt:kimi-quota-admission.yaml:witness:kimi-smoke-witness:'
            'supported_tool:hapax-kimi-quota-admission:model:kimi-code/k3:'
            'observed_at:2026-05-17T07:59:00Z:fresh_until:2026-05-17T08:05:00Z')
CASES = [
    ('agy.review.direct', 'google-antigravity-cli-agy', AGY_REF),
    ('kimi.interactive.lane', 'moonshot-kimi-code-managed', KIMI_REF),
    ('glmcp.review.direct', 'z_ai-glm-coding-plan', reference(payg=False)),
    *[(r, 'anthropic-claude-subscription', CLAUDE_REF.replace('claude.headless.full', r))
      for r in ('claude.headless.full', 'claude.review.opus', 'claude.interactive.full')],
]


def registry():
    def variant(effort):
        return dict(variant_id=f'agy@gemini-4-argon-{effort}',
            knobs_override=dict(model_id='gemini-4-argon', effort=effort),
            score_delta={}, scores_inherited_from=None,
            blocked_reasons=[] if effort == 'low' else ['measurement_only'])
    return dict(routes=[dict(route_id='agy.review.direct',
        execution_descriptor=dict(model_id='gemini-4-argon', effort='low'),
        descriptor_variants=[variant(e) for e in ('low', 'medium', 'high')])])


@pytest.fixture(autouse=True)
def binding(tmp_path, monkeypatch):
    import socket
    import subprocess
    def forbidden(*args, **kwargs):
        pytest.fail('reader attempted network, provider or subprocess action')
    monkeypatch.setattr(socket.socket, 'connect', forbidden)
    monkeypatch.setattr(socket, 'create_connection', forbidden)
    monkeypatch.setattr(subprocess, 'Popen', forbidden)
    monkeypatch.setenv('HAPAX_SPINE_CONFIG_DIR', str(tmp_path))
    p = tmp_path / 'platform-capability-registry.json'
    p.write_text(json.dumps(registry()))
    return p


def data(case, *, writer=True, **changes):
    route, provider, ref = case
    now = CLAUDE_NOW if route.startswith('claude.') else NOW
    raw = snapshot(route_id=route, provider=provider, evidence_refs=[ref],
                   captured_at=now-timedelta(minutes=1), fresh_until=now + timedelta(minutes=5))
    raw.update(changes)
    return q.QuotaSpendLedger.model_validate(payload(captured_at=now,
        generated_from=[WRITER] if writer else ['fixture:other'], quota_snapshots=[raw])), now


@pytest.mark.parametrize('case', CASES)
def test_each_declared_route_accepts_only_its_evidence(case):
    state, now = data(case)
    before = state.model_dump_json()
    assert route_state(state, case[0], now=now) == (
        State.FRESH, (case[2],))
    assert q._subscription_quota_state(state, now=now).value == 'fresh'
    assert not q.evaluate_paid_route_eligibility(state, q.PaidRouteRequest.model_validate(paid()), now=now).eligible
    assert state.model_dump_json() == before


@pytest.mark.parametrize('case', CASES)
@pytest.mark.parametrize('fault', ['writer', 'provider', 'foreign-ref', 'missing-ref', 'missing-expiry', 'expired'])
def test_admission_scope_and_freshness_refusals(case, fault):
    changes = {}; now = CLAUDE_NOW if case[0].startswith('claude.') else NOW
    if fault == 'provider': changes['provider'] = 'other-provider'
    if fault == 'foreign-ref': changes['evidence_refs'] = [KIMI_REF if case[0] != 'kimi.interactive.lane' else AGY_REF]
    if fault == 'missing-ref': changes['evidence_refs'] = ['fixture:unobserved']
    if fault == 'missing-expiry': changes['fresh_until'] = None
    if fault == 'expired': changes['fresh_until'] = now
    state, now = data(case, writer=fault != 'writer', **changes)
    result, refs = route_state(state, case[0], now=now)
    assert result.value == ('stale' if fault == 'expired' else 'unknown')
    reason = ('fresh_until_expired' if fault == 'expired' else 'fresh_until_missing'
              if fault == 'missing-expiry' else 'untrusted_' + (
                  'claude' if case[0].startswith('claude.') else case[0].split('.')[0]) + '_admission_evidence')
    assert any(reason in ref for ref in refs)
    assert q._subscription_quota_state(state, now=now) is not State.FRESH


@pytest.mark.parametrize('family,ref', [('agy', AGY_REF), ('kimi', KIMI_REF)])
@pytest.mark.parametrize('fault', ['label', 'prefix', 'tool', 'model', 'observed', 'expiry',
                                  'witness-missing', 'witness-duplicate', 'witness-shape', 'witness-secret'])
def test_locator_guards(family, ref, fault):
    witness = ref.split(':witness:')[1].split(':')[0]
    replacements = {
        'label': (family+'-quota-admission.yaml', 'ordinary.yaml'),
        'prefix': ('relay-receipt:', 'prefix:relay-receipt:'),
        'tool': ('supported_tool:hapax-', 'supported_tool:other-'),
        'model': ('model:', 'wrong-model:'), 'observed': ('observed_at:', 'reported_at:'),
        'expiry': ('fresh_until:', 'expires_at:'), 'witness-missing': (witness, ''),
        'witness-duplicate': (':observed_at:', ':witness:second:supported_tool:other:observed_at:'),
        'witness-shape': (witness, 'a b'), 'witness-secret': (witness, 'sk-fixture'),
    }
    bad = ref.replace(*replacements[fault])
    assert not getattr(q, f'_is_{family}_admission_evidence_ref')(bad)
    state, now = data(CASES[0 if family == 'agy' else 1], evidence_refs=[bad])
    result, refs = route_state(state, family+'.'+('review.direct' if family == 'agy' else 'interactive.lane'), now=now)
    assert result.value == 'unknown'
    if fault == 'witness-secret':
        assert bad not in refs and any('redacted-secretish-sha256:' in r for r in refs)


@pytest.mark.parametrize('family,ref', [('agy', AGY_REF), ('kimi', KIMI_REF)])
def test_safe_hashed_labels_and_aliases(family, ref):
    fn = getattr(q, f'_is_{family}_admission_evidence_ref')
    assert fn(ref.replace(family+'-quota-admission.yaml', 'unsafe-receipt-name-sha256:0123456789abcdef'))
    assert not fn(ref.replace(family+'-quota-admission.yaml', 'unsafe-receipt-name-sha256:xyz'))
    if family == 'agy':
        assert fn(ref.replace('model:gemini-4-argon:', 'model:gemini-4-argon-low:'))
        assert not fn(ref.replace('model:gemini-4-argon:', 'model:gemini-4-argon-medium:'))
    else:
        assert not fn(ref.replace('model:kimi-code/k3:', 'model:kimi-code/k2:'))


@pytest.mark.parametrize('secret', ['sk-fixture', 'api_key', 'a'*32])
def test_kimi_secretish_label_refused(secret):
    assert not q._is_kimi_admission_evidence_ref(KIMI_REF.replace('kimi-quota-admission.yaml', f'kimi-quota-admission-{secret}.yaml'))


@pytest.mark.parametrize('fault', ['missing-map', 'unknown-bounded-route'])
def test_missing_provider_mapping_and_unhandled_route_fail_closed(monkeypatch, fault):
    state, _ = data(CASES[1])
    snap = state.quota_snapshots[0]
    if fault == 'missing-map':
        monkeypatch.setattr(q, 'RECEIPT_BOUNDED_SUBSCRIPTION_PROVIDERS', {})
    else:
        snap = snap.model_copy(update={'route_id':'future.route'})
        monkeypatch.setattr(q, 'RECEIPT_BOUNDED_SUBSCRIPTION_ROUTES', {'future.route'})
        monkeypatch.setattr(q, 'RECEIPT_BOUNDED_SUBSCRIPTION_PROVIDERS', {'future.route':snap.provider})
    assert q._subscription_quota_missing_required_admission_evidence(state, snap)
    assert q._subscription_quota_untrusted_admission_evidence_reason(snap) == (
        'untrusted_route_admission_evidence' if fault == 'unknown-bounded-route' else 'untrusted_kimi_admission_evidence')


def test_nonfresh_and_unbounded_routes_preserve_scope():
    for status in ('unknown', 'stale', 'exhausted'):
        state, now = data(CASES[1], writer=False, subscription_quota_state=status)
        assert not q._subscription_quota_missing_required_admission_evidence(state, state.quota_snapshots[0])
        assert route_state(state, CASES[1][0], now=now)[0].value == status
    state, now = data(('codex.headless.full','codex','fixture:quota'), writer=False)
    assert route_state(state, 'codex/headless/full', now=now)[0].value == 'fresh'


@pytest.mark.parametrize('state', ['unknown', 'stale', 'exhausted'])
def test_route_strict_reduction_differs_from_any_capacity(state):
    good, now = data(CASES[1]); a = good.quota_snapshots[0]
    b = a.model_copy(update={'snapshot_id':'other', 'subscription_quota_state':State(state)})
    ledger = good.model_copy(update={'quota_snapshots':(a,b)})
    assert q._subscription_quota_state(ledger, now=now).value == 'fresh'
    assert route_state(ledger, CASES[1][0], now=now)[0].value == state


@pytest.mark.parametrize('fault', ['route', 'measurement', 'pool'])
def test_route_selection_excludes_unrelated_observations(fault):
    state, now = data(CASES[1]); snap = state.quota_snapshots[0]
    changes = {'route_id':'other.route'} if fault == 'route' else (
        {'admission_compatible':False, 'route_id':None} if fault == 'measurement'
        else {'capacity_pool':q.CapacityPool.LOCAL_COMPUTE})
    state = state.model_copy(update={'quota_snapshots':(snap.model_copy(update=changes),)})
    assert route_state(state, CASES[1][0], now=now) == (
        State.UNKNOWN, ('quota-snapshot:kimi.interactive.lane:missing',))


def test_normalized_route_and_no_evidence_projection():
    case = (CASES[1][0].replace('.', '/'), *CASES[1][1:]); state, now = data(case)
    assert route_state(state, ' kimi/interactive/lane ', now=now)[0].value == 'fresh'
    a = state.quota_snapshots[0].model_copy(update={'evidence_refs':(), 'subscription_quota_state':State.UNKNOWN})
    state = state.model_copy(update={'quota_snapshots':(a,)})
    assert route_state(state, CASES[1][0], now=now)[1] == ('quota-snapshot:kimi.interactive.lane:no-evidence',)


@pytest.mark.parametrize('ref', [HASHED_IGNORED, 'relay-receipt:claude-subscription-quota-admission.yaml:ignored:expired'])
def test_safe_ignored_is_retained_but_never_admission(ref):
    state, now = data(CASES[3], evidence_refs=[ref])
    status, refs = route_state(state, CASES[3][0], now=now)
    assert status.value == 'unknown' and ref in refs
    assert any('claude_receipt_not_current' in r for r in refs)


@pytest.mark.parametrize('middle', ['witness:sk-fixture:', 'billing:cus123:', 'lane:cx-teal:', 'witness:benign:'])
def test_ignored_locator_repair_survives_consumer_wiring(middle):
    bad = 'relay-receipt:claude-subscription-quota-admission.yaml:' + middle + 'ignored:expired'
    state, now = data(CASES[3], evidence_refs=[bad])
    status, refs = route_state(state, CASES[3][0], now=now)
    assert status.value == 'unknown' and bad not in refs
    assert any('redacted-' in r for r in refs)


def test_redaction_route_and_secret_precedence():
    bad = CLAUDE_REF.replace('account-live-quota:observed', 'account-live-quota:unobserved')
    digest = hashlib.sha256(bad.encode()).hexdigest()[:16]
    assert q._redact_quota_evidence_ref('claude.headless.full', bad) == 'quota-evidence-ref:redacted-untrusted-claude-admission-sha256:'+digest
    assert q._redact_quota_evidence_ref('other.route', bad) == bad
    bad = bad + ':sk-fixture'; digest = hashlib.sha256(bad.encode()).hexdigest()[:16]
    assert q._redact_quota_evidence_ref('claude.headless.full', bad) == 'quota-evidence-ref:redacted-secretish-sha256:'+digest


@pytest.mark.parametrize('minutes', [-6, 10])
def test_claude_receipt_clock_remains_independent_of_snapshot_expiry(minutes):
    state, now = data(CASES[3], fresh_until=CLAUDE_NOW+timedelta(hours=1))
    status, refs = route_state(state, CASES[3][0], now=now+timedelta(minutes=minutes))
    assert status.value == 'stale' and any('claude_receipt_not_current' in r for r in refs)


def test_payg_refusal_and_explanatory_evidence_preserved():
    state = payg_ledger(quota_snapshots=[payg_snapshot()], generated_from=[WRITER])
    status, refs = route_state(state, 'glmcp.review.direct', now=NOW)
    assert status.value == 'unknown'
    assert any('payg_spend_gate_missing_or_ineligible' in r for r in refs)
    for key in ('primary_error_class', 'quota_wall_evidence_ref'):
        bad = reference().replace(key+':', key+'::'+key+':')
        assert not q._is_glmcp_admission_evidence_ref(bad)


def test_binding_resolves_at_use_and_measurement_is_not_admission(binding):
    assert q.agy_review_model_binding() == ('gemini-4-argon-low', 'gemini-4-argon')
    for effort in ('medium', 'high'):
        model = 'gemini-4-argon-'+effort
        assert q.agy_measurement_model(model) == model
        assert not q._is_agy_admission_evidence_ref(AGY_REF.replace('model:gemini-4-argon:', f'model:{model}:'))
    r = registry(); r['routes'][0]['execution_descriptor']['effort'] = 'high'
    r['routes'][0]['descriptor_variants'][2]['blocked_reasons'] = []
    binding.write_text(json.dumps(r))
    assert q.agy_review_model_binding() == ('gemini-4-argon-high', 'gemini-4-argon')
    assert not q._is_agy_admission_evidence_ref(AGY_REF.replace('model:gemini-4-argon:', 'model:gemini-4-argon-low:'))


@pytest.mark.parametrize('fault', ['missing', 'json', 'shape', 'no-route', 'two-routes', 'no-variant',
    'two-variants', 'blocked', 'blocked-type', 'prefix', 'model', 'base', 'effort', 'foreign-model', 'foreign-effort'])
def test_review_binding_refuses_without_fallback(binding, fault):
    r = registry(); route = r['routes'][0]; v = route['descriptor_variants'][0]
    if fault == 'no-route': r['routes'] = []
    if fault == 'two-routes': r['routes'].append(copy.deepcopy(route))
    if fault == 'no-variant': route['descriptor_variants'] = []
    if fault == 'two-variants': route['descriptor_variants'].append(copy.deepcopy(v))
    if fault == 'blocked': v['blocked_reasons'] = ['measurement_only']
    if fault == 'blocked-type': v['blocked_reasons'] = ''
    if fault == 'prefix': v['variant_id'] = 'gemini-4-argon-low'
    if fault == 'model': v['variant_id'] = 'agy@other-model'
    if fault == 'base':
        route['execution_descriptor']['model_id'] = 'other-model'; v['knobs_override']['model_id'] = 'other-model'
    if fault == 'effort': route['execution_descriptor']['effort'] = 'undeclared'
    if fault in {'foreign-model', 'foreign-effort'}:
        route['descriptor_variants'] = [v]
        v['knobs_override']['model_id' if fault == 'foreign-model' else 'effort'] = 'other'
    binding.write_text('{' if fault == 'json' else json.dumps([] if fault == 'shape' else r))
    if fault == 'missing': binding.unlink()
    with pytest.raises(ValueError, match='repair the governed.*no model fallback'):
        q.agy_review_model_binding()


@pytest.mark.parametrize('fault', ['missing', 'json', 'shape', 'two-routes', 'no-variant', 'two-variants',
    'blocked', 'inherited', 'scores', 'effort', 'mismatch', 'non-gemini'])
def test_measurement_leaf_refuses_without_fallback(binding, fault):
    r = registry(); route = r['routes'][0]; v = route['descriptor_variants'][1]; model = 'gemini-4-argon-medium'
    if fault == 'two-routes': r['routes'].append(copy.deepcopy(route))
    if fault == 'no-variant': route['descriptor_variants'] = []
    if fault == 'two-variants': route['descriptor_variants'].append(copy.deepcopy(v))
    if fault == 'blocked': v['blocked_reasons'] = []
    if fault == 'inherited': v['scores_inherited_from'] = 'agy.review.direct'
    if fault == 'scores': v['score_delta'] = {'quality':0.8}
    if fault == 'effort':
        model = 'gemini-4-argon-ultra'; v['variant_id'] = 'agy@'+model; v['knobs_override']['effort'] = 'ultra'
    if fault == 'mismatch': v['knobs_override']['model_id'] = 'gemini-other'
    if fault == 'non-gemini':
        model = 'other-medium'; v['variant_id'] = 'agy@'+model; v['knobs_override']['model_id'] = 'other'
    binding.write_text('{' if fault == 'json' else json.dumps([] if fault == 'shape' else r))
    if fault == 'missing': binding.unlink()
    with pytest.raises(ValueError, match='declare an unscored measurement_only.*no model fallback'):
        q.agy_measurement_model(model)


@pytest.mark.parametrize('fault', ['absent', 'malformed', 'valid'])
def test_resolved_ledger_retains_source_and_error(tmp_path, fault):
    fixtures = tmp_path/'fixtures.json'; live = tmp_path/'live.json'
    fixtures.write_text(q.QuotaSpendLedger.model_validate(payload(captured_at=NOW)).model_dump_json())
    if fault != 'absent': live.write_text('{' if fault == 'malformed' else fixtures.read_text())
    result = q.load_quota_spend_ledger_resolved(live_path=live, fixtures_path=fixtures)
    assert result.source == ('live' if fault == 'valid' else 'fixtures')
    assert result.path == (live if fault == 'valid' else fixtures)
    assert (result.live_error is not None) == (fault == 'malformed')
    if result.live_error: assert str(live) in result.live_error
    assert result.ledger.ledger_stale(NOW+timedelta(days=1))


@pytest.mark.parametrize('raw', ['{', '[]', '{}'])
def test_bad_fixtures_refuse_typed(tmp_path, raw):
    p = tmp_path/'invalid.json'; p.write_text(raw)
    with pytest.raises(q.QuotaSpendLedgerError, match=str(p)):
        q.load_quota_spend_ledger(p)
    with pytest.raises(q.QuotaSpendLedgerError):
        q.load_quota_spend_ledger_resolved(live_path=tmp_path/'absent', fixtures_path=p)


def test_declared_config_binding_and_explicit_path_precedence(tmp_path, monkeypatch):
    p = tmp_path/'explicit.json'; p.write_text(q.QuotaSpendLedger.model_validate(payload(captured_at=NOW)).model_dump_json())
    monkeypatch.delenv('HAPAX_SPINE_CONFIG_DIR')
    assert q.load_quota_spend_ledger(p).captured_at == NOW
    with pytest.raises(RuntimeError, match='HAPAX_SPINE_CONFIG_DIR'):
        q.load_quota_spend_ledger()
    for fn, args in [(q.agy_review_model_binding, ()), (q.agy_measurement_model, ('gemini-4-argon-medium',))]:
        with pytest.raises(RuntimeError, match='HAPAX_SPINE_CONFIG_DIR'): fn(*args)
    monkeypatch.setenv('HAPAX_SPINE_CONFIG_DIR', str(tmp_path))
    (tmp_path/'quota-spend-ledger-fixtures.json').write_text(p.read_text())
    assert q.load_quota_spend_ledger().captured_at == NOW
    assert q.load_quota_spend_ledger_resolved(live_path=tmp_path/'absent').source == 'fixtures'


@pytest.mark.parametrize('states,expected', [([], 'unknown'), (['unknown'], 'unknown'),
    (['stale'], 'stale'), (['exhausted','stale'], 'exhausted'),
    (['fresh','exhausted'], 'fresh')])
def test_aggregate_precedence(states, expected):
    ledger, now = data(CASES[1]); snap = ledger.quota_snapshots[0]
    ledger = ledger.model_copy(update={'quota_snapshots':tuple(snap.model_copy(update={
        'snapshot_id':str(i), 'subscription_quota_state':State(s)})
        for i,s in enumerate(states))})
    assert q._subscription_quota_state(ledger, now=now).value == expected


def _mutations():
    """Red/exact restore/green; excludes redundant hash-label and missing-provider prechecks.
    """
    import ast, os, subprocess, sys, tempfile
    path = Path(__file__).resolve().parents[1]/'src/hapax/spine/quota_spend_ledger.py'
    assert Path(q.__file__).resolve() == path
    original = path.read_bytes(); source = original.decode(); tree = ast.parse(source)
    lines = source.splitlines(keepends=True); offsets = [0]
    for line in lines: offsets.append(offsets[-1]+len(line))
    controls = []
    def change(label, node, code):
        a = offsets[node.lineno-1]+node.col_offset
        b = offsets[node.end_lineno-1]+node.end_col_offset
        controls.append((label, (source[:a]+code+source[b:]).encode()))
    for fn in (n for n in tree.body if isinstance(n, ast.FunctionDef)):
        for n in ast.walk(fn):
            code = ast.get_source_segment(source, n)
            if isinstance(n, ast.BoolOp) and fn.name in {
                '_is_agy_admission_evidence_ref', '_is_kimi_admission_evidence_ref',
                '_has_safe_agy_admission_witness', '_has_safe_kimi_admission_witness',
                'agy_measurement_model', 'agy_review_model_binding'}:
                if isinstance(n.op, ast.And):
                    for i,v in enumerate(n.values): change(fn.name+str(n.lineno)+str(i), v, 'True')
                elif fn.name in {'agy_measurement_model', 'agy_review_model_binding'}:
                    for i,v in enumerate(n.values): change(fn.name+str(n.lineno)+str(i), v, 'False')
            if isinstance(n, ast.If) and fn.name in {
                '_effective_subscription_quota_state', '_subscription_quota_missing_required_admission_evidence',
                '_has_safe_agy_admission_witness', '_has_safe_kimi_admission_witness',
                'agy_review_model_binding', 'agy_measurement_model'}:
                if not isinstance(n.test, ast.BoolOp) and ast.get_source_segment(source,n.test) != 'expected_provider is None':
                    change(fn.name+':if'+str(n.lineno), n.test, 'False')
            if isinstance(n, ast.If) and fn.name == '_redact_quota_evidence_ref':
                change('redaction'+str(n.lineno), n.test, 'False')
            if isinstance(n, ast.Assign) and fn.name == 'subscription_quota_state_for_route' and n.targets[0].id in {
                'noncurrent_receipt_refs', 'untrusted_fresh_refs', 'missing_payg_spend_gate_refs'}:
                change(n.targets[0].id, n.value, '()')
            if isinstance(n, ast.Call) and fn.name == 'subscription_quota_state_for_route' and code == '_redact_quota_evidence_ref(normalized_route_id, ref)':
                change('consumer-redaction', n, 'ref')
            if isinstance(n, ast.keyword) and fn.name == 'load_quota_spend_ledger_resolved' and n.arg in {'source','live_error'}:
                change('loader-'+n.arg+str(n.lineno), n.value, '"fixtures"' if code == 'source="live"' else '"live"' if n.arg == 'source' else 'None')
    def run(label):
        env = os.environ.copy(); env.pop('PYTHONPATH', None)
        with tempfile.TemporaryDirectory(prefix='s07b-pycache-') as cache:
            env['PYTHONPYCACHEPREFIX'] = cache
            r = subprocess.run([sys.executable, '-m', 'pytest', '-q', str(Path(__file__).resolve())],
                cwd=path.parents[3], env=env, text=True, capture_output=True)
        output = r.stdout+r.stderr
        print(json.dumps({'phase':label,'exit':r.returncode}), flush=True)
        print(output, flush=True)
        if label.endswith(':red'): assert 'AssertionError' in output or 'DID NOT RAISE' in output, 'behavioral failure required'
        return r.returncode
    assert run('original-green') == 0
    for label, mutant in controls:
        try:
            assert path.read_bytes() == original and mutant != original
            print(json.dumps({'control':label,'mutant_sha256':hashlib.sha256(mutant).hexdigest()}), flush=True)
            path.write_bytes(mutant)
            assert run(label+':red') == 1
        finally: path.write_bytes(original)
        assert path.read_bytes() == original and run(label+':restored-green') == 0
    print(json.dumps({'controls':len(controls),'all_killed_and_restored':True,
                     'source_sha256':hashlib.sha256(original).hexdigest()}), flush=True)


if __name__ == '__main__':
    import sys
    if sys.argv[1:] == ['--mutation-controls']: _mutations()
    else: raise SystemExit('use --mutation-controls')
