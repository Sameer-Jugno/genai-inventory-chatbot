#!/usr/bin/env bash
# Bring the full Inventory Planner stack up with one command.
#
# Usage (from repo root):
#   ./scripts/stack-up.sh
#   IMAGE_TAG=my-tag ./scripts/stack-up.sh
#   ./scripts/stack-up.sh --skip-image      # reuse image already in ECR / tfvars
#   ./scripts/stack-up.sh --skip-secrets
#   ./scripts/stack-up.sh --skip-index
#   ./scripts/stack-up.sh --skip-demo-user
#
# Prerequisites:
#   - AWS credentials (aws sts get-caller-identity)
#   - terraform, docker, python3, zip, pip
#   - terraform/envs/dev/terraform.tfvars
#   - .env with GROQ_API_KEY and HF_TOKEN
#
# What it does:
#   1) Build ingestion Lambda zip
#   2) terraform apply (foundation + OpenSearch + Lambda; ECS if image ready)
#   3) Build/push chat image to ECR (unless --skip-image)
#   4) terraform apply with ECS enabled
#   5) Load provider secrets into Secrets Manager
#   6) Create OpenSearch inventory index (if missing)
#   7) Ensure demo@example.com Cognito user exists
#
# Does NOT re-upload catalog files — after a fresh destroy, upload to S3 again
# (see DATASET_ANALYTICS.txt / APPLICATION_FLOW.txt).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TF_DIR="${ROOT}/terraform/envs/dev"
REGION="${AWS_REGION:-us-east-1}"
IMAGE_TAG="${IMAGE_TAG:-stack-$(date +%Y%m%d%H%M%S)}"

SKIP_IMAGE=0
SKIP_SECRETS=0
SKIP_INDEX=0
SKIP_DEMO_USER=0

for arg in "$@"; do
  case "${arg}" in
    --skip-image) SKIP_IMAGE=1 ;;
    --skip-secrets) SKIP_SECRETS=1 ;;
    --skip-index) SKIP_INDEX=1 ;;
    --skip-demo-user) SKIP_DEMO_USER=1 ;;
    -h|--help)
      sed -n '2,30p' "$0"
      exit 0
      ;;
    *)
      echo "Unknown arg: ${arg}" >&2
      exit 1
      ;;
  esac
done

log() { printf '\n==> %s\n' "$*"; }
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

need() { command -v "$1" >/dev/null 2>&1 || die "missing required command: $1"; }

need aws
need terraform
need docker
need python3
need zip

[[ -f "${TF_DIR}/terraform.tfvars" ]] || die "missing ${TF_DIR}/terraform.tfvars (copy from terraform.tfvars.example)"
[[ -f "${ROOT}/.env" ]] || die "missing ${ROOT}/.env (need GROQ_API_KEY + HF_TOKEN)"

log "Checking AWS identity"
aws sts get-caller-identity --output table
ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
ECR_REPO="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/inventory-planner-dev-chat-app"

log "Building ingestion Lambda package"
bash "${ROOT}/scripts/build_ingestion_package.sh"

log "Terraform init"
(
  cd "${TF_DIR}"
  terraform init -input=false
)

EXISTING_IMAGE="$(
  grep -E '^chat_container_image' "${TF_DIR}/terraform.tfvars" \
    | sed -E 's/.*=[[:space:]]*"([^"]+)".*/\1/' \
    | head -1 || true
)"

ECS_ALREADY_IN_STATE=0
if (
  cd "${TF_DIR}"
  terraform state list 2>/dev/null | grep -q 'module.ecs_chat'
); then
  ECS_ALREADY_IN_STATE=1
fi

# After a full destroy, ECR is empty — create foundation first, then push image,
# then enable ECS. If ECS is already in state, never flip enable_phase3=false
# (that would delete the live chat service).
if [[ "${ECS_ALREADY_IN_STATE}" -eq 0 ]]; then
  log "Bootstrap apply (no ECS yet — enable_phase3=false)"
  (
    cd "${TF_DIR}"
    terraform apply -input=false -auto-approve \
      -var="enable_iam=true" \
      -var="enable_phase2=true" \
      -var="enable_phase3=false" \
      -var="chat_container_image="
  )
else
  log "ECS already in Terraform state — skipping bootstrap (keeps live chat)"
fi

ECR_URL="$(
  cd "${TF_DIR}"
  terraform output -raw ecr_repository_url
)"

if [[ "${SKIP_IMAGE}" -eq 0 ]]; then
  log "Building chat Docker image (tag=${IMAGE_TAG})"
  docker build -f "${ROOT}/services/chat/Dockerfile" -t "inventory-planner-chat:${IMAGE_TAG}" "${ROOT}"

  log "Pushing image to ECR ${ECR_URL}:${IMAGE_TAG}"
  mkdir -p /tmp/docker-ecr
  echo '{}' > /tmp/docker-ecr/config.json
  aws ecr get-login-password --region "${REGION}" \
    | DOCKER_CONFIG=/tmp/docker-ecr docker login --username AWS --password-stdin \
      "${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com"
  DOCKER_CONFIG=/tmp/docker-ecr docker tag "inventory-planner-chat:${IMAGE_TAG}" "${ECR_URL}:${IMAGE_TAG}"
  DOCKER_CONFIG=/tmp/docker-ecr docker push "${ECR_URL}:${IMAGE_TAG}"
  IMAGE_URI="${ECR_URL}:${IMAGE_TAG}"

  # Keep tfvars in sync so later plain `terraform apply` uses the same image.
  if grep -q '^chat_container_image' "${TF_DIR}/terraform.tfvars"; then
    sed -i.bak -E "s|^chat_container_image[[:space:]]*=.*|chat_container_image = \"${IMAGE_URI}\"|" \
      "${TF_DIR}/terraform.tfvars"
    rm -f "${TF_DIR}/terraform.tfvars.bak"
  else
    printf '\nchat_container_image = "%s"\n' "${IMAGE_URI}" >> "${TF_DIR}/terraform.tfvars"
  fi
else
  IMAGE_URI="${EXISTING_IMAGE}"
  [[ -n "${IMAGE_URI}" ]] || die "--skip-image needs chat_container_image set in terraform.tfvars"
  log "Reusing existing image ${IMAGE_URI}"
fi

log "Terraform apply (full stack — ECS chat on)"
(
  cd "${TF_DIR}"
  terraform apply -input=false -auto-approve \
    -var="enable_iam=true" \
    -var="enable_phase2=true" \
    -var="enable_phase3=true" \
    -var="chat_container_image=${IMAGE_URI}"
)

if [[ "${SKIP_SECRETS}" -eq 0 ]]; then
  log "Loading provider secrets from .env"
  bash "${ROOT}/scripts/put_provider_secrets.sh"
else
  log "Skipping secrets (--skip-secrets)"
fi

if [[ "${SKIP_INDEX}" -eq 0 ]]; then
  log "Ensuring OpenSearch inventory index exists"
  ENDPOINT="$(
    cd "${TF_DIR}"
    terraform output -raw opensearch_collection_endpoint
  )"
  export OPENSEARCH_ENDPOINT="${ENDPOINT}"
  export OPENSEARCH_INDEX="inventory-items"
  export AWS_REGION="${REGION}"
  # Script is idempotent enough: if index exists it may error — tolerate that.
  set +e
  python3 "${ROOT}/scripts/create_opensearch_index.py"
  rc=$?
  set -e
  if [[ "${rc}" -ne 0 ]]; then
    echo "Note: index create returned ${rc} (often means it already exists)."
  fi
else
  log "Skipping OpenSearch index (--skip-index)"
fi

if [[ "${SKIP_DEMO_USER}" -eq 0 ]]; then
  log "Ensuring Cognito demo user demo@example.com"
  POOL_ID="$(
    cd "${TF_DIR}"
    terraform output -raw cognito_user_pool_id
  )"
  if aws cognito-idp admin-get-user \
    --user-pool-id "${POOL_ID}" \
    --username 'demo@example.com' >/dev/null 2>&1; then
    echo "Demo user already exists."
  else
    aws cognito-idp admin-create-user \
      --user-pool-id "${POOL_ID}" \
      --username 'demo@example.com' \
      --user-attributes Name=email,Value=demo@example.com Name=email_verified,Value=true \
      --temporary-password 'TempPass123!' \
      --message-action SUPPRESS >/dev/null
    aws cognito-idp admin-set-user-password \
      --user-pool-id "${POOL_ID}" \
      --username 'demo@example.com' \
      --password 'DemoPass123!' \
      --permanent
    echo "Created demo@example.com / DemoPass123!"
  fi
else
  log "Skipping demo user (--skip-demo-user)"
fi

ALB_DNS="$(
  cd "${TF_DIR}"
  terraform output -raw alb_dns_name
)"

cat <<EOF

============================================================
Stack is UP
============================================================
Chat URL:  http://${ALB_DNS}/
Login:     demo@example.com / DemoPass123!
Image:     ${IMAGE_URI}

Cost tip: when finished, run:
  ./scripts/stack-down.sh

After a fresh destroy+up, re-upload catalog files to S3 uploads/
(see DATASET_ANALYTICS.txt) — OpenSearch starts empty.
============================================================
EOF
