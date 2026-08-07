#!/usr/bin/env bash
# Push Groq + Hugging Face + Chainlit keys from local .env into AWS Secrets Manager.
# Supports GROQ_API_KEY plus optional GROQ_API_KEY_2..GROQ_API_KEY_8 for failover.
# Does not print secret values.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ROOT}/.env"

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "Missing ${ENV_FILE}" >&2
  exit 1
fi

# shellcheck disable=SC1090
set -a
source "${ENV_FILE}"
set +a

: "${GROQ_API_KEY:?GROQ_API_KEY missing in .env}"
: "${HF_TOKEN:?HF_TOKEN missing in .env}"

# Chainlit requires CHAINLIT_AUTH_SECRET at container start.
if [[ -z "${CHAINLIT_AUTH_SECRET:-}" ]]; then
  CHAINLIT_AUTH_SECRET="$(python3 - <<'PY'
import secrets
print(secrets.token_urlsafe(48))
PY
)"
  printf '\nCHAINLIT_AUTH_SECRET=%s\n' "${CHAINLIT_AUTH_SECRET}" >> "${ENV_FILE}"
  echo "Generated CHAINLIT_AUTH_SECRET and appended to .env"
fi
export CHAINLIT_AUTH_SECRET

SECRET_ID="${1:-}"
if [[ -z "${SECRET_ID}" ]]; then
  if [[ -n "${PROVIDER_SECRETS_ARN:-}" ]]; then
    SECRET_ID="${PROVIDER_SECRETS_ARN}"
  else
    SECRET_ID="$(
      cd "${ROOT}/terraform/envs/dev"
      terraform output -raw provider_secrets_arn 2>/dev/null || true
    )"
  fi
fi

if [[ -z "${SECRET_ID}" ]]; then
  echo "Pass secret ARN/name as arg 1, or apply Terraform so provider_secrets_arn exists." >&2
  exit 1
fi

PAYLOAD="$(python3 - <<'PY'
import json, os

payload = {
    "GROQ_API_KEY": os.environ["GROQ_API_KEY"],
    "HF_TOKEN": os.environ["HF_TOKEN"],
    "CHAINLIT_AUTH_SECRET": os.environ["CHAINLIT_AUTH_SECRET"],
}
# Optional failover keys — only include values that are actually set.
for index in range(2, 9):
    name = f"GROQ_API_KEY_{index}"
    value = (os.environ.get(name) or "").strip()
    if value:
        payload[name] = value
if (os.environ.get("GROQ_API_KEYS") or "").strip():
    payload["GROQ_API_KEYS"] = os.environ["GROQ_API_KEYS"].strip()

print(json.dumps(payload))
PY
)"

aws secretsmanager put-secret-value \
  --secret-id "${SECRET_ID}" \
  --secret-string "${PAYLOAD}" \
  --output text \
  --query 'VersionId'

KEY_COUNT="$(python3 - <<'PY'
import os
count = 1
for index in range(2, 9):
    if (os.environ.get(f"GROQ_API_KEY_{index}") or "").strip():
        count += 1
print(count)
PY
)"

echo "Updated secret ${SECRET_ID} with ${KEY_COUNT} Groq key(s) (version id printed above). Values not shown."
