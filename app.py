from fastapi import FastAPI, Request
from pydantic import BaseModel
from typing import Union, Optional, List, Dict, Any
from aiohttp import ClientSession
import aioredis
import json
import os
from fastapi.templating import Jinja2Templates
from pycoingecko import CoinGeckoAPI
import logging

class PriceResponse(BaseModel):
    symbol: str
    price: Union[float, int]
    currency: str
    change_24h: Optional[float]

class PriceInfo(BaseModel):
    price: float
    change_24h: float

class SymbolPrice(BaseModel):
    currencies: Dict[str, PriceInfo]

app = FastAPI(title="Crypto Prices API", description="An API for getting cryptocurrency prices", version="1.0.0")
cg = CoinGeckoAPI()
templates = Jinja2Templates(directory="templates")

logging.basicConfig(level=logging.INFO)

# Read environment variables for Redis config
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
CACHE_EXPIRATION_TIME = int(os.getenv("CACHE_EXPIRATION_TIME", 300))

@app.on_event("startup")
async def startup():
    global redis_client
    redis_url = f"redis://{REDIS_HOST}:{REDIS_PORT}"
    redis_client = aioredis.from_url(redis_url)

@app.on_event("shutdown")
async def shutdown():
    await redis_client.close()

@app.get('/')
async def home(request: Request):
    api_info = {
        "title": "My Crypto Prices API",
        "description": "An API for getting cryptocurrency prices",
        "version": "1.0.0"
    }
    return templates.TemplateResponse("index.html", {"request": request, "api_info": api_info})

@app.get('/symbols', response_model=List[str])
async def get_crypto_symbols():
    cache_key = "symbols"
    cached_symbols = await redis_client.get(cache_key)
    
    if cached_symbols:
        symbols = json.loads(cached_symbols.decode())
        redis_client.close()
        return symbols

    coins_list = cg.get_coins_list()
    symbols = [coin['id'] for coin in coins_list]
    
    await redis_client.setex(cache_key, CACHE_EXPIRATION_TIME, json.dumps(symbols))
    redis_client.close()

    return symbols

@app.get('/price', response_model=Dict[str, Any])
async def get_crypto_prices(symbols: str, currency: str = 'usd'):
    symbol_list = symbols.split(',')
    price_responses = {}

    for symbol in symbol_list:
        cache_key = f"price:{symbol}:{currency}"
        cached_price_data = await redis_client.get(cache_key)
        
        if cached_price_data:
            price_data = json.loads(cached_price_data.decode())
            logging.info(f"Fetched {symbol} data from the cache.")
        else:
            price_data = cg.get_price(ids=symbol, vs_currencies=currency, include_24hr_change='true')
            if price_data:
                await redis_client.setex(cache_key, CACHE_EXPIRATION_TIME, json.dumps(price_data))
            logging.info(f"Fetched {symbol} data from the CoinGecko API.")
        
        if price_data:
            price = price_data[symbol][currency]
            change_24h = price_data[symbol].get(f"{currency}_24h_change")
            price_responses[symbol] = {
                currency: price,
                f"{currency}_24h_change": change_24h
            }
    return price_responses
