from __future__ import annotations
import argparse,json
from pathlib import Path
from .common import dump,read_jsonl,jsonl
from .bm25 import PageBM25,build
from .corpus import ingest
from .retrieve import ask,validate_citation
from .fixtures import fixture
from .evaluate import evaluate

def main():
 p=argparse.ArgumentParser(description='Local evidence service plus an explicitly optional genuine Page Search SDK adapter')
 sub=p.add_subparsers(dest='command',required=True)
 a=sub.add_parser('fixture');a.add_argument('--out',required=True)
 a=sub.add_parser('ingest');a.add_argument('--manifest',required=True);a.add_argument('--out',required=True)
 a=sub.add_parser('build');a.add_argument('--pages',required=True);a.add_argument('--out',required=True)
 a=sub.add_parser('ask');a.add_argument('--index',required=True);a.add_argument('--question',required=True);a.add_argument('--model');a.add_argument('--version');a.add_argument('--version-policy',choices=['explicit','latest'],default='explicit');a.add_argument('--claim');a.add_argument('--out',required=True)
 a=sub.add_parser('evaluate');a.add_argument('--index',required=True);a.add_argument('--cases',required=True);a.add_argument('--out',required=True)
 a=sub.add_parser('serve');a.add_argument('--index',required=True);a.add_argument('--host',default='127.0.0.1');a.add_argument('--port',type=int,default=8765)
 a=sub.add_parser('verify');a.add_argument('--index',required=True);a.add_argument('--out',required=True)
 a=sub.add_parser('validate-citation');a.add_argument('--index',required=True);a.add_argument('--citation',required=True);a.add_argument('--out',required=True)
 a=sub.add_parser('import-pageindex');a.add_argument('--response',required=True);a.add_argument('--mapping',required=True);a.add_argument('--out',required=True)
 a=sub.add_parser('pageindex-search');a.add_argument('--mapping',required=True);a.add_argument('--question',required=True);a.add_argument('--out',required=True);a.add_argument('--allow-live',action='store_true')
 a=sub.add_parser('pageindex-upload');a.add_argument('--manifest',required=True);a.add_argument('--out',required=True);a.add_argument('--allow-live',action='store_true')
 for name in ['ask','evaluate','serve']:
  a=sub.choices[name];a.add_argument('--mode',choices=['bm25','neighbors','scoped'],default='scoped');a.add_argument('--page-budget',type=int,default=4);a.add_argument('--char-budget',type=int,default=6000)
 a=sub.choices['pageindex-search'];a.add_argument('--page-budget',type=int,default=4);a.add_argument('--char-budget',type=int,default=6000)
 args=p.parse_args()
 if args.command=='fixture':fixture(args.out)
 elif args.command=='ingest':ingest(args.manifest,args.out)
 elif args.command=='build':build(args.pages,args.out)
 elif args.command=='ask':
  q={k:getattr(args,k) for k in ['question','model','version','version_policy','claim']};result=ask(PageBM25.load(args.index),q,args.mode,args.page_budget,args.char_budget);dump(args.out,result);print({k:result[k] for k in ['decision','reasons','budget']})
 elif args.command=='evaluate':evaluate(PageBM25.load(args.index),args.cases,args.out,args.mode,args.page_budget,args.char_budget)
 elif args.command=='serve':
  from .server import serve
  serve(PageBM25.load(args.index),args.host,args.port,args.mode,args.page_budget,args.char_budget)
 elif args.command=='validate-citation':
  result=validate_citation(json.loads(Path(args.citation).read_text()),PageBM25.load(args.index));dump(args.out,result|{'semantic_review_required':True,'entailment_verified':False});print(result)
 elif args.command=='verify':
  index=PageBM25.load(args.index);checks={'physical_pages_positive':all(type(p['page'])is int and p['page']>0 for p in index.pages),'unique_document_page_keys':len(index.by_key)==len(index.pages),'all_text_hashes_match':all(__import__('tech_evidence.common',fromlist=['text_sha']).text_sha(p['text'])==p['text_sha256'] for p in index.pages)}
  dump(args.out,{'checks':checks,'all_passed':all(checks.values()),'n_pages':len(index.pages)});print(checks)
  if not all(checks.values()):raise SystemExit(1)
 else:
  from .pageindex_adapter import import_response,search,upload
  if args.command=='import-pageindex':import_response(json.loads(Path(args.response).read_text()),json.loads(Path(args.mapping).read_text()),args.out)
  elif args.command=='pageindex-search':search(json.loads(Path(args.mapping).read_text()),args.question,args.out,args.page_budget,args.char_budget,args.allow_live)
  else:upload(args.manifest,args.out,args.allow_live)
if __name__=='__main__':main()
