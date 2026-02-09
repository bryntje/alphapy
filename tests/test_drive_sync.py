"""
Tests for Google Drive sync functionality with Secret Manager integration.

Tests cover:
- Secret Manager fallback to environment variable
- Error handling when Secret Manager is unavailable
- Caching behavior
- Drive client initialization
"""

import pytest
import os
import json
from unittest.mock import Mock, patch, MagicMock
from utils.drive_sync import _ensure_drive, drive
from utils.gcp_secrets import get_secret, clear_cache, _secret_cache


class TestSecretManagerIntegration:
    """Tests for Secret Manager integration in drive_sync."""
    
    @pytest.fixture(autouse=True)
    def reset_drive_global(self):
        """Reset the global drive variable before each test."""
        # Import here to avoid circular imports
        import utils.drive_sync
        utils.drive_sync.drive = None
        clear_cache()
        yield
        utils.drive_sync.drive = None
        clear_cache()
    
    @pytest.fixture
    def mock_credentials_json(self):
        """Sample Google service account credentials JSON."""
        return json.dumps({
            "type": "service_account",
            "project_id": "test-project",
            "private_key_id": "test-key-id",
            "private_key": "-----BEGIN PRIVATE KEY-----\ntest-key\n-----END PRIVATE KEY-----\n",
            "client_email": "test@test-project.iam.gserviceaccount.com",
            "client_id": "123456789",
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/test%40test-project.iam.gserviceaccount.com"
        })
    
    def test_secret_manager_fallback_to_env(self, mock_credentials_json, monkeypatch):
        """Test that drive_sync falls back to environment variable when Secret Manager is unavailable."""
        # Mock config to simulate Secret Manager not configured
        with patch('utils.drive_sync.config') as mock_config:
            mock_config.GOOGLE_PROJECT_ID = None
            mock_config.GOOGLE_SECRET_NAME = "alphapy-google-credentials"
            mock_config.GOOGLE_CREDENTIALS_JSON = mock_credentials_json
            
            # Mock get_secret to return None (Secret Manager unavailable)
            with patch('utils.drive_sync.get_secret', return_value=None):
                # Mock GoogleAuth and GoogleDrive
                with patch('utils.drive_sync.GoogleAuth') as mock_auth:
                    mock_gauth = MagicMock()
                    mock_config.GOOGLE_CREDENTIALS_JSON = mock_credentials_json
                    mock_auth.return_value = mock_gauth
                    
                    with patch('utils.drive_sync.ServiceAccountCredentials') as mock_creds:
                        mock_cred_obj = MagicMock()
                        mock_creds.from_json_keyfile_dict.return_value = mock_cred_obj
                        mock_gauth.credentials = mock_cred_obj
                        
                        with patch('utils.drive_sync.GoogleDrive') as mock_drive_class:
                            mock_drive_instance = MagicMock()
                            mock_drive_class.return_value = mock_drive_instance
                            
                            result = _ensure_drive()
                            
                            # Should use environment variable fallback
                            assert result is not None
                            mock_creds.from_json_keyfile_dict.assert_called_once()
    
    def test_secret_manager_priority(self, mock_credentials_json, monkeypatch):
        """Test that Secret Manager is tried before environment variable."""
        secret_manager_value = mock_credentials_json  # Use valid JSON
        env_value = mock_credentials_json
        
        # Reset drive global
        import utils.drive_sync
        utils.drive_sync.drive = None
        
        with patch('utils.drive_sync.config') as mock_config:
            mock_config.GOOGLE_PROJECT_ID = "test-project"
            mock_config.GOOGLE_SECRET_NAME = "alphapy-google-credentials"
            mock_config.GOOGLE_CREDENTIALS_JSON = env_value
            
            # Mock get_secret to return (value, source) when return_source=True
            with patch('utils.drive_sync.get_secret', return_value=(secret_manager_value, "secret_manager")) as mock_get_secret:
                with patch('utils.drive_sync.GoogleAuth') as mock_auth:
                    mock_gauth = MagicMock()
                    mock_auth.return_value = mock_gauth
                    
                    with patch('utils.drive_sync.ServiceAccountCredentials') as mock_creds:
                        mock_cred_obj = MagicMock()
                        mock_creds.from_json_keyfile_dict.return_value = mock_cred_obj
                        mock_gauth.credentials = mock_cred_obj
                        
                        with patch('utils.drive_sync.GoogleDrive') as mock_drive_class:
                            mock_drive_instance = MagicMock()
                            mock_drive_class.return_value = mock_drive_instance
                            
                            result = _ensure_drive()
                            
                            # Should have called get_secret with Secret Manager config and return_source
                            mock_get_secret.assert_called_once_with(
                                mock_config.GOOGLE_SECRET_NAME,
                                mock_config.GOOGLE_PROJECT_ID,
                                return_source=True,
                            )
                            # Should use Secret Manager value, not env value
                            mock_creds.from_json_keyfile_dict.assert_called_once()
                            # Verify it was called with Secret Manager value (after json.loads)
                            call_args = mock_creds.from_json_keyfile_dict.call_args
                            # json.loads is called on the credentials_json, so we get a dict
                            called_dict = call_args[0][0]
                            expected_dict = json.loads(secret_manager_value)
                            assert called_dict == expected_dict
    
    def test_no_credentials_available(self, monkeypatch):
        """Test that drive_sync returns None when no credentials are available."""
        # Reset drive global
        import utils.drive_sync
        utils.drive_sync.drive = None
        
        with patch('utils.drive_sync.config') as mock_config:
            mock_config.GOOGLE_PROJECT_ID = None
            mock_config.GOOGLE_SECRET_NAME = "alphapy-google-credentials"
            mock_config.GOOGLE_CREDENTIALS_JSON = None
            
            with patch('utils.drive_sync.get_secret', return_value=None):
                result = _ensure_drive()
                assert result is None
    
    def test_invalid_json_credentials(self, monkeypatch):
        """Test error handling for invalid JSON credentials."""
        # Reset drive global
        import utils.drive_sync
        utils.drive_sync.drive = None
        
        with patch('utils.drive_sync.config') as mock_config:
            mock_config.GOOGLE_PROJECT_ID = None
            mock_config.GOOGLE_SECRET_NAME = "alphapy-google-credentials"
            mock_config.GOOGLE_CREDENTIALS_JSON = "invalid-json"
            
            with patch('utils.drive_sync.get_secret', return_value=None):
                result = _ensure_drive()
                # Should return None due to JSON decode error
                assert result is None


class TestGCPSecretsUtility:
    """Tests for GCP secrets utility functions."""
    
    @pytest.fixture(autouse=True)
    def clear_cache_before_test(self):
        """Clear cache before each test."""
        clear_cache()
        yield
        clear_cache()
    
    def test_cache_storage_and_retrieval(self, monkeypatch):
        """Test that secrets are cached and retrieved correctly."""
        secret_name = "test-secret"
        secret_value = "test-value"
        
        # Mock Secret Manager to return a value
        with patch('utils.gcp_secrets._fetch_from_secret_manager', return_value=secret_value):
            with patch('utils.gcp_secrets.config') as mock_config:
                mock_config.GOOGLE_PROJECT_ID = "test-project"
                
                # First call should fetch from Secret Manager
                result1 = get_secret(secret_name)
                assert result1 == secret_value
                assert secret_name in _secret_cache
                
                # Second call should use cache
                with patch('utils.gcp_secrets._fetch_from_secret_manager') as mock_fetch:
                    result2 = get_secret(secret_name)
                    assert result2 == secret_value
                    # Should not call Secret Manager again
                    mock_fetch.assert_not_called()
    
    def test_fallback_to_environment_variable(self, monkeypatch):
        """Test fallback to environment variable when Secret Manager is unavailable."""
        secret_name = "test-secret"
        # get_secret converts secret_name to uppercase and replaces - with _
        env_var_name = "TEST_SECRET"
        env_value = "env-value"
        
        monkeypatch.setenv(env_var_name, env_value)
        
        with patch('utils.gcp_secrets.config') as mock_config:
            mock_config.GOOGLE_PROJECT_ID = None
            
            # Mock _fetch_from_secret_manager to return None
            with patch('utils.gcp_secrets._fetch_from_secret_manager', return_value=None):
                # get_secret looks for env var with uppercase and underscores
                # secret_name "test-secret" becomes "TEST_SECRET"
                result = get_secret(secret_name)
                # Should find the env var since it matches the converted name
                assert result == env_value
    
    def test_secret_manager_error_handling(self, monkeypatch):
        """Test that Secret Manager errors are handled gracefully."""
        secret_name = "test-secret"
        
        with patch('utils.gcp_secrets.config') as mock_config:
            mock_config.GOOGLE_PROJECT_ID = "test-project"
            
            # Mock Secret Manager to raise an exception
            def mock_fetch(*args, **kwargs):
                raise Exception("Secret Manager error")
            
            with patch('utils.gcp_secrets._fetch_from_secret_manager', side_effect=mock_fetch):
                result = get_secret(secret_name)
                # Should return None on error, not raise exception
                assert result is None
    
    def test_clear_cache(self, monkeypatch):
        """Test cache clearing functionality."""
        secret_name = "test-secret"
        secret_value = "test-value"
        
        # Add to cache manually
        import time
        from utils.gcp_secrets import _store_in_cache
        _store_in_cache(secret_name, secret_value)
        assert secret_name in _secret_cache
        
        # Clear specific secret
        clear_cache(secret_name)
        assert secret_name not in _secret_cache
        
        # Add multiple secrets
        _store_in_cache("secret1", "value1")
        _store_in_cache("secret2", "value2")
        assert len(_secret_cache) == 2
        
        # Clear all
        clear_cache()
        assert len(_secret_cache) == 0
