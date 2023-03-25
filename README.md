# CoinGeckgo prices

A basic FastAPI application with Redis to cache the query results.

## Requirements

- Docker

## Installation

TODO

## Local run

### Run the redis container

`docker run -d --name redis -p 6379:6379 redis`

If you want to have an "advanced interface" to watch the cache, use redis-stack:

`docker run -d --name redis -p 6379:6379 -p 8001:8001 redis/redis-stack:latest`

### Run the python app

uvicorn app:app --reload

Check the API doc http://127.0.0.1:8000/docs

Use the API http://127.0.0.1:8000/price?symbols=cosmos&currency=usd
