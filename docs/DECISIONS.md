# Architecture Decision Record

Decisions made while implementing the CandyWagon POC, recorded so each
component in the deployed system can be traced back to a requirement or an
explicit engineering choice.

Sources of truth: `SOW-Candywagon-POC-Candywagon Pilot.pdf` and
`CandyWagon Architecture.png` (both held locally, not committed).

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
