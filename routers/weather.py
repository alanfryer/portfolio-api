import logging
from fastapi import APIRouter, Depends
from services.weather_service import WeatherService

# Initialise the router module for weather operations
router = APIRouter(prefix="/v1/weather", tags=["Weather"])
logger = logging.getLogger("portfolio_app")

def get_weather_service() -> WeatherService:
    return WeatherService()


@router.get("/hourly")
def get_hourly_forecast(
    location: str, 
    date: str,
    hour: int, 
    weather: WeatherService = Depends(get_weather_service)):
    """
    HTTP GET Endpoint: Fetches hourly forecast for a date and time.

    :param location: The location to return the weather for.
    :return: A JSON dictionary containing the weather, or a JSONResponse on failure.
    """
    
    return weather.get_hourly_forecast(location, date, hour)

@router.get("/daily")
def get_daily_forecast(
    location: str, 
    date: str,
    weather: WeatherService = Depends(get_weather_service)):
    """
    HTTP GET Endpoint: Fetches daily forecast for a date.

    :param location: The location to return the weather for.
    :return: A JSON dictionary containing the weather, or a JSONResponse on failure.
    """
    
    return weather.get_daily_forecast(location, date)