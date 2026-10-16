import base64
import pytest
from unittest.mock import MagicMock, patch
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
# 1. Edge Cases & Scheme Level Valuations
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
# 2. Case A: Basic Authentication Paths
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
# 3. Case B: Bearer Token (JWT) Paths
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