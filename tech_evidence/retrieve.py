from __future__ import annotations
import math,re,time
from .common import tokens,text_sha
from .query import validate_query,resolve_scope,page_scope

def span_window(page,question,length):
 text=page['text'];terms=set(tokens(question));best=(0,0.)
 for m in re.finditer(r'\S+',text):
  if set(tokens(m.group()))&terms:
   start=max(0,min(len(text)-length,m.start()-length//3));window=text[start:start+length];score=sum(1 for t in tokens(window) if t in terms)
   if score>best[1]:best=(start,score)
 start=best[0];return start,min(len(text),start+length)

def validate_citation(c,index):
 if not isinstance(c,dict) or not isinstance(c.get('doc_id'),str) or type(c.get('page'))is not int or c['page']<1:return {'coordinate_valid':False,'reason':'invalid_citation_identifier_types'}
 key=(c.get('doc_id'),c.get('page'));i=index.by_key.get(key)
 if i is None:return {'coordinate_valid':False,'reason':'unknown_document_or_page'}
 p=index.pages[i];a,b=c.get('char_start'),c.get('char_end')
 if c.get('document_sha256')!=p.get('document_sha256',p.get('pdf_sha256')):return {'coordinate_valid':False,'reason':'document_snapshot_mismatch'}
 if c.get('extraction_id')!=p['extraction_id'] or c.get('pdf_sha256')!=p.get('pdf_sha256') or c.get('text_sha256')!=p['text_sha256']:return {'coordinate_valid':False,'reason':'extraction_or_snapshot_mismatch'}
 if type(a)is not int or type(b)is not int or not 0<=a<b<=len(p['text']):return {'coordinate_valid':False,'reason':'span_out_of_bounds'}
 quote=p['text'][a:b]
 if quote!=c.get('quote') or text_sha(quote)!=c.get('quote_sha256'):return {'coordinate_valid':False,'reason':'quote_does_not_match_source_span'}
 return {'coordinate_valid':True,'reason':'same_extraction_exact_span','coordinate_basis':'characters_in_this_extraction_only','pdf_geometry_or_visual_verified':False}

def claim_check(claim,quote):
 if not claim:return {'status':'not_requested','entailment_verified':False}
 a=' '.join(claim.lower().split());b=' '.join(quote.lower().split())
 if a in b:return {'status':'literal_match','entailment_verified':False}
 nums=re.findall(r'\d+(?:\.\d+)?',a)
 if nums and any(n not in b for n in nums):return {'status':'numeric_literal_absent','entailment_verified':False}
 return {'status':'not_a_literal_match','entailment_verified':False}

def ask(index,payload,mode='scoped',page_budget=4,char_budget=6000):
 start=time.perf_counter()
 if mode not in ['bm25','neighbors','scoped'] or type(page_budget)is not int or type(char_budget)is not int or page_budget<1 or char_budget<1:raise ValueError('invalid mode/budget')
 q=validate_query(payload);scope=resolve_scope(q,index.pages);allowed=None
 if mode=='scoped':allowed={i for i,p in enumerate(index.pages) if (scope['requested_model'] is None or p['metadata'].get('model')==scope['requested_model']) and (scope['requested_version'] is None or p['metadata'].get('version')==scope['requested_version'])}
 ranked=index.search(q['question'],allowed);selected=[];seen=set();scores=dict(ranked)
 def add(i,kind):
  if i not in seen and len(selected)<page_budget:seen.add(i);selected.append((i,kind))
 if mode=='bm25':
  for i,_ in ranked[:page_budget]:add(i,'ranked')
 else:
  for i,_ in ranked:
   add(i,'ranked');p=index.pages[i]
   for offset in [-1,1]:
    j=index.by_key.get((p['doc_id'],p['page']+offset))
    if j is not None and (allowed is None or j in allowed):add(j,'neighbor')
   if len(selected)>=page_budget:break
 candidates=[];remaining=char_budget
 for position,(i,kind) in enumerate(selected):
  if remaining<=0:break
  p=index.pages[i];limit=max(1,min(1800,remaining//max(1,len(selected)-position)));a,b=span_window(p,q['question'],limit)
  if b<=a:continue
  quote=p['text'][a:b];remaining-=len(quote)
  c={k:p[k] for k in ['doc_id','page','extraction_id','pdf_sha256','text_sha256']};c['document_sha256']=p.get('document_sha256',p.get('pdf_sha256'));c.update(char_start=a,char_end=b,quote=quote,quote_sha256=text_sha(quote),score=float(scores.get(i,0.)),selection=kind,metadata=p['metadata'],layout_risk=p.get('layout_risk',False))
  c['source_backend']=p.get('backend','unknown');c['read']=p.get('read','text');c['same_pdf_mapping_verified']=p.get('same_pdf_mapping_verified',p.get('backend')=='local_pypdf');c['visual_verification_performed']=p.get('visual_verification_performed',False);c['mapping_basis']=p.get('mapping_basis','local_pdf_hash_and_extractor' if p.get('backend')=='local_pypdf' else 'synthetic_or_unverified');c.update(validate_citation(c,index));c.update(page_scope(p,scope));c['claim_check']=claim_check(q.get('claim'),quote);c['required_conditions']=p.get('required_conditions',[]);c['condition_topic_terms']=p.get('condition_topic_terms',[]);applicable=not c['condition_topic_terms'] or bool(set(tokens(q['question']))&set(c['condition_topic_terms']));c['conditions_applicable_by_literal_topic']=applicable;c['missing_conditions']=[s for s in c['required_conditions'] if applicable and s.lower() not in (q['question']+' '+(q.get('claim') or '')).lower()];candidates.append(c)
 reasons=list(scope['reasons']);decision='support'
 if not candidates:decision='insufficient';reasons.append('no_positive_lexical_evidence_within_scope')
 elif any(not c['coordinate_valid'] or not c['scope_valid'] for c in candidates):decision='review';reasons.append('candidate_package_has_invalid_coordinate_or_scope')
 if candidates and candidates[0]['layout_risk']:decision='review';reasons.append('layout_or_cross_page_conditions_need_review')
 if candidates and any(c['source_backend'] in ['pageindex_sdk','contract_fixture','saved_pageindex_response_unverified'] and (not c['same_pdf_mapping_verified'] or c['read']=='image' and not c['visual_verification_performed']) for c in candidates):decision='review';reasons.append('remote_mapping_or_visual_verification_incomplete')
 if any(index.pages[i].get('read')=='image' for i,_ in selected):decision='review' if candidates else 'insufficient';reasons.append('selected_image_page_not_visually_verified')
 if candidates and q.get('claim') and candidates[0]['claim_check']['status']!='literal_match':decision='review';reasons.append('proposed_claim_not_locally_literal_supported')
 if candidates and any(c['missing_conditions'] for c in candidates):decision='review';reasons.append('visible_source_conditions_not_explicit_in_query')
 if scope['ambiguous'] and candidates:decision='review'
 if any(x in scope['reasons'] for x in ['unknown_requested_model','unknown_requested_version']):decision='insufficient'
 response={'query':q,'backend':'local_page_bm25','method_mode':mode,'not_pageindex':True,'decision':decision,'decision_meaning':'support means structurally checked evidence candidates, not a semantically supported answer',
 'semantic_review_required':True,'scope':scope,'reasons':list(dict.fromkeys(reasons)),'candidates':candidates,
 'budget':{'page_budget':page_budget,'pages_returned':len(candidates),'pages_selected_including_unread_images':len(selected),'char_budget':char_budget,'evidence_chars':sum(len(c['quote']) for c in candidates),'utf8_bytes':sum(len(c['quote'].encode()) for c in candidates),'corpus_pages_scored':len(index.pages) if allowed is None else len(allowed),'model_tokens':'not measured; no LLM was invoked'},
 'renderer':'extractive_non_llm','answer_excerpt':candidates[0]['quote'] if candidates and decision!='insufficient' else None,'seconds':time.perf_counter()-start}
 return response
