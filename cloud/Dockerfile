# Build from the repo root (not from cloud/):
#   docker build -f cloud/Dockerfile -t fennsill-cloud:latest .
#
# Cloud imports shared modules outside cloud/:
#   connector/runtime/artifact_security.py
#   connector/mcp_catalog.py
#   templates/chart_page.py

FROM python:3.12-slim

WORKDIR /app

COPY cloud/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY cloud/ /app/cloud/
COPY connector/mcp_catalog.py /app/connector/mcp_catalog.py
COPY connector/runtime/artifact_security.py /app/connector/runtime/artifact_security.py
COPY templates/chart_page.py /app/templates/chart_page.py

WORKDIR /app/cloud

ENV FENNSILL_CLOUD_HOST=0.0.0.0
ENV FENNSILL_CLOUD_PORT=8080
ENV FENNSILL_CLOUD_DB=/data/cloud.db
ENV PYTHONPATH=/app/cloud:/app/connector:/app/connector/runtime:/app/templates

VOLUME ["/data"]
EXPOSE 8080

CMD ["python", "main.py"]
