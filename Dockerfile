FROM python:3.11-slim-bookworm

LABEL org.opencontainers.image.description="get-crypto-prices"
LABEL org.opencontainers.image.source="ghcr.io/charlesjudith/coingecko-prices:latest"

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        gcc \
        libc6-dev && \
    rm -rf /var/lib/apt/lists/* && \
    apt-get clean

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt
COPY . .

EXPOSE 8000

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4", "--loop", "uvloop", "--http", "h11", "--backlog", "2048"]
