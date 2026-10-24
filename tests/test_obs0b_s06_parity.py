"""Offline S06 cases from Council cef55b52 tests/shared/test_quota_spend_ledger.py.
The current-data checker reuses S05; no settlement or provider call.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
import json
from pathlib import Path

import pytest
from pydantic import ValidationError
from hapax.spine import quota_spend_ledger as q
from test_obs0b_s05_parity import payload, paid

NOW = datetime(2026, 5, 17, 8, tzinfo=UTC)
FIELDS = ('provider_balance_usd', 'provider_balance_observed_at',
          'provider_balance_covers_spend_before', 'provider_balance_evidence_ref')
BALANCE = dict(zip(FIELDS, ('100.00', NOW - timedelta(minutes=1),
                          NOW - timedelta(minutes=2), 'fixture:provider-balance')))
ROUTE = 'glmcp.review.direct'


def budget(**changes):
    raw = dict(budget_id='tb-20260517-reader', authority_case='CASE-READER-TEST',
        approved_by='operator', created_at=NOW-timedelta(hours=1), expires_at=NOW+timedelta(hours=1),
        capacity_pool='api_paid_spend', providers_allowed=['z_ai'],
        profiles_allowed=['glmcp-review-direct'], task_classes_allowed=['independent-review'],
        quality_floors_allowed=['frontier_review_required'], total_cap_usd='100.00',
        per_task_cap_usd='2.00', daily_cap_usd='20.00', subscription_path_checked_at=NOW,
        reason_subscription_path_not_used='fixture Coding Plan quota exhausted')
    raw.update(changes); return raw


def spend(**changes):
    raw = dict(spend_id='spend-20260517T075900Z-glmcp-payg-review-test', task_id='task-a',
        authority_case='CASE-READER-TEST', route_id=ROUTE, capacity_pool='api_paid_spend',
        budget_id='tb-20260517-reader', provider='z_ai', model_or_engine='glm-5.2',
        model_id='z_ai-glm-5.2', auth_surface='api_key', quality_floor='frontier_review_required',
        quality_preservation_reason='fixture reader test', spend_reason='quota_exhaustion',
        estimated_cost_usd='0.05', created_at=NOW-timedelta(minutes=3),
        reconcile_by=NOW+timedelta(hours=1), reconciliation_state='pending')
    raw.update(changes); return raw


def ledger(**changes):
    raw = payload(captured_at=NOW, transition_budgets=[budget()], spend_receipts=[])
    raw.update(changes); return q.QuotaSpendLedger.model_validate(raw)


def request(**changes):
    raw = paid(route_id=ROUTE, provider='z_ai', profile='glmcp-review-direct')
    raw.update(changes); return q.PaidRouteRequest.model_validate(raw)


def reference(*, payg=True, model='glm-5.2', witness='glmcp-payg-spend-20260517t075900z-test.yaml'):
    endpoint='https://api.z.ai/api/paas/v4' if payg else 'https://api.z.ai/api/coding/paas/v4'
    wall=('primary_error_class:quota_exhausted:quota_wall_evidence_ref:cx-glmcp-quota-wall.yaml:'
          if payg else '')
    return (f'relay-receipt:glmcp-quota-admission.yaml:witness:{witness}:'
        f'supported_tool:hapax-glmcp-reviewer:endpoint:{endpoint}:model:{model}:{wall}'
        'observed_at:2026-05-17T07:59:00Z:fresh_until:2026-05-17T08:05:00Z')


def snapshot(ref=None, **changes):
    raw = dict(snapshot_id='quota-reader-glmcp', captured_at=NOW-timedelta(minutes=1),
        fresh_until=NOW+timedelta(minutes=5), route_id=ROUTE, provider='z_ai-glm-coding-plan',
        capacity_pool='subscription_quota', subscription_quota_state='fresh',
        evidence_refs=[reference() if ref is None else ref], operator_visible_reason='fixture observation')
    raw.update(changes); return q.QuotaSnapshot.model_validate(raw)


@pytest.fixture(autouse=True)
def no_external_actions(monkeypatch):
    import socket, subprocess
    def forbidden(*args, **kwargs): pytest.fail('reader attempted network or subprocess action')
    monkeypatch.setattr(socket.socket, 'connect', forbidden)
    monkeypatch.setattr(socket, 'create_connection', forbidden)
    monkeypatch.setattr(subprocess, 'Popen', forbidden)


def test_balance_roundtrip_and_absent_fields():
    old=q.TransitionBudget.model_validate(budget())
    assert all(k not in old.model_dump() for k in FIELDS)
    explicit=q.TransitionBudget.model_validate(budget(**dict.fromkeys(FIELDS)))
    assert explicit.model_dump_json()==old.model_dump_json()
    current=q.TransitionBudget.model_validate(budget(**BALANCE))
    assert current.provider_balance_usd==Decimal('100.00')
    assert all(k in current.model_dump() for k in FIELDS)
    assert q.TransitionBudget.model_validate_json(current.model_dump_json())==current


@pytest.mark.parametrize('field', FIELDS)
def test_partial_balance_proof_refuses(field):
    raw=budget(**BALANCE); raw[field]=None
    with pytest.raises(ValidationError, match='complete'): q.TransitionBudget.model_validate(raw)


@pytest.mark.parametrize('change,message', [
    ({'provider_balance_evidence_ref':' '}, 'complete'),
    ({'provider_balance_usd':'99.99'}, 'exceeds'),
    ({'provider_balance_covers_spend_before':NOW}, 'after it was observed'),
    ({'provider_balance_observed_at':NOW.replace(tzinfo=None)}, 'timezone-aware'),
    ({'provider_balance_covers_spend_before':NOW.replace(tzinfo=None)}, 'timezone-aware'),
    ({'provider_balance_evidence_ref':'/home/person/balance.png'}, 'repo-relative'),
    ({'provider_balance_usd':'-1'}, 'greater than or equal'),
])
def test_invalid_balance_proof_refuses(change,message):
    with pytest.raises(ValidationError, match=message):
        q.TransitionBudget.model_validate(budget(**{**BALANCE, **change}))


@pytest.mark.parametrize('field', ['providers_allowed','profiles_allowed',
                                 'task_classes_allowed','quality_floors_allowed'])
def test_trust_cannot_define_budget(field):
    with pytest.raises(ValidationError, match='agentic-trust'):
        q.TransitionBudget.model_validate(budget(**{field:['agentic-trust-evidence-receipt-v1:fixture']}))


@pytest.mark.parametrize('change,covered', [
    ({},True), ({'budget_id':'tb-20260517-reader'},False),
    ({'provider':'another-provider'},False),
    ({'created_at':BALANCE['provider_balance_covers_spend_before']},False),
    ({'created_at':NOW},False),
])
def test_balance_coverage_boundaries(change,covered):
    b=q.TransitionBudget.model_validate(budget(**BALANCE))
    r=q.SpendReceipt.model_validate(spend(**{'budget_id':'tb-20260516-old',**change}))
    assert b.provider_balance_covers(r) is covered
    assert not q.TransitionBudget.model_validate(budget()).provider_balance_covers(r)


def test_task_hash_roundtrip():
    old=q.SpendReceipt.model_validate(spend())
    assert 'task_hash' not in old.model_dump()
    assert q.SpendReceipt.model_validate(spend(task_hash=None)).model_dump_json()==old.model_dump_json()
    hashed=q.SpendReceipt.model_validate(spend(task_hash='sha256:'+'a'*64))
    assert hashed.model_dump()['task_hash']=='sha256:'+'a'*64
    assert q.SpendReceipt.model_validate_json(hashed.model_dump_json())==hashed


@pytest.mark.parametrize('value', ['sha256:'+'A'*64,'sha256:'+'a'*63,'sha256:'+'a'*65,'a'*64])
def test_task_hash_refusal(value):
    with pytest.raises(ValidationError):q.SpendReceipt.model_validate(spend(task_hash=value))


def settled(**changes):
    return spend(**{'reconciliation_state':'settled_by_provider_balance', 'reconciled_at':NOW,
        'reconciliation_reason':'fixture:reviewed-balance', **changes})


def test_settlement_read_is_inert():
    r=q.SpendReceipt.model_validate(settled())
    before=r.model_dump_json()
    assert r.actual_cost_usd is None and r.cost_against_cap()==Decimal('0.05')
    assert not r.is_unreconciled_overdue(NOW+timedelta(days=2)) and not r.is_frozen_refused()
    assert r.reconciliation_state.value=='settled_by_provider_balance'
    assert r.model_dump_json()==before


@pytest.mark.parametrize('change,message', [
    ({'actual_cost_usd':'0.05','cap_remaining_usd':'1.95'}, 'cannot claim actual'),
    ({'reconciled_at':None}, 'requires its evidence'),
    ({'reconciliation_reason':None}, 'requires its evidence'),
    ({'reconciled_at':NOW.replace(tzinfo=None)}, 'timezone-aware'),
])
def test_settlement_refusals(change,message):
    with pytest.raises(ValidationError,match=message):q.SpendReceipt.model_validate(settled(**change))


def test_zero_actual_precedes_estimate():
    r=q.SpendReceipt.model_validate(settled(reconciliation_state='reconciled',
        actual_cost_usd='0',cap_remaining_usd='1'))
    assert r.cost_against_cap()==0


@pytest.mark.parametrize('cost,eligible', [('0.05',True),('0.050001',False)])
def test_accumulated_task_cap(cost,eligible):
    prior=spend(estimated_cost_usd=cost)
    other=spend(spend_id='spend-20260517T075900Z-other',task_id='task-aa',estimated_cost_usd='5')
    state=ledger(transition_budgets=[budget(per_task_cap_usd='0.10')],spend_receipts=[prior,other])
    before=state.model_dump_json();decision=q.evaluate_paid_route_eligibility(state,request(),now=NOW)
    assert decision.eligible is eligible
    if eligible:assert decision.cap_remaining_usd==Decimal('0')
    else:assert decision.state=='refused_exhausted_budget'
    assert state.model_dump_json()==before


@pytest.mark.parametrize('state', ['pending','frozen_refused'])
def test_read_never_settles_spend(state):
    older=budget(budget_id='tb-20260516-old',expires_at=NOW-timedelta(minutes=1))
    r=spend(budget_id=older['budget_id'],reconcile_by=NOW-timedelta(minutes=1),
        reconciliation_state=state)
    if state=='frozen_refused':r.update(reconciled_at=NOW,reconciliation_reason='fixture:refused')
    data=ledger(transition_budgets=[budget(**BALANCE),older],spend_receipts=[r])
    before=data.model_dump_json();decision=q.evaluate_paid_route_eligibility(data,request(),now=NOW)
    assert not decision.eligible and decision.state=='refused_budget_gate'
    assert ('unreconciled' if state=='pending' else 'frozen/refused') in ' '.join(decision.blocking_reasons)
    assert data.model_dump_json()==before


@pytest.mark.parametrize('change', [{'per_task_cap_usd':'0.01'}, {'total_cap_usd':'0.01'},
                                  {'daily_cap_usd':'0.01'}])
def test_each_cap_can_independently_refuse(change):
    decision=q.evaluate_paid_route_eligibility(ledger(transition_budgets=[budget(**change)]),request(),now=NOW)
    assert not decision.eligible and decision.state=='refused_exhausted_budget'


@pytest.mark.parametrize('kind', ['stale','expired','missing'])
def test_read_time_budget_refusals(kind):
    changes={'captured_at':NOW-timedelta(days=1)} if kind=='stale' else {
        'transition_budgets':[] if kind=='missing' else [budget(expires_at=NOW)]}
    decision=q.evaluate_paid_route_eligibility(ledger(**changes),request(),now=NOW)
    assert not decision.eligible


def test_request_identity_and_amount():
    r=q._glmcp_payg_budget_request('task-a')
    assert r==request() and r.estimated_cost_usd==Decimal('0.05')
    with pytest.raises(ValidationError):q._glmcp_payg_budget_request('')


@pytest.mark.parametrize('payg', [False,True])
@pytest.mark.parametrize('model', ['glm-5.2','glm-5.3'])
def test_current_glm_witnesses(payg,model):
    ref=reference(payg=payg,model=model)
    assert q._is_glmcp_admission_evidence_ref(ref)
    assert q._is_glmcp_payg_admission_evidence_ref(ref) is payg


@pytest.mark.parametrize('field,value', [
    ('error',None), ('wall',None), ('error','transport_error'), ('wall','sk-fixture'),
    ('wall','/private/path'), ('error','quota_exhausted:primary_error_class:quota_exhausted'),
    ('wall','wall.yaml:quota_wall_evidence_ref:wall2.yaml'),
    ('error',''), ('wall',''),
    ('error',':primary_error_class:quota_exhausted'),
    ('error','quota_exhausted:primary_error_class:'),
    ('wall',':quota_wall_evidence_ref:wall.yaml'),
    ('wall','wall.yaml:quota_wall_evidence_ref:'),
    ('endpoint','https://api.z.ai/api/paas/v4:endpoint:https://api.z.ai/api/coding/paas/v4'),
])
def test_payg_field_refusal(field,value):
    key,old={'error':('primary_error_class','quota_exhausted'),
        'wall':('quota_wall_evidence_ref','cx-glmcp-quota-wall.yaml'),
        'endpoint':('endpoint','https://api.z.ai/api/paas/v4')}[field]
    ref=reference().replace(f'{key}:{old}:','' if value is None else f'{key}:{value}:')
    assert not q._has_glmcp_payg_witness_fields_for_endpoint(ref)
    assert not q._is_glmcp_admission_evidence_ref(ref)


@pytest.mark.parametrize('payg', [False,True])
@pytest.mark.parametrize('extra', ['primary_error_class:quota_exhausted:',
    'quota_wall_evidence_ref:wall.yaml:', 'primary_error_class::', 'quota_wall_evidence_ref::',
    'primary_error_class:', 'quota_wall_evidence_ref:'])
def test_rejects_extra_payg_fields(payg,extra):
    ref=reference(payg=payg)+':'+extra
    assert not q._has_glmcp_payg_witness_fields_for_endpoint(ref)
    assert not q._is_glmcp_admission_evidence_ref(ref)


@pytest.mark.parametrize('old,new', [
    ('glmcp-quota-admission.yaml','not-admission.yaml'), ('model:glm-5.2:','model:glm-5:'),
    ('supported_tool:hapax-glmcp-reviewer:','supported_tool:other-tool:'),
    ('witness:glmcp-payg-spend-20260517t075900z-test.yaml:','witness:sk-fixture:'),
    ('observed_at:','reported_at:'), ('fresh_until:','expires_at:'),
])
def test_admission_reference_outer_guards(old,new):
    assert not q._is_glmcp_admission_evidence_ref(reference().replace(old,new))


@pytest.mark.parametrize('change', [{'route_id':'other.route'}, {'provider':'other-provider'},
    {'capacity_pool':'subscription_quota'}, {'spend_reason':'burst_capacity'}])
def test_foreign_spend_refusal(change):
    r=q.SpendReceipt.model_validate(spend(**change))
    assert q._glmcp_payg_spend_receipt_witness_refs(r)==set()
    assert q._matching_glmcp_payg_spend_receipts(ledger(spend_receipts=[spend(**change)]),snapshot())==()


def test_explicit_spend_witnesses():
    r=q.SpendReceipt.model_validate(spend());data=ledger(spend_receipts=[spend()])
    assert q._glmcp_payg_spend_receipt_witness_refs(r)=={r.spend_id,'glmcp-payg-spend-20260517t075900z-test.yaml'}
    for ref in [reference()]:
        assert q._matching_glmcp_payg_spend_receipts(data,snapshot(ref))==(r,)
    for ref in [reference(witness=r.spend_id),reference(witness='some-other-receipt.yaml'),reference(payg=False),
                reference().replace('quota_exhausted','transport_error')]:
        assert q._matching_glmcp_payg_spend_receipts(data,snapshot(ref))==()


@pytest.mark.parametrize('case', ['valid','no_budget','no_receipt','no_gate','wrong_budget','exhausted','expired'])
def test_integration_payg_gate(case):
    b=budget();r=spend()
    refs=[reference(),'spend-gate:glmcp.review.direct:eligible_active_budget',
          'spend-gate-budget:tb-20260517-reader']
    if case=='no_gate':refs=refs[:1]
    if case=='wrong_budget':r['budget_id']='tb-20260516-other'
    if case=='exhausted':b['per_task_cap_usd']='0.05'
    if case=='expired':b['expires_at']=NOW
    budgets=[b]+([budget(budget_id='tb-20260516-other',expires_at=NOW)] if case=='wrong_budget' else [])
    data=ledger(transition_budgets=[] if case=='no_budget' else budgets,
        spend_receipts=[] if case in {'no_receipt','no_budget'} else [r],quota_snapshots=[snapshot(evidence_refs=refs)],
        generated_from=['scripts/hapax-quota-telemetry-writer'])
    before=data.model_dump_json()
    expected='fresh' if case=='valid' else 'unknown'
    state,_=q.subscription_quota_state_for_route(data,ROUTE,now=NOW)
    assert state.value==expected
    assert q.build_dashboard(data,now=NOW).subscription_quota_state.value==expected
    assert data.model_dump_json()==before


def _mutations():
    """Break each reader boundary, observe red, restore exact bytes and observe green."""
    import ast, hashlib, os, subprocess, sys, tempfile
    path=Path(__file__).resolve().parents[1]/'src/hapax/spine/quota_spend_ledger.py'
    assert Path(q.__file__).resolve()==path
    original=path.read_bytes();source=original.decode();tree=ast.parse(source)
    lines=source.splitlines(keepends=True);offsets=[0]
    for line in lines:offsets.append(offsets[-1]+len(line))
    controls=[]
    def change(label,node,code):
        a=offsets[node.lineno-1]+node.col_offset;b=offsets[node.end_lineno-1]+node.end_col_offset
        controls.append((label,(source[:a]+code+source[b:]).encode()))
    for fn in (n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef)):
        for n in ast.walk(fn):
            code=ast.get_source_segment(source,n)
            if fn.name in {'_budget_contract','_receipt_contract'} and isinstance(n,ast.Raise) and any(s in code for s in (
                'provider balance evidence must be complete','balance cannot cover','exceeds the observed',
                'agentic-trust observation evidence cannot define','balance-settled spend')):
                change(fn.name+str(n.lineno),n,'pass')
            if isinstance(n,ast.Expr) and isinstance(n.value,ast.Call):
                if code.startswith('_require_aware(') and 'provider_balance_' in code:
                    var=n.value.args[0].id
                    change(var+'-clock',n,f'{var} = {var}.replace(tzinfo=UTC)')
                if (code=='_require_aware(self.reconciled_at, "reconciled_at")'
                    or fn.name=='_budget_contract' and code.startswith('_reject_private_or_identity_refs(')
                    or fn.name.startswith('_serialize_without_') and code.startswith('payload.pop(')):
                    change(fn.name+str(n.lineno),n,'pass')
            if isinstance(n,ast.If) and fn.name=='cost_against_cap':
                change('cost:'+str(n.lineno),n.test,'False')
            if isinstance(n,ast.Return) and fn.name=='provider_balance_covers':
                change('balance-coverage',n.value,'True')
            if isinstance(n,ast.BoolOp) and fn.name in {
                '_is_glmcp_admission_evidence_ref','_is_glmcp_payg_admission_evidence_ref',
                '_has_glmcp_payg_witness_fields_for_endpoint','_glmcp_payg_spend_receipt_witness_refs'}:
                for i,value in enumerate(n.values):
                    change(fn.name+str(n.lineno)+':'+str(i),value,'True' if isinstance(n.op,ast.And) else 'False')
            if isinstance(n,ast.If) and fn.name=='_has_glmcp_payg_witness_fields_for_endpoint':
                if 'len(endpoint_matches)' in code:
                    change('ambiguous-endpoint',n,'endpoint_matches = [GLMCP_ADMISSION_PAYG_ENDPOINT]')
                elif 'len(primary_error_matches)' in code:change('witness-count',n.test,'False')
                else:change('coding-plan-fields',n.body[0].value,'True')
            if isinstance(n,ast.If) and fn.name=='evaluate_paid_route_eligibility' and (
                code.startswith(('if ledger.ledger_stale','if overdue:','if frozen:'))
                or 'request.estimated_cost_usd >' in ast.get_source_segment(source,n.test)):
                change('eligibility:'+str(n.lineno),n.test,'False')
    for n in ast.walk(tree):
        if isinstance(n,ast.AnnAssign) and isinstance(n.target,ast.Name) and n.target.id=='task_hash':
            change('task-hash',n,'task_hash: str | None = None')
    replacements=[
        ('GLMCP_PAYG_ESTIMATED_COST_USD = "0.05"','GLMCP_PAYG_ESTIMATED_COST_USD = "0.04"'),
        ('"task_id": task_id,','"task_id": "wrong-task",'),
        ('request.task_id,','"wrong-task",'),
        ('if witnesses & _glmcp_payg_spend_receipt_witness_refs(receipt)','if True'),
        ('decision.budget_id == receipt.budget_id','True'),
        ('required_refs.issubset(set(snapshot.evidence_refs))','True'),
        ('if _subscription_quota_missing_required_payg_spend_gate(ledger, snapshot, now=now):','if False:'),
    ]
    for field in ('primary_error_class','quota_wall_evidence_ref'):
        old=f'r":{field}:([^:]*)(?=:|$)"'
        for new in (old.replace('*','+'),old.replace('|$',''),old.replace('(?=:|$)',':')):
            replacements.append((old,new))
    for old,new in replacements:
        assert source.count(old)==1,old
        controls.append((old,source.replace(old,new).encode()))
    def run(label):
        env=os.environ.copy();env.pop('PYTHONPATH',None)
        with tempfile.TemporaryDirectory(prefix='s06-cache-') as cache:
            env['PYTHONPYCACHEPREFIX']=cache
            r=subprocess.run([sys.executable,'-m','pytest','-q',str(Path(__file__).resolve())],
                cwd=path.parents[3],env=env,capture_output=True,text=True)
        output=r.stdout+r.stderr;print(json.dumps({'phase':label,'exit':r.returncode}),flush=True)
        print(output,flush=True)
        if label.endswith(':red'):assert 'DID NOT RAISE' in output or 'AssertionError' in output
        return r.returncode
    assert run('original-green')==0
    for label,mutant in controls:
        try:
            assert path.read_bytes()==original and mutant!=original
            path.write_bytes(mutant);assert run(label+':red')==1
        finally:path.write_bytes(original)
        assert path.read_bytes()==original and run(label+':restored-green')==0
    print(json.dumps({'controls':len(controls),'all_killed_and_restored':True,
        'restored_sha256':hashlib.sha256(original).hexdigest()}),flush=True)


if __name__=='__main__':
    import sys
    if sys.argv[1:]==['--mutation-controls']:_mutations()
    else:raise SystemExit('use --mutation-controls')
