import pytest
from fastapi import FastAPI, Depends
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from services.db_service import Base, DatabaseService
from services.auth_service import AuthService, RoleChecker

# ==========================================
# TEST SETTING INITIALIZATION (In-Memory)
# ==========================================
TEST_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Core initialization blueprint components
app = FastAPI()
auth_service = AuthService()

# Create dummy protected target testing routes
@app.get("/admin-only")
def admin_route(current_user: dict = Depends(RoleChecker(["admin"]))):
    return {"status": "success", "msg": "Welcome, Administrator."}

@app.get("/user-or-admin")
def mixed_route(current_user: dict = Depends(RoleChecker(["admin", "user"]))):
    return {"status": "success", "msg": "Access granted."}


@pytest.fixture(scope="function", autouse=True)
def setup_test_db():
    """Generates structural schemas clean before each test execution run."""
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db_session():
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client():
    return TestClient(app)

# ==========================================
# RBAC EXECUTION BEHAVIOR TESTING RUNNERS
# ==========================================

def test_admin_access_allowed(client, db_session):
    """Verifies that a user with an admin scope can access admin routes."""
    db = DatabaseService(db_session)
    hashed_pw = auth_service.get_password_hash("AdminPass123!")
    db.create_user(username="superadmin", hashed_pw=hashed_pw, roles=["admin"])

    # Generate an active JWT for our admin user
    token_response = auth_service.create_access_token("superadmin", "AdminPass123!")
    token = token_response["access_token"]

    headers = {"Authorization": f"Bearer {token}"}
    response = client.get("/admin-only", headers=headers)
    
    assert response.status_code == 200
    assert response.json()["status"] == "success"


def test_standard_user_blocked_from_admin_route(client, db_session):
    """Verifies that standard users receive a 403 Forbidden response on admin endpoints."""
    db = DatabaseService(db_session)
    hashed_pw = auth_service.get_password_hash("UserPass123!")
    db.create_user(username="regularjoe", hashed_pw=hashed_pw, roles=["user"])

    # Generate token for the non-privileged profile account
    token_response = auth_service.create_access_token("regularjoe", "UserPass123!")
    token = token_response["access_token"]

    headers = {"Authorization": f"Bearer {token}"}
    response = client.get("/admin-only", headers=headers)
    
    # Assert that access is denied with a 403 status code
    assert response.status_code == 403
    assert "Forbidden" in response.json()["detail"]


def test_mixed_clearance_route(client, db_session):
    """Ensures multiple allowed roles are handled correctly."""
    db = DatabaseService(db_session)
    hashed_pw = auth_service.get_password_hash("UserPass123!")
    db.create_user(username="regularjoe", hashed_pw=hashed_pw, roles=["user"])

    token_response = auth_service.create_access_token("regularjoe", "UserPass123!")
    token = token_response["access_token"]

    headers = {"Authorization": f"Bearer {token}"}
    response = client.get("/user-or-admin", headers=headers)
    
    assert response.status_code == 200
    assert response.json()["msg"] == "Access granted."


def test_unauthenticated_request_blocked(client):
    """Verifies requests without an Authorization header are blocked."""
    response = client.get("/admin-only")
    assert response.status_code == 401
