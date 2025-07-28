from fastapi import FastAPI, Request, HTTPException
from pydantic import BaseModel
from typing import Union, Optional, List, Dict, Any
from aiohttp import ClientSession
import redis.asyncio as redis  # Using redis package async functionality
import json
import os
import asyncio
from fastapi.templating import Jinja2Templates
from pycoingecko import CoinGeckoAPI
import logging

class PriceResponse(BaseModel):
    symbol: str
    price: Union[float, int]
    currency: str
    change_24h: Optional[float]
    market_cap: Optional[float]
    circulating_supply: Optional[float]

class PriceInfo(BaseModel):
    price: float
    change_24h: float
    market_cap: Optional[float]
    circulating_supply: Optional[float]

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

# Batch size for API calls (CoinGecko allows up to 250 symbols per request)
BATCH_SIZE = 100

@app.on_event("startup")
async def startup():
    global redis_client
    # Create Redis client with redis-py async functionality
    redis_client = redis.Redis(
        host=REDIS_HOST, 
        port=REDIS_PORT, 
        decode_responses=True
    )

@app.on_event("shutdown")
async def shutdown():
    await redis_client.aclose()  # Use aclose() for proper async cleanup

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
        symbols = json.loads(cached_symbols)
        logging.info("Fetched symbols from cache")
        return symbols
    
    try:
        coins_list = cg.get_coins_list()
        symbols = [coin['id'] for coin in coins_list]
        
        await redis_client.setex(cache_key, CACHE_EXPIRATION_TIME, json.dumps(symbols))
        logging.info(f"Fetched {len(symbols)} symbols from CoinGecko API")
        return symbols
    except Exception as e:
        logging.error(f"Error fetching symbols: {e}")
        raise HTTPException(status_code=500, detail="Error fetching symbols")

async def get_cached_prices(symbols: List[str], currency: str) -> Dict[str, Dict]:
    """Get cached prices for multiple symbols concurrently"""
    cache_keys = [f"price:{symbol}:{currency}" for symbol in symbols]
    
    # Get all cached data in a single pipeline operation
    async with redis_client.pipeline() as pipe:
        for key in cache_keys:
            pipe.get(key)
        cached_results = await pipe.execute()
    
    cached_data = {}
    uncached_symbols = []
    
    for symbol, cached_result in zip(symbols, cached_results):
        if cached_result:
            try:
                cached_data[symbol] = json.loads(cached_result)
                logging.info(f"Cache hit for {symbol}")
            except json.JSONDecodeError:
                uncached_symbols.append(symbol)
        else:
            uncached_symbols.append(symbol)
    
    return cached_data, uncached_symbols

async def fetch_detailed_data(symbols: List[str], currency: str) -> Dict[str, Dict]:
    """Fetch detailed data including circulating supply using coins/markets endpoint"""
    if not symbols:
        return {}
    
    try:
        # Use the coins/markets endpoint for detailed data including circulating supply
        market_data = cg.get_coins_markets(
            vs_currency=currency,
            ids=','.join(symbols),
            order='market_cap_desc',
            per_page=len(symbols),
            page=1,
            sparkline=False,
            price_change_percentage='24h'
        )
        
        detailed_data = {}
        for coin in market_data:
            symbol = coin['id']
            detailed_data[symbol] = {
                symbol: {
                    currency: coin['current_price'],
                    f"{currency}_market_cap": coin['market_cap'],
                    f"{currency}_24h_change": coin['price_change_percentage_24h'],
                    "circulating_supply": coin['circulating_supply']
                }
            }
        
        return detailed_data
    
    except Exception as e:
        logging.error(f"Error fetching detailed market data: {e}")
        return {}

async def fetch_prices_batch(symbols: List[str], currency: str) -> Dict[str, Dict]:
    """Fetch prices for multiple symbols with market cap and circulating supply"""
    if not symbols:
        return {}
    
    try:
        # First try the simple price endpoint with market cap
        symbols_str = ','.join(symbols)
        price_data = cg.get_price(
            ids=symbols_str, 
            vs_currencies=currency, 
            include_24hr_change='true',
            include_market_cap='true'
        )
        
        # Get detailed data for circulating supply
        detailed_data = await fetch_detailed_data(symbols, currency)
        
        # Merge the data
        final_data = {}
        for symbol in symbols:
            if symbol in price_data:
                symbol_info = price_data[symbol].copy()
                
                # Add circulating supply from detailed data if available
                if symbol in detailed_data and 'circulating_supply' in detailed_data[symbol][symbol]:
                    symbol_info['circulating_supply'] = detailed_data[symbol][symbol]['circulating_supply']
                
                final_data[symbol] = {symbol: symbol_info}
        
        if final_data:
            # Cache each symbol's data individually for future requests
            async with redis_client.pipeline() as pipe:
                for symbol in symbols:
                    if symbol in final_data:
                        cache_key = f"price:{symbol}:{currency}"
                        pipe.setex(cache_key, CACHE_EXPIRATION_TIME, json.dumps(final_data[symbol]))
                await pipe.execute()
            
            logging.info(f"Fetched {len(final_data)} symbols with detailed data from CoinGecko API")
        
        return final_data or {}
    
    except Exception as e:
        logging.error(f"Error fetching batch prices with detailed data: {e}")
        # Fallback to simple price data without circulating supply
        try:
            symbols_str = ','.join(symbols)
            price_data = cg.get_price(
                ids=symbols_str, 
                vs_currencies=currency, 
                include_24hr_change='true',
                include_market_cap='true'
            )
            
            fallback_data = {}
            for symbol in symbols:
                if symbol in price_data:
                    fallback_data[symbol] = {symbol: price_data[symbol]}
            
            return fallback_data or {}
        except Exception as fallback_e:
            logging.error(f"Fallback also failed: {fallback_e}")
            return {}

def process_batches(symbols: List[str], batch_size: int = BATCH_SIZE) -> List[List[str]]:
    """Split symbols into batches for processing"""
    return [symbols[i:i + batch_size] for i in range(0, len(symbols), batch_size)]

@app.get('/price', response_model=Dict[str, Any])
async def get_crypto_prices(symbols: str, currency: str = 'usd'):
    symbol_list = [s.strip() for s in symbols.split(',') if s.strip()]
    
    if not symbol_list:
        raise HTTPException(status_code=400, detail="No symbols provided")
    
    if len(symbol_list) > 1000:  # Reasonable limit to prevent abuse
        raise HTTPException(status_code=400, detail="Too many symbols requested (max 1000)")
    
    try:
        # Step 1: Check cache for all symbols
        cached_data, uncached_symbols = await get_cached_prices(symbol_list, currency)
        
        # Step 2: Fetch uncached symbols in batches
        all_price_data = cached_data.copy()
        
        if uncached_symbols:
            logging.info(f"Fetching {len(uncached_symbols)} uncached symbols")
            
            # Process uncached symbols in batches to avoid API limits
            batches = process_batches(uncached_symbols, BATCH_SIZE)
            
            # Create tasks for concurrent batch processing
            batch_tasks = [
                fetch_prices_batch(batch, currency) 
                for batch in batches
            ]
            
            # Execute all batch requests concurrently
            batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)
            
            # Merge batch results
            for result in batch_results:
                if isinstance(result, dict):
                    all_price_data.update(result)
                else:
                    logging.error(f"Batch request failed: {result}")
        
        # Step 3: Format response
        price_responses = {}
        for symbol in symbol_list:
            if symbol in all_price_data:
                symbol_data = all_price_data[symbol]
                if symbol in symbol_data and currency in symbol_data[symbol]:
                    price = symbol_data[symbol][currency]
                    change_24h = symbol_data[symbol].get(f"{currency}_24h_change")
                    market_cap = symbol_data[symbol].get(f"{currency}_market_cap")
                    circulating_supply = symbol_data[symbol].get("circulating_supply")
                    
                    price_responses[symbol] = {
                        currency: price,
                        f"{currency}_24h_change": change_24h,
                        f"{currency}_market_cap": market_cap,
                        "circulating_supply": circulating_supply
                    }
                else:
                    logging.warning(f"Invalid data structure for {symbol}")
            else:
                logging.warning(f"No price data found for {symbol}")
        
        logging.info(f"Returning prices for {len(price_responses)} symbols")
        return price_responses
    
    except Exception as e:
        logging.error(f"Error in get_crypto_prices: {e}")
        raise HTTPException(status_code=500, detail="Error fetching prices")

# Health check endpoint
@app.get('/health')
async def health_check():
    try:
        # Test Redis connection
        await redis_client.ping()
        return {"status": "healthy", "redis": "connected"}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}
