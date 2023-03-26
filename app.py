from fastapi import FastAPI
from pycoingecko import CoinGeckoAPI
import redis
from typing import Dict
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Union
from typing import List
import os

class PriceResponse(BaseModel):
    symbol: str
    price: Union[float, int]
    currency: str

# get configuration variables from environment variables
REDIS_HOST = os.environ.get('REDIS_HOST', 'localhost')
REDIS_PORT = os.environ.get('REDIS_PORT', 6379)
REDIS_DB = os.environ.get('REDIS_DB', 0)
REDIS_PASSWORD = os.environ.get('REDIS_PASSWORD', None)

app = FastAPI()

# initialize CoinGecko API client and Redis client
cg = CoinGeckoAPI()

redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB, password=None)

# set cache expiration time to 5 minutes
cache_expiration_time = 300

# define API endpoint to get all available symbols
@app.get('/symbols', response_model=List[str])
async def get_crypto_symbols():
    """Get all available symbols"""
    print("Fetching all available symbols from CoinGecko API...")
    coins_list = cg.get_coins_list()
    return [coin["id"] for coin in coins_list]

# define API endpoint to get the price of a cryptocurrency by symbol
@app.get('/price', response_model=List[PriceResponse])
async def get_crypto_prices(symbols: str, currency: str = 'usd'):
    """Get the prices of cryptocurrencies by symbol"""
    # split the symbols string into a list of symbols
    symbol_list = symbols.split(',')

    # create a list of price responses for each symbol
    price_responses = []
    for symbol in symbol_list:
        # check if price data is available in Redis cache
        cache_key = f"price:{symbol}:{currency}"
        cached_price = redis_client.get(cache_key)
        if cached_price is not None:
            print(f"Fetching {symbol} price in {currency} from cache...")
            price_responses.append({'symbol': symbol, 'price': float(cached_price.decode()), 'currency': currency})
        else:
            # fetch price data from CoinGecko API
            print(f"Fetching {symbol} price in {currency} from CoinGecko API...")
            price_data = cg.get_price(ids=symbol, vs_currencies=currency)
            if not price_data.get(symbol):
                return JSONResponse(content={'message': f"{symbol} not found"}, status_code=404)
            price = price_data[symbol][currency]

            # cache the price data in Redis
            redis_client.setex(cache_key, cache_expiration_time, price)

            price_responses.append({'symbol': symbol, 'price': price, 'currency': currency})

    return price_responses

