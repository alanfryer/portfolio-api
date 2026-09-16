from fastapi import APIRouter, Depends
from services.exchange_rate_service import ExchangeRateService

# Initialise the router module for exchange rate operations
router = APIRouter()


def get_exchange_rate_service() -> ExchangeRateService:
    return ExchangeRateService()


# PERFORMANCE FIX: Changed from 'async def' to 'def'.
# Because 'get_exchange_rates' uses the synchronous 'requests' library,
# defining this as a standard synchronous function forces FastAPI to execute it
# within a separate thread pool. This prevents it from blocking the main event loop.
@router.get("/v1/exchange/rates/{currency_symbol}")
def get_exchange_rates(currency_symbol: str):
    """
    HTTP GET Endpoint: Fetches live exchange rates for a specific base currency
    and caches the response layout locally into 'exchange_rates.json'.

    :param currency_symbol: The 3-letter currency code (e.g., 'USD', 'EUR').
    :return: A JSON dictionary containing the exchange rate matrix, or a JSONResponse on failure.
    """
    # Call the core utility system to process the API request and handle file mutations
    return ExchangeRateService.get_exchange_rates(currency_symbol)
