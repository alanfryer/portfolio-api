from datetime import datetime
from functools import lru_cache
import json
import logging
import os
from typing import Any, Dict, Tuple
from fastapi import HTTPException, status
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

MET_OFFICE_URL = "https://data.hub.api.metoffice.gov.uk/sitespecific/v0/point"
GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
WEATHER_CODES_FILE = "weather_codes.json"
MET_OFFICE_API_KEY = os.getenv("MET_OFFICE_API_KEY", "").strip()

# Setup standard structured logging instead of using print()
logger = logging.getLogger("portfolio_app")



# Reuse a single HTTP session with retries for connection pooling and resilience
_session = requests.Session()
_retries = Retry(total=3, backoff_factor=0.3, status_forcelist=[429, 500, 502, 503, 504])
_session.mount("https://", HTTPAdapter(max_retries=_retries))

class WeatherService:
    WEATHER_CODES: Dict[str, str] = None
    def __init__(self):
        if WeatherService.WEATHER_CODES is None:
            WeatherService.WEATHER_CODES = self._load_weather_codes()
            
        logger.info("Initialized the Weather Service")
    
    @staticmethod    
    def _load_weather_codes():
        """Load weather code descriptions once at module import."""
        try:
            logger.info(f"Loading weather codes from file {WEATHER_CODES_FILE}")
            with open(WEATHER_CODES_FILE, "r", encoding="utf-8") as file:
                return json.load(file)

        except (FileNotFoundError, json.JSONDecodeError, OSError) as e:
            logger.error("Could not load weather codes from '%s': %s", WEATHER_CODES_FILE, e)
            return {}
   
    def get_weather_code(self, code: str) -> str:
        """Return human-readable weather description for a Met Office weather code."""
        return self.WEATHER_CODES.get(str(code), "Unknown code")


    @lru_cache(maxsize=256)
    def get_location_coordinates(self, location: str) -> Tuple[float, float]:
        """Fetch (latitude, longitude) for a location string using Open-Meteo."""
        cleaned = location.strip()
        if not cleaned:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Location parameter cannot be empty.",
            )
            
        params = {
            "name": cleaned,
            "count": 1,
            "language": "en",
            "format": "json",
        }

        try:
            response = _session.get(GEOCODE_URL, params=params, timeout=5.0)
            response.raise_for_status()
            data = response.json()

            results = data.get("results")
            
            if not results:
                msg = f"No coordinates found for location '{cleaned}'."
                logger.info(msg)
  
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=msg
                )

            top_match = results[0]
            return float(top_match["latitude"]), float(top_match["longitude"])

        except HTTPException:
            # Re-raise HTTPExceptions untouched so they aren't caught below
            raise
        except requests.Timeout as e:
            msg = f"Geocoding request timed out for '{cleaned}'"
            logger.warning(msg)
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail=msg,
            ) from e
        except requests.HTTPError as e:
            status_code = e.response.status_code if e.response is not None else "Unknown"
            msg = f"Geocoding API HTTP error ({status_code}) for '{cleaned}': {e}"
            logger.warning(msg)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=msg,
            ) from e
        except requests.RequestException as e:
            msg = f"Network error geocoding '{cleaned}': {e}"
            logger.warning(msg)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=msg,
            ) from e
        except (ValueError, KeyError, TypeError) as e:
            msg = f"Unexpected geocoding payload structure for '{cleaned}': {e}"
            logger.error(msg)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=msg,
            ) from e


    def get_forecast(self, location: str, timesteps: str) -> Dict[str, Any]:
        """Retrieve site-specific forecast properties from the Met Office DataHub API."""
        if not MET_OFFICE_API_KEY:
            logger.error("MET_OFFICE_API_KEY is missing or empty.")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Weather service API key is not configured.",
            )

        # Raises HTTPException automatically if location is invalid/not found
        lat, lon = self.get_location_coordinates(location)
        url = f"{MET_OFFICE_URL}/{timesteps.lstrip('/')}"

        headers = {
            "accept": "application/json",
            "apikey": MET_OFFICE_API_KEY,
        }

        params = {
            "excludeParameterMetadata": "TRUE",
            "includeLocationName": "TRUE",
            "latitude": lat,
            "longitude": lon,
        }

        try:
            response = _session.get(url, headers=headers, params=params, timeout=5.0)
            response.raise_for_status()
            forecast = response.json()

            if not isinstance(forecast, dict):
                msg = f"Expected response to be a dictionary, got {type(forecast).__name__}."
                logger.error(msg)
                raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=msg)

            features = forecast.get("features")
            if not features or not isinstance(features, list):
                msg = f"No forecast features returned for '{location}'."
                logger.warning(msg)
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg)

            properties = features[0].get("properties")
            if not isinstance(properties, dict):
                msg = "Missing or invalid 'properties' object in forecast feature."
                logger.warning(msg)
                raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=msg)

            return properties

        except HTTPException:
            raise
        except requests.Timeout as e:
            msg = f"Forecast request timed out for '{location}'"
            logger.warning(msg)
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail=msg,
            ) from e
        except requests.HTTPError as e:
            status_code = e.response.status_code if e.response is not None else "Unknown"
            msg = f"Met Office API HTTP error ({status_code}) retrieving forecast: {e}"
            logger.warning(msg)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=msg,
            ) from e
        except requests.RequestException as e:
            msg = f"Network error getting forecast for '{location}': {e}"
            logger.warning(msg)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=msg,
            ) from e
        except (ValueError, KeyError, IndexError, TypeError) as e:
            msg = f"Unexpected JSON structure in forecast response: {e}"
            logger.error(msg)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=msg,
            ) from e


    def get_hourly_forecast(self, location: str, target_date: str, target_hour: int) -> Dict:
        """Parse a forecast dictionary and return the formatted weather string for a target date and hour."""
        
        forecast = self.get_forecast(location, "hourly")
        station = (forecast.get("location") or {}).get("name", "Unknown station")
        days = forecast.get("timeSeries", [])

        for day in days:
            try:
                weather_date = day["time"]
                dt = datetime.strptime(weather_date, "%Y-%m-%dT%H:%MZ")
            except (KeyError, TypeError, ValueError) as e:
                logger.warning("Skipping entry due to invalid or missing timestamp: %s", e)
                continue

            if dt.strftime("%d-%m-%Y") != target_date or dt.hour != target_hour:
                continue

            temp = day.get("screenTemperature", "N/A")
            feels_like_temp = day.get("feelsLikeTemperature", "N/A")
            wind_speed = day.get("windSpeed10m", "N/A")
            wind_direction = day.get("windDirectionFrom10m", "N/A")
            wind_gust_speed = day.get("windGustSpeed10m", "N/A")
            precipitation = day.get("probOfPrecipitation", "N/A")
            humidity = day.get("screenRelativeHumidity", "N/A")

            weather_code = day.get("significantWeatherCode")
            weather_description = (
                self.get_weather_code(str(weather_code)) if weather_code is not None else "Unknown"
            )

            summary = (
                f"Nearest weather station {station}, Date: {weather_date}, "
                f"{weather_description}, Temperature: {temp}, Feels like: {feels_like_temp}, "
                f"Wind speed: {wind_speed}, direction: {wind_direction}, "
                f"Wind Gust speed: {wind_gust_speed}, Probability of rain: {precipitation}%, "
                f"Humidity: {humidity}%"
            )   
            
            return {
                "location": location,
                "summary": summary,
                "timeSeries": [day]
            }
        
        msg = f"No forecast found matching {target_date} at {target_hour}."
        logger.warning(msg)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=msg,
        )

