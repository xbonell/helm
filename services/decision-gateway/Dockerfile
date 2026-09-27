# Minimal DecisionEngine HTTP adapter (Milestone 5 fleshes out the interface).
# Milestone 1 ships a health-only stub so compose validates and the service boots.

FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DECISION_GATEWAY_HOST=0.0.0.0 \
    DECISION_GATEWAY_PORT=8081 \
    DECIDER_BASE_URL=http://decider:8000

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY engine.py app.py .

EXPOSE 8081
CMD ["python", "app.py"]
