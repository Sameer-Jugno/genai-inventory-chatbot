# Inventory Planner — Phase 3 (Chat / agent plane)

> **Apply still blocked** on `iam:CreateRole` (same as Phase 1–2).
> Offline chat code and Terraform are ready; keep `enable_phase3` false until
> IAM is granted and Phase 2 ingest has been verified.

## Goal

Authenticated user → Chainlit on ECS → Bedrock tool-use agent → Titan embed +
OpenSearch retrieval → rental recommendations grounded in indexed inventory
(ADR-009–011).

## Offline complete (no apply required)

- [x] ADRs 009–011 in `docs/DECISIONS.md`
- [x] Chat service `services/chat/` (persona, retrieval, sessions, images, agent, Chainlit)
- [x] Reuses Phase 2 clients: `EmbeddingClient`, `OpenSearchInventoryClient`, schema v2
- [x] DynamoDB session adapter matching ADR-002 keys (`session_id` + `timestamp`)
- [x] Cognito JWT verification via JWKS (no `cognito-idp` IAM on the task role)
- [x] ECS Fargate Terraform module (`terraform/modules/ecs_chat/`)
- [x] `envs/dev` wiring behind `enable_phase3` (requires `enable_phase2` + `enable_iam`)
- [x] ECS task role granted Titan invoke (query-time embeddings)
- [x] Dockerfile for the ECR chat image
- [x] Live one-turn smoke script: `scripts/chat_turn.py`
- [x] Unit tests for tool schema, formatting, persona scope, session records

## Blocked on AWS / lead

1. IAM CreateRole (same blocker as Phase 2)
2. `enable_iam = true` → apply
3. Phase 2 apply + index bootstrap + sample upload
4. Build/push chat image to ECR
5. `enable_phase3 = true` → plan/apply (ECS service + ALB forward)
6. Create Cognito UAT users; issue access tokens for Chainlit
7. Open ALB URL and run persona sample queries

## Flags

| Variable | Default | Meaning |
|---|---|---|
| `enable_iam` | `false` | ECS + Lambda roles |
| `enable_phase2` | `false` | AOSS + ingestion Lambda |
| `enable_phase3` | `false` | ECS chat service + ALB forward (requires Phase 2) |

## Local / offline checks (no live index)

```bash
python -m pip install -r services/chat/requirements.txt
python -m unittest discover -s tests -v
```

After Phase 2 is live:

```bash
export OPENSEARCH_ENDPOINT="https://..."
export BEDROCK_CHAT_MODEL_ID="us.anthropic.claude-sonnet-4-5-20250929-v1:0"
python scripts/chat_turn.py "vintage outdoor lounge seating for 20 people under 300"
```

## Explicitly out of POC chat scope (see ADR-009)

- Catalog upload through the chat UI (ADR-003)
- Mood-board / photo vision analysis
- Floor-plan packing solvers
- Hard combinatorial fewest-vendor optimization (agent groups by vendor instead)

Do **not** `terraform init` inside `terraform/modules/*`.
