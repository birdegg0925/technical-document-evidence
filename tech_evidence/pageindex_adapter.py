"""Optional genuine Page Search SDK boundary. No local algorithm is labeled PageIndex."""
from __future__ import annotations
import os,time,copy
from pathlib import Path
from .common import dump,jsonl,read_manifest,object_sha,text_sha,file_sha,protected_cache_out

def mapping_documents(mapping):
 docs=mapping.get('documents',[])
 if len({d['remote_doc_id'] for d in docs})!=len(docs):raise ValueError('duplicate remote_doc_id mapping')
 return docs
def flatten_response(response,mapping,backend='saved_pageindex_response_unverified'):
 by_remote={d['remote_doc_id']:d for d in mapping_documents(mapping)};pages=[]
 for result in response.get('results',[]):
  for doc in result.get('documents',[]):
   remote=doc.get('id');local=by_remote.get(remote)
   if local is None:raise ValueError('response document is absent from mapping')
   for row in doc.get('pages',[]):
    page=row.get('page')
    if type(page)is not int or page<1 or (local.get('physical_pages') and page>local['physical_pages']):raise ValueError('remote physical page out of bounds')
    read=row.get('read','text');text=row.get('text') or '';original_text_length=len(text) if isinstance(text,str) else 0
    if read not in ['text','image']:raise ValueError('unknown Page Search read mode')
    if not isinstance(text,str):raise ValueError('remote text must be a string')
    # Image rows never receive local pypdf text as a silent substitute.
    if read=='image':text=''
    pdf_sha=local.get('pdf_sha256');binding={'remote_doc_id':remote,'doc_id':local['doc_id'],'pdf_sha256':pdf_sha}
    trusted=backend=='pageindex_sdk' and mapping.get('backend')=='pageindex_sdk' and mapping.get('executed') is True and local.get('mapping_provenance')=='uploaded_by_this_adapter' and local.get('upload_binding_sha256')==object_sha(binding) and local.get('pre_upload_sha256')==local.get('post_upload_sha256')==pdf_sha
    eid='pageindex_text:'+object_sha({'remote':remote,'pdf_sha':pdf_sha,'page':page,'text':text})[:24]
    metadata=copy.deepcopy(local.get('metadata',{}));metadata['doc_id']=local['doc_id']
    pages.append({'doc_id':local['doc_id'],'remote_doc_id':remote,'page':page,'text':text,'extraction_id':eid,'pdf_sha256':pdf_sha,'document_sha256':pdf_sha,
      'text_sha256':text_sha(text),'metadata':metadata,'layout_risk':read=='image','read':read,'backend':backend,'relevance':row.get('relevance'),
      'upstream_text_length':original_text_length,'same_pdf_mapping_verified':trusted,'mapping_basis':'local_adapter_upload_record' if trusted else 'unverified_saved_or_operator_mapping','provider_content_hash_verified':False,'visual_verification_performed':False,'more_pages':bool(doc.get('more_pages')),'failed_pages':doc.get('failed_pages',[])})
 return pages

def normalize_for_application(response,mapping,page_budget=4,char_budget=6000,backend='saved_pageindex_response_unverified'):
 pages=flatten_response(response,mapping,backend);kept=[];chars=0;seen=set()
 for p in pages:
  key=(p['doc_id'],p['page'])
  if key in seen:continue
  seen.add(key)
  if len(kept)>=page_budget:continue
  row=copy.deepcopy(p);text=row['text'][:max(0,char_budget-chars)];chars+=len(text);row['application_quote']=text;row['application_char_start']=0;row['application_char_end']=len(text);kept.append(row)
 image=any(p['read']=='image' for p in kept);incomplete=bool(response.get('failed_documents') or response.get('processing_documents') or any(p['more_pages'] or p['failed_pages'] for p in pages))
 return {'backend':backend,'executed':backend=='pageindex_sdk','pages':kept,'decision':'review' if kept else 'insufficient','semantic_review_required':True,
  'reasons':['remote_extraction_coordinates_are_not_local_pypdf_offsets']+(['image_read_requires_actual_visual_review'] if image else [])+(['upstream_incomplete_or_processing'] if incomplete else []),
  'budget':{'page_budget':page_budget,'application_pages_kept':len(kept),'char_budget':char_budget,'application_chars_kept':chars,
            'upstream_page_rows_returned':len(pages),'upstream_text_chars_returned':sum(p['upstream_text_length'] for p in pages),'strict_upstream_budget_equal_to_local':False},
  'usage':response.get('usage'),'provider_seconds':response.get('seconds'),'raw_failure_status':{k:response.get(k) for k in ['failed_documents','processing_documents']},
  'visual_verification_performed':False,'local_offset_mapping_performed':False}

def real_client(allow_live):
 if not allow_live:return None,'live_api_not_authorized'
 if not os.environ.get('PAGEINDEX_API_KEY'):return None,'PAGEINDEX_API_KEY_missing'
 try:from pageindex import PageSearchClient
 except ImportError:return None,'optional_pageindex_sdk_not_installed'
 return PageSearchClient(),None

def search(mapping,question,out,page_budget=4,char_budget=6000,allow_live=False,client=None,backend='pageindex_sdk'):
 if page_budget<1 or char_budget<1:raise ValueError('positive budgets required')
 if client is not None and backend!='contract_fixture':raise ValueError('injected clients must be labeled contract_fixture')
 if client is None:
  client,reason=real_client(allow_live)
  if client is None:result={'backend':'pageindex_sdk','executed':False,'skip_reason':reason,'decision':'insufficient','semantic_review_required':True};dump(out,result);return result
 docs=mapping_documents(mapping);protected_cache_out(out,[d.get('metadata',{}) for d in docs]);ids=[d['remote_doc_id'] for d in docs]
 if not ids:raise ValueError('at least one uploaded document mapping required')
 args={'document':ids[0]} if len(ids)==1 else {'documents':ids}
 try:response=client.search(question,top_k=page_budget,include_text=True,**args)
 except Exception as error:
  result={'backend':backend,'executed':backend=='pageindex_sdk','succeeded':False,'error_type':type(error).__name__,'decision':'insufficient','semantic_review_required':True,'usage':None,'note':'provider error text is not logged because it may contain credentials'};dump(out,result);return result
 result=normalize_for_application(response,mapping,page_budget,char_budget,backend);dump(out,result);dump(str(out)+'.raw.json',response);return result

def upload(manifest,out,allow_live=False):
 if not allow_live:
  result={'backend':'pageindex_sdk','executed':False,'skip_reason':'live_api_not_authorized','documents':[]};dump(out,result);return result
 docs=read_manifest(manifest);preflight=[]
 # Validate every declared snapshot before constructing an SDK client or uploading any file.
 for doc in docs:
  p=Path(doc['pdf_path']);p=p if p.is_absolute() else Path(manifest).parent/p
  before=file_sha(p)
  if doc.get('pdf_sha256') and before!=doc['pdf_sha256']:raise ValueError('manifest PDF hash mismatch before any upload: '+doc['doc_id'])
  preflight.append((doc,p,before))
 client,reason=real_client(allow_live)
 if client is None:result={'backend':'pageindex_sdk','executed':False,'skip_reason':reason,'documents':[]};dump(out,result);return result
 entries=[]
 for doc,p,before in preflight:
  if file_sha(p)!=before:raise ValueError('local snapshot changed before upload')
  try:response=client.upload(str(p))
  except Exception as error:
   result={'backend':'pageindex_sdk','executed':True,'succeeded':False,'error_type':type(error).__name__,'documents':entries,'usage':None};dump(out,result);return result
  after=file_sha(p)
  if after!=before:
   result={'backend':'pageindex_sdk','executed':True,'succeeded':False,'reason':'snapshot_changed_during_upload','remote_doc_id':response.get('doc_id'),'mapping_provenance':'unverified','documents':entries};dump(out,result);return result
  entries.append({'upload_binding_sha256':object_sha({'remote_doc_id':response['doc_id'],'doc_id':doc['doc_id'],'pdf_sha256':before}),'remote_doc_id':response['doc_id'],'doc_id':doc['doc_id'],'pdf_sha256':before,'pre_upload_sha256':before,'post_upload_sha256':after,'physical_pages':doc.get('physical_pages'),
                  'mapping_provenance':'uploaded_by_this_adapter','metadata':{k:v for k,v in doc.items() if k!='pdf_path'}})
 result={'backend':'pageindex_sdk','executed':True,'succeeded':True,'documents':entries};dump(out,result);return result

def import_response(response,mapping,out):
 pages=flatten_response(response,mapping,'contract_fixture' if mapping.get('backend')=='contract_fixture' else 'saved_pageindex_response_unverified');protected_cache_out(out,[p['metadata'] for p in pages]);jsonl(out,pages);return pages
