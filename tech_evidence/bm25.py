"""Actual Okapi BM25 over physical pages, with fixed public lexical normalization."""
from __future__ import annotations
import collections,math
from .common import tokens,dump,read_jsonl,protected_cache_out,object_sha

class PageBM25:
 def __init__(self,pages,k1=1.5,b=.75):
  self.pages=pages;self.k1=float(k1);self.b=float(b);self.tf=[collections.Counter(tokens(p['text'])) for p in pages];self.lengths=[sum(x.values()) for x in self.tf]
  self.average=sum(self.lengths)/max(1,len(pages));self.df=collections.Counter(t for bag in self.tf for t in bag);self.by_key={}
  for i,p in enumerate(pages):
   key=(p['doc_id'],p['page'])
   if key in self.by_key:raise ValueError('duplicate physical page key')
   self.by_key[key]=i
 def search(self,question,allowed=None):
  query=collections.Counter(tokens(question));N=len(self.pages);scored=[]
  for i,bag in enumerate(self.tf):
   if allowed is not None and i not in allowed:continue
   score=0.
   for term,qtf in query.items():
    freq=bag.get(term,0)
    if not freq:continue
    idf=math.log(1+(N-self.df[term]+.5)/(self.df[term]+.5))
    den=freq+self.k1*(1-self.b+self.b*self.lengths[i]/max(self.average,1e-9));score+=idf*freq*(self.k1+1)/den*qtf
   if score>0:scored.append((i,float(score)))
  return sorted(scored,key=lambda x:(-x[1],self.pages[x[0]]['doc_id'],self.pages[x[0]]['page']))
 def save(self,path):
  protected_cache_out(path,[p['metadata'] for p in self.pages]);dump(path,{'format':'local_page_bm25_v1','k1':self.k1,'b':self.b,'pages':self.pages,'corpus_fingerprint':object_sha(self.pages),'contains_full_source_text':True,'not_pageindex':True})
 @classmethod
 def load(cls,path):
  import json
  obj=json.loads(__import__('pathlib').Path(path).read_text())
  if obj['format']!='local_page_bm25_v1':raise ValueError('unknown local index format')
  if object_sha(obj['pages'])!=obj['corpus_fingerprint']:raise ValueError('index corpus fingerprint mismatch')
  return cls(obj['pages'],obj['k1'],obj['b'])
def build(pages_path,out):
 index=PageBM25(read_jsonl(pages_path));index.save(out);print(f'indexed {len(index.pages)} physical pages');return index
