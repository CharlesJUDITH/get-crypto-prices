# CoinGeckgo prices

A basic FastAPI application with Redis to cache the query results.

## Requirements

- Docker

## Local run

Export some environment variables:

`export REDIS_PORT=6379`
`export REDIS_HOST=localhost`
`export REDIS_DB=0`

For "production usage", use a password:
`export REDIS_PASSEWORD=youpasswordhere`

### Run the redis container

`docker run -d --name redis --env REDIS_PASSWORD -p 6379:6379 redis`

If you want to have an "advanced interface" to watch the cache, use redis-stack:

`docker run -d --name redis -p 6379:6379 -p 8001:8001 --env redis/redis-stack:latest`

### Run the python app

`docker pull ghcr.io/charlesjudith/coingecko-prices:latest`

`docker run --env REDIS_HOST --env REDIS_PORT --env REDIS_DB --env REDIS_PASSWORD -p 8000:8000 coingecko-prices:latest`

Check the API doc http://127.0.0.1:8000/docs

Use the API http://127.0.0.1:8000/price?symbols=cosmos&currency=usd

## Demo

The demo as been deployed on Akash cloud.

http://provider.bdl.computer:32749/docs
