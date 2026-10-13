import pytest

from fastapi import FastAPI, HTTPException, status
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, AsyncMock

# Import your router and dependencies
# Adjust these import paths based on your actual project structure
from routers.users import router, get_db_service, get_auth_service
from services.authorization_service import authorize

# Setup a dummy FastAPI app to test the router in isolation
app = FastAPI()
app.include_router(router)
@pytest.fixture
def client(mock_db):
    """Fixture to provide a TestClient with overridden dependencies."""
    # Override the DB dependency to return our mock
    app.dependency_overrides[get_db_service] = lambda: mock_db
    
        # Default override for authorize (simulating a valid authenticated user)
    app.dependency_overrides[authorize] = lambda: {"username": "admin", "scopes": []}
    
    with TestClient(app) as test_client:
        yield test_client
        
    # Clear overrides after each test case
    app.dependency_overrides.clear()
    
@pytest.fixture
def mock_db():
    """Fixture to provide a mocked DatabaseService."""
    return MagicMock()

@pytest.fixture
def mock_auth_service():
    """Fixture to provide a mocked AuthorizationService."""
    mock = MagicMock()
    # If create_access_token is async, mock it using AsyncMock
    mock.create_access_token = AsyncMock() 
    return mock


# --- TEST CASES FOR: POST /v1/users (add_user) ---

def test_add_user_success(client, mock_db):
    # Arrange
    user_payload = {
        "username": "newuser@example.com",  # Fixed: Must be a valid email format
        "password": "securepassword123",
        "scopes": ["view", "add"]            # Fixed: Must be items in ALLOWED_SCOPES
    }
    
    # Mocking the return value matching your updated inputs
    mock_db.register_user.return_value = {
        "username": "newuser@example.com", 
        "scopes": ["view", "add"]
    }

    # Act
    response = client.post("/v1/users/", json=user_payload)

    # Assert
    assert response.status_code == status.HTTP_201_CREATED
    assert response.json() == {"username": "newuser@example.com", "scopes": ["view", "add"]}
    
    # Note: Pydantic converts the incoming password string into a SecretStr object inside the route.
    # Depending on how db.register_user extracts it, assert against the mock call parameters.
    mock_db.register_user.assert_called_once()

# --- TEST CASES FOR: DELETE /v1/users/{username} (delete_user) ---

def test_delete_user_success(client, mock_db):
    # Arrange
    username_to_delete = "testuser"
    mock_db.get_user.return_value = {"username": username_to_delete} # User exists

    # Act
    response = client.delete(f"/v1/users/{username_to_delete}")

    # Assert
    assert response.status_code == status.HTTP_204_NO_CONTENT
    mock_db.get_user.assert_called_once_with(username_to_delete)
    mock_db.delete_user.assert_called_once_with(username_to_delete)


def test_delete_user_not_found(client, mock_db):
    # Arrange
    username_to_delete = "nonexistent"
    mock_db.get_user.return_value = None # User does not exist

    # Act
    response = client.delete(f"/v1/users/{username_to_delete}")

    # Assert
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json()["detail"] == f"The user '{username_to_delete}' does not exist."
    mock_db.delete_user.assert_not_called()


def test_delete_user_unauthorized(client):
    # Arrange: Override authorize dependency to simulate auth failure/missing credentials
    def mock_authorize_fail():
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    
    app.dependency_overrides[authorize] = mock_authorize_fail

    # Act
    response = client.delete("/v1/users/testuser")

    # Assert
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


# --- TEST CASES FOR: PUT /v1/users/{username} (update_user_password) ---

def test_update_password_self_success(client, mock_db):
    # Arrange: Target username must be a valid email format
    username_to_update = "johndoe@example.com"
    app.dependency_overrides[authorize] = lambda: {"username": username_to_update, "scopes": ["view"]}
    update_payload = {"password": "newsecurepassword11"}
    
    mock_db.get_user.return_value = {"username": username_to_update}

    # Act
    response = client.put(f"/v1/users/{username_to_update}", json=update_payload)

    # Assert
    assert response.status_code == status.HTTP_200_OK
    mock_db.update_user_password.assert_called_once_with(username_to_update, "newsecurepassword11")


def test_update_password_as_admin_success(client, mock_db):
    # Arrange: Admin updates another user's email-formatted username
    app.dependency_overrides[authorize] = lambda: {"username": "admin_user@example.com", "scopes": ["admin"]}
    username_to_update = "targetuser@example.com"
    update_payload = {"password": "adminresetpassword!"}
    
    mock_db.get_user.return_value = {"username": username_to_update}

    # Act
    response = client.put(f"/v1/users/{username_to_update}", json=update_payload)

    # Assert
    assert response.status_code == status.HTTP_200_OK
    mock_db.update_user_password.assert_called_once_with(username_to_update, "adminresetpassword!")


def test_update_password_forbidden_mismatch(client, mock_db):
    # Arrange: Regular user attempts to change someone else's password
    app.dependency_overrides[authorize] = lambda: {"username": "attacker@example.com", "scopes": ["view"]}
    username_to_update = "victim_user@example.com"
    update_payload = {"password": "hackedpassword"}

    # Act
    response = client.put(f"/v1/users/{username_to_update}", json=update_payload)

    # Assert
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.json()["detail"] == "You do not have permission to update this user's password."
    mock_db.update_user_password.assert_not_called()


def test_update_password_user_not_found(client, mock_db):
    # Arrange: Valid permissions but target account doesn't exist
    app.dependency_overrides[authorize] = lambda: {"username": "admin@example.com", "scopes": ["admin"]}
    username_to_update = "nonexistent@example.com"
    update_payload = {"password": "somepassword123"}
    mock_db.get_user.return_value = None

    # Act
    response = client.put(f"/v1/users/{username_to_update}", json=update_payload)

    # Assert
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json()["detail"] == f"The user '{username_to_update}' does not exist."
    mock_db.update_user_password.assert_not_called()
