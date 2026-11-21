import logging
from fastapi import APIRouter, Depends
from services.weather_service import WeatherService

# Initialise the router module for exchange rate operations
router = APIRouter()
logger = logging.getLogger("portfolio_app")

def get_weather_service() -> WeatherService:
    return WeatherService()



@router.get("/v1/weather/hourly")
def get_hourly_forecast(
    location: str, 
    date: str,
    hour: int, 
    weather: WeatherService = Depends(get_weather_service)):
    """
    HTTP GET Endpoint: Fetches live exchange rates for a specific base currency
    and caches the response layout locally into 'exchange_rates.json'.

    :param location: The location to return the weather for.
    :return: A JSON dictionary containing the weather, or a JSONResponse on failure.
    """
    
    return weather.get_hourly_forecast(location, date, hour)
