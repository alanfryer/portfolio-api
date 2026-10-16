import json
import pytest
import requests
from unittest.mock import patch, mock_open, MagicMock
# Adjust this import to match the actual file name where ExchangeRateService lives
from services.exchange_rate_service import ExchangeRateService


# =====================================================================
# TEST CASES FOR: get_exchange_rates
# =====================================================================

@patch("services.exchange_rate_service.requests.get")
@patch("services.exchange_rate_service.open", new_callable=mock_open)
def test_get_exchange_rate_success(mock_file, mock_get):
    # Arrange
    base_currency = "USD"
    mock_payload = {"result": "success", "rates": {"GBP": 0.75, "EUR": 0.90}}
    
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = mock_payload
    mock_get.return_value = mock_response

    # Act
    result = ExchangeRateService.get_exchange_rates(base_currency)

    # Assert
    assert result == mock_payload
    mock_get.assert_called_once_with(
        f"https://open.er-api.com/v6/latest/{base_currency}", timeout=5
    )
    # Check that it writes the JSON string to file correctly
    mock_file.assert_called_once_with("exchange_rates.json", "w", encoding="utf-8")
    
    # Consolidate standard json.dump chunks into one string evaluation
    written_data = "".join(call.args[0] for call in mock_file().write.call_args_list)
    assert "GBP" in written_data


@patch("services.exchange_rate_service.requests.get")
def test_get_exchange_rate_bad_status_code(mock_get, capsys):
    # Arrange
    mock_response = MagicMock()
    mock_response.status_code = 404
    mock_get.return_value = mock_response

    # Act
    result = ExchangeRateService.get_exchange_rates("INVALID")

    # Assert
    assert result is None
    captured = capsys.readouterr()
    assert "Failed to retrieve Exchange rates. Status: 404" in captured.out


@patch("services.exchange_rate_service.requests.get")
def test_get_exchange_rate_network_exception(mock_get, capsys):
    # Arrange
    mock_get.side_effect = requests.RequestException("Connection Timeout")

    # Act
    result = ExchangeRateService.get_exchange_rates("USD")

    # Assert
    assert result is None
    captured = capsys.readouterr()
    assert "Network error updating exchange rates: Connection Timeout" in captured.out


# =====================================================================
# TEST CASES FOR: get_exchange_rate
# =====================================================================

@patch("services.exchange_rate_service.open", new_callable=mock_open, read_data='{"rates": {"GBP": 0.78, "EUR": 0.91}}')
def test_get_exchange_rate_parse_success(mock_file):
    # Act
    rate = ExchangeRateService.get_exchange_rate("USD")

    # Assert
    assert rate == 0.78
    mock_file.assert_called_once_with("exchange_rates.json", "r", encoding="utf-8")


@patch("services.exchange_rate_service.open", new_callable=mock_open, read_data='{"rates": {"EUR": 0.91}}')
def test_get_exchange_rate_missing_gbp_key_fallback(mock_file):
    # Act: Key exists but target sub-key 'GBP' doesn't
    rate = ExchangeRateService.get_exchange_rate("USD")

    # Assert
    assert rate == 1.0


@patch("services.exchange_rate_service.open", side_effect=FileNotFoundError)
def test_get_exchange_rate_file_not_found(mock_file, capsys):
    # Act
    rate = ExchangeRateService.get_exchange_rate("USD")

    # Assert
    assert rate == 1.0
    captured = capsys.readouterr()
    assert "Warning: Could not parse exchange_rates.json" in captured.out


@patch("services.exchange_rate_service.open", new_callable=mock_open, read_data="{ invalid json [ }")
def test_get_exchange_rate_corrupt_json(mock_file, capsys):
    # Act
    rate = ExchangeRateService.get_exchange_rate("USD")

    # Assert
    assert rate == 1.0
    captured = capsys.readouterr()
    assert "Warning: Could not parse exchange_rates.json" in captured.out


@patch("services.exchange_rate_service.open", new_callable=mock_open, read_data='{"wrong_structure": true}')
def test_get_exchange_rate_key_error(mock_file, capsys):
    # Act: Missing the entire 'rates' base key
    rate = ExchangeRateService.get_exchange_rate("USD")

    # Assert
    assert rate == 1.0
    captured = capsys.readouterr()
    assert "Warning: Could not parse exchange_rates.json" in captured.out
