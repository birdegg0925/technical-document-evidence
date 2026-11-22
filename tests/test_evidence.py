import copy,json,threading,urllib.request,urllib.error
from pathlib import Path
import pytest
from tech_evidence.fixtures import fixture
from tech_evidence.bm25 import PageBM25
from tech_evidence.common import read_jsonl,dump,text_sha,object_sha
from tech_evidence.query import validate_query,resolve_scope,parse_model_mentions
from tech_evidence.retrieve import ask,validate_citation
from tech_evidence.server import make_handler
from tech_evidence.pageindex_adapter import normalize_for_application,search
from http.server import HTTPServer

@pytest.fixture(scope='module')
def data(tmp_path_factory):
 p=tmp_path_factory.mktemp('fixture');pages,cases=fixture(p);return p,pages,cases,PageBM25(pages)

def test_bm25_is_page_retrieval_not_a_fake_pageindex(data):
 p,pages,cases,index=data;r=ask(index,cases[0]['query'],mode='scoped')
 assert r['backend']=='local_page_bm25' and r['not_pageindex']
 assert r['candidates'][0]['doc_id']=='fiction_d1_v2';assert r['semantic_review_required'] is True

def test_gold_is_forbidden_and_case_gold_does_not_affect_ask(data):
 _,_,cases,index=data
 with pytest.raises(ValueError):ask(index,{'question':'x','gold':{'answer':'SECRET'}})
 r1=ask(index,cases[0]['query']);c=copy.deepcopy(cases[0]);c['gold']={'relevant_pages':[{'doc_id':'WRONG','page':999}]};r2=ask(index,c['query'])
 for k in ['query','decision','candidates','scope']:assert r1[k]==r2[k]

@pytest.mark.parametrize('mode',['bm25','neighbors','scoped'])
def test_expansion_counts_in_absolute_page_and_character_budget(data,mode):
 _,_,cases,index=data;r=ask(index,cases[0]['query'],mode,2,89)
 assert len(r['candidates'])<=2 and sum(len(c['quote']) for c in r['candidates'])<=89
 assert all(validate_citation(c,index)['coordinate_valid'] for c in r['candidates'])
 if r['decision']=='support':assert all(c['scope_valid'] and c['coordinate_valid'] for c in r['candidates'])

@pytest.mark.parametrize('mutation',['span','quote','extraction','page','source'])
def test_incorrect_citation_is_rejected(data,mutation):
 _,_,cases,index=data;c=copy.deepcopy(ask(index,cases[0]['query'])['candidates'][0])
 if mutation=='span':c['char_start']+=1
 elif mutation=='quote':c['quote']='invented text'
 elif mutation=='extraction':c['extraction_id']='some_other_parser'
 elif mutation=='page':c['page']=999
 else:c['document_sha256']='different_snapshot'
 assert validate_citation(c,index)['coordinate_valid'] is False

def test_model_longest_alias_and_user_field_precedence(data):
 assert parse_model_mentions('Pico 2 memory',{'pico':'pico','pico 2':'pico2'})==['pico2']
 assert parse_model_mentions('Pico2内存',{'pico':'pico','pico2':'pico2'})==['pico2']
 _,pages,_,_=data;q=validate_query({'question':'Compare FICT-D2 with a chip mentioned as background','model':'FICT-D1'})
 assert resolve_scope(q,pages)['requested_model']=='FICT-D1'

def test_latest_uses_documented_dates_not_lexical_version(data):
 _,pages,_,_=data;ps=copy.deepcopy([p for p in pages if p['metadata']['model']=='FICT-D1'])
 for p in ps:
  p['metadata']['version']='9.0' if 'v1' in p['doc_id'] else '10.0';p['metadata']['effective_date']='2020-01-01' if 'v1' in p['doc_id'] else '2021-01-01'
 scope=resolve_scope(validate_query({'question':'latest FICT-D1 manual','model':'FICT-D1','version_policy':'latest'}),ps)
 assert scope['requested_version']=='10.0';assert scope['latest_scope'].startswith('indexed_snapshot')
 for p in ps:p['metadata']['effective_date']=None;p['metadata']['release_date']=None
 assert 'latest_date_missing' in resolve_scope(validate_query({'question':'latest','model':'FICT-D1','version_policy':'latest'}),ps)['reasons']

def test_unknown_model_never_silently_maps_to_existing_model(data):
 *_,index=data;r=ask(index,{'question':'supply voltage of nonexistent FICT-Z99','model':'FICT-Z99'})
 assert r['decision']=='insufficient' and r['answer_excerpt'] is None

def test_scope_and_citation_do_not_claim_entailment(data):
 _,_,cases,index=data;r=ask(index,cases[0]['query'])
 assert r['semantic_review_required'] is True
 assert all(c['claim_check']['entailment_verified'] is False for c in r['candidates'])

def test_layout_warning_preserved_but_unrelated_conditions_not_forced(data):
 _,_,cases,index=data;r=ask(index,cases[0]['query'])
 assert r['decision']=='support';assert any(c['layout_risk'] for c in r['candidates'])
 assert all(not c['missing_conditions'] for c in r['candidates'])
 q={'question':'fast mode current for FICT-T1 version 2.0','model':'FICT-T1','version':'2.0'};r=ask(index,q)
 assert r['decision']=='review';assert any(c['missing_conditions'] for c in r['candidates'])

def test_source_and_requirement_groups_are_disjoint(data):
 _,_,cases,_=data
 for field in ['source_group','requirement_family']:
  assert {c[field] for c in cases if c['split']=='dev'}.isdisjoint({c[field] for c in cases if c['split']=='test'})

def test_local_http_forbids_hidden_fields_and_checks_citations(data):
 *_,index=data;server=HTTPServer(('127.0.0.1',0),make_handler(index));thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();base=f'http://127.0.0.1:{server.server_port}'
 try:
  assert json.load(urllib.request.urlopen(base+'/health'))['pageindex_api_called'] is False
  req=urllib.request.Request(base+'/ask',data=json.dumps({'question':'FICT-D1 voltage','model':'FICT-D1','version':'2.0'}).encode(),headers={'Content-Type':'application/json'})
  response=json.load(urllib.request.urlopen(req));assert response['semantic_review_required']
  req=urllib.request.Request(base+'/ask',data=b'{"question":"x","gold":"DO_NOT_SEND"}',headers={'Content-Type':'application/json'})
  with pytest.raises(urllib.error.HTTPError) as e:urllib.request.urlopen(req)
  assert e.value.code==400
 finally:server.shutdown();server.server_close()

@pytest.fixture
def api_mapping():return {'documents':[{'remote_doc_id':'remote-A','doc_id':'fiction_A','pdf_sha256':'fake_fixture_hash','physical_pages':3,'mapping_provenance':'operator_supplied_unverified','metadata':{'model':'FICT-API','version':'1','source_kind':'synthetic'}}]}

def test_true_sdk_shape_mock_is_labeled_contract_fixture(tmp_path,api_mapping):
 class Client:
  def search(self,question,**kwargs):
   assert kwargs=={'top_k':1,'include_text':True,'document':'remote-A'}
   return {'results':[{'documents':[{'id':'remote-A','name':'fixture.pdf','pages':[{'page':1,'read':'text','relevance':.9,'text':'Fixture evidence text'},{'page':2,'read':'image','relevance':.8,'text':'ignored image OCR'}],'more_pages':True}]}], 'usage':{'credits':0.0}}
 r=search(api_mapping,'fixture?',tmp_path/'response.json',1,8,client=Client(),backend='contract_fixture')
 assert r['backend']=='contract_fixture' and r['executed'] is False
 assert r['budget']['upstream_page_rows_returned']==2 and r['budget']['application_chars_kept']==8
 assert r['local_offset_mapping_performed'] is False


def test_remote_images_never_hydrated_from_local_pypdf(api_mapping):
 response={'results':[{'documents':[{'id':'remote-A','pages':[{'page':2,'read':'image','text':'a fake local text substitute','relevance':1}]}]}]}
 r=normalize_for_application(response,api_mapping)
 assert r['pages'][0]['text']=='' and not r['visual_verification_performed']
 assert r['budget']['upstream_text_chars_returned']>0


def test_missing_key_skips_without_mock_fallback(tmp_path,monkeypatch,api_mapping):
 monkeypatch.delenv('PAGEINDEX_API_KEY',raising=False);r=search(api_mapping,'question',tmp_path/'skip.json',allow_live=True)
 assert not r['executed'] and r['skip_reason']=='PAGEINDEX_API_KEY_missing'


def test_provider_exception_does_not_log_key(tmp_path,api_mapping):
 class Client:
  def search(self,*args,**kwargs):raise RuntimeError('SECRET_KEY_SHOULD_NOT_APPEAR')
 r=search(api_mapping,'q',tmp_path/'failure.json',client=Client(),backend='contract_fixture')
 assert 'SECRET_KEY' not in json.dumps(r) and not r['succeeded']


def test_no_answer_labels_do_not_get_perfect_recall(data,tmp_path):
 from tech_evidence.evaluate import evaluate
 from tech_evidence.common import jsonl
 _,_,cases,index=data;rows=[cases[0],{'case_id':'negative','source_set':'public_manual_pilot','split':'pilot','requirement_family':'instance','source_group':'instance','query':{'question':'serial number for FICT-D2','model':'FICT-D2'},'gold':{'relevant_pages':[],'answerable_in_snapshot':False}}]
 path=tmp_path/'cases.jsonl';jsonl(path,rows);s=evaluate(index,path,tmp_path/'eval')
 assert s['retrieval']['labeled_cases']==1 and s['official_pilot_warning']

def test_upload_hash_preflight_happens_before_any_sdk_client(tmp_path,monkeypatch):
 import tech_evidence.pageindex_adapter as adapter
 p=tmp_path/'fixture.pdf';p.write_bytes(b'not a real manufacturer PDF; hash-contract fixture')
 manifest=tmp_path/'manifest.json';dump(manifest,[{'doc_id':'synthetic_contract','pdf_path':str(p),'pdf_sha256':'WRONG'}])
 called=[]
 monkeypatch.setattr(adapter,'real_client',lambda allow:called.append(True))
 with pytest.raises(ValueError):adapter.upload(manifest,tmp_path/'mapping.json',allow_live=True)
 assert not called


def test_bad_content_length_is_rejected_without_waiting_for_eof(data):
 import http.client
 *_,index=data;server=HTTPServer(('127.0.0.1',0),make_handler(index));thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
 try:
  for bad in ['-1','not_an_integer']:
   conn=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=2)
   conn.putrequest('POST','/ask');conn.putheader('Content-Length',bad);conn.endheaders();response=conn.getresponse();assert response.status==400;response.read();conn.close()
 finally:server.shutdown();server.server_close()

def test_explicit_fields_cannot_hide_clear_question_conflicts(data):
 *_,index=data
 r=ask(index,{'question':'supply voltage for FICT-D2','model':'FICT-D1','version':'2.0'})
 assert r['decision']=='review' and 'question_model_conflicts_with_explicit_field' in r['reasons']
 r=ask(index,{'question':'FICT-D1 version 1.0 supply voltage','model':'FICT-D1','version':'2.0'})
 assert r['decision']=='review' and 'question_version_conflicts_with_explicit_field' in r['reasons']
 scope=resolve_scope(validate_query({'question':'FICT-D1 compared with FICT-D2','model':'FICT-D1'}),index.pages)
 assert 'question_model_conflicts_with_explicit_field' not in scope['reasons']


def test_remote_saved_text_cannot_launder_as_verified_pdf(api_mapping):
 from tech_evidence.pageindex_adapter import flatten_response
 mapping=copy.deepcopy(api_mapping);mapping['backend']='pageindex_sdk';mapping['executed']=True;mapping['documents'][0]['mapping_provenance']='uploaded_by_this_adapter'
 response={'results':[{'documents':[{'id':'remote-A','pages':[{'page':1,'read':'text','text':'Supply voltage is 3 V.','relevance':1}]}]}]}
 pages=flatten_response(response,mapping,'saved_pageindex_response_unverified');assert not pages[0]['same_pdf_mapping_verified']
 index=PageBM25(pages);r=ask(index,{'question':'supply voltage','model':'FICT-API','version':'1'})
 assert r['decision']=='review' and r['candidates'][0]['source_backend']=='saved_pageindex_response_unverified'
 assert r['candidates'][0]['coordinate_valid'] and not r['candidates'][0]['pdf_geometry_or_visual_verified']
 duplicate=copy.deepcopy(mapping);duplicate['documents'].append(copy.deepcopy(duplicate['documents'][0]))
 with pytest.raises(ValueError):flatten_response(response,duplicate)

@pytest.mark.parametrize('citation',[None,[],{'doc_id':'x','page':True},{'doc_id':3,'page':1},{'doc_id':'x','page':0}])
def test_citation_identifier_types_are_strict(data,citation):
 *_,index=data
 assert validate_citation(citation,index)['coordinate_valid'] is False
