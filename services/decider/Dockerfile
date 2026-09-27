# Thin wrapper around Mapika Decider HTTP server.
# No fork — installs published `decider-ai[serve]` from PyPI.
# Uses CPU torch wheels by default (no NVIDIA assumed).

FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HF_HOME=/cache/huggingface \
    DECIDER_MODEL=Mapika/decider-2b \
    DECIDER_DEVICE=cpu \
    DECIDER_WARMUP=0 \
    USE_HUB_KERNELS=NO

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Install CPU torch first so decider-ai does not pull CUDA wheels.
# Then remove FLA/Triton: those packages claim CPU rollback but still call Triton
# and crash with "0 active drivers" on CPU-only hosts. Transformers falls back
# to its pure-PyTorch Qwen3.5 kernels (slower, correct).
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir "decider-ai[serve]" \
    && pip uninstall -y flash-linear-attention fla-core triton || true

WORKDIR /app
RUN mkdir -p /cache/huggingface

EXPOSE 8000

# Official entrypoint shape from scripts/serve.sh:
# uvicorn decider.serve:app --host 0.0.0.0 --port 8000
CMD ["uvicorn", "decider.serve:app", "--host", "0.0.0.0", "--port", "8000"]
