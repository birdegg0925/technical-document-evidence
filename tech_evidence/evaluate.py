"""Gold is read only by the outer evaluator, never by retrieval or scope decisions."""
from __future__ import annotations
import csv,copy
from pathlib import Path
from .common import read_jsonl,jsonl,dump,file_sha
from .retrieve import ask

def evaluate(index,cases_path,out,mode='scoped',page_budget=4,char_budget=6000):
 cases=read_jsonl(cases_path)
 if len({c['case_id'] for c in cases})!=len(cases):raise ValueError('duplicate case_id')
 out=Path(out);out.mkdir(parents=True,exist_ok=True);records=[]
 for case in cases:
  response=ask(index,copy.deepcopy(case['query']),mode,page_budget,char_budget);gold=case.get('gold',{});relevant={(p['doc_id'],p['page']) for p in gold.get('relevant_pages',[])}
  returned={(p['doc_id'],p['page']) for p in response['candidates']};anchors=gold.get('required_anchors',[]);matched=[]
  for anchor in anchors:matched.append(any(c['doc_id']==anchor['doc_id'] and c['page']==anchor['page'] and anchor['text'] in c['quote'] for c in response['candidates']))
  row={k:case.get(k) for k in ['case_id','source_set','split','requirement_family','source_group']};row.update(response=response,
   metrics={'has_labeled_pages':bool(relevant),'page_hit_any':bool(relevant&returned) if relevant else None,'page_recall_nonexhaustive':len(relevant&returned)/len(relevant) if relevant else None,
    'literal_anchor_count':len(anchors),'literal_anchors_found':sum(matched),'decision_agreement':response['decision']==gold['expected_decision'] if 'expected_decision' in gold else None,
    'potential_over_support_on_labeled_no_answer':(gold.get('answerable_in_snapshot') is False or (not relevant and gold.get('expected_decision')=='insufficient')) and response['decision']=='support'})
  records.append(row)
 jsonl(out/'records.jsonl',records)
 retrieval=[r['metrics'] for r in records if r['metrics']['has_labeled_pages']];agreements=[r['metrics']['decision_agreement'] for r in records if r['metrics']['decision_agreement'] is not None]
 anchor_n=sum(r['metrics']['literal_anchor_count'] for r in records);anchor_hit=sum(r['metrics']['literal_anchors_found'] for r in records)
 summary={'n':len(records),'source_sets':sorted(set(r['source_set'] for r in records)),'splits':sorted(set(r['split'] for r in records)),
 'requirement_families':sorted(set(r['requirement_family'] for r in records)),'source_groups':sorted(set(r['source_group'] for r in records)),
 'retrieval':{'labeled_cases':len(retrieval),'page_hit_rate_any':sum(r['page_hit_any'] for r in retrieval)/len(retrieval) if retrieval else None,
              'page_recall_nonexhaustive':sum(r['page_recall_nonexhaustive'] for r in retrieval)/len(retrieval) if retrieval else None},
 'anchors':{'literal_anchor_count':anchor_n,'literal_anchors_found':anchor_hit,'literal_anchor_coverage':anchor_hit/anchor_n if anchor_n else None},
 'decision':{'labeled_cases':len(agreements),'agreement':sum(agreements)/len(agreements) if agreements else None,
             'potential_over_support_on_labeled_no_answer':sum(r['metrics']['potential_over_support_on_labeled_no_answer'] for r in records)},
 'mean_pages':sum(r['response']['budget']['pages_returned'] for r in records)/max(1,len(records)),
 'mean_chars':sum(r['response']['budget']['evidence_chars'] for r in records)/max(1,len(records)),
 'budget':{'page_budget':page_budget,'char_budget':char_budget},'mode':mode,'cases_sha256':file_sha(cases_path),
 'scope':'page labels may be non-exhaustive; literal anchor coverage and structural decisions do not measure answer correctness or entailment',
 'official_pilot_warning':'manual-curated official questions are a pilot, not a sealed independent generalization test' if any(r['source_set'] in ['official_pilot','public_manual_pilot'] or r['split']=='pilot' for r in records) else None}
 dump(out/'summary.json',summary)
 fields=['case_id','source_set','split','requirement_family','source_group','decision','page_hit_any','page_recall_nonexhaustive','pages','chars']
 with (out/'cases.csv').open('w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
  for r in records:w.writerow({k:r.get(k) for k in fields[:5]}|{'decision':r['response']['decision'],'page_hit_any':r['metrics']['page_hit_any'],'page_recall_nonexhaustive':r['metrics']['page_recall_nonexhaustive'],'pages':r['response']['budget']['pages_returned'],'chars':r['response']['budget']['evidence_chars']})
 print(summary);return summary
