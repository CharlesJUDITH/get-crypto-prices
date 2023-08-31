from fastapi import FastAPI
from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates
from pycoingecko import CoinGeckoAPI
import redis
from typing import Dict
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Union, List, Optional, Any, Dict
import json
import os

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

# get configuration variables from environment variables
REDIS_HOST = os.environ.get('REDIS_HOST', 'localhost')
REDIS_PORT = os.environ.get('REDIS_PORT', 6379)
REDIS_DB = os.environ.get('REDIS_DB', 0)
REDIS_PASSWORD = os.environ.get('REDIS_PASSWORD', None)
CACHE_EXPIRATION_TIME = os.environ.get('CACHE_EXPIRATION_TIME', 300)

app = FastAPI(title="Crypto Prices API", description="An API for getting cryptocurrency prices", version="1.0.0")

# initialize CoinGecko API client and Redis client
cg = CoinGeckoAPI()

redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB, password=None)

# set cache expiration time to 5 minutes
cache_expiration_time = int(CACHE_EXPIRATION_TIME)


templates = Jinja2Templates(directory="templates")

@app.get("/")
async def home(request: Request):
    api_info = {
        "title": "My Crypto Prices API",
        "description": "An API for getting cryptocurrency prices",
        "version": "1.0.0"
    }
    return templates.TemplateResponse("index.html", {"request": request, "api_info": api_info})

# define API endpoint to get all available symbols
@app.get('/symbols', response_model=List[str])
async def get_crypto_symbols():
    cache_key = "symbols"
    cached_symbols = redis_client.get(cache_key)

    if cached_symbols is not None:
        print("Fetching all available symbols from cache...")
        symbols = cached_symbols.decode().split(',')
        return symbols

    print("Fetching all available symbols from CoinGecko API...")
    coins_list = cg.get_coins_list()
    symbols = [coin["id"] for coin in coins_list]
    # Store the list of symbols in the cache
    redis_client.setex(cache_key, cache_expiration_time, ','.join(symbols))

    return symbols

@app.get('/price', response_model=Dict[str, Any])
async def get_crypto_prices(symbols: str, currency: str = 'usd'):
    symbol_list = symbols.split(',')
    price_responses = {}  # Initialize an empty dictionary, not a list

    for symbol in symbol_list:
        cache_key = f"price:{symbol}:{currency}"
        cached_price_data = redis_client.get(cache_key)

        if cached_price_data:
            cached_price_data = json.loads(cached_price_data.decode())
            print(f"Fetching {symbol} price in {currency} from cache...")
            price = cached_price_data['price']
            price_variation = cached_price_data['change_24h']
        else:
            print(f"Fetching {symbol} price in {currency} from CoinGecko API...")
            price_data = cg.get_price(ids=symbol, vs_currencies=currency, include_24hr_change='true')

            if not price_data.get(symbol):
                continue

            price = price_data[symbol][currency]
            price_variation = price_data[symbol].get(f"{currency}_24h_change")

            # Cache the price and 24h_change
            redis_client.setex(cache_key, cache_expiration_time, json.dumps({'price': price, 'change_24h': price_variation}))

        # Update the price_responses dictionary
        if symbol not in price_responses:
            price_responses[symbol] = {}

        price_responses[symbol][currency] = price
        price_responses[symbol][f"{currency}_24h_change"] = price_variation

    return price_responses

