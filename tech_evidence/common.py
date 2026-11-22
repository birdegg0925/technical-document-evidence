from __future__ import annotations
import hashlib,json,re,unicodedata
from pathlib import Path

def dump(path,obj):
 p=Path(path);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(obj,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
def jsonl(path,rows):
 p=Path(path);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(''.join(json.dumps(r,ensure_ascii=False,allow_nan=False)+'\n' for r in rows),encoding='utf-8')
def read_jsonl(path):return [json.loads(x) for x in Path(path).read_text().splitlines() if x.strip()]
def text_sha(s):return hashlib.sha256(s.encode('utf-8')).hexdigest()
def object_sha(x):return text_sha(json.dumps(x,sort_keys=True,ensure_ascii=False))
def file_sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for chunk in iter(lambda:f.read(1<<20),b''):h.update(chunk)
 return h.hexdigest()
def read_manifest(path):
 p=Path(path);obj=json.loads(p.read_text())
 docs=obj['documents'] if isinstance(obj,dict) else obj
 if not isinstance(docs,list):raise ValueError('manifest must be document list or {documents:[...]}')
 if len({d['doc_id'] for d in docs})!=len(docs):raise ValueError('duplicate doc_id')
 return docs
STOP=set('a an and are as at be by can do does for from has have how i in is it its may much of on or our the this to what which with you your'.split())
CHINESE={'内存':['ram','sram','memory'],'闪存':['flash'],'频率':['frequency','clock'],'时钟':['clock'],'状态机':['state','machine'],'电压':['voltage'],'温度':['temperature'],'电流':['current']}
def tokens(text):
 text=unicodedata.normalize('NFKC',text).lower()
 extra=[t for k,v in CHINESE.items() if k in text for t in v]
 raw=re.findall(r'[a-z][a-z0-9_+.-]*|\d+(?:\.\d+)?|[\u4e00-\u9fff]',text)
 raw=[t.strip('.-') for t in raw if t not in STOP]
 if 'sram' in raw:extra.append('ram')
 if 'ram' in raw:extra.append('sram')
 return [t for t in raw+extra if t]

def protected_cache_out(out,documents):
 fixtures = Path(__file__).resolve().parents[1] / 'fixtures'
 if any(d.get('source_kind') == 'official' for d in documents) and Path(out).resolve().is_relative_to(fixtures):
  raise ValueError('Choose a local cache outside fixtures/ for official source text and indexes.')
