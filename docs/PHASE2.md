# Inventory Planner — Phase 2 (Data plane & ingestion)

> **Apply still blocked** on `iam:CreateRole` (same as Phase 1 IAM).
> Offline code and Terraform are ready; keep `enable_iam` / `enable_phase2`
> false in `terraform.tfvars` until the lead grants IAM.

## Goal

Admin upload under `uploads/` → Lambda → Bedrock + OpenSearch + `images/` →
searchable inventory items (ADR-005–008).

## Offline complete (no apply required)

- [x] ADRs 005–008 in `docs/DECISIONS.md`
- [x] Shared schema `shared/schema/`
- [x] OpenSearch mapping + SigV4 `scripts/create_opensearch_index.py`
- [x] OpenSearch Terraform module (`terraform/modules/opensearch/`)
- [x] Ingestion Lambda Terraform module (S3 `uploads/` notify, DLQ, alarm, logs)
- [x] Ingestion code: CSV / XLSX / fixed-width TXT / PDF / HTML → embed → upsert
- [x] Retrieval-ready schema v2: SKU, name, category, price, quantity, URL, 3D reference, features, colors, source page
- [x] XLSX scraper/master-sheet support, including row-anchored embedded images
- [x] Deterministic product-page PDF path for large price/quantity catalogs; bounded Claude fallback for visual/general PDFs
- [x] Controlled deterministic tagging for the supplied catalog vocabulary
- [x] Concurrent Titan embedding for 200-row catalogs
- [x] Live vector retrieval smoke: `scripts/query_inventory.py`
- [x] Package build: `scripts/build_ingestion_package.sh` (preserves `services.*` / `shared.*`)
- [x] Generic scraper feeder: `scraper/fetch.py` (writes artifacts for `uploads/`)
- [x] `envs/dev` wiring behind `enable_iam` + `enable_phase2` (defaults **false**)
- [x] IAM hooks for AOSS (`aoss:APIAccessAll`) and DLQ (`sqs:SendMessage`)

## Blocked on AWS / lead

1. IAM CreateRole / GetRole
2. `enable_iam = true` → plan/apply (~3 roles)
3. `scripts/build_ingestion_package.sh`
4. `enable_phase2 = true` → plan/apply (OpenSearch + Lambda)
5. Add bootstrap principal ARN if you will run the index script as your user
6. `OPENSEARCH_ENDPOINT=… python scripts/create_opensearch_index.py`
7. Upload a valid catalog under `uploads/{vendor}/` and verify DLQ stays empty
8. Run `scripts/query_inventory.py` to verify semantic + filtered retrieval

## Build order (executed)

1. Schema + ADRs
2. OpenSearch TF module (apply gated)
3. Lambda TF + CSV / XLSX / fixed-width TXT / PDF / HTML path
4. Images + embedding + OpenSearch clients
5. DLQ + IAM AOSS/SQS statements
6. Scraper as secondary feeder into the same pipeline

## Local smoke (no AWS)

```bash
python -m pip install -r services/ingestion/requirements.txt
python -m unittest discover -s tests -v
python services/ingestion/smoke_csv_parser.py
```

## Data-driven behavior

- Fixed-width table exports are parsed deterministically without pandas in Lambda.
- XLSX scraper exports and sparse asset sheets are normalized from header aliases;
  embedded row images are copied to `images/`.
- One-product-per-page PDFs with SKU, price, quantity, and dimensions use a
  deterministic parser, avoiding hundreds of unnecessary Claude calls.
- Visual-grid PDFs use page-level Claude document vision; text-first catalogs
  use bounded text chunks.
- Uploads are capped at 128 MiB, which covers the supplied 103 MiB catalog.
- PDF requests are bounded by page count and character count; no catalog tail is silently clipped.
- Missing price, quantity, location, date availability, descriptions, and dimensions remain null.
- Invalid prose-only CSV uploads fail into the DLQ instead of succeeding with zero items.
- Raw client files under `docs/` are local-only and gitignored.
- DOCX persona files, UI images, and demo video are requirements/reference
  material, not inventory uploads.

After the live index exists:

```bash
export OPENSEARCH_ENDPOINT="https://..."
python scripts/query_inventory.py \
  "vintage outdoor lounge seating" \
  --category seating \
  --max-price 300 \
  --min-quantity 2
```

## Flags

| Variable | Default | Meaning |
|---|---|---|
| `enable_iam` | `false` | Create ECS + Lambda roles |
| `enable_phase2` | `false` | Create AOSS collection + ingestion Lambda (requires `enable_iam`) |

Do **not** `terraform init` inside `terraform/modules/*` — lock files belong only under `envs/dev`.
