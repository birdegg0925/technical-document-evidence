from __future__ import annotations
import datetime,re
from pydantic import BaseModel,Field,ConfigDict

class Query(BaseModel):
 question:str=Field(min_length=1,max_length=4000)
 model:str|None=None
 version:str|None=None
 version_policy:str='explicit'
 claim:str|None=None
 model_config=ConfigDict(extra='forbid')

def validate_query(payload):
 q=Query(**payload)
 if q.version_policy not in ['explicit','latest']:raise ValueError('version_policy must be explicit/latest')
 if not q.question.strip():raise ValueError('question is empty')
 return q.model_dump()

def catalog(pages):
 docs={p['doc_id']:p['metadata'] for p in pages};aliases={}
 for d in docs.values():
  model=d.get('model')
  if model:
   for alias in [model]+d.get('model_aliases',[]):aliases[alias.lower()]=model
 return docs,aliases

def parse_model_mentions(question,aliases):
 found=[];occupied=[]
 for alias,model in sorted(aliases.items(),key=lambda a:-len(a[0])):
  pattern=r'(?<![A-Za-z0-9_])'+re.escape(alias).replace(r'\ ',r'\s+')+r'(?![A-Za-z0-9_])'
  for m in re.finditer(pattern,question,re.I):
   if any(m.start()<b and m.end()>a for a,b in occupied):continue
   occupied.append((m.start(),m.end()));found.append(model)
 return list(dict.fromkeys(found))

def resolve_scope(query,pages):
 docs,aliases=catalog(pages);mentions=parse_model_mentions(query['question'],aliases);reasons=[]
 requested=query.get('model')
 if requested:
  model=aliases.get(requested.lower(),requested)
  if model not in {d.get('model') for d in docs.values()}:reasons.append('unknown_requested_model')
 else:
  model=mentions[0] if len(mentions)==1 else None
  if len(mentions)>1:reasons.append('multiple_model_mentions')
  elif not mentions and len({d.get('model') for d in docs.values()})>1:reasons.append('model_unspecified')
 if requested and mentions and model not in mentions:reasons.append('question_model_conflicts_with_explicit_field')
 version=query.get('version');policy=query['version_policy']
 textual_versions=list(dict.fromkeys(re.findall(r'\b(?:version\s*|v)(\d+(?:\.\d+)*)\b',query['question'],re.I)+re.findall(r'\b(?:revision|release)\s+(R?\d+(?:\.\d+)*)\b',query['question'],re.I)))
 if query.get('version') and textual_versions and query['version'].lower() not in [v.lower() for v in textual_versions]:reasons.append('question_version_conflicts_with_explicit_field')
 if len(textual_versions)>1:reasons.append('multiple_version_mentions')
 if version is None:
  m=re.search(r'\b(?:version\s*|v)(\d+(?:\.\d+)*)\b',query['question'],re.I)
  if m:version=m.group(1)
  if version is None:
   m=re.search(r'\b(?:revision|release)\s+(R?\d+(?:\.\d+)*)\b',query['question'],re.I)
   if m:version=m.group(1)
 if version is None and re.search(r'\blatest\b|\bcurrent\s+(?:version|revision|manual|datasheet)\b|最新',query['question'],re.I):policy='latest'
 scoped=[d for d in docs.values() if model is None or d.get('model')==model]
 versions={d.get('version') for d in scoped if d.get('version')}
 if version is not None:
  by_case={v.lower():v for v in versions};version=by_case.get(version.lower(),version)
  if version not in versions:reasons.append('unknown_requested_version')
 if version is None and len(versions)>1:
  if policy!='latest':reasons.append('version_unspecified')
  else:
   dates=[]
   for d in scoped:
    value=d.get('effective_date') or d.get('release_date')
    try:date=datetime.date.fromisoformat(value) if value else None
    except ValueError:date=None
    dates.append((date,d.get('version')))
   if any(d[0] is None for d in dates):reasons.append('latest_date_missing')
   else:
    newest=max(d[0] for d in dates);latest={v for dt,v in dates if dt==newest}
    if len(latest)!=1:reasons.append('latest_date_tie')
    else:version=next(iter(latest))
 return {'requested_model':model,'requested_version':version,'model_mentions':mentions,'textual_version_mentions':textual_versions,'version_policy':policy,'latest_scope':'indexed_snapshot_only_not_manufacturer_completeness','reasons':reasons,'ambiguous':bool(reasons)}

def page_scope(page,scope):
 m=page['metadata'];model_ok=scope['requested_model'] is None or m.get('model')==scope['requested_model'];version_ok=scope['requested_version'] is None or m.get('version')==scope['requested_version']
 return {'model_match':model_ok,'version_match':version_ok,'scope_valid':model_ok and version_ok and not scope['ambiguous']}
