FROM python:3.9-slim-buster

LABEL org.opencontainers.image.description get-crypto-prices
LABEL org.opencontainers.image.source="ghcr.io/charlesjudith/coingecko-prices:latest"

RUN apt-get update && \
    apt-get install -y gcc && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/
RUN pip install -r /app/requirements.txt

COPY . /app/
WORKDIR /app

EXPOSE 8000

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4", "--loop", "uvloop", "--http", "h11", "--backlog", "2048"]
