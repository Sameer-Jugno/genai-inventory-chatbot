#!/usr/bin/env bash
# Build a deployable zip for the ingestion Lambda.
# Preserves package layout so imports match the repo:
#   services.ingestion.*  and  shared.schema.*
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIST="${ROOT}/dist"
BUILD="${DIST}/ingestion_build"
ZIP="${DIST}/ingestion.zip"

rm -rf "${BUILD}" "${ZIP}"
mkdir -p "${BUILD}/services/ingestion" "${BUILD}/shared"

cp "${ROOT}/services/__init__.py" "${BUILD}/services/__init__.py"
cp "${ROOT}/services/ingestion/__init__.py" "${BUILD}/services/ingestion/__init__.py"
cp "${ROOT}/services/ingestion/"*.py "${BUILD}/services/ingestion/"
cp -R "${ROOT}/services/ingestion/parsers" "${BUILD}/services/ingestion/parsers"
cp "${ROOT}/shared/__init__.py" "${BUILD}/shared/__init__.py"
cp -R "${ROOT}/shared/schema" "${BUILD}/shared/schema"
cp -R "${ROOT}/shared/providers" "${BUILD}/shared/providers"

# Runtime deps that are not in the Lambda base image.
# Wheels must match the Lambda runtime (python3.12 / x86_64), not the local
# interpreter — pydantic ships a compiled pydantic_core binary.
LAMBDA_PYTHON_VERSION="3.12"
LAMBDA_PLATFORM="manylinux2014_x86_64"

python3 -m pip install \
  --quiet \
  --target "${BUILD}" \
  --platform "${LAMBDA_PLATFORM}" \
  --python-version "${LAMBDA_PYTHON_VERSION}" \
  --implementation cp \
  --only-binary=:all: \
  "pydantic>=2,<3" \
  "opensearch-py>=2.4,<3" \
  "requests-aws4auth>=1.2,<2" \
  "pdfplumber>=0.11,<0.12" \
  "boto3>=1.34,<2" \
  "openpyxl>=3.1,<4" \
  "pypdf>=6,<7"

(
  cd "${BUILD}"
  zip -qr "${ZIP}" .
)

echo "Built ${ZIP}"
echo "Lambda handler: services.ingestion.handler.handler"
