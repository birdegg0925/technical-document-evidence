from __future__ import annotations
from pathlib import Path
import importlib.metadata,json,time
from pypdf import PdfReader
from .common import dump,jsonl,read_manifest,file_sha,text_sha,object_sha,protected_cache_out

def ingest(manifest,out):
 docs=read_manifest(manifest);protected_cache_out(out,docs);out=Path(out);pages=[];summary=[];started=time.perf_counter()
 for doc in docs:
  source=Path(doc['pdf_path'])
  if not source.is_absolute():source=(Path(manifest).parent/source).resolve()
  checksum=file_sha(source)
  if doc.get('pdf_sha256') and doc['pdf_sha256']!=checksum:raise ValueError('PDF hash differs from declared snapshot: '+doc['doc_id'])
  reader=PdfReader(source);eid='pypdf:'+object_sha({'pdf':checksum,'pypdf':importlib.metadata.version('pypdf'),'method':'extract_text_raw_v1'})[:24]
  metadata={k:v for k,v in doc.items() if k not in ['pdf_path','layout_risk_pages']};metadata['pdf_sha256']=checksum
  for i,page in enumerate(reader.pages,1):
   text=page.extract_text() or ''
   pages.append({'doc_id':doc['doc_id'],'page':i,'text':text,'extraction_id':eid,'pdf_sha256':checksum,'document_sha256':checksum,'text_sha256':text_sha(text),
                 'metadata':metadata,'layout_risk':i in doc.get('layout_risk_pages',[]),'read':'text','backend':'local_pypdf'})
  summary.append({'doc_id':doc['doc_id'],'physical_pages':len(reader.pages),'pdf_sha256':checksum,'extraction_id':eid,'empty_text_pages':sum(p['doc_id']==doc['doc_id'] and not p['text'].strip() for p in pages)})
  print(f"ingested {doc['doc_id']}: {len(reader.pages)} physical pages",flush=True)
 jsonl(out/'pages.jsonl',pages);dump(out/'corpus_manifest.json',{'documents':summary,'total_pages':len(pages),'contains_full_source_text':True,'seconds':time.perf_counter()-started,'scope':'text extraction only, not layout/visual verification'})
 return pages
