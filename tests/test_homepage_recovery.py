import pytest
from app import create_app, db
from models.user import User
import routes.main as main_module
from routes.main import ensure_core_database_schema
from unittest.mock import patch, MagicMock


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
    """Verify that repeated successful initialization remains idempotent."""
    with app.app_context():
        main_module._CORE_SCHEMA_INITIALIZED = False
        result1 = ensure_core_database_schema()
        assert result1 is True
        assert main_module._CORE_SCHEMA_INITIALIZED is True

        # Second and third calls return True immediately via cache flag
        assert ensure_core_database_schema() is True
        assert ensure_core_database_schema() is True


def test_schema_initialization_success_sets_flag(app):
    """Verify that successful schema initialization sets _CORE_SCHEMA_INITIALIZED to True."""
    with app.app_context():
        main_module._CORE_SCHEMA_INITIALIZED = False
        res = ensure_core_database_schema()
        assert res is True
        assert main_module._CORE_SCHEMA_INITIALIZED is True


def test_schema_initialization_failure_does_not_set_flag(app):
    """Verify that if a required schema operation fails, _CORE_SCHEMA_INITIALIZED remains False."""
    with app.app_context():
        main_module._CORE_SCHEMA_INITIALIZED = False
        # Simulate failure in partner table check
        with patch('models.partner.Partner.__table__.create', side_effect=Exception("Simulated lock timeout")):
            # Simulate table not existing to trigger the create call
            with patch('sqlalchemy.inspect') as mock_inspect:
                mock_inst = MagicMock()
                mock_inst.get_table_names.return_value = ['users', 'money_transactions']
                mock_inst.get_columns.return_value = [{'name': 'email_verified'}, {'name': 'partner_id'}]
                mock_inspect.return_value = mock_inst

                res = ensure_core_database_schema()
                assert res is False
                assert main_module._CORE_SCHEMA_INITIALIZED is False


def test_schema_initialization_retry_after_failure(app):
    """Verify that subsequent retry succeeds after a temporary failure and sets the flag."""
    with app.app_context():
        main_module._CORE_SCHEMA_INITIALIZED = False

        # Attempt 1 fails
        with patch('sqlalchemy.inspect', side_effect=Exception("Database temporarily unavailable")):
            res1 = ensure_core_database_schema()
            assert res1 is False
            assert main_module._CORE_SCHEMA_INITIALIZED is False

        # Attempt 2 (DB recovered): succeeds and sets flag
        res2 = ensure_core_database_schema()
        assert res2 is True
        assert main_module._CORE_SCHEMA_INITIALIZED is True


def test_load_user_resilience_on_database_error(app, client):
    """Verify that load_user does not crash the request with 500 when database throws an exception."""
    with patch('app.db.session.get', side_effect=Exception("Simulated DB connection failure")):
        with client.session_transaction() as sess:
            sess['_user_id'] = "999"

        # The homepage should still return 200 rather than crashing with 500
        response = client.get('/')
        assert response.status_code == 200


def test_load_user_logs_database_error(app):
    """Verify that load_user logs database errors with user_id and exception details."""
    with app.test_request_context():
        from flask_login import current_user
        # Find load_user function registered in login_manager
        loader_fn = app.login_manager._user_callback
        assert loader_fn is not None

        with patch('app.db.session.get', side_effect=Exception("Connection dropped by database")):
            with patch.object(app.logger, 'error') as mock_logger_error:
                result = loader_fn("456")
                assert result is None
                mock_logger_error.assert_called_once()
                log_msg = mock_logger_error.call_args[0][0]
                assert "user_id=456" in log_msg
                assert "Connection dropped by database" in log_msg


def test_load_user_distinguishes_invalid_id(app):
    """Verify that load_user handles invalid non-integer user IDs without treating them as DB errors."""
    with app.test_request_context():
        loader_fn = app.login_manager._user_callback
        assert loader_fn is not None

        with patch.object(app.logger, 'error') as mock_logger_error:
            result = loader_fn("invalid-uuid-string")
            assert result is None
            # Database error should not be logged for invalid format
            mock_logger_error.assert_not_called()
