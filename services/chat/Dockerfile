# Inventory Planner chat image (Chainlit + Bedrock agent).
# Build from repository root:
#   docker build -f services/chat/Dockerfile -t inventory-planner-chat .

FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    CHAINLIT_HOST=0.0.0.0 \
    CHAINLIT_PORT=8000

COPY services/chat/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY shared /app/shared
COPY services /app/services

EXPOSE 8000

CMD ["chainlit", "run", "services/chat/app.py", "--host", "0.0.0.0", "--port", "8000"]
