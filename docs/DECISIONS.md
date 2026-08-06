# Architecture Decision Record

Decisions made while implementing the Inventory Planner POC, recorded so each
component in the deployed system can be traced back to a requirement or an
explicit engineering choice.

Sources of truth: the client SOW PDF and architecture diagram (both held
locally under generic local filenames, not committed).

Anything in this file marked **Delta** is a component that does *not* appear in
the client architecture diagram. The SOW requires the final runbook to document
how the delivered solution differs from the original diagram, so these are
tracked from the start rather than reconstructed at handover.

---

## ADR-001 — Amazon Cognito for user authentication (Delta)

**Status:** Accepted

### Context

The architecture diagram shows a client reaching an internet-facing Application
Load Balancer with no authentication layer in front of the chat application. The
SOW does not list authentication as an activity or deliverable, and explicitly
places security hardening out of scope.

Taken literally, that means a public URL where anyone who finds it can query the
client's vendor inventory catalog and consume Bedrock tokens on the client's
account.

### Decision

Provision a Cognito User Pool with admin-created users only. End users
authenticate with Cognito from the client; the chat app verifies the JWT. The
ECS task role has no `cognito-idp:*` permissions — verifying tokens uses
Cognito's public JWKS endpoint, which does not require IAM.

### Rationale

The SOW requires UAT by the Client's team, which means named testers rather than
anonymous access. It also assigns all AWS service costs to the Client, so an
unauthenticated endpoint invoking a foundation model is a direct cost exposure.
Cognito is the lowest-effort managed way to gate access without building
credential storage.

### Alternatives considered

- **No authentication.** Matches the diagram most literally. Rejected: an open
  chat endpoint on the public internet is not defensible for a demo containing
  client data, regardless of what the diagram omits.
- **ALB-native authentication** (`authenticate-cognito` listener action). Moves
  auth to the edge and requires no application code. Rejected for the POC
  because it requires HTTPS and therefore an ACM certificate and a DNS name,
  which the SOW does not provide for. Worth revisiting once TLS exists.
- **Cognito Identity Pool.** Rejected: identity pools exist to hand AWS
  credentials to end users. This application never does that — the ECS task role
  holds all AWS permissions, so an identity pool adds a moving part with no
  purpose here.

### Consequences

- Cognito remains in Terraform (pool + app client) for end-user login.
- IAM does not grant the ECS task Cognito API access. If we later move login
  into server-side code, those permissions would need to be added back.

### POC tradeoffs accepted

- `USER_PASSWORD_AUTH` sends the password to Cognito over TLS. Production should
  use `USER_SRP_AUTH`, which never transmits the password itself.
- MFA is disabled to keep the UAT login flow simple for Client testers.
- No SES integration, so Cognito's built-in email delivery is used. This avoids
  SES sandbox verification, at the cost of a low daily email limit.
- `deletion_protection = "INACTIVE"` so the stack can be destroyed and rebuilt
  freely during development.

### Revisit when

TLS is terminated at the ALB, at which point ALB-native Cognito authentication
becomes the simpler and stronger option.

---

## ADR-002 — DynamoDB for chat session history (Delta)

**Status:** Accepted

### Context

The SOW requires users to "interact conversationally with the interface to
explore available inventory," which means multi-turn conversation where earlier
turns inform later ones. The diagram shows no persistence layer for that
conversation state — only OpenSearch for inventory and S3 for images.

The chat application runs on ECS Fargate. Fargate tasks are replaceable by
design: a task can be stopped for a deployment, a health check failure, or
scaling, and the replacement starts with empty memory.

### Decision

Store conversation state in a DynamoDB table keyed by `session_id` with a
`timestamp` sort key, and treat that table as the source of truth for session
history rather than in-process memory.

### Rationale

Conversation state held in the container's memory disappears with the task. With
more than one task behind the ALB, consecutive requests from the same user can
also land on different tasks, so in-memory state is not merely fragile but
incorrect. DynamoDB gives a durable, low-latency key-value store whose access
pattern — fetch all turns for one session, ordered by time — is served exactly
by the base table's key schema.

### Alternatives considered

- **In-memory sessions.** Simplest, and adds nothing to the diagram. Rejected:
  a conversation lost on every deployment would undermine the UAT the SOW
  requires.
- **ElastiCache / Redis.** Faster and a natural fit for session data. Rejected:
  it runs continuously and bills by the hour whether used or not, while
  DynamoDB on-demand costs nothing when idle. Wrong economics for a POC that
  sits unused between demos.
- **Storing conversations in OpenSearch.** Avoids a new service. Rejected:
  conflates the inventory catalog with application state, and OpenSearch is a
  poor fit for high-frequency small writes.

### Configuration notes

- `PAY_PER_REQUEST` billing: unpredictable and very low POC traffic makes
  provisioned capacity guesswork.
- TTL enabled on `expires_at`. Terraform only enables the feature; the
  application must set the value per item, or nothing ever expires.
- Point-in-time recovery and server-side encryption enabled — both are cheap
  and make the table's posture defensible without effort.

### Revisit when

The Chainlit data layer's expected key schema is known in Phase 3. The current
keys are inferred from the access pattern and may need to change to match what
the framework actually writes.

---

## ADR-003 — Inventory uploads are performed by an administrator, not through the chat UI

**Status:** Accepted

### Context

The SOW's first deliverable states the solution "allows users to upload
structured data containing event planning inventory for ingestion into the data
catalog." That sentence can be read two ways: end users uploading through the
chat interface, or an operator placing vendor files into the landing bucket.

The architecture diagram supports the second reading. It labels the bucket "User
Uploads / Scraped Data" and draws no path from the Chainlit interface to that
bucket — the only arrow into it comes from outside the system boundary.

### Decision

Files are placed under the data bucket's `uploads/` prefix directly by an
administrator using the AWS console or CLI. The chat application has no upload
capability and no write permission on that prefix.

### Rationale

The ingestion pipeline is triggered by an S3 event notification, so it behaves
identically no matter how the object arrives. Nothing about the primary SOW focus
— upload, ingest, vectorize, retrieve — depends on who performs the PUT.

Adding an upload path through the UI would mean file type and size validation,
upload progress and failure handling in the interface, and write permission on
the landing bucket for the web-facing task. That is real surface area for a
feature the diagram does not ask for.

### Consequences

- The ECS task role holds no permission on `uploads/*`. Its only S3 permission
  is `GetObject` on `images/*`, needed to generate presigned URLs for images
  shown in chat responses.
- Vendor file ingestion is an operator action, and the runbook must document it
  as such.

### Revisit when

The Client asks for self-service vendor uploads. At that point the UI needs
`PutObject` scoped to a per-vendor key prefix — not blanket bucket write — plus
validation before the object lands.

---

## ADR-004 — One S3 bucket with lifecycle-specific prefixes

**Status:** Accepted

### Context

The client architecture diagram shows separate buckets for raw uploads and
processed images. Both data sets are private POC artifacts with the same owner,
encryption requirement, versioning policy, and environment lifecycle.

### Decision

Use one private data bucket with two prefixes:

- `uploads/` for administrator-uploaded CSV, PDF, and scraped HTML
- `images/` for assets produced by the ingestion Lambda

The bucket name includes the AWS account ID so it is deterministic and unique
in S3's global namespace.

### Rationale

One bucket removes a resource without weakening isolation for this POC. IAM
policies grant access to object-prefix ARNs, so the ECS task can read only
`images/*`, while Lambda can read `uploads/*` and write `images/*`.

### Consequences

- The future S3 event notification must filter on the `uploads/` prefix. A
  bucket-wide notification would cause images written by Lambda to retrigger
  ingestion and could create a processing loop.
- Prefix-level IAM policies require more care than policies against separate
  bucket ARNs.
- This is a deliberate delta from the client diagram and must appear in the
  final architecture and runbook.

### Revisit when

Uploads and images require different retention, encryption, ownership, access
logging, replication, or deletion policies. Separate buckets become preferable
as soon as their lifecycles diverge.

---

## Deltas summary

| Component | In diagram | Reason for inclusion |
|---|---|---|
| Cognito User Pool | No | Gate access to a public endpoint invoking Bedrock on the Client's account |
| DynamoDB sessions table | No | Multi-turn conversation must survive Fargate task replacement |
| One S3 data bucket | No (diagram shows two) | Shared lifecycle; prefixes retain IAM and event separation for the POC |

---

## ADR-005 — OpenSearch Serverless for the inventory vector catalog

**Status:** Accepted (pending account capability check)

### Context

The SOW requires a vector database so conversational queries can retrieve relevant
event-planning inventory. The architecture diagram names OpenSearch. For a
training POC the catalog will be small and often idle between demos.

### Decision

Use **Amazon OpenSearch Serverless** with collection type `VECTORSEARCH` when
the account/region supports it. Fall back to a single-node managed OpenSearch
domain only if Serverless is unavailable.

Index mapping (created by script, not Terraform):

- `embedding` — knn_vector, dimension **1024**, cosine similarity (Titan Embeddings V2)
- Keyword/numeric fields for `vendor`, `tags`, `source_type`, `quantity`, etc.

### Rationale

Serverless avoids paying for a always-on domain while the stack sits unused.
VECTORSEARCH matches the RAG access pattern. Managed OpenSearch remains a valid
fallback but has a continuous idle cost that is a poor fit for training.

### Consequences

- Confirm Serverless availability in `us-east-1` before apply.
- IAM must allow the ingestion role to write and the future ECS task role to read.
- Index mappings live in `scripts/opensearch_index_mapping.json` and are applied
  by `scripts/create_opensearch_index.py` after the collection exists.

### Revisit when

Serverless is unavailable, cost exceeds expectations, or filter+vector query
latency is unacceptable for UAT.

---

## ADR-006 — One OpenSearch document per inventory item

**Status:** Accepted

### Context

Generic RAG often chunks long documents into fixed-size passages. This POC is an
**inventory catalog**, not a document library. The SOW asks for description,
dimensions, quantity, images, and tags per asset.

### Decision

Each inventory item is **exactly one** OpenSearch document. CSV rows map 1:1.
PDFs and scraped pages are normalized by an LLM into zero or more item records,
each stored as its own document.

Embedding input (must match at query time):

```text
{name} | {description} | category: {...} | subcategory: {...} |
dimensions: {...} | features: {...} | colors: {...} | tags: {...}
```

### Rationale

Retrieval must return whole items the planner can use, not mid-paragraph
fragments. Item-level documents keep filters (vendor, tags, quantity) aligned
with the business object.

### Consequences

- Shared schema lives in `shared/schema/` and is imported by ingestion and
  (later) the chat retrieval path.
- Re-ingestion upserts by deterministic `item_id` to stay idempotent.

### Revisit when

Vendors supply long unstructured brochures where passage-level RAG is clearly
better than item extraction — unlikely for this SOW.

---

## ADR-007 — S3 → Lambda ingest with DLQ; scrape is a secondary feeder

**Status:** Accepted

### Context

The diagram shows S3 uploads triggering Lambda, which calls Bedrock and writes
OpenSearch and images. The SOW prioritizes structured uploads over scraping.

### Decision

- Ingestion is an S3 event on prefix `uploads/` only.
- Failed invocations go to an SQS dead-letter queue.
- Scraper (Phase 2.5) only produces payloads that enter the **same** schema and
  pipeline — no parallel indexing path.

### Rationale

Prefix filtering prevents image writes from re-triggering ingest. A single
pipeline keeps UAT and debugging simple. DLQ makes silent data loss visible.

### Revisit when

Very large files need async Step Functions orchestration — not required for POC
file sizes assumed by the SOW.

---

## ADR-008 — Normalize heterogeneous catalogs into retrieval-ready item records

**Status:** Accepted

### Context

The supplied samples are not one uniform CSV:

- a 200-row fixed-width chair export with SKU, product URL, description,
  quantity, unit price, dimensions, and sparse tags;
- scraper-export XLSX catalogs with prose quantities, image URLs, category
  hierarchies, and duplicated snapshots;
- a sparse master XLSX with multiple inventory categories, optional 3D
  references, and embedded row-anchored PNG assets;
- a 242-page website-print PDF with one SKU, price, quantity, and dimensions
  block per product page;
- an eight-page visual chair catalog whose extracted text contains categories
  and names but no reliable prices or quantities;
- a 60-page inventory catalog with one or more items per page, categories,
  descriptions, dimensions/features, and no reliable per-item price;
- one `.csv` containing prose rather than an inventory table.

The sample user queries also ask for budget, vendor consolidation, location,
date availability, quantity, and aesthetic matching. The supplied catalogs do
not contain every one of those facts.

### Decision

Normalize every valid source into schema version 2 with:

- stable source identity (`source_item_id`/SKU or product URL when present);
- item name, description, category/subcategory, features, dimensions;
- quantity, unit price, currency, source page, and product URL only when
  actually supplied;
- deterministic controlled tags plus source/LLM tags;
- one canonical `search_text` field used for both Titan embedding and lexical
  retrieval.

CSV, fixed-width tables, XLSX workbooks, and one-product-per-page PDFs use
deterministic parsers. XLSX embedded images are associated by worksheet row and
copied to the image prefix. Other PDFs are split on page boundaries (maximum
eight detail pages/two dense listing pages and 10,000 characters per model
call), then Claude extracts structured items. Repeated TOC/detail records are
deduplicated by stable item identity, keeping the richer record. Invalid
inventory files fail loudly so the Lambda DLQ surfaces them instead of
reporting false success.

When duplicate exports resolve to the same item ID, OpenSearch uses a
completeness score (SKU, description, price/quantity, dimensions, links,
images, tags) and refuses to replace a richer document with a weaker one.

### Consequences

- Budget, quantity, category, vendor, and semantic retrieval are supported by
  indexed fields.
- Date availability and vendor service area must not be inferred when absent.
  The future chat layer must clearly state that live availability is unknown.
- Direct `image_url` fields and row-anchored XLSX images are copied into
  `images/`. Embedded PDF images are not auto-associated because multi-item
  visual pages do not provide a reliable image-to-item key; the item keeps its
  source PDF/page or product URL.
- Persona behavior, floor-plan calculations, mood-board analysis, and
  fewest-vendor optimization belong to the Phase 3 agent/retrieval layer; the
  Phase 2 index now preserves the facts those tools can safely use.
- Client-supplied raw files remain local and gitignored; only generic parser
  fixtures are committed.

---

## ADR-009 — Chainlit + Bedrock Converse tool-use for the chat agent

**Status:** Accepted

### Context

The architecture diagram and ECR module describe a Chainlit interface with an
agent running on ECS Fargate. Sample queries ask for curated rental lists,
budget awareness, vendor consolidation, and aesthetic matching against the
indexed catalog. The ECR comment names “Strands”; the ECS task role already
grants Bedrock `InvokeModel` / `InvokeModelWithResponseStream` on the Claude
inference profile used elsewhere in the POC.

### Decision

Ship Chainlit as the UI and implement the agent with Amazon Bedrock
**Converse tool-use** (not a separate agent framework). The single retrieval
tool is `search_inventory`, backed by the same Titan + OpenSearch path as
Phase 2 smoke scripts. Pure Python helpers format hits, estimate budgets from
indexed prices, and group results by vendor.

### Rationale

Converse tool-use is the AWS API the task role already authorizes and matches
the ingestion extraction client’s Bedrock usage. Adding Strands would introduce
another SDK and release cadence without changing the tool contract or the
retrieval path. Chainlit remains the named UI surface for UAT.

### Alternatives considered

- **Strands Agents SDK.** Matches the ECR comment literally. Deferred: same
  tool contract can be wrapped later without changing OpenSearch or schema.
- **LangChain / LlamaIndex.** Rejected for POC surface area.
- **Direct RAG prompt without tools.** Rejected: filters (price, quantity,
  category, vendor) are clearer and more testable as structured tool input.

### Consequences

- Chat depends on Phase 2 index fields and `OpenSearchInventoryClient.vector_search`.
- Mood-board vision, floor-plan solvers, and hard fewest-vendor optimization
  stay out of the POC agent; the persona states limits honestly.
- ECS task role must invoke Titan at query time (added beside Claude).

### Revisit when

Strands (or another framework) is mandated by the client diagram review, or
multi-tool workflows (vision, packing) become in-scope.

---

## ADR-010 — One retrieval tool with structured filters

**Status:** Accepted

### Context

Persona queries mix semantic intent (“Slim Aarons”, “old Bollywood”) with
constraints (guest count, budget, NYC/Brooklyn). Schema v2 already stores
category, unit_price, quantity, vendor, and colors as filterable fields.

### Decision

Expose a single tool, `search_inventory`, with optional filters:

- `query` (required) — embedded with Titan; must mirror ingest `embedding_text`
- `category`, `vendor`, `color`
- `max_unit_price`, `min_quantity`
- `size` (hit count, capped)

The agent may call the tool more than once per turn. Responses must not invent
price, quantity, availability, date holds, or service areas when absent from
hits. Live availability is always stated as unknown unless a future data
source supplies it.

### Consequences

- `scripts/query_inventory.py` and `scripts/chat_turn.py` share the same client.
- Budget figures in chat are sums/estimates over returned `unit_price` values
  only; missing prices are called out.

---

## ADR-011 — Cognito JWT verification via JWKS; sessions in DynamoDB

**Status:** Accepted

### Context

ADR-001 requires Cognito for UAT users. ADR-002 provisioned DynamoDB with
`session_id` (HASH) + `timestamp` (RANGE) and TTL on `expires_at`. The ECS
task role intentionally has no `cognito-idp:*` permissions.

### Decision

- Chainlit authenticates requests by verifying a Cognito **access token**
  (Bearer) against the user pool JWKS over HTTPS. No Cognito API IAM on the task.
- Each user/assistant turn is written to the existing DynamoDB table with
  `expires_at = now + 30 days`. History for a session is a `Query` on
  `session_id` ordered by `timestamp`.

### Consequences

- UAT users must present a valid Cognito access token (issued outside the
  container — hosted UI or admin/CLI flows operated by the team).
- Chainlit’s built-in data layer is not used as the source of truth; our
  session adapter owns the ADR-002 schema.
- ALB remains HTTP for the POC (no ACM); Cognito is application-level, not
  ALB `authenticate-cognito`.

---

## ADR-012 — Groq + Hugging Face while Bedrock account access is blocked

**Status:** Accepted (temporary provider path for training POC)

### Context

Personal and corporate AWS accounts returned `authorizationStatus: NOT_AUTHORIZED`
for Bedrock Titan/Claude despite IAM and payment fixes. Waiting on AWS Support
blocks end-to-end demo of an otherwise complete Phase 2/3 stack.

### Decision

- **Embeddings:** Hugging Face Inference (`BAAI/bge-large-en-v1.5`, 1024-d) via HTTPS.
- **LLM (extract + chat tool-use):** Groq OpenAI-compatible API (`llama-3.3-70b-versatile`).
- **Secrets:** `GROQ_API_KEY` + `HF_TOKEN` in AWS Secrets Manager
  (`PROVIDER_SECRETS_ARN`); local `.env` for offline smoke tests only.
- Keep OpenSearch mapping at dimension **1024** (same as Titan), so the existing
  index shape remains valid after re-ingest.
- Visual PDF document-vision (Bedrock Converse documents) is not available on Groq;
  fall back to extractable page text or require CSV/XLSX/text PDF.

### Consequences

- Demo no longer depends on Bedrock Marketplace authorization.
- Lambda/ECS need outbound HTTPS (Lambda is not VPC-bound; ECS private subnet uses NAT).
- Re-ingest catalog after switching providers (embedding space differs from Titan).
- Bedrock can be restored later by swapping client modules only; tool contract stays.
