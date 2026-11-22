# Technical Document Evidence Retrieval

This service retrieves candidate excerpts from technical manuals and checks that each citation points to the claimed document, revision, physical page and character span. It returns the evidence a support engineer can review before answering a question.

[Retrieval](tech_evidence/retrieve.py) compares page-level BM25, BM25 with neighboring pages, and model and revision filtering under a shared page and character cap. [Citation validation](tech_evidence/retrieve.py) binds offsets to a specific text extraction and checks them against that extraction. The API reports that semantic review is required because a matching span can describe the right product without supporting the requested claim.

## Public manuals pilot

The reference pilot used three Raspberry Pi manuals with 670 physical pages and 18 pilot questions, including 16 with selected-page labels. Each mode was capped at four pages and 6,000 characters per query.

| Mode | Questions with at least one labeled page | Mean recall over labeled pages | Mean pages returned |
| --- | ---: | ---: | ---: |
| [BM25](results/bm25.json) | 13 / 16 | 78.1% | 4.00 |
| [BM25 plus neighbors](results/neighbors.json) | 10 / 16 | 50.0% | 4.00 |
| [Model and revision scoped](results/scoped.json) | 12 / 16 | 71.9% | 3.78 |

BM25 retrieved the most labeled evidence in this pilot. The page labels were non-exhaustive. In one unlabeled question about an individual device's serial number, two modes returned structurally valid evidence candidates even though the manual could not supply that device's serial number.

The [PageIndex adapter](tech_evidence/pageindex_adapter.py) normalizes responses against an explicit source mapping. Saved contract fixtures exercise the adapter.

## Run locally

Use Python 3.12 from the repository root.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pytest tests -q
python -m tech_evidence.cli ask --index fixtures/index.json \
  --question "Supply voltage for FICT-D1 version 2.0?" \
  --model FICT-D1 --version 2.0 --mode scoped --page-budget 4 \
  --char-budget 6000 --out runs/fixture_ask.json
python -m tech_evidence.cli serve --index fixtures/index.json --host 127.0.0.1 --port 8765
```

The bundled [synthetic corpus](fixtures/fixture_manifest.json) has 14 pages across six fictional manuals. To rebuild the public-manual pilot, run the following commands and repeat the last step with `neighbors` and `scoped`.

```bash
python scripts/download_official.py --out runs/public_documents
python -m tech_evidence.cli ingest --manifest runs/public_documents/manifest.json --out runs/public_corpus
python -m tech_evidence.cli build --pages runs/public_corpus/pages.jsonl --out runs/public_index.json
python -m tech_evidence.cli evaluate --index runs/public_index.json \
  --cases public_manual_pilot.jsonl --mode bm25 --page-budget 4 --char-budget 6000 \
  --out runs/public_bm25
```

The [downloader](scripts/download_official.py) credits the Raspberry Pi sources, records their declared CC BY-ND 4.0 license, and rejects snapshots whose hashes have changed. Source PDFs and extracted text are fetched and processed locally.
