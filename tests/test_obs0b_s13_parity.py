"""S13: S02a/S02b + S03 cef55b52 LOCAL projection; synthetic receipts test integrity."""
import copy
from datetime import UTC,datetime,timedelta
import hashlib,json
from pathlib import Path

import pytest
from pydantic import ValidationError
from hapax.spine import dispatcher_policy as p
from hapax.spine import platform_capability_registry as r
from hapax.spine.capability_surface_delta import CapabilitySurfaceDelta,CapabilitySurfaceDescriptor
from test_obs0b_s02a_parity import PRODUCER,delta
from test_obs0b_s02b_parity import TRUST
from test_obs0b_s03_parity import root
from test_obs0b_s05_parity import payload as ledger_payload

HOLD='fixture_hold'
POLICY='test:synthetic-policy'
REVIEW='frontier_review_required'
EXCLUDED='frontier_required_without_equivalence_record'
BLOCKS='blocked_reasons'
REFS='evidence_refs'
RID='route_id'
CLASSES='excluded_task_classes'
FLOORS='eligible_quality_floors'
QENV='quality_envelope'
EVID='evidence'
FRESH='freshness'

ENTITLE='local_inference_entitlement'
FETCH='read_only_fetch'
ACTUATE='runtime_actuation'
CONNECT='connector_mutation'
QUALITY='quality_equivalence'
OPUS='opus_model_entitlement'

NOW=datetime(2026,5,17,19,55,tzinfo=UTC)
LOCAL='local_tool.local.worker'
CODEX='codex.headless.full'
SID=TRUST['shape_id']
CFG='HAPAX_SPINE_CONFIG_DIR'
ENV='HAPAX_CAPABILITY_SURFACE_DELTA_FILE'
BIND='candidate-binding-sha256:'+'a'*64
LOCAL_BLOCKS=['local_inference_worker_receipt_admission_required','fresh_capability_evidence_absent','quota_telemetry_unknown']
param=pytest.mark.parametrize
load=p.load_dispatch_policy_sources
apply=p.apply_route_authority_receipts
fresh=p._load_fresh_route_authority_receipts
Receipt=p.RouteAuthorityReceipt
Sources=p.DispatchPolicySources
Registry=r.PlatformCapabilityRegistry

@pytest.fixture
def mp(monkeypatch):return monkeypatch
@pytest.fixture
def tmp(tmp_path):return tmp_path
@pytest.fixture(autouse=True)
def offline(mp,tmp):
  import socket,subprocess
  def forbidden(*a,**kw):pytest.fail('unexpected external action or receipt production')
  mp.setattr(socket.socket,'connect',forbidden);mp.setattr(socket,'create_connection',forbidden)
  mp.setattr(subprocess,'Popen',forbidden)
  for name in('build_route_authority_receipt','write_route_authority_receipt','write_route_decision_receipt'):
    mp.setattr(p,name,forbidden)
  mp.setenv(CFG,str(tmp/'missing'));mp.setenv('HAPAX_PLATFORM_CAPABILITY_RECEIPT_DIR','none')
  mp.setenv('HAPAX_QUOTA_SPEND_LEDGER_LIVE',str(tmp/'absent-live-ledger'));mp.delenv(ENV,raising=False)

def put(path,value):
  path.parent.mkdir(parents=True,exist_ok=True)
  path.write_text(json.dumps(value,default=lambda x:x.isoformat().replace('+00:00','Z')))
  return path

def payload(kind=ENTITLE,**changes):
  value=dict(route_authority_receipt_schema=1,receipt_id='synthetic',receipt_type=kind,
    route_id=LOCAL,issued_at=NOW.isoformat().replace('+00:00','Z'),stale_after='1h',
    signed_by='synthetic-fixture',evidence_refs=[POLICY],quality_floors=[],task_ids=[],mutation_surfaces=[])
  if kind==QUALITY:value['quality_floors']=[REVIEW]
  if kind==OPUS:value[RID]='claude.review.opus'
  if kind in(ACTUATE,CONNECT):value.update(task_ids=['synthetic-task'],mutation_surfaces=['source'])
  if kind==FETCH:value.update(task_ids=['synthetic-task'],evidence_refs=[BIND])
  value.update(changes);value['signed_payload_sha256']=p.route_authority_receipt_payload_hash(value)
  return value

def receipt(kind=ENTITLE,**changes):
  return Receipt.model_validate(payload(kind,**changes))

def local(hold=True):
  data=root();target=next(x for x in data['routes']if x[RID]==LOCAL)
  target[BLOCKS]=LOCAL_BLOCKS.copy()+([HOLD]if hold else[])
  target['route_state']='blocked'
  if hold:target[FRESH][EVID]['resource'][BLOCKS]=[HOLD]
  for name,reason in[('capability','fresh_capability_evidence_absent'),('quota','quota_telemetry_unknown')]:
    target[FRESH][name+'_checked_at']=None
    target[FRESH][EVID][name]=dict(evidence_refs=[],blocked_reasons=[reason])
  return data

def files(tmp,reg=None):
  return dict(registry_path=put(tmp/'registry.json',reg or local()),
    quota_ledger_path=put(tmp/'ledger.json',ledger_payload()),receipt_dir=tmp/'receipts',now=NOW)

def read(tmp,reg=None,**kw):
  return load(**(files(tmp,reg)|kw))

def producer(tmp,**changes):
  data=copy.deepcopy(PRODUCER);data.update(changes)
  return put(tmp/'delta.json',data)
@param('kind',[ENTITLE,FETCH,ACTUATE,CONNECT,OPUS,QUALITY])
def test_schema_inert(kind):
  reg=Registry.model_validate(local());before=reg.model_dump_json()
  obj=receipt(kind);sources=Sources(registry=reg,route_authority_receipts=(obj,))
  assert sources.registry.model_dump_json()==before
  assert sources.registry.route_map()[LOCAL].blocked_reasons==LOCAL_BLOCKS+[HOLD]
@param('ref',['bare','sha256:abcd','run:fixture','hash:abc','digest:abc','bad namespace:item',
  'agentic-trust-evidence-receipt-v1:fixture','test:'+SID,'',':item','test:'])
def test_policy_ref_refusal(ref):
  raw=payload(evidence_refs=['test:typed',ref])
  with pytest.raises(ValidationError,match='namespaced non-observation'):Receipt.model_validate(raw)
@param('kind,change',[
  (ENTITLE,{RID:CODEX}),
  (FETCH,{'task_ids':[]}),(FETCH,{'task_ids':['a','b']}),
  (FETCH,{'task_ids':[' ']}),(FETCH,{'mutation_surfaces':['source']}),
  (FETCH,{'quality_floors':[REVIEW]}),
  (FETCH,{REFS:['test:unbound']}),
  (FETCH,{REFS:[BIND,BIND]}),
  (FETCH,{REFS:['candidate-binding-sha256:'+'A'*64]}),
  (FETCH,{'receipt_id':'../escape'}),(FETCH,{'receipt_id':'a'*129}),
  (OPUS,{RID:CODEX}),(QUALITY,{'quality_floors':[]}),
  (ACTUATE,{'task_ids':[]}),(ACTUATE,{'mutation_surfaces':[]}),
  (CONNECT,{'task_ids':[]}),(CONNECT,{'mutation_surfaces':[]}),
  (ENTITLE,{'signed_by':' '}),
])
def test_authority_scope(kind,change):
  with pytest.raises(ValidationError):receipt(kind,**change)
@param('fault',['tampered','json','missing-field','unknown-type','untyped'])
def test_parse_refusal(tmp,fault):
  raw=payload()
  if fault=='tampered':raw[RID]='local_tool.other.worker'
  if fault=='missing-field':del raw['signed_payload_sha256']
  if fault=='unknown-type':raw['receipt_type']='invented'
  if fault=='untyped':raw=payload(evidence_refs=['schema-only'])
  path=put(tmp/'bad.json',raw)
  if fault=='json':path.write_text('{')
  with pytest.raises(ValueError,match='invalid route authority receipt'):
    fresh(tmp,now=NOW)
@param('kind',[ACTUATE,CONNECT,FETCH])
def test_action_nonclearing(tmp,kind):
  reg=Registry.model_validate(local());before=reg.model_dump_json()
  obj=receipt(kind)
  assert p._route_authority_removable_reasons(obj)==set()
  put(tmp/'route-authority'/'action.json',payload(kind))
  got=apply(reg,receipt_dir=tmp,now=NOW)
  assert got.model_dump_json()==before and reg.model_dump_json()==before
@param('kind',[OPUS,QUALITY,ENTITLE])
@param('age',[timedelta(hours=1),timedelta(hours=1,microseconds=1)])
def test_freshness(tmp,kind,age):
  put(tmp/'receipt.json',payload(kind,issued_at=(NOW-age).isoformat().replace('+00:00','Z')))
  got=fresh(tmp,now=NOW)
  assert len(got)==int(age==timedelta(hours=1))
  assert fresh(tmp/'absent',now=NOW)==()
def test_task_dedup(tmp):
  for name,kind,task,minute in[('z',FETCH,'a',0),('a',FETCH,'b',0),
      ('old',FETCH,'a',-1),('same',FETCH,'a',0),('runtime',ACTUATE,'a',0)]:
    put(tmp/(name+'.json'),payload(kind,receipt_id=name,task_ids=[task],issued_at=(NOW+timedelta(minutes=minute)).isoformat().replace('+00:00','Z')))
  got=fresh(tmp,now=NOW)
  assert[(x.receipt_type,x.task_ids,x.receipt_id)for x in got]==[
    (FETCH,('a',),'same'),(FETCH,('b',),'a'),(ACTUATE,('a',),'runtime')]
def test_surface_authority(tmp):
  for hold in(False,True):
    reg=Registry.model_validate(local(hold));old=reg.model_dump_json()
    put(tmp/'route-authority'/'local.json',payload())
    got=apply(reg,receipt_dir=tmp,now=NOW);route=got.route_map()[LOCAL]
    assert route.blocked_reasons==([HOLD]if hold else[])
    assert route.route_state==('blocked' if hold else 'active')
    assert reg.model_dump_json()==old
    ref=p.route_authority_receipt_reference(receipt())
    for name in('capability','quota'):
      ev=getattr(route.freshness.evidence,name)
      assert ev.blocked_reasons==[]and ev.evidence_refs==[POLICY,ref]
      assert getattr(route.freshness,name+'_checked_at')==NOW
      assert getattr(route.freshness,name+'_stale_after')=='1h'
    for name in('resource','provider_docs'):
      assert getattr(route.freshness.evidence,name)==getattr(reg.route_map()[LOCAL].freshness.evidence,name)
      assert getattr(route.freshness,name+'_checked_at')==getattr(reg.route_map()[LOCAL].freshness,name+'_checked_at')
    assert got.route_map()[CODEX]==reg.route_map()[CODEX]
    assert apply(got,receipt_dir=tmp,now=NOW)==got
  put(tmp/'route-authority'/'local.json',payload(route_id='local_tool.unknown.worker'))
  with pytest.raises(ValueError,match='unsupported route'):apply(reg,receipt_dir=tmp,now=NOW)
def test_typed_authority(tmp):
  for kind,block in[(QUALITY,'quality_equivalence_record_absent'),(OPUS,'opus_model_entitlement_receipt_absent')]:
    raw=payload(kind);data=root();route=next(x for x in data['routes']if x[RID]==raw[RID])
    route[BLOCKS]=[block,HOLD]+route[FRESH][EVID]['quota'][BLOCKS]
    route[FRESH][EVID]['capability'][BLOCKS]=[block]
    route[QENV][CLASSES]=[EXCLUDED,'fixture_class']
    route[QENV][FLOORS]=['frontier_required']
    reg=Registry.model_validate(data)
    put(tmp/kind/'route-authority'/'receipt.json',raw)
    got=apply(reg,receipt_dir=tmp/kind,now=NOW).route_map()[raw[RID]]
    assert set(got.blocked_reasons)==set(reg.route_map()[raw[RID]].blocked_reasons)-{block}
    assert(REVIEW in got.quality_envelope.eligible_quality_floors)is(kind==QUALITY)
    assert(EXCLUDED in got.quality_envelope.excluded_task_classes)is(kind!=QUALITY)
    assert 'fixture_class' in got.quality_envelope.excluded_task_classes
    assert len(got.quality_envelope.explicit_equivalence_records)==1
@param('bad',[False,True])
def test_nonsupply(tmp,bad):
  data=local()
  if bad:data['omitted_capability_shapes'][0]['observed_at']='bad'
  got=read(tmp,data)
  assert got.registry is not None and got.registry_error is None and got.quota_error is None
  assert len(got.non_supply_observation_errors)==int(bad)
  shape=got.registry.omitted_capability_shapes[0]
  assert not shape.demand_eligible and shape.route_ids==[]and shape.shape_state.value=='evidence_only'
  assert got.registry.route_map()[LOCAL].blocked_reasons==LOCAL_BLOCKS+[HOLD]
  assert got.surface_delta_refs_by_route==got.surface_delta_blockers_by_route=={}
  assert got.quota_ledger_source=='explicit' and got.route_authority_receipts==()
@param('fault',['identity','registry-json','registry-missing','quota-json','quota-missing','authority-json'])
def test_source_errors(tmp,fault):
  kw=files(tmp)
  if fault=='identity':
    data=local();data['omitted_capability_shapes'][0]['demand_eligible']=True;put(kw['registry_path'],data)
  for prefix in('registry','quota'):
    if fault==prefix+'-json':kw[prefix+'_path' if prefix=='registry' else 'quota_ledger_path'].write_text('{')
    if fault==prefix+'-missing':kw[prefix+'_path' if prefix=='registry' else 'quota_ledger_path'].unlink()
  if fault=='authority-json':put(tmp/'receipts/route-authority/bad.json',{})
  got=load(**kw)
  bad_reg=fault not in('quota-json','quota-missing')
  assert(got.registry is None)is bad_reg and bool(got.registry_error)is bad_reg
  assert(got.quota_ledger is None)is(not bad_reg)and bool(got.quota_error)is(not bad_reg)
def test_loader_binding(mp,tmp):
  kw=files(tmp);put(tmp/'platform-capability-registry.json',local())
  put(tmp/'quota-spend-ledger-fixtures.json',ledger_payload())
  put(tmp/'receipts/route-authority/local.json',payload())
  mp.setenv(CFG,str(tmp));mp.setenv('HAPAX_PLATFORM_CAPABILITY_RECEIPT_DIR',str(tmp/'receipts'))
  got=load(now=NOW)
  assert got.registry.route_map()[LOCAL].blocked_reasons==[HOLD]
  assert len(got.route_authority_receipts)==1 and got.quota_ledger is not None
  assert got.quota_ledger_source=='fixtures' and got.quota_live_error is None
  (tmp/'absent-live-ledger').write_text('{')
  fallback=load(now=NOW)
  assert fallback.quota_ledger_source=='fixtures' and fallback.quota_live_error
  explicit=load(**kw)
  assert explicit.registry==got.registry and explicit.route_authority_receipts==got.route_authority_receipts
  mp.setenv(CFG,str(tmp/'missing'))
  assert load(**kw)==explicit
  missing=load(registry_path=kw['registry_path'],now=NOW)
  assert missing.registry is not None and missing.quota_error and missing.quota_ledger is None
  def boom(**kw):raise RuntimeError('unrelated runtime failure')
  mp.setattr(p,'load_quota_spend_ledger_resolved',boom)
  with pytest.raises(RuntimeError,match='unrelated'):load(registry_path=kw['registry_path'],now=NOW)
@param('value',[None,'','0','none','None','false','False','  none  ','~/synthetic-delta.json'])
def test_delta_env(mp,value):
  if value is not None:mp.setenv(ENV,value)
  got=p._surface_delta_path_from_env()
  assert got==(Path(value).expanduser()if value and value.startswith('~')else None)
def test_delta_keys():
  obj=copy.deepcopy(PRODUCER['descriptors'][0]);obj.update(surface_id='route.'+CODEX,route_id=LOCAL)
  assert p._surface_delta_descriptor_route_keys(CapabilitySurfaceDescriptor.model_validate(obj))==tuple(sorted((CODEX,LOCAL)))
  obj.update(surface_id='surface.synthetic',route_id=None)
  assert p._surface_delta_descriptor_route_keys(CapabilitySurfaceDescriptor.model_validate(obj))==()
  assert p._surface_delta_dispatch_lookup_keys(['route.a','surface.b','typed:c',CODEX])=={CODEX}
  for field in('surface_id','prior_descriptor_ref','observed_descriptor_ref',REFS):
    changes=dict(surface_id='surface.synthetic',prior_descriptor_ref='ref:old',observed_descriptor_ref='ref:new',evidence_refs=['ref:extra'])
    changes[field]=['join:target']if field==REFS else 'join:target'
    obj=CapabilitySurfaceDelta.model_validate(delta(**changes))
    keys,dispatch=p._surface_delta_route_key_sets(obj,{'join:target':[CODEX,'route.fake','type:fake','surface.fake']})
    assert dispatch=={CODEX}and{CODEX,'join:target'}<=keys
  obj=CapabilitySurfaceDelta.model_validate(delta('new_capability',surface_id='surface.new'))
  assert p._surface_delta_route_key_sets(obj,{})[1]==set()
  obj=CapabilitySurfaceDelta.model_validate(delta('absent_determination',surface_id='route.'+CODEX))
  assert p._surface_delta_route_key_sets(obj,{})[1]=={CODEX}
  assert p._surface_delta_values_for_route(None,CODEX)==()
  assert p._surface_delta_values_for_route({CODEX:['a','a','b'],'__all__':['b','c']},CODEX)==('a','b','c')
  assert p._surface_delta_values_for_route({'__all__':['x']},LOCAL)==('x',)
@param('known',[None,[],[CODEX],['unrelated.route']])
@param('joined',[False,True])
def test_global_delta(tmp,known,joined):
  data=copy.deepcopy(PRODUCER)
  if not joined:data['deltas'][0]=delta(surface_id='surface.unjoined',prior_descriptor_ref='ref:missing')
  data['deltas']*=2
  path=producer(tmp,**data)
  refs,blocks=p._surface_delta_route_index(path,known_route_ids=known)
  global_expected=(not joined)or(known is not None and CODEX not in known)
  assert('__all__' in blocks)is global_expected
  assert refs==blocks and bool(refs)
  if joined:assert blocks[CODEX]
  assert all(len(v)==1 for v in refs.values())
@param('surface',['surface.'+SID,'SURFACE/'+SID.upper().replace('.','/'),'surface.'+SID+'.child','route.'+CODEX])
def test_evidence_precedence(tmp,surface):
  data=copy.deepcopy(PRODUCER);data['descriptors'][0]['surface_id']=surface
  data['deltas'][0]=delta(surface_id=surface)
  path=producer(tmp,**data)
  evidence=[SID,'route.'+CODEX]
  refs,blocks=p._surface_delta_route_index(path,known_route_ids=(x for x in[CODEX]),evidence_only_surface_ids=iter(evidence))
  inert=not(surface.endswith('.child')or surface=='route.'+CODEX)
  assert bool(refs)is(not inert)and bool(blocks)is(not inert)
  if not inert:assert blocks[CODEX]
  if inert:
    got=read(tmp,surface_delta_path=path)
    assert got.surface_delta_refs_by_route==got.surface_delta_blockers_by_route=={}
@param('fault',['valid','json','missing','schema'])
def test_delta_loader(mp,tmp,fault):
  path=producer(tmp)
  if fault=='json':path.write_text('{')
  if fault=='missing':path.unlink()
  if fault=='schema':put(path,{'schema_version':999})
  mp.setenv(ENV,str(tmp/'env-missing.json'))
  got=read(tmp,surface_delta_path=path)
  if fault=='valid':
    ref='capability_surface_delta:stale:route.'+CODEX+':test:single-stale-codex'
    assert got.surface_delta_refs_by_route[CODEX]==got.surface_delta_blockers_by_route[CODEX]==(ref,)
    assert '__all__' not in got.surface_delta_blockers_by_route
    mp.setenv(ENV,str(path));assert read(tmp)==got
  else:
    assert set(got.surface_delta_refs_by_route)==set(got.surface_delta_blockers_by_route)=={'__all__'}
    ref=got.surface_delta_refs_by_route['__all__'][0]
    assert ref==got.surface_delta_blockers_by_route['__all__'][0]
    assert ref.startswith('capability_surface_delta:unknown:producer_file:delta.json:')
    assert ref.endswith(':invalid_or_unreadable')and str(tmp)not in ref
  assert got.registry is not None and got.quota_ledger is not None
def test_error_redaction():
  ref=p._surface_delta_producer_error_ref(Path('/synthetic/private/delta.json'),ValueError('sensitive-fixture'))
  assert 'sensitive-fixture' not in ref and '/synthetic' not in ref
  assert ref!=p._surface_delta_producer_error_ref(Path('/synthetic/private/delta.json'),ValueError('different'))

def _mutations():
  import ast,os,subprocess,sys,tempfile
  path=Path(p.__file__);orig=path.read_bytes();src=orig.decode();pos=[0]
  assert path.resolve()==Path(__file__).resolve().parents[1]/'src/hapax/spine/dispatcher_policy.py'
  for line in src.splitlines(True):pos.append(pos[-1]+len(line))
  edits=[]
  def text(n):return ast.get_source_segment(src,n)
  def add(n,value):
    a=pos[n.lineno-1]+n.col_offset;b=pos[n.end_lineno-1]+n.end_col_offset
    edits.append((str(n.lineno)+':'+value,(src[:a]+value+src[b:]).encode()))
  names={'RouteAuthorityReceipt','load_dispatch_policy_sources','apply_route_authority_receipts',
    '_apply_route_authority_receipt_to_route_payload','_load_fresh_route_authority_receipts','_route_authority_removable_reasons'}
  # Redundant short circuits.
  skip={'not receipt_dir.exists()','not authority_receipts','not original'}
  for fn in ast.parse(src).body:
    if getattr(fn,'name','') not in names and not getattr(fn,'name','').startswith('_surface_delta_'):continue
    for n in ast.walk(fn):
      if isinstance(n,ast.If) and text(n.test) not in skip:add(n.test,'False')
      if isinstance(n,ast.BoolOp) and (fn.name=='RouteAuthorityReceipt' or 'normalized_surface in evidence_only_surfaces' in text(n) or fn.name=='_surface_delta_dispatch_lookup_keys'):
        for part in n.values:add(part,'True' if isinstance(n.op,ast.And) else 'False')
      if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='any':add(n.func,'all')
      if isinstance(n,ast.Return) and fn.name=='_surface_delta_producer_error_ref':add(n.value,'str(path)+str(exc)')
      if isinstance(n,ast.Return) and fn.name=='_surface_delta_values_for_route' and 'global_values' in text(n):add(n.value,'route_values')
      if isinstance(n,ast.IfExp) and fn.name.startswith('_apply_route_authority'):add(n.test,'False')
      if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='load_platform_capability_registry_for_dispatch':add(n.args[0],'None')
  def run():
    env=os.environ.copy();env.pop('PYTHONPATH',None)
    with tempfile.TemporaryDirectory() as cache:
      env['PYTHONPYCACHEPREFIX']=cache
      return subprocess.call([sys.executable,'-m','pytest','-q',__file__],env=env)
  assert run()==0
  for label,mut in edits:
    try:
      assert path.read_bytes()==orig and mut!=orig;ast.parse(mut)
      print(json.dumps({'control':label,'mutant_sha256':hashlib.sha256(mut).hexdigest()}),flush=True)
      path.write_bytes(mut);assert run()==1
    finally:path.write_bytes(orig)
    assert path.read_bytes()==orig and run()==0
  print(json.dumps({'controls':len(edits),'all_killed_and_restored':True,'source_sha256':hashlib.sha256(orig).hexdigest()}))

if __name__=='__main__':
  import sys
  assert sys.argv[1:]==['--mutation-controls'];_mutations()
