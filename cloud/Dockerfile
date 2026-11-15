FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

ENV FENNSILL_CLOUD_HOST=0.0.0.0
ENV FENNSILL_CLOUD_PORT=8080
ENV FENNSILL_CLOUD_DB=/data/cloud.db
ENV PYTHONPATH=/app

VOLUME ["/data"]
EXPOSE 8080

CMD ["python", "main.py"]
