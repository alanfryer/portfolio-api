

def test_get_portfolio_summary(client, mocker, mock_portfolio_data):
    """Test the GET endpoint fetching the portfolio overview."""
    # Mock the service layer so it returns our test data instead of hitting disk/DB
    mocker.patch("routers.portfolio.get_portfolio_stocks", return_value=mock_portfolio_data)
    
    response = client.get("/portfolio")
    
    assert response.status_code == 200
    assert "assets" in response.json()
    assert len(response.json()["assets"]) == 2

def test_add_asset_invalid_data(client):
    """Test validation errors (schemas.py compliance) when adding a bad asset entry."""
    invalid_payload = {
        "ticker": "INVALID",
        "shares": -5,  # Should fail validation if schemas.py specifies Ge(0)
        "purchase_price": "not-a-number"
    }
    
    response = client.post("/portfolio", json=invalid_payload)
    
    # FastAPI automatically returns 422 Unprocessable Entity for schema validation failures
    assert response.status_code == 422 
