FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PERSONAL_ASSISTANT_HOST=0.0.0.0 \
    PERSONAL_ASSISTANT_PORT=8083 \
    DECISION_GATEWAY_URL=http://decision-gateway:8081 \
    MODEL_ROUTER_URL=http://model-router:8082 \
    WEATHER_BASE_URL=https://api.open-meteo.com \
    WEATHER_LOCATIONS="Barcelona:41.3874,2.1686;Sant Cugat del Vallès:41.4728,2.0864"

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY weather.py locations.py brief.py app.py .

EXPOSE 8083
CMD ["python", "app.py"]
