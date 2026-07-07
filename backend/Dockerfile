FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl \
    && rm -rf /var/lib/apt/lists/*

# Pre-install CPU-only PyTorch so pymilvus-model skips NVIDIA GPU deps (~1.5GB savings)
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

# Tier 1: heavy deps (rarely change — cached across builds)
COPY requirements-base.txt .
RUN pip install --no-cache-dir -r requirements-base.txt

# Tier 2: lightweight deps (frequently change — only this layer rebuilds)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /app/data/personas /app/data/uploads

ENV PYTHONUNBUFFERED=1

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
