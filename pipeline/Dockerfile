FROM python:3.11-slim AS base

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir streamlink

WORKDIR /app
COPY pyproject.toml ./
COPY src ./src

RUN pip install --no-cache-dir -e .

# -- API image -----------------------------------------------------------
FROM base AS api
EXPOSE 8000
CMD ["uvicorn", "streamclip.api.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]

# -- worker image ----------------------------------------------------------
FROM base AS worker
CMD ["python", "-m", "streamclip.worker_main"]
