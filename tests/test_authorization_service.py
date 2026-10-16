import base64
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
import jwt
from fastapi import HTTPException, Request, status
from pydantic import SecretStr

# Ensure the import matches your plural 'services' directory structure
from services.authorization_service import AuthorizationService

# -------------------------------------------------------------------------
# Reusable Fixtures
# -------------------------------------------------------------------------

@pytest.fixture
def auth_service():
    """Initializes the service instance and injects a mock exception handler."""
    # Using a context manager inside the fixture avoids lifecycle runtime issues
    with patch("services.authorization_service.DatabaseService") as mock_db_class:
        mock_db_class.return_value = MagicMock()
        service = AuthorizationService()
    
    def mock_exception_handler(detail, status_code=status.HTTP_401_UNAUTHORIZED, scheme="Bearer"):
        return HTTPException(status_code=status_code, detail=detail)
        
    service.create_auth_exception = MagicMock(side_effect=mock_exception_handler)
    return service

@pytest.fixture
def mock_request():
    """Generates a standard FastAPI Request mock instance."""
    return MagicMock(spec=Request)
# -------------------------------------------------------------------------
# 1. Tests for create_access_token
# -------------------------------------------------------------------------

# -------------------------------------------------------------------------
# 1. Tests for create_access_token
# -------------------------------------------------------------------------

@patch("services.authorization_service.jwt.encode")
def test_create_access_token_success(mock_jwt_encode, auth_service):
    """Test successful JWT generation when valid credentials are provided."""
    # Arrange
    username = "valid_user"
    password = "correct_password"
    mock_user_record = {"username": username, "scopes": ["read", "write"]}
    
    # 1. Mock the user validation method
    auth_service.authenticate_user = MagicMock(return_value=mock_user_record)
    
    # 2. Mock jwt.encode to return a dummy token string instead of calling real crypto logic
    mock_jwt_encode.return_value = "mocked.jwt.token.string"

    # Act
    token = auth_service.create_access_token(username, password)

    # Assert
    assert token == "mocked.jwt.token.string"
    auth_service.authenticate_user.assert_called_once_with(username, password)
    
    # Verify that jwt.encode was called with the correct structural keys
    mock_jwt_encode.assert_called_once()
    called_args, called_kwargs = mock_jwt_encode.call_args
    
    payload = called_args[0]
    assert payload["sub"] == username
    assert "exp" in payload
    assert isinstance(payload["exp"], int)


def test_create_access_token_invalid_credentials(auth_service):
    """Test that providing an invalid username/password raises an HTTP exception."""
    # Arrange
    username = "invalid_user"
    password = "wrong_password"
    auth_service.authenticate_user = MagicMock(return_value=None)

    # Act & Assert
    with pytest.raises(HTTPException) as exc_info:
        auth_service.create_access_token(username, password)
        
    assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
    assert "Failed to create JWT Token" in exc_info.value.detail

    
# -------------------------------------------------------------------------
# 2. Edge Cases & Scheme Level Valuations
# -------------------------------------------------------------------------

@pytest.mark.asyncio(loop_scope="function")
async def test_authenticate_no_authorization_header(auth_service, mock_request):
    mock_request.headers.get.return_value = None
    with pytest.raises(HTTPException) as exc_info:
        await auth_service.authenticate(mock_request)
    assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
    assert "No Authorization Header" in exc_info.value.detail

@pytest.mark.asyncio(loop_scope="function")
async def test_authenticate_unsupported_scheme(auth_service, mock_request):
    mock_request.headers.get.return_value = "Digest analyticaltokenstring123"
    with pytest.raises(HTTPException) as exc_info:
        await auth_service.authenticate(mock_request)
    assert "Unsupported authentication scheme" in exc_info.value.detail

# -------------------------------------------------------------------------
# 3. Case A: Basic Authentication Paths
# -------------------------------------------------------------------------

@pytest.mark.asyncio(loop_scope="function")
async def test_authenticate_basic_success(auth_service, mock_request):
    encoded_creds = "dXNlcjE6cGFzc3dvcmQxMjM="
    mock_request.headers.get.return_value = f"Basic {encoded_creds}"
    auth_service.authenticate_user = MagicMock(
        return_value={"username": "user1", "scopes": ["read", "write"]}
    )
    result = await auth_service.authenticate(mock_request)
    assert result["username"] == "user1"
    assert result["auth_method"] == "basic"
    auth_service.authenticate_user.assert_called_once_with("user1", SecretStr("password123"))

@pytest.mark.asyncio(loop_scope="function")
async def test_authenticate_basic_missing_delimiter(auth_service, mock_request):
    encoded_creds = "bm9jb2xvbmRlbGltaXRlcg=="
    mock_request.headers.get.return_value = f"Basic {encoded_creds}"
    with pytest.raises(HTTPException) as exc_info:
        await auth_service.authenticate(mock_request)
    assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
    assert "Missing delimiter from Base64 encoded credentials" in exc_info.value.detail

@pytest.mark.asyncio(loop_scope="function")
async def test_authenticate_basic_failed_credentials(auth_service, mock_request):
    encoded_creds = "dXNlcjE6cGFzc3dvcmQxMjM="
    mock_request.headers.get.return_value = f"Basic {encoded_creds}"
    auth_service.authenticate_user = MagicMock(return_value=None)
    with pytest.raises(HTTPException) as exc_info:
        await auth_service.authenticate(mock_request)
    assert "Failed authentication" in exc_info.value.detail

# -------------------------------------------------------------------------
# 4. Case B: Bearer Token (JWT) Paths
# -------------------------------------------------------------------------

@pytest.mark.asyncio(loop_scope="function")
@patch("services.authorization_service.jwt.decode")
async def test_authenticate_bearer_jwt_success(mock_jwt_decode, auth_service, mock_request):
    mock_request.headers.get.return_value = "Bearer valid.jwt.token"
    mock_jwt_decode.return_value = {
        "sub": "test_user",
        "scopes": ["add", "update"],
    }
    result = await auth_service.authenticate(mock_request)
    assert result["username"] == "test_user"
    assert result["auth_method"] == "bearer"
    assert "add" in result["scopes"]

@pytest.mark.asyncio(loop_scope="function")
@patch("services.authorization_service.jwt.decode")
async def test_authenticate_bearer_missing_sub(mock_jwt_decode, auth_service, mock_request):
    mock_request.headers.get.return_value = "Bearer valid.jwt.token"
    mock_jwt_decode.return_value = {"scopes": ["add"]}
    with pytest.raises(HTTPException) as exc_info:
        await auth_service.authenticate(mock_request)
    assert "Could not get the username from the JWT Token" in exc_info.value.detail

@pytest.mark.asyncio(loop_scope="function")
@patch("services.authorization_service.jwt.decode")
async def test_authenticate_bearer_expired_token(mock_jwt_decode, auth_service, mock_request):
    mock_request.headers.get.return_value = "Bearer expired.jwt.token"
    mock_jwt_decode.side_effect = jwt.exceptions.ExpiredSignatureError("Signature has expired")
    with pytest.raises(HTTPException) as exc_info:
        await auth_service.authenticate(mock_request)
    assert "JWT Token Error" in exc_info.value.detail

@pytest.mark.asyncio(loop_scope="function")
@patch("services.authorization_service.jwt.decode")
async def test_authenticate_bearer_malformed_jwt(mock_jwt_decode, auth_service, mock_request):
    mock_request.headers.get.return_value = "Bearer broken.jwt.token"
    mock_jwt_decode.side_effect = jwt.PyJWTError("Invalid signature token structure")
    with pytest.raises(HTTPException) as exc_info:
        await auth_service.authenticate(mock_request)
    assert "Error parsing the JWT Token" in exc_info.value.detail

# -------------------------------------------------------------------------
# 5. Tests for Static Methods (get_password_hash & verify_password)
# -------------------------------------------------------------------------

def test_get_password_hash_success():
    """Test that get_password_hash successfully converts a SecretStr into a valid bcrypt string."""
    # Arrange
    plain_password = SecretStr("my_super_secret_password")

    # Act
    hashed_password = AuthorizationService.get_password_hash(plain_password)

    # Assert
    assert isinstance(hashed_password, str)
    assert len(hashed_password) > 0
    # bcyrpt hashes typically start with $2b$ or $2a$
    assert hashed_password.startswith("$2") 


def test_verify_password_integration():
    """Integration test validating that a generated hash successfully verifies against its plain source."""
    # Arrange
    correct_password = SecretStr("correct_pass123")
    wrong_password = SecretStr("incorrect_pass123")

    # Act
    hashed_password = AuthorizationService.get_password_hash(correct_password)

    # Assert
    assert AuthorizationService.verify_password(correct_password, hashed_password) is True
    assert AuthorizationService.verify_password(wrong_password, hashed_password) is False


@patch("services.authorization_service.bcrypt.checkpw")
def test_verify_password_exception_handling(mock_checkpw):
    """Test that verify_password handles internal runtime exceptions cleanly and returns False."""
    # Arrange
    plain_password = SecretStr("password123")
    hashed_password = "$2b$12$dummyhashstringhere..."
    
    # Force bcrypt to throw a runtime exception (e.g., malformed hash string type)
    mock_checkpw.side_effect = Exception("Malformed hash error simulation")

    # Act
    result = AuthorizationService.verify_password(plain_password, hashed_password)

    # Assert
    assert result is False
    mock_checkpw.assert_called_once()
    
# -------------------------------------------------------------------------
# 6. Tests for authorize Method
# -------------------------------------------------------------------------

@pytest.mark.asyncio(loop_scope="function")
async def test_authorize_success_without_portfolio(auth_service, mock_request):
    """Test successful authorization when HTTP method mapping passes and no portfolio check is requested."""
    # Arrange
    mock_request.method = "POST"
    mock_user_context = {"username": "test_user", "scopes": ["add"], "auth_method": "bearer"}
    
    # Mock the internal authenticate dependency method
    auth_service.authenticate = AsyncMock(return_value=mock_user_context)

    # Act
    result = await auth_service.authorize(mock_request)

    # Assert
    assert result == mock_user_context
    auth_service.authenticate.assert_called_once_with(mock_request)


@pytest.mark.asyncio(loop_scope="function")
@pytest.mark.parametrize("http_method, required_scope", [
    ("POST", "add"),
    ("PUT", "update"),
    ("PATCH", "update"),
    ("DELETE", "delete")
])
async def test_authorize_missing_required_scope(auth_service, mock_request, http_method, required_scope):
    """Test that missing the scoped permission for a destructive CRUD verb triggers a 403 Forbidden exception."""
    # Arrange
    mock_request.method = http_method
    mock_user_context = {"username": "test_user", "scopes": ["read"], "auth_method": "bearer"} # Missing the needed scope
    auth_service.authenticate = AsyncMock(return_value=mock_user_context)

    # Act & Assert
    with pytest.raises(HTTPException) as exc_info:
        await auth_service.authorize(mock_request)

    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
    assert f"Required scope '{required_scope}' missing" in exc_info.value.detail


@pytest.mark.asyncio(loop_scope="function")
async def test_authorize_success_with_portfolio_ownership(auth_service, mock_request):
    """Test successful authorization when both scope rules and asset ownership validations pass."""
    # Arrange
    mock_request.method = "DELETE"
    portfolio_id = "portfolio_abc"
    mock_user_context = {"username": "owner_user", "scopes": ["delete"], "auth_method": "bearer"}
    
    auth_service.authenticate = AsyncMock(return_value=mock_user_context)
    # Configure the internal DatabaseService mock to return True for ownership verification
    auth_service.database_service.verify_portfolio_ownership.return_value = True

    # Act
    result = await auth_service.authorize(mock_request, portfolio_id=portfolio_id)

    # Assert
    assert result == mock_user_context
    auth_service.database_service.verify_portfolio_ownership.assert_called_once_with("owner_user", portfolio_id)


@pytest.mark.asyncio(loop_scope="function")
async def test_authorize_failed_portfolio_ownership(auth_service, mock_request):
    """Test that a 403 Forbidden is raised if the database indicates the user does not own the asset resource."""
    # Arrange
    mock_request.method = "PUT"
    portfolio_id = "target_portfolio_123"
    mock_user_context = {"username": "malicious_user", "scopes": ["update"], "auth_method": "bearer"}
    
    auth_service.authenticate = AsyncMock(return_value=mock_user_context)
    # Force the ownership verification path check to fail
    auth_service.database_service.verify_portfolio_ownership.return_value = False

    # Act & Assert
    with pytest.raises(HTTPException) as exc_info:
        await auth_service.authorize(mock_request, portfolio_id=portfolio_id)

    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
    assert "Could not verify the ownership of the Portfolio" in exc_info.value.detail

# -------------------------------------------------------------------------
# 7. Tests for authenticate_user Method
# -------------------------------------------------------------------------
@patch.object(AuthorizationService, "verify_password")
def test_authenticate_user_success(mock_verify_password, auth_service):
    """Test that a valid username and password combination returns the full user document."""
    # Arrange
    username = "test_user"
    raw_password = "correct_password"
    mock_db_user = {
        "username": username,
        "hashed_password": "$2b$12$securehashvalue...",
        "scopes": ["read", "add"]
    }
    
    # Configure DB mock to return the user record
    auth_service.database_service.get_user.return_value = mock_db_user
    # Configure password verification mock to succeed
    mock_verify_password.return_value = True

    # Act
    result = auth_service.authenticate_user(username, raw_password)

    # Assert
    assert result == mock_db_user
    auth_service.database_service.get_user.assert_called_once_with(username)
    mock_verify_password.assert_called_once_with(raw_password, mock_db_user["hashed_password"])


@patch.object(AuthorizationService, "verify_password")
def test_authenticate_user_wrong_password(mock_verify_password, auth_service):
    """Test that a valid username but an incorrect password raises a 401 HTTPException."""
    # Arrange
    username = "test_user"
    raw_password = "wrong_password"
    mock_db_user = {
        "username": username,
        "hashed_password": "$2b$12$securehashvalue...",
        "scopes": ["read"]
    }
    
    auth_service.database_service.get_user.return_value = mock_db_user
    # Configure password verification to fail
    mock_verify_password.return_value = False

    # Act & Assert
    with pytest.raises(HTTPException) as exc_info:
        auth_service.authenticate_user(username, raw_password)

    assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
    assert f"Password verification failed for the User '{username}'" in exc_info.value.detail
    auth_service.database_service.get_user.assert_called_once_with(username)
    mock_verify_password.assert_called_once_with(raw_password, mock_db_user["hashed_password"])


@patch.object(AuthorizationService, "verify_password")
def test_authenticate_user_not_found_in_db(mock_verify_password, auth_service):
    """Test that looking up a non-existent username raises a 401 HTTPException immediately without checking password."""
    # Arrange
    username = "missing_user"
    raw_password = "any_password"
    
    # Configure DB mock to return None (user not found)
    auth_service.database_service.get_user.return_value = None

    # Act & Assert
    with pytest.raises(HTTPException) as exc_info:
        auth_service.authenticate_user(username, raw_password)

    assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
    assert f"The User '{username}' has not been registered" in exc_info.value.detail
    auth_service.database_service.get_user.assert_called_once_with(username)
    # verify_password should never be run if there is no user database object
    mock_verify_password.assert_not_called()
