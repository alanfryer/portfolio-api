from datetime import datetime
from functools import lru_cache
import json
import logging
import os
from typing import Any, Dict, Optional, Tuple
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

MET_OFFICE_URL = "https://data.hub.api.metoffice.gov.uk/sitespecific/v0/point"
GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
WEATHER_CODES_FILE = "weather_codes.json"
MET_OFFICE_API_KEY = os.getenv("METOFFICE_API_KEY", "").strip()

# Setup standard structured logging instead of using print()
logger = logging.getLogger("portfolio_app")

# Reuse a single HTTP session with retries for connection pooling and resilience
_session = requests.Session()
_retries = Retry(total=3, backoff_factor=0.3, status_forcelist=[429, 500, 502, 503, 504])
_session.mount("https://", HTTPAdapter(max_retries=_retries))

class WeatherService:
    def __init__(self):
        logger.info("Initialized the Weather Service")
        
    @lru_cache(maxsize=1)
    def _load_weather_codes(self, filepath: str = WEATHER_CODES_FILE) -> Dict[str, str]:
        """Load and cache weather code descriptions once instead of reading disk repeatedly."""
        try:
            with open(filepath, "r", encoding="utf-8") as file:
                return json.load(file)
        except (FileNotFoundError, json.JSONDecodeError, OSError) as e:
            logger.error("Could not load weather codes from '%s': %s", filepath, e)
            return {}


    def get_weather_code(self, code: str) -> str:
        """Return human-readable weather description for a Met Office weather code."""
        return self._load_weather_codes().get(str(code), "Unknown code")


    @lru_cache(maxsize=256)
    def get_location_coordinates(self, location: str) -> Optional[Tuple[float, float]]:
        """Fetch (latitude, longitude) for a location string using Open-Meteo."""
        cleaned = location.strip()
        if not cleaned:
            return None

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
                logger.info("No coordinates found for location: '%s'", cleaned)
                return None

            top_match = results[0]
            return float(top_match["latitude"]), float(top_match["longitude"])

        except requests.Timeout:
            logger.warning("Geocoding request timed out for '%s'", cleaned)
        except requests.HTTPError as e:
            logger.warning("HTTP error (%s) for '%s': %s", e.response.status_code, cleaned, e)
        except requests.RequestException as e:
            logger.warning("Network error geocoding '%s': %s", cleaned, e)
        except (ValueError, KeyError, TypeError) as e:
            logger.error("Unexpected API payload structure for '%s': %s", cleaned, e)

        return None


    def get_forecast(self, 
        location: str,
        timesteps: str,
    ) -> Optional[Dict[str, Any]]:
        """Retrieve site-specific forecast properties from the Met Office DataHub API."""
        coords = self.get_location_coordinates(location)
        if coords is None:
            logger.warning("Cannot retrieve forecast; coordinates not found for '%s'", location)
            return None

        lat, lon = coords
        url = f"{MET_OFFICE_URL}/{timesteps.lstrip('/')}"

        headers = {
            "accept": "application/json",
            "apikey": MET_OFFICE_API_KEY
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
                logger.error("Expected response to be a dictionary, got %s.", type(forecast).__name__)
                return None

            features = forecast.get("features")
            if not features or not isinstance(features, list):
                logger.warning("Forecast response contains an empty or invalid 'features' list.")
                return None

            properties = features[0].get("properties")
            if not isinstance(properties, dict):
                logger.warning("Missing or invalid 'properties' object in forecast feature.")
                return None

            return properties

        except requests.Timeout:
            logger.warning("Forecast request timed out for '%s'", location)
        except requests.HTTPError as e:
            logger.warning("HTTP error (%s) retrieving forecast: %s", e.response.status_code, e)
        except requests.RequestException as e:
            logger.warning("Network error getting forecast: %s", e)
        except (ValueError, KeyError, IndexError, TypeError) as e:
            logger.error("Unexpected JSON structure in forecast response: %s", e)

        return None


    def get_hourly_forecast(self, location: str, target_date: str, target_hour: int) -> Dict:
        """Parse a forecast dictionary and return the formatted weather string for a target date and hour."""
        
        forecast = self.get_forecast(location, "hourly")
        
        if not forecast:
            msg = f"Could not find forecast for location {location}."
            logger.warning("Could not find forecast for location %s", location)
            return {"error": msg }

        try:
            # Safely handle cases where 'location' is missing or None (e.g., if includeLocationName='FALSE')
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
                
                data = {
                    "location": location,
                    "summary": summary,
                    "timeSeries": [day]
                }
                
                return data

            logger.warning("No forecast found matching %s at %02d:00.", target_date, target_hour)
            return {}

        except (KeyError, IndexError, TypeError) as e:
            logger.error("Unexpected JSON structure while parsing forecast: %s", e, exc_info=True)
            return None