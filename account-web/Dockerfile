FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

ENV FENNSILL_ACCOUNT_HOST=0.0.0.0
ENV FENNSILL_ACCOUNT_PORT=8090
ENV FENNSILL_API_BASE=https://mcp.fennsill.com
ENV FENNSILL_PUBLIC_MCP_URL=https://mcp.fennsill.com/mcp

EXPOSE 8090
CMD ["python", "server.py"]
