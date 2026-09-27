# Minimal ModelProvider HTTP service.

FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MODEL_ROUTER_HOST=0.0.0.0 \
    MODEL_ROUTER_PORT=8082 \
    MODEL_PROVIDER=stub \
    MODEL_NAME=stub/local

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY provider.py app.py .

EXPOSE 8082
CMD ["python", "app.py"]
