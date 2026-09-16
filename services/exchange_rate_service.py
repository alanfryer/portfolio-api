import datetime
import json
import requests


class ExchangeRateService:
    @staticmethod
    def get_exchange_rates(currency_symbol: str) -> dict | None:
        """
        Fetches the live macroeconomic currency matrix via ://er-api.com
        and caches the payload locally into 'exchange_rates.json'.

        :param currency_symbol: Base comparison denomination (e.g., 'USD')
        """
        url = f"https://open.er-api.com/v6/latest/{currency_symbol}"
        try:
            # Enforced a 5-second explicit timeout constraint to prevent hanging API connections
            response = requests.get(url, timeout=5)
            status_code = response.status_code

            if status_code == 200:
                exchange_rates = response.json()
                with open("exchange_rates.json", "w", encoding="utf-8") as f:
                    json.dump(exchange_rates, f, indent=4)  # Safe JSON writing abstraction
                return exchange_rates

            print(f"Failed to retrieve Exchange rates. Status: {status_code}")
            return None
        except requests.RequestException as e:
            print(f"Network error updating exchange rates: {e}")
            return None

    @staticmethod
    def get_exchange_rate(currency_symbol: str) -> float:
        """
        Reads the locally cached 'exchange_rates.json' file to parse out specific valuation relationships.
        Returns 1.0 as a safe fallback if parsing fail conditions trigger.
        """
        filename = "exchange_rates.json"
        try:
            with open(filename, "r", encoding="utf-8") as file:
                data = json.load(file)
            return data["rates"].get("GBP", 1.0)
        except (FileNotFoundError, json.JSONDecodeError, KeyError):
            print("Warning: Could not parse exchange_rates.json, using fallback 1.0 rate.")
            return 1.0
