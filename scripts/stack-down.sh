#!/usr/bin/env bash
# Tear down the full Inventory Planner AWS stack with one command (cost control).
#
# Usage (from repo root):
#   ./scripts/stack-down.sh            # interactive confirm
#   ./scripts/stack-down.sh --yes      # no prompt
#
# Destroys everything Terraform manages in terraform/envs/dev, including:
#   VPC/ALB/ECS, OpenSearch Serverless, Lambda, Cognito, DynamoDB sessions,
#   S3 data bucket (force_destroy), ECR repo (+ images), Secrets Manager secret
#
# After destroy, catalog data and chat history are GONE. Bring back with:
#   ./scripts/stack-up.sh
# then re-upload inventory files to S3.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TF_DIR="${ROOT}/terraform/envs/dev"
AUTO_YES=0

for arg in "$@"; do
  case "${arg}" in
    -y|--yes) AUTO_YES=1 ;;
    -h|--help)
      sed -n '2,20p' "$0"
      exit 0
      ;;
    *)
      echo "Unknown arg: ${arg}" >&2
      exit 1
      ;;
  esac
done

command -v terraform >/dev/null 2>&1 || { echo "missing terraform" >&2; exit 1; }
command -v aws >/dev/null 2>&1 || { echo "missing aws" >&2; exit 1; }
[[ -f "${TF_DIR}/terraform.tfvars" ]] || { echo "missing ${TF_DIR}/terraform.tfvars" >&2; exit 1; }

aws sts get-caller-identity --output table

if [[ "${AUTO_YES}" -ne 1 ]]; then
  cat <<EOF

WARNING: This permanently destroys the Inventory Planner AWS stack.
OpenSearch index, S3 uploads/images, DynamoDB chat history, Cognito users,
and the ECR chat images will be deleted.

EOF
  read -r -p "Type 'destroy' to continue: " answer
  [[ "${answer}" == "destroy" ]] || { echo "Aborted."; exit 1; }
fi

echo "==> Terraform init"
(
  cd "${TF_DIR}"
  terraform init -input=false
)

echo "==> Terraform destroy (all modules)"
(
  cd "${TF_DIR}"
  # Match stack-up flags so destroy sees the same resource graph as apply.
  terraform destroy -input=false -auto-approve \
    -var="enable_iam=true" \
    -var="enable_phase2=true" \
    -var="enable_phase3=true" \
    -var="chat_container_image=$(grep -E '^chat_container_image' terraform.tfvars | sed -E 's/.*=[[:space:]]*\"([^\"]+)\".*/\1/' | head -1)"
)

cat <<EOF

============================================================
Stack is DOWN — billable chat/search resources should stop.
Bring it back later with:
  ./scripts/stack-up.sh
============================================================
EOF
