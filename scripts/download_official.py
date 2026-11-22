#!/usr/bin/env python3
"""Download/cache the frozen official snapshots; fail on hash drift, never substitute fixtures."""
import argparse,hashlib,json,urllib.request
from pathlib import Path
DOCS=[
 {'doc_id':'pico','model':'pico','model_aliases':['Raspberry Pi Pico'],'version':'R22','build_date_raw':'19/11/2026','build_commit':'d9d02bdfeecd','physical_pages':31,
  'source_url':'https://datasheets.raspberrypi.com/pico/pico-datasheet.pdf','resolved_url':'https://pip-assets.raspberrypi.com/categories/610-raspberry-pi-pico/documents/RP-008307-DS-3-pico-datasheet.pdf','pdf_sha256':'bc6c12c43cba947c61e76331fc6c0a9f979545ff50699b8934adcbc39d4410eb'},
 {'doc_id':'pico2','model':'pico2','model_aliases':['Pico 2','Raspberry Pi Pico 2'],'version':'R5','build_date_raw':'03/07/2026','build_commit':'d4e0f1799616','physical_pages':24,
  'source_url':'https://datasheets.raspberrypi.com/pico/pico-2-datasheet.pdf','resolved_url':'https://pip-assets.raspberrypi.com/categories/1005-raspberry-pi-pico-2/documents/RP-008299-DS-3-pico-2-datasheet.pdf','pdf_sha256':'cbcfaf881018c686495a2e53c7bd281e7e0a8217d79447d73eda7c8f74b7f675'},
 {'doc_id':'rp2040','model':'rp2040','model_aliases':['RP2040'],'version':'R13','build_date_raw':'19/11/2026','build_commit':'4c5ccacb2c2f','physical_pages':615,
  'source_url':'https://datasheets.raspberrypi.com/rp2040/rp2040-datasheet.pdf','resolved_url':'https://pip-assets.raspberrypi.com/categories/814-rp2040/documents/RP-008371-DS-2-rp2040-datasheet.pdf','pdf_sha256':'a4c31537d6052d2b83a12c0d550b1e0a172ca12a342d3dee40d8d03416028b4d'}]
def checksum(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--out',required=True);args=p.parse_args();out=Path(args.out).resolve()
 fixtures = Path(__file__).resolve().parents[1] / 'fixtures'
 if out.is_relative_to(fixtures):
  raise ValueError('Choose a local cache outside fixtures/ for official PDFs.')
 out.mkdir(parents=True,exist_ok=True);documents=[]
 for record in DOCS:
  d=record.copy();dest=out/f"{d['doc_id']}.pdf";cached=dest.exists() and checksum(dest)==d['pdf_sha256']
  if not cached:
   req=urllib.request.Request(d['resolved_url'],headers={'User-Agent':'Technical-evidence-study/0.1'})
   with urllib.request.urlopen(req,timeout=90) as response:data=response.read(50_000_001)
   if len(data)>50_000_000:raise ValueError('snapshot exceeds download size limit')
   if hashlib.sha256(data).hexdigest()!=d['pdf_sha256']:raise ValueError('official snapshot hash drift; refresh source annotation before changing this study')
   dest.write_bytes(data)
  d.update(pdf_path=str(dest),source_kind='official',title=d['doc_id']+' official datasheet snapshot',release_date=None,effective_date=None,
           license_name='CC BY-ND 4.0, as declared in the PDF colophon',license_url='https://creativecommons.org/licenses/by-nd/4.0/',cached=cached)
  documents.append(d);print(d['doc_id'],'cached' if cached else 'downloaded',d['physical_pages'],'pages',flush=True)
 (out/'manifest.json').write_text(json.dumps({'documents':documents,'snapshot_date':'2026-11-21','note':'build date is not treated as original release/effective date; raw PDFs are stored in the local download cache'},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
