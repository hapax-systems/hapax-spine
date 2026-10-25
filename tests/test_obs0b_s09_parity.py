"""Offline S09 readers; TRUST/RESEARCH are frozen cef55b52 rows from S02b.
Other cases are explicitly synthetic/adversarial. No request is fetched.
"""
import copy
from datetime import UTC,datetime,timedelta
import json
from pathlib import Path
from typing import get_type_hints

import pytest
from hapax.spine import platform_capability_registry as r
from hapax.spine.capability_surface_delta import CapabilitySurfaceDelta
from test_obs0b_s02a_parity import delta
from test_obs0b_s02b_parity import TRUST,RESEARCH
from test_obs0b_s03_parity import root
from test_obs0b_s08b_parity import rec,RID,REVIEW,HOLD

NOW=datetime(2026,5,17,19,55,tzinfo=UTC)
SID=TRUST['shape_id']
CFG='HAPAX_SPINE_CONFIG_DIR'
param=pytest.mark.parametrize

Shape=r.CapabilityShapeDescriptor
State=r.CapabilityShapeState
Fresh=r.CapabilityShapeFreshnessState
RegistryError=r.PlatformCapabilityRegistryError

@pytest.fixture
def mp(monkeypatch):
  return monkeypatch

@pytest.fixture
def tmp(tmp_path):
  return tmp_path

@pytest.fixture(autouse=True)
def offline(mp,tmp):
  import socket,subprocess
  def forbidden(*args,**kwargs):
    pytest.fail('unexpected network, subprocess or live ledger read')
  mp.setattr(socket.socket,'connect',forbidden)
  mp.setattr(socket,'create_connection',forbidden)
  mp.setattr(subprocess,'Popen',forbidden)
  mp.setattr(r,'load_quota_spend_ledger_resolved',forbidden)
  mp.setenv(CFG,str(tmp/'absent-config'))
  mp.setenv('HAPAX_PLATFORM_CAPABILITY_RECEIPT_DIR','none')
  mp.setenv('HAPAX_QUOTA_SPEND_LEDGER_LIVE','none')

def shape(**changes):
  value=copy.deepcopy(TRUST)
  value.update(changes)
  return value

def registry(*shapes):
  value=root()
  value['omitted_capability_shapes']=list(shapes)or[shape()]
  return r.PlatformCapabilityRegistry.model_validate(value)

def load(*args,**kwargs):
  return r.load_platform_capability_registry_for_dispatch(*args,**kwargs)

def facts(**changes):
  value=dict(url='https://arxiv.org/abs/synthetic',documents_used=11,
    gets_used=29,downloaded_bytes=104857600-1024,request_byte_limit=1024,
    authentication='none',billing='declared_zero_incremental',endpoint_public=True,
    admission_passed=True,quota_fresh=True)
  return value|changes

def candidate(**changes):
  return r.check_primary_source_candidate_request(RESEARCH['candidate_binding'],facts(**changes))

@param('change,reason',[
  ({'documents_used':12},'bound_exhausted'),
  ({'gets_used':30},'bound_exhausted'),
  ({'downloaded_bytes':104857600-1023},'bound_exhausted'),
  ({'request_byte_limit':1025},'bound_exhausted'),
  ({'authentication':'required'},'unexpected_authentication'),
  ({'authentication':'unknown'},'unexpected_authentication'),
  ({'billing':'paid'},'unknown_billing'),({'billing':'unknown'},'unknown_billing'),
  ({'endpoint_public':False},'unsafe_endpoint'),({'endpoint_public':None},'unsafe_endpoint'),
  ({'admission_passed':False},'failed_admission'),({'quota_fresh':False},'failed_admission'),
])
def test_request_refusals(change,reason):
  got=candidate(**change)
  assert got.stop_reasons==(reason,)
  assert not got.within_declared_constraints and got.execution_authorized is False

@param('url',[
  'http://arxiv.org/paper','https://arxiv.org.attacker.example/paper',
  'https://sub.arxiv.org/paper','https://unknown.example/paper',
  'https://reader@arxiv.org/paper','https://:secret-fixture@arxiv.org/paper',
  'https://arxiv.org:444/paper','https://arxiv.org:bad/paper',
  'https://arxiv.org:99999/paper','https://arxiv.org/paper?q=x',
  'https://arxiv.org/paper#fragment','https://arxiv.org/white space',
  'https://arxiv.org/\tpath','https://arxiv.org/\x01path','https://[invalid/paper',
])
def test_endpoint_refusal(url):
  got=candidate(url=url)
  assert got.stop_reasons==('unsafe_endpoint',)and not got.execution_authorized

def test_request_never_authority():
  for url in('https://arxiv.org/paper','https://arxiv.org:443/paper'):
    got=candidate(url=url)
    assert got.within_declared_constraints and got.stop_reasons==()
    assert got.execution_authorized is False
  got=candidate(
    documents_used=12,authentication='required',billing='unknown',
    endpoint_public=False,quota_fresh=False)
  assert got.stop_reasons==('bound_exhausted','unexpected_authentication',
    'unknown_billing','unsafe_endpoint','failed_admission')

IDENTITY_FAULTS=[
  ('shape_id',''),('shape_id',' '),('shape_id',1),
  ('descriptor_schema',True),('descriptor_schema',1.0),('descriptor_schema',2),
  ('demand_eligible',True),('demand_eligible',0),('demand_eligible',None),
  ('route_ids',['codex.headless.full']),('route_ids',None),('route_ids',()),
  ('authority_ceiling','authoritative'),('authority_ceiling','unknown-value'),
  ('shape_state','unknown-value'),('surface_delta_signal','capability_surface_delta:local_compute'),
  ('surface_delta_signal',''),('observation_receipt_class',None),
  ('observation_receipt_class',' '),('observation_receipt_class',1),
  ('observation_receipt_class','WrongReceipt'),('shape_state','intake_required'),
]

@param('field,value',IDENTITY_FAULTS)
def test_identity_refusal(tmp,field,value):
  row=shape(**{field:value})
  with pytest.raises(ValueError):
    r._dispatch_shape_identity(row)
  if field=='observation_receipt_class' and value!='WrongReceipt':
    with pytest.raises(ValueError):r._dispatch_shape_identity(row|{'shape_id':'synthetic'})
  if isinstance(value,tuple):return  # JSON converts () to [].
  data=root();data['omitted_capability_shapes']=[row]
  path=tmp/'registry.json';path.write_text(json.dumps(data))
  with pytest.raises(RegistryError):
    load(path,apply_receipts=False,now=NOW)

@param('bad',[None,[],'shape',1])
def test_object_required(bad):
  with pytest.raises(ValueError,match='must be an object'):
    r._dispatch_shape_identity(bad)

def test_typed_identity():
  for row in(TRUST,RESEARCH):
    before=copy.deepcopy(row)
    assert r._dispatch_shape_identity(row)==(
      row['shape_id'],r.AuthorityCeiling.READ_ONLY,State(row['shape_state']))
    assert row==before
  class Row(dict):
    pass
  with pytest.raises(ValueError):
    r._dispatch_shape_identity(Row(TRUST))
  alias=shape(shape_id='SURFACE/LOCAL_COMPUTE/AGENTIC_TRUST_EVALUATOR_SURFACE',
    shape_state='measurement_pending',surface_delta_signal='capability_surface_delta:local_compute')
  with pytest.raises(ValueError,match='permanent evidence-only identity'):
    r._dispatch_shape_identity(alias)

@param('rows',[None,{},[],(),[None]])
def test_shape_collection(rows):
  with pytest.raises(ValueError):
    r._dispatch_safe_omitted_shapes(rows)

@param('field,value',[
  ('shape_class','invalid'),('observed_at','invalid'),('stale_after','invalid'),
  ('stale_after','1000000000d'),('evidence_refs',None),('resource_semantics',[]),
  ('failure_classes',[None]),('summary',None),('freshness_state','invalid'),
])
def test_observation_isolation(tmp,field,value):
  data=root();data['omitted_capability_shapes'][0][field]=value
  path=tmp/'registry.json';original=json.dumps(data);path.write_text(original)
  with pytest.raises(RegistryError):
    r.load_platform_capability_registry(path,now=NOW)
  got,errors=load(path,now=NOW,apply_receipts=False)
  assert len(errors)==1 and SID in errors[0]
  assert[x.model_dump(mode='json')for x in got.routes]==[x.model_dump(mode='json')for x in registry().routes]
  s=got.omitted_capability_shapes[0]
  assert s.shape_id==SID and s.shape_state is State.EVIDENCE_ONLY
  assert s.authority_ceiling is r.AuthorityCeiling.READ_ONLY
  assert not s.demand_eligible and s.route_ids==[]and s.surface_delta_signal is None
  assert s.observation_receipt_class==TRUST['observation_receipt_class']
  assert s.observed_at is None and s.evidence_refs==[]
  assert s.freshness_state is Fresh.MISSING
  assert s.blocked_reasons==['observation_metadata_invalid_fail_local']
  assert s.remediation_refs==['require:repair-platform-capability-registry-observation-metadata']
  assert path.read_text()==original
  assert r.check_registry_freshness(got,now=NOW)==r.check_registry_freshness(registry(),now=NOW)

@param('state',['evidence_only','intake_required','measurement_pending','deprecated'])
def test_repair_disposition(state):
  row=shape(shape_id='local_compute.synthetic',shape_state=state,
    shape_class='invalid',summary=None,carrier_family='',harness_shape='',
    stale_after='bad',resource_semantics=[],spend_semantics=None,observability=[],
    failure_classes=[],measurement_plan_refs=[],surface_delta_signal=None)
  if state!='evidence_only':row['surface_delta_signal']=''
  got,errors=r._dispatch_safe_omitted_shapes([row])
  assert len(errors)==len(got)==1
  s=got[0]
  assert s.shape_state.value==state and not s.demand_eligible and s.route_ids==[]
  assert s.surface_delta_signal==(None if state=='evidence_only' else 'capability_surface_delta:local_compute')
  assert s.shape_class is r.CapabilityShapeClass.LOCAL_COMPUTE
  assert s.blocked_reasons==['deprecated_observation_metadata_invalid' if state=='deprecated' else 'observation_metadata_invalid_fail_local']
  assert s.spend_semantics==['no-spend-authority']
  assert s.measurement_plan_refs==['require:repair-observation-metadata']

def test_loader_binding(mp,tmp):
  data=root();path=tmp/'platform-capability-registry.json';path.write_text(json.dumps(data))
  mp.delenv(CFG)
  got,errors=load(path,apply_receipts=False)
  assert errors==()and got==registry()
  with pytest.raises(RuntimeError,match=CFG):load()
  mp.setenv(CFG,str(tmp))
  assert load(apply_receipts=False)==(got,())
  def forbidden(*args,**kwargs):pytest.fail('disabled receipt overlay ran')
  mp.setattr(r,'apply_platform_capability_receipts',forbidden)
  mp.setattr(r,'_apply_route_authority_receipts_from_dir',forbidden)
  assert load(path,receipt_dir=tmp,apply_receipts=False)==(got,())
  mp.setenv(CFG,str(tmp/'missing'))
  assert load(path,apply_receipts=False)==(got,())

@param('fault',['absent','json','array','empty-shapes','duplicate','alias','route-poison'])
def test_global_refusals(tmp,fault):
  data=root();path=tmp/'registry.json'
  if fault=='empty-shapes':data['omitted_capability_shapes']=[]
  if fault=='duplicate':data['omitted_capability_shapes']*=2
  if fault=='alias':data['omitted_capability_shapes'].append(shape(shape_id='surface.'+SID))
  if fault=='route-poison':data['routes'][0]['route_id']='invented.route.name'
  if fault!='absent':path.write_text('{' if fault=='json' else '[]' if fault=='array' else json.dumps(data))
  with pytest.raises(RegistryError,match='invalid dispatch platform capability registry'):
    load(path,apply_receipts=False,now=NOW)

def test_receipt_time_binding(mp,tmp):
  from hapax.spine import dispatcher_policy as policy
  data=root()
  target=next(v for v in data['routes']if v['route_id']==REVIEW)
  target['blocked_reasons']=[HOLD,'opus_model_entitlement_receipt_absent']
  target['freshness']['evidence']['capability']['blocked_reasons']=['opus_model_entitlement_receipt_absent']
  path=tmp/'registry.json';path.write_text(json.dumps(data))
  receipts=tmp/'receipts';auth=receipts/'route-authority';auth.mkdir(parents=True)
  (receipts/'synthetic.json').write_text(rec().model_dump_json())
  grant=policy.build_route_authority_receipt(receipt_type='opus_model_entitlement',
    route_id=REVIEW,evidence_refs=['test:synthetic'],signed_by='fixture',issued_at=NOW)
  (auth/'synthetic.json').write_text(grant.model_dump_json())
  mp.setattr(r,'_route_specific_quota_admission_fresh',lambda*a,**kw:(False,()))
  got,errors=load(path,receipt_dir=receipts,now=NOW)
  assert not errors
  by_id=got.route_map()
  assert by_id[RID].freshness.capability_checked_at==NOW
  assert 'opus_model_entitlement_receipt_absent' not in by_id[REVIEW].blocked_reasons
  assert HOLD in by_id[REVIEW].blocked_reasons
  assert got==r.load_platform_capability_registry(path,receipt_dir=receipts,now=NOW)
  mp.setenv('HAPAX_PLATFORM_CAPABILITY_RECEIPT_DIR',str(receipts))
  assert load(path,now=NOW)==(got,())

def disposition(reg,change):
  return r.disposition_for_capability_surface_delta(reg,change)

def signal(surface):
  return CapabilitySurfaceDelta.model_validate(delta(surface_id=surface))

def ordinary(name='local_compute.synthetic',state='measurement_pending',token='local_compute'):
  return shape(shape_id=name,shape_state=state,
    surface_delta_signal='capability_surface_delta:'+token,
    blocked_reasons=['deprecated' if state=='deprecated' else 'measurement_required'])

@param('surface,expected',[
  (SID,True),('surface.'+SID,True),('SURFACE/'+SID.upper().replace('.','/'),True),
  (SID+'.child',False),('surface.'+SID+'.child',False),('local_compute.unrelated',False),
])
def test_exact_identity(surface,expected):
  reg=registry();old=reg.model_dump_json()
  assert r.is_registered_evidence_only_surface(reg,surface)is expected
  got=disposition(reg,signal(surface))
  assert got.action.value==('known_evidence_only_observe' if expected else 'mint_intake')
  assert got.demand_eligible is False and reg.model_dump_json()==old
  assert got.descriptor_id==(SID if expected else None)
  assert('evidence_only_observation_not_dispatch_supply' in got.reason_codes)is expected
  assert 'measured_supply_leaf_absent' in got.reason_codes

@param('surface,state,action',[
  ('local_compute.synthetic','measurement_pending','known_hold_for_measurement'),
  ('local_compute.synthetic.child','intake_required','known_hold_for_measurement'),
  ('surface.local_compute.child','measurement_pending','known_hold_for_measurement'),
  ('local_compute.synthetic-other','measurement_pending','mint_intake'),
  ('local_compute.synthetic.child','deprecated','deprecated_refuse'),
  ('surface.local_compute.child','deprecated','mint_intake'),
])
def test_matching_non_supply(surface,state,action):
  row=ordinary(state=state);reg=registry(shape(),row)
  got=disposition(reg,signal(surface))
  assert got.action.value==action and got.demand_eligible is False
  assert r.is_registered_evidence_only_surface(reg,row['shape_id'])is False
  if action!='mint_intake':assert got.remediation_refs==tuple(row['remediation_refs'])

def test_evidence_precedence_and_sort():
  reg=registry(shape(),ordinary('aaa.carrier'),ordinary('zzz.carrier'))
  got=disposition(reg,signal('surface.'+SID))
  assert got.action.value=='known_evidence_only_observe' and got.descriptor_id==SID
  reg=registry(shape(),ordinary('zzz.carrier'),ordinary('aaa.carrier'))
  got=disposition(reg,signal('surface.local_compute.child'))
  assert got.action.value=='known_hold_for_measurement' and got.descriptor_id=='aaa.carrier'
  assert not got.demand_eligible
  s=Shape.model_validate(ordinary())
  s.surface_delta_signal=None
  assert r._surface_matches_shape(signal('surface.local_compute.child'),s)is False

@param('fault,ok',[
  ('fresh',True),('stale-boundary',True),('stale',False),('future-boundary',True),
  ('future',False),('missing',False),('state',False),('no-evidence',False),('naive',True),
])
def test_freshness_isolation(fault,ok):
  reg=registry(shape(observed_at=NOW,freshness_state='fresh',evidence_refs=['test:fresh'],blocked_reasons=[]))
  s=reg.omitted_capability_shapes[0]
  s.stale_after='1h'
  if fault.startswith('stale'):s.observed_at=NOW-timedelta(hours=1,microseconds=int(fault=='stale'))
  if fault.startswith('future'):s.observed_at=NOW+timedelta(minutes=1,microseconds=int(fault=='future'))
  if fault=='missing':s.observed_at=None
  if fault=='state':s.freshness_state=Fresh.CONTRADICTORY
  if fault=='no-evidence':s.evidence_refs=[]
  if fault=='naive':s.observed_at=NOW.replace(tzinfo=None)
  routes=[x.model_dump_json()for x in reg.routes]
  got=r.check_omitted_shape_freshness(reg,now=NOW)
  assert got.ok is ok and got.shape_count==1 and got.checked_at==NOW
  assert got.shapes[0].ok is ok and bool(got.shapes[0].errors)is(not ok)
  assert got.shapes[0].evidence_refs==tuple(s.evidence_refs)
  assert got.shapes[0].blocked_reasons==tuple(s.blocked_reasons)
  assert got.to_dict()['shapes'][0]['shape_id']==SID
  assert routes==[x.model_dump_json()for x in reg.routes]
  reg.omitted_capability_shapes.append(Shape.model_validate(ordinary('aaa.first')))
  report=r.check_omitted_shape_freshness(reg,now=NOW)
  assert report.shape_count==2 and not report.ok
  assert[x.shape_id for x in report.shapes]==sorted(x.shape_id for x in reg.omitted_capability_shapes)

def test_whole_tuple():
  entries=r._DYNAMIC_ENTRYPOINTS
  assert len(entries)==len({x.__qualname__ for x in entries})==16
  assert entries[8] is r.disposition_for_capability_surface_delta
  for entry in entries:
    obj=r
    for part in entry.__qualname__.split('.'):obj=getattr(obj,part)
    assert callable(entry) and entry==obj
  assert get_type_hints(r.disposition_for_capability_surface_delta)['delta'] is CapabilitySurfaceDelta

def _mutations():
  import ast,hashlib,os,subprocess,sys,tempfile
  p=Path(r.__file__);orig=p.read_bytes();s=orig.decode();lines=s.splitlines(True);pos=[0]
  assert p.resolve()==Path(__file__).resolve().parents[1]/'src/hapax/spine/platform_capability_registry.py'
  for line in lines:pos.append(pos[-1]+len(line))
  edits=[]
  def add(n,text):
    a=pos[n.lineno-1]+n.col_offset;b=pos[n.end_lineno-1]+n.end_col_offset
    edits.append((str(n.lineno)+':'+text,(s[:a]+text+s[b:]).encode()))
  fns=[n for n in ast.parse(s).body if isinstance(n,ast.FunctionDef)][-8:]
  assert len(fns)==8 and fns[0].name=='check_primary_source_candidate_request'
  for fn in fns:
    for n in ast.walk(fn):
      if isinstance(n,ast.If):add(n.test,'False')
      if isinstance(n,ast.BoolOp) and (fn is fns[0] or fn.name=='is_registered_evidence_only_surface'):
        for part in n.values:
          # Password implies a non-None username under urlsplit: redundant conjunct.
          if ast.get_source_segment(s,part)!='target.password is None':add(part,'True' if isinstance(n.op,ast.And) else 'False')
      if isinstance(n,ast.Continue):add(n,'pass')
      if isinstance(n,ast.Call) and isinstance(n.func,ast.Name):
        if n.func.id=='all':add(n.func,'any')
        if n.func.id in ('sorted','resolve_config_path'):add(n,ast.get_source_segment(s,n.args[0]))
      if isinstance(n,ast.keyword) and n.arg=='now':add(n.value,'None')
      if isinstance(n,ast.IfExp) and ast.get_source_segment(s,n.test)=='apply_receipts':add(n.test,'True')
  text='    disposition_for_capability_surface_delta,\n'
  assert s.count(text)==1;edits.append(('tuple-entry',s.replace(text,'').encode()))
  def run():
    env=os.environ.copy();env.pop('PYTHONPATH',None)
    with tempfile.TemporaryDirectory() as cache:
      env['PYTHONPYCACHEPREFIX']=cache
      out=subprocess.run([sys.executable,'-m','pytest','-q',__file__],env=env,text=True,capture_output=True)
    print(out.stdout+out.stderr,flush=True);return out.returncode
  assert run()==0
  for label,mut in edits:
    try:
      assert p.read_bytes()==orig and mut!=orig;ast.parse(mut)
      print(json.dumps({'control':label,'mutant_sha256':hashlib.sha256(mut).hexdigest()}),flush=True)
      p.write_bytes(mut);assert run()==1
    finally:p.write_bytes(orig)
    assert p.read_bytes()==orig and run()==0
  print(json.dumps({'controls':len(edits),'all_killed_and_restored':True,'source_sha256':hashlib.sha256(orig).hexdigest()}))

if __name__=='__main__':
  import sys
  assert sys.argv[1:]==['--mutation-controls'];_mutations()
