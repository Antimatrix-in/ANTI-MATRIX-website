import pytest
from app import create_app, db
from models.user import User
from routes.main import ensure_core_database_schema
from unittest.mock import patch


@pytest.fixture
def app():
    app = create_app('testing')
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


def test_homepage_unauthenticated(client):
    """Verify that unauthenticated visitors can access the homepage successfully."""
    response = client.get('/')
    assert response.status_code == 200
    assert b"ANTI-MATRIX" in response.data or b"anti-matrix" in response.data.lower()


def test_homepage_authenticated_user(app, client):
    """Verify that authenticated users can access the homepage without HTTP 500."""
    with app.app_context():
        user = User(
            name="Test Recover User",
            email="recover_user@antimatrix.co.in",
            role="applicant",
            email_verified=True
        )
        user.set_password("SecurePassword123!")
        db.session.add(user)
        db.session.commit()
        user_id = user.id

    # Simulate logged in session cookie
    with client.session_transaction() as sess:
        sess['_user_id'] = str(user_id)
        sess['_fresh'] = True

    response = client.get('/')
    assert response.status_code == 200


def test_ensure_core_database_schema_idempotence(app):
    """Verify that ensure_core_database_schema runs cleanly and is idempotent."""
    with app.app_context():
        result = ensure_core_database_schema()
        assert result is True
        # Second call returns True immediately via cache flag
        assert ensure_core_database_schema() is True


def test_load_user_resilience_on_database_error(app, client):
    """Verify that load_user does not crash the request with 500 when database throws an exception."""
    with patch('models.user.User.query') as mock_query:
        # Cause an exception during user lookup
        mock_query.get.side_effect = Exception("Simulated DB connection failure")

        with client.session_transaction() as sess:
            sess['_user_id'] = "999"

        # The homepage should still return 200 rather than crashing with 500
        response = client.get('/')
        assert response.status_code == 200
