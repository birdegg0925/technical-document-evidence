"""Clearly fictional text-page manuals and source/requirement-grouped flow fixtures."""
from pathlib import Path
from .common import dump,jsonl,text_sha,object_sha

def fixture(out):
 out=Path(out);out.mkdir(parents=True,exist_ok=True);pages=[];cases=[];docs=[]
 for prefix,split,source_group in [('D','dev','fictional_development_manuals'),('T','test','fictional_heldout_manuals')]:
  model=f'FICT-{prefix}1';other=f'FICT-{prefix}2'
  for ver,date,voltage,current in [('1.0','2023-01-01','5.0 V','2.0 A'),('2.0','2025-06-01','3.3 V','1.6 A')]:
   doc=f'fiction_{prefix.lower()}1_v{ver[0]}';meta={'doc_id':doc,'title':f'FICTIONAL training instrument {model} v{ver}','model':model,'model_aliases':[],
    'version':ver,'effective_date':date,'release_date':date,'source_kind':'synthetic','source_url':'fixture://'+doc}
   texts=[f'SYNTHETIC FICTIONAL MANUAL. This is not a real product.\n{model} version {ver}.\nThe permitted supply voltage is {voltage}. Sampling interval: 10 ms.\n',
          f'SYNTHETIC FICTIONAL MANUAL.\n{model} version {ver}. Current table continued.\nFast mode continuous current: {current} *\nSee the operating footnote on the next physical page.\n',
          f'SYNTHETIC FICTIONAL MANUAL.\n{model} version {ver}.\nOperating footnote: Fast mode current rating applies only at 25 C with a heat sink.\nAmbient operating range is -10 C to 50 C.\n']
   digest=object_sha(texts);eid='fixture_text:'+digest[:24]
   for j,text in enumerate(texts,1):pages.append({'doc_id':doc,'page':j,'text':text,'extraction_id':eid,'pdf_sha256':None,'document_sha256':digest,'text_sha256':text_sha(text),'metadata':meta,'layout_risk':j in [2,3],
    'required_conditions':['25 C','heat sink'] if j==2 else [],'condition_topic_terms':['current','fast'] if j==2 else [],'read':'text','backend':'synthetic_text_fixture_not_pdf'})
   docs.append(meta)
  doc=f'fiction_{prefix.lower()}2_v1';meta={'doc_id':doc,'title':f'FICTIONAL instrument {other}','model':other,'model_aliases':[],'version':'1.0','effective_date':'2024-01-01','release_date':'2024-01-01','source_kind':'synthetic','source_url':'fixture://'+doc}
  text=f'SYNTHETIC FICTIONAL MANUAL. Not an actual product.\n{other} version 1.0. Permitted supply voltage is 1.8 V. Continuous current rating is 0.4 A at 25 C.\n';digest=text_sha(text)
  pages.append({'doc_id':doc,'page':1,'text':text,'extraction_id':'fixture_text:'+digest[:24],'pdf_sha256':None,'document_sha256':digest,'text_sha256':text_sha(text),'metadata':meta,'layout_risk':False,'read':'text','backend':'synthetic_text_fixture_not_pdf'});docs.append(meta)
  def case(suffix,question,relevant,decision,**query):
   cases.append({'case_id':f'{prefix}-{suffix}','source_set':'synthetic_fixture','split':split,'requirement_family':'supply_voltage_and_sampling' if prefix=='D' else 'continuous_current_and_temperature',
    'source_group':source_group,'query':{'question':question,**query},'gold':{'relevant_pages':[{'doc_id':d,'page':p} for d,p in relevant],'expected_decision':decision},
    'provenance':'self-authored fictional text pages and flow labels; no real manufacturer case'})
  if prefix=='D':
   case('explicit',f'What is the permitted supply voltage for {model} version 2.0?',[(f'fiction_{prefix.lower()}1_v2',1)],'support',model=model,version='2.0')
   case('old',f'What is the supply voltage for {model} version 1.0?',[(f'fiction_{prefix.lower()}1_v1',1)],'support',model=model,version='1.0')
   case('missing-version',f'What is the supply voltage for {model}?',[(f'fiction_{prefix.lower()}1_v1',1),(f'fiction_{prefix.lower()}1_v2',1)],'review',model=model)
   case('other-model',f'What supply voltage is permitted for {other}?',[(doc,1)],'support',model=other,version='1.0')
   case('no-answer',f'What is the sampling jitter spectrum for {model} version 2.0?',[],'insufficient',model=model,version='2.0')
  else:
   case('crosspage',f'What fast mode current applies for {model} version 2.0?',[(f'fiction_{prefix.lower()}1_v2',2),(f'fiction_{prefix.lower()}1_v2',3)],'review',model=model,version='2.0')
   cases[-1]['gold']['required_anchors']=[{'doc_id':f'fiction_{prefix.lower()}1_v2','page':2,'text':'1.6 A'},{'doc_id':f'fiction_{prefix.lower()}1_v2','page':3,'text':'25 C with a heat sink'}]
   case('latest',f'For the latest {model} manual, what is the fast mode current?',[(f'fiction_{prefix.lower()}1_v2',2),(f'fiction_{prefix.lower()}1_v2',3)],'review',model=model,version_policy='latest')
   case('old',f'What fast mode current applies to {model} version 1.0?',[(f'fiction_{prefix.lower()}1_v1',2),(f'fiction_{prefix.lower()}1_v1',3)],'review',model=model,version='1.0')
   case('other-model',f'What continuous current is rated for {other}?',[(doc,1)],'support',model=other,version='1.0')
   case('wrong-claim',f'Check the continuous current rating of {other}.',[(doc,1)],'review',model=other,version='1.0',claim='Continuous current rating is 2.0 A')
   case('no-answer',f'What is the sensor wavelength response of {model} version 2.0?',[],'insufficient',model=model,version='2.0')
 jsonl(out/'pages.jsonl',pages);dump(out/'documents.json',{'documents':docs})
 for split in ['dev','test']:jsonl(out/f'cases_{split}.jsonl',[c for c in cases if c['split']==split])
 dump(out/'fixture_manifest.json',{'data_kind':'fictional text-page manuals, not real PDFs or company cases','pages':len(pages),'documents':len(docs),'cases':len(cases),
  'splits':{s:sum(c['split']==s for c in cases) for s in ['dev','test']},'source_groups_disjoint':True,'requirement_families_disjoint':True,
  'scope':'self-authored grouped flow/property tests; shared manual structure, not independent real-world generalization'})
 print(f'fictional fixture: documents={len(docs)} pages={len(pages)} cases={len(cases)}');return pages,cases
