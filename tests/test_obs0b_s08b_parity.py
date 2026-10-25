"""S08b offline: S03 pools, S04 receipts, S08a quota locators."""
import copy
from datetime import timedelta
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from hapax.spine import platform_capability_registry as r,quota_spend_ledger as q
from hapax.spine.platform_capability_receipts import PlatformCapabilityReceipt,EvidenceStatus as Status
from test_obs0b_s03_parity import root,route,POOL
from test_obs0b_s04_parity import payload,NOW
from test_obs0b_s08a_parity import POOL_REF
REVIEW='claude.review.opus'
HOLD='operator_hold'
CFG_ENV='HAPAX_SPINE_CONFIG_DIR'
REG_ENV='HAPAX_PLATFORM_CAPABILITY_REGISTRY'
STAMP=NOW.isoformat().replace('+00:00','Z')
param=pytest.mark.parametrize
OBS=Status.OBSERVED; BAD=Status.BLOCKED; UNOBS=Status.UNOBSERVABLE
LIVE_ENV='HAPAX_QUOTA_SPEND_LEDGER_LIVE'
RID='claude.headless.full'
BLOCK='account_live_quota_receipt_absent'
POSITIVE='fixture:account-live-quota:observed'
UNKNOWN='quota_telemetry_unknown'
@pytest.fixture
def tmp(tmp_path):
  return tmp_path
@pytest.fixture
def mp(monkeypatch):
  return monkeypatch
@pytest.fixture(autouse=True)
def offline(mp,tmp):
  import socket,subprocess
  def forbidden(*a,**kw): pytest.fail('unexpected network, process or unbound ledger read')
  mp.setattr(socket.socket,'connect',forbidden)
  mp.setattr(socket,'create_connection',forbidden)
  mp.setattr(subprocess,'Popen',forbidden)
  mp.setattr(r,'load_quota_spend_ledger_resolved',forbidden,raising=False)
  mp.setenv(CFG_ENV,str(tmp/'config'))
  mp.setenv('HAPAX_PLATFORM_CAPABILITY_RECEIPT_DIR','none')
  mp.setenv(LIVE_ENV,'none')
  mp.delenv(REG_ENV,raising=False)
def rec(rid=RID,*,quota='observed',quota_reasons=(),healthy=True):
  p=payload(current=True); p['routes']=[rid]
  w=dict(path='/fixture/route-wrapper',exists=True,executable=healthy,sha256='a'*64)
  p['wrapper']=w; p['route_wrappers']={rid:w}
  for key in ('capability','resource'):
    p[key].update(status='observed',reason_codes=[],evidence_refs=['test:observed'])
  p['quota'].update(status=quota,reason_codes=list(quota_reasons),
    evidence_refs=[f'platform-capability-registry:{rid}:quota:observed'])
  return PlatformCapabilityReceipt.model_validate(p)
def fold(mp,v,rc,*,fresh=False,refs=()):
  mp.setattr(r,'_route_specific_quota_admission_fresh',lambda *a,**kw:(fresh,refs),raising=False)
  r._apply_receipt_to_route_payload(v,rc,now=NOW)
  return v
def test_pool_binding_precedence(mp,tmp):
  p=tmp/'explicit.json'; p.write_text(json.dumps(root()))
  mp.setenv(REG_ENV,str(tmp/'absent'))
  mp.delenv(CFG_ENV)
  home=tmp/'synthetic-home'
  def forbidden(*a,**kw): pytest.fail('static pool resolution applied receipts')
  mp.setattr(r,'apply_platform_capability_receipts',forbidden)
  got=r.resolve_subscription_pool_bindings(p,home=home)
  assert set(got)=={REVIEW}
  binding=got[REVIEW]; assert binding.pool=='max-2'
  for field in ('receipt_dir','headless_dir','pace_activation','durable_sink_root'):
    assert getattr(binding,field)==home/POOL[field]
  assert binding.config_dir==home/POOL['config_home']
  assert r.resolve_subscription_pool_binding(' claude/review/opus ',p,home=home)==binding
  assert r.resolve_subscription_pool_binding(RID,p,home=home) is None
  mp.setenv(REG_ENV,str(p))
  assert r.resolve_subscription_pool_bindings(home=home)==got
  mp.delenv(REG_ENV)
  with pytest.raises(RuntimeError,match=CFG_ENV): r.resolve_subscription_pool_bindings(home=home)
  cfg=tmp/'config';cfg.mkdir();(cfg/'platform-capability-registry.json').write_text(p.read_text())
  mp.setenv(CFG_ENV,str(cfg))
  assert r.resolve_subscription_pool_bindings(home=home)==got
  mp.setattr(Path,'home',lambda:home)
  assert r.resolve_subscription_pool_bindings()==got
@param('raw',[None,'{','[]','{}'])
def test_pool_error_remediation(tmp,raw):
  p=tmp/'bad.json'
  if raw is not None:p.write_text(raw)
  with pytest.raises(r.PlatformCapabilityRegistryError,match='next action: repair'):
    r.resolve_subscription_pool_bindings(p,home=tmp)
@param('setting',[None,'',' ','/fixture/config'])
def test_config_locator(mp,tmp,setting):
  env={} if setting is None else {'CLAUDE_CONFIG_DIR':setting}
  mp.setattr(Path,'home',lambda:tmp/'default')
  expected=Path('/fixture/config') if setting=='/fixture/config' else tmp/'.claude'
  assert r.claude_config_dir_for_env(env,home=tmp)==expected
  if not setting or not setting.strip():assert r.claude_config_dir_for_env(env)==tmp/'default'/'.claude'
  mp.setattr(Path,'expanduser',lambda p:tmp/'expanded')
  assert r.claude_config_dir_for_env({'CLAUDE_CONFIG_DIR':' ~/configured '})==tmp/'expanded'
@param('status',list(Status))
@param('ref_kind',['exact','sibling','prefix','suffix'])
def test_quota_route_correlation(status,ref_kind):
  rc=rec();rc.quota.status=status
  ref=f'platform-capability-registry:{RID}:quota:observed'
  rc.quota.evidence_refs=[{'exact':ref,'sibling':ref.replace(RID,REVIEW),
    'prefix':'x:'+ref,'suffix':ref+':extra'}[ref_kind]]
  assert r._receipt_quota_names_route(rc,{'route_id':RID}) is (status is OBS and ref_kind=='exact')
  assert not r._receipt_quota_names_route(rc,{})
  rc.quota.evidence_refs=['platform-capability-registry::quota:observed']
  assert not r._receipt_quota_names_route(rc,{})
@param('fault',['none','observed','extra','capability','resource','wrong-pool','paid-no-ledger','paid-ledger','bootstrap-ledger'])
def test_unobservable_quota_bounds(fault):
  rc=rec(quota='unobservable',quota_reasons=(UNKNOWN,))
  v={'capacity_pool':'subscription_quota','telemetry':{'quota_source':'manual'}}
  if fault=='observed':rc.quota.status=OBS
  if fault=='extra':rc.quota.reason_codes.append('quota_exhausted')
  if fault=='capability':rc.capability.status=BAD
  if fault=='resource':rc.resource.status=BAD
  if fault=='wrong-pool':v.update(capacity_pool='local_compute',telemetry={'quota_source':'ledger'})
  if fault.startswith('paid'):v['capacity_pool']='api_paid_spend'
  if fault=='bootstrap-ledger':v['capacity_pool']='bootstrap_budget'
  if fault.endswith('-ledger') and fault!='paid-no-ledger':v['telemetry']['quota_source']='ledger'
  expected=fault in {'none','paid-ledger','bootstrap-ledger'}
  assert r._quota_unobservable_nonblocking(v,rc) is expected
  rc.capability.status=rc.resource.status=BAD
  v={'capacity_pool':'subscription_quota'}
  rc.quota.status=UNOBS;rc.quota.reason_codes=[]
  assert r._quota_unobservable_nonblocking(v,rc,capability_status=OBS,resource_status=OBS)
  rc.capability.status=rc.resource.status=OBS
  assert not r._quota_unobservable_nonblocking(v,rc,capability_status=BAD)
  assert not r._quota_unobservable_nonblocking(v,rc,resource_status=BAD)
@param('fault',['none','untracked','fixtures','invalid-live','os','typed','value','stale','wrong-pool','unbound','empty-refs'])
def test_live_pool_admission(mp,tmp,fault):
  v={'route_id':REVIEW,'subscription_pool_binding':{'pool':'max-2'}}
  if fault=='untracked':v['route_id']='codex.headless.full'
  if fault=='unbound':v.pop('subscription_pool_binding')
  calls=[];ledger=object();refs=() if fault=='empty-refs' else (POOL_REF.replace('pool-max-2','pool-max-1') if fault=='wrong-pool' else POOL_REF,)
  def load(**kw):
    calls.append(('load',kw))
    errors={'os':OSError,'typed':q.QuotaSpendLedgerError,'value':ValueError}
    if fault in errors:raise errors[fault]('fixture error')
    return SimpleNamespace(source='fixtures' if fault in {'fixtures','invalid-live'} else 'live',live_error='bad' if fault=='invalid-live' else None,ledger=ledger)
  def state(obj,rid,**kw):
    assert obj is ledger and rid==v['route_id'] and kw=={'now':NOW}
    return q.SubscriptionQuotaState.STALE if fault=='stale' else q.SubscriptionQuotaState.FRESH,refs
  mp.setattr(r,'load_quota_spend_ledger_resolved',load,raising=False)
  mp.setattr(r,'subscription_quota_state_for_route',state,raising=False)
  p=tmp/'ledger';mp.setenv(LIVE_ENV,str(p))
  fresh,ev=r._route_specific_quota_admission_fresh(v,now=NOW)
  assert fresh is (fault in {'none','unbound'})
  if fault=='untracked':assert calls==[] and ev==()
  else:assert calls==[('load',{'live_path':p})]
  if fault in {'wrong-pool','empty-refs'}:assert ev==(*refs,'quota-spend-ledger:claude.review.opus:admission-not-from-declared-pool:max-2')
  if fault=='fixtures':assert ev==()
  if fault=='invalid-live':assert ev==('quota-spend-ledger:claude.review.opus:live-ledger-invalid',)
  if fault in {'os','typed','value'}:assert len(ev)==1 and ':read-error:' in ev[0]
  if fault in {'none','unbound','stale'}:assert ev==refs
@param('rid',[RID,'claude.interactive.full',REVIEW,'agy.review.direct','kimi.interactive.lane','glmcp.review.direct'])
@param('fresh',[False,True])
def test_admission_projection(mp,rid,fresh):
  v=route(rid);block=r.ROUTE_SPECIFIC_QUOTA_ADMISSION_BLOCKERS[rid]
  v['blocked_reasons']=[HOLD]+([block] if fresh else []);v['freshness']['evidence']['quota']['blocked_reasons']=[block] if fresh else []
  v['telemetry']['quota_source']='none'
  refs=(POSITIVE,'test:context',POSITIVE)
  fold(mp,v,rec(rid),fresh=fresh,refs=refs)
  ev=v['freshness']['evidence']['quota']
  assert (block in v['blocked_reasons']) is (not fresh)
  assert (block in ev['blocked_reasons']) is (not fresh)
  assert HOLD in v['blocked_reasons'] and v['route_state']=='blocked'
  assert (POSITIVE in ev['evidence_refs']) is (fresh or rid not in {RID,'claude.interactive.full'})
  assert ev['evidence_refs'].count('test:context')==1
  assert ev['evidence_refs'].count(POSITIVE)<=1
  assert v['telemetry']['quota_source']==('ledger' if fresh else 'manual')
@param('fault',['healthy','wrapper','unmeasured','unobserved','quota-exhausted','sibling','unobservable','untracked'])
def test_overlay_refusals(mp,fault):
  v=route();rc=rec(healthy=fault!='wrapper');old=copy.deepcopy(v)
  v['blocked_reasons']=[HOLD,'fresh_capability_evidence_absent','fresh_resource_evidence_absent',BLOCK]
  for surface in ('capability','resource'):v['freshness']['evidence'][surface]['blocked_reasons']=['fresh_'+surface+'_evidence_absent']
  if fault=='unmeasured':v['blocked_reasons'].append('capability_scores_asserted_not_measured')
  if fault=='unobserved':
    rc.capability.status=BAD;rc.capability.reason_codes=['measurement_held']
  if fault=='quota-exhausted':rc.quota.reason_codes=['quota_exhausted']
  if fault=='sibling':
    rc.quota.evidence_refs=['platform-capability-registry:claude.review.opus:quota:observed']
    v['route_id']='codex.headless.full';v['freshness']['evidence']['quota']['blocked_reasons']=[UNKNOWN]
  if fault=='unobservable':
    rc.quota.status=UNOBS;rc.quota.reason_codes=[UNKNOWN];v['blocked_reasons'].append(UNKNOWN)
  if fault=='untracked':
    v['route_id']='codex.headless.full';rc=rec(v['route_id'])
  fold(mp,v,rc)
  ev=v['freshness']['evidence'];ref=r.receipt_reference(rc)
  healthy=fault not in {'wrapper','unobserved'}
  assert ('fresh_capability_evidence_absent' in v['blocked_reasons']) is (not healthy)
  assert ('fresh_resource_evidence_absent' in v['blocked_reasons']) is (fault=='wrapper')
  for key,bad in [('capability',not healthy),('resource',fault=='wrapper')]:
    assert ('fresh_'+key+'_evidence_absent' in ev[key]['blocked_reasons']) is bad
  assert HOLD in v['blocked_reasons']
  assert (BLOCK in v['blocked_reasons']) is (fault!='untracked')
  if fault=='unobservable':assert UNKNOWN not in v['blocked_reasons']
  if fault=='quota-exhausted':assert 'quota_exhausted' in ev['quota']['blocked_reasons'] and 'quota_exhausted' in v['blocked_reasons']
  if fault=='sibling':assert {BLOCK,UNKNOWN}<=set(ev['quota']['blocked_reasons'])
  if fault=='wrapper':
    assert 'sanctioned_wrapper_not_executable' in ev['capability']['blocked_reasons'] and 'wrapper_not_executable' in ev['resource']['blocked_reasons']
    assert 'sanctioned_wrapper_not_executable' in v['blocked_reasons'] and 'wrapper_not_executable' in v['blocked_reasons']
  assert all(t['observed_at']==STAMP and t['evidence_ref']==ref for t in v['tool_state'])
  if fault in {'wrapper','unmeasured','unobserved'}:assert v['capability_scores']==old['capability_scores']
  else:assert all(s['observed_at']==STAMP and ref in s['evidence_refs'] for s in v['capability_scores'].values())
  assert f'local:{rc.wrapper.path}:exists:true' in ev['resource']['evidence_refs']
  assert (f'local:{rc.wrapper.path}:sha256:{rc.wrapper.sha256}' in ev['capability']['evidence_refs']) is (fault!='wrapper')
@param('fault',['fresh','expired','future','wrong-route','absent'])
def test_receipt_loader_fences(mp,tmp,fault):
  reg=r.PlatformCapabilityRegistry.model_validate(root());rc=rec()
  if fault=='expired':rc.observed_at=NOW-timedelta(days=2)
  if fault=='future':rc.observed_at=NOW+timedelta(minutes=2)
  if fault=='wrong-route':rc.routes=['unknown.route.full']
  if fault!='absent':(tmp/'receipt.json').write_text(rc.model_dump_json())
  seen=[]
  def admission(v,**kw):seen.append((v['route_id'],kw));return False,()
  mp.setattr(r,'_route_specific_quota_admission_fresh',admission,raising=False)
  got=r.apply_platform_capability_receipts(reg,receipt_dir=tmp,now=NOW)
  actual=got.model_dump(mode='json')['routes'];old=reg.model_dump(mode='json')['routes']
  if fault=='fresh':
    target=RID
    assert seen==[(target,{'now':NOW})]
    assert next(v for v in actual if v['route_id']==target)!=next(v for v in old if v['route_id']==target)
    assert [v for v in actual if v['route_id']!=target]==[v for v in old if v['route_id']!=target]
  else:assert actual==old and seen==[]
@param('fault',['fresh','stale','wrong-route','bad-signature','none'])
def test_authority_loader(mp,tmp,fault):
  from hapax.spine import dispatcher_policy as policy
  data=root();target=next(x for x in data['routes'] if x['route_id']==REVIEW)
  target['blocked_reasons']=[HOLD,'opus_model_entitlement_receipt_absent']
  target['freshness']['evidence']['capability']['blocked_reasons']=['opus_model_entitlement_receipt_absent']
  path=tmp/'registry.json';path.write_text(json.dumps(data));receipts=tmp/'receipts';auth=receipts/'route-authority';auth.mkdir(parents=True)
  if fault!='none':
    obj=policy.build_route_authority_receipt(receipt_type='opus_model_entitlement',route_id='claude.headless.opus' if fault=='wrong-route' else REVIEW,evidence_refs=['test:synthetic-authority'],signed_by='synthetic-test',issued_at=NOW-timedelta(days=2) if fault=='stale' else NOW)
    v=obj.model_dump(mode='json')
    if fault=='bad-signature':v['signed_payload_sha256']='0'*64
    (auth/'synthetic.json').write_text(json.dumps(v))
  mp.setenv('HAPAX_PLATFORM_CAPABILITY_RECEIPT_DIR',str(tmp/'wrong'))
  if fault=='bad-signature':
    with pytest.raises(r.PlatformCapabilityRegistryError,match='signed payload hash mismatch'):r.load_platform_capability_registry(path,receipt_dir=receipts,now=NOW)
    return
  parsed=r.load_platform_capability_registry(path,receipt_dir=receipts,now=NOW)
  got=next(x for x in parsed.routes if x.route_id==REVIEW)
  assert ('opus_model_entitlement_receipt_absent' in got.blocked_reasons) is (fault!='fresh')
  assert HOLD in got.blocked_reasons
  assert json.loads(path.read_text())==data
def _mutations():
  import ast,hashlib,os,subprocess,sys,tempfile
  path=Path(r.__file__);orig=path.read_bytes();src=orig.decode();tree=ast.parse(src)
  assert path.resolve()==Path(__file__).resolve().parents[1]/'src/hapax/spine/platform_capability_registry.py'
  lines=src.splitlines(keepends=True);pos=[0]
  for line in lines:pos.append(pos[-1]+len(line))
  edits=[]
  def add(n,text):
    a=pos[n.lineno-1]+n.col_offset;b=pos[n.end_lineno-1]+n.end_col_offset
    edits.append((str(len(edits)+1),(src[:a]+text+src[b:]).encode()))
  for fn in tree.body:
    if not isinstance(fn,ast.FunctionDef):continue
    if fn.name not in {'_apply_receipt_to_route_payload','_quota_unobservable_nonblocking',
      '_route_specific_quota_admission_fresh','_receipt_quota_names_route','apply_platform_capability_receipts',
      '_apply_route_authority_receipts_from_dir'}:continue
    for n in ast.walk(fn):
      code=ast.get_source_segment(src,n)
      if isinstance(n,ast.If) and ast.get_source_segment(src,n.test) not in {'receipt is None','not receipts'}:add(n.test,'False')
      if isinstance(n,ast.IfExp) and 'removable_reasons' in src.splitlines()[n.lineno-1]:add(n.test,'True')
      if isinstance(n,ast.Return) and isinstance(n.value,ast.BoolOp):
        for part in n.value.values:add(part,'True')
      if code=='state is SubscriptionQuotaState.FRESH':add(n,'True')
      if code=='not _ref_has_token_suffix(ref, CLAUDE_ADMISSION_ACCOUNT_LIVE_QUOTA_SUFFIX)':add(n,'True')
      if isinstance(n,ast.Return) and fn.name=='_receipt_quota_names_route' and isinstance(n.value,ast.Compare):add(n.value,'True')
      if isinstance(n,ast.Return) and fn.name=='_apply_route_authority_receipts_from_dir':add(n.value,'registry')
      if isinstance(n,ast.keyword) and n.arg=='now':add(n.value,'None')
      if isinstance(n,ast.Expr) and code=='top_blockers.extend(freshness["evidence"]["quota"]["blocked_reasons"])':add(n,'pass')
  def run(label):
    env=os.environ.copy();env.pop('PYTHONPATH',None)
    with tempfile.TemporaryDirectory() as cache:
      env['PYTHONPYCACHEPREFIX']=cache
      p=subprocess.run([sys.executable,'-m','pytest','-q',__file__],capture_output=True,text=True,env=env)
    out=p.stdout+p.stderr;print(label,p.returncode,out,flush=True)
    if label=='red':assert 'AssertionError' in out or 'DID NOT RAISE' in out
    return p.returncode
  assert run('initial-green')==0
  for label,mut in edits:
    try:
      assert path.read_bytes()==orig and mut!=orig
      print(json.dumps({'control':label,'mutant_sha256':hashlib.sha256(mut).hexdigest()}),flush=True)
      path.write_bytes(mut);assert run('red')==1
    finally:path.write_bytes(orig)
    assert path.read_bytes()==orig and run('restored-green')==0
  print(json.dumps({'controls':len(edits),'all_killed_and_restored':True,'source_sha256':hashlib.sha256(orig).hexdigest()}))
if __name__=='__main__':
  import sys
  if sys.argv[1:]==['--mutation-controls']:_mutations()
  else:raise SystemExit('use --mutation-controls')
