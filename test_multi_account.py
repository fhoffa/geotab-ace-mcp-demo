#!/usr/bin/env python3
"""
Tests for multi-account support in Geotab ACE.
"""

import os
import pytest
from unittest.mock import patch

from geotab_ace import AccountManager, GeotabCredentials, AuthenticationError


class TestAccountManagerMultiAccount:
    """Tests for multi-account configuration."""

    def test_load_multiple_accounts(self):
        """Test loading multiple accounts from environment variables."""
        env_vars = {
            "GEOTAB_ACCOUNT_1_NAME": "fleet1",
            "GEOTAB_ACCOUNT_1_USERNAME": "user1@example.com",
            "GEOTAB_ACCOUNT_1_PASSWORD": "pass1",
            "GEOTAB_ACCOUNT_1_DATABASE": "db1",
            "GEOTAB_ACCOUNT_2_NAME": "fleet2",
            "GEOTAB_ACCOUNT_2_USERNAME": "user2@example.com",
            "GEOTAB_ACCOUNT_2_PASSWORD": "pass2",
            "GEOTAB_ACCOUNT_2_DATABASE": "db2",
        }

        with patch.dict(os.environ, env_vars, clear=True):
            mgr = AccountManager()

            assert mgr.account_count() == 2
            assert mgr.has_accounts()

            accounts = mgr.list_accounts()
            assert len(accounts) == 2

            # First account should be default
            assert mgr.get_default_account() == "fleet1"

            # Check account details
            fleet1 = next(a for a in accounts if a["name"] == "fleet1")
            assert fleet1["database"] == "db1"
            assert fleet1["username"] == "user1@example.com"
            assert fleet1["is_default"] is True

            fleet2 = next(a for a in accounts if a["name"] == "fleet2")
            assert fleet2["database"] == "db2"
            assert fleet2["is_default"] is False

    def test_get_client_for_specific_account(self):
        """Test getting client for a specific account."""
        env_vars = {
            "GEOTAB_ACCOUNT_1_NAME": "fleet1",
            "GEOTAB_ACCOUNT_1_USERNAME": "user1@example.com",
            "GEOTAB_ACCOUNT_1_PASSWORD": "pass1",
            "GEOTAB_ACCOUNT_1_DATABASE": "db1",
            "GEOTAB_ACCOUNT_2_NAME": "fleet2",
            "GEOTAB_ACCOUNT_2_USERNAME": "user2@example.com",
            "GEOTAB_ACCOUNT_2_PASSWORD": "pass2",
            "GEOTAB_ACCOUNT_2_DATABASE": "db2",
        }

        with patch.dict(os.environ, env_vars, clear=True):
            mgr = AccountManager()

            # Get client for fleet2
            client = mgr.get_client("fleet2")
            assert client.credentials.database == "db2"
            assert client.credentials.username == "user2@example.com"

    def test_get_client_default_account(self):
        """Test getting client without specifying account uses default."""
        env_vars = {
            "GEOTAB_ACCOUNT_1_NAME": "fleet1",
            "GEOTAB_ACCOUNT_1_USERNAME": "user1@example.com",
            "GEOTAB_ACCOUNT_1_PASSWORD": "pass1",
            "GEOTAB_ACCOUNT_1_DATABASE": "db1",
        }

        with patch.dict(os.environ, env_vars, clear=True):
            mgr = AccountManager()

            # Get client without specifying account
            client = mgr.get_client()
            assert client.credentials.database == "db1"

    def test_client_caching(self):
        """Test that clients are cached and reused."""
        env_vars = {
            "GEOTAB_ACCOUNT_1_NAME": "fleet1",
            "GEOTAB_ACCOUNT_1_USERNAME": "user1@example.com",
            "GEOTAB_ACCOUNT_1_PASSWORD": "pass1",
            "GEOTAB_ACCOUNT_1_DATABASE": "db1",
        }

        with patch.dict(os.environ, env_vars, clear=True):
            mgr = AccountManager()

            client1 = mgr.get_client("fleet1")
            client2 = mgr.get_client("fleet1")

            # Should be the same instance
            assert client1 is client2

    def test_different_accounts_different_clients(self):
        """Test that different accounts get different clients."""
        env_vars = {
            "GEOTAB_ACCOUNT_1_NAME": "fleet1",
            "GEOTAB_ACCOUNT_1_USERNAME": "user1@example.com",
            "GEOTAB_ACCOUNT_1_PASSWORD": "pass1",
            "GEOTAB_ACCOUNT_1_DATABASE": "db1",
            "GEOTAB_ACCOUNT_2_NAME": "fleet2",
            "GEOTAB_ACCOUNT_2_USERNAME": "user2@example.com",
            "GEOTAB_ACCOUNT_2_PASSWORD": "pass2",
            "GEOTAB_ACCOUNT_2_DATABASE": "db2",
        }

        with patch.dict(os.environ, env_vars, clear=True):
            mgr = AccountManager()

            client1 = mgr.get_client("fleet1")
            client2 = mgr.get_client("fleet2")

            # Should be different instances
            assert client1 is not client2
            assert client1.credentials.database == "db1"
            assert client2.credentials.database == "db2"

    def test_invalid_account_error(self):
        """Test error when requesting non-existent account."""
        env_vars = {
            "GEOTAB_ACCOUNT_1_NAME": "fleet1",
            "GEOTAB_ACCOUNT_1_USERNAME": "user1@example.com",
            "GEOTAB_ACCOUNT_1_PASSWORD": "pass1",
            "GEOTAB_ACCOUNT_1_DATABASE": "db1",
        }

        with patch.dict(os.environ, env_vars, clear=True):
            mgr = AccountManager()

            with pytest.raises(AuthenticationError) as exc_info:
                mgr.get_client("nonexistent")

            assert "nonexistent" in str(exc_info.value)
            assert "fleet1" in str(exc_info.value)

    def test_set_default_account(self):
        """Test changing the default account."""
        env_vars = {
            "GEOTAB_ACCOUNT_1_NAME": "fleet1",
            "GEOTAB_ACCOUNT_1_USERNAME": "user1@example.com",
            "GEOTAB_ACCOUNT_1_PASSWORD": "pass1",
            "GEOTAB_ACCOUNT_1_DATABASE": "db1",
            "GEOTAB_ACCOUNT_2_NAME": "fleet2",
            "GEOTAB_ACCOUNT_2_USERNAME": "user2@example.com",
            "GEOTAB_ACCOUNT_2_PASSWORD": "pass2",
            "GEOTAB_ACCOUNT_2_DATABASE": "db2",
        }

        with patch.dict(os.environ, env_vars, clear=True):
            mgr = AccountManager()

            assert mgr.get_default_account() == "fleet1"

            mgr.set_default_account("fleet2")
            assert mgr.get_default_account() == "fleet2"

            # Now default client should be fleet2
            client = mgr.get_client()
            assert client.credentials.database == "db2"

    def test_set_invalid_default_account(self):
        """Test error when setting non-existent default account."""
        env_vars = {
            "GEOTAB_ACCOUNT_1_NAME": "fleet1",
            "GEOTAB_ACCOUNT_1_USERNAME": "user1@example.com",
            "GEOTAB_ACCOUNT_1_PASSWORD": "pass1",
            "GEOTAB_ACCOUNT_1_DATABASE": "db1",
        }

        with patch.dict(os.environ, env_vars, clear=True):
            mgr = AccountManager()

            with pytest.raises(AuthenticationError):
                mgr.set_default_account("nonexistent")

    def test_skip_incomplete_accounts(self):
        """Test that accounts with missing credentials are skipped."""
        env_vars = {
            "GEOTAB_ACCOUNT_1_NAME": "fleet1",
            "GEOTAB_ACCOUNT_1_USERNAME": "user1@example.com",
            # Missing password and database
            "GEOTAB_ACCOUNT_2_NAME": "fleet2",
            "GEOTAB_ACCOUNT_2_USERNAME": "user2@example.com",
            "GEOTAB_ACCOUNT_2_PASSWORD": "pass2",
            "GEOTAB_ACCOUNT_2_DATABASE": "db2",
        }

        with patch.dict(os.environ, env_vars, clear=True):
            mgr = AccountManager()

            # Only fleet2 should be loaded
            assert mgr.account_count() == 1
            assert mgr.get_default_account() == "fleet2"


class TestAccountManagerLegacy:
    """Tests for legacy single-account configuration."""

    def test_load_legacy_single_account(self):
        """Test loading legacy single account configuration."""
        env_vars = {
            "GEOTAB_API_USERNAME": "user@example.com",
            "GEOTAB_API_PASSWORD": "password",
            "GEOTAB_API_DATABASE": "mydb",
        }

        with patch.dict(os.environ, env_vars, clear=True):
            mgr = AccountManager()

            assert mgr.account_count() == 1
            assert mgr.has_accounts()
            assert mgr.get_default_account() == "default"

            accounts = mgr.list_accounts()
            assert len(accounts) == 1
            assert accounts[0]["name"] == "default"
            assert accounts[0]["database"] == "mydb"

    def test_legacy_client_access(self):
        """Test getting client with legacy config."""
        env_vars = {
            "GEOTAB_API_USERNAME": "user@example.com",
            "GEOTAB_API_PASSWORD": "password",
            "GEOTAB_API_DATABASE": "mydb",
        }

        with patch.dict(os.environ, env_vars, clear=True):
            mgr = AccountManager()

            # Can access via "default" name
            client = mgr.get_client("default")
            assert client.credentials.database == "mydb"

            # Can access without name (uses default)
            client = mgr.get_client()
            assert client.credentials.database == "mydb"

    def test_multi_account_takes_priority(self):
        """Test that multi-account config takes priority over legacy."""
        env_vars = {
            # Legacy config
            "GEOTAB_API_USERNAME": "legacy@example.com",
            "GEOTAB_API_PASSWORD": "legacypass",
            "GEOTAB_API_DATABASE": "legacydb",
            # Multi-account config
            "GEOTAB_ACCOUNT_1_NAME": "fleet1",
            "GEOTAB_ACCOUNT_1_USERNAME": "user1@example.com",
            "GEOTAB_ACCOUNT_1_PASSWORD": "pass1",
            "GEOTAB_ACCOUNT_1_DATABASE": "db1",
        }

        with patch.dict(os.environ, env_vars, clear=True):
            mgr = AccountManager()

            # Should load multi-account, not legacy
            assert mgr.account_count() == 1
            assert mgr.get_default_account() == "fleet1"

            client = mgr.get_client()
            assert client.credentials.database == "db1"


class TestAccountManagerNoConfig:
    """Tests for no configuration scenarios."""

    def test_no_accounts_configured(self):
        """Test behavior when no accounts are configured."""
        with patch.dict(os.environ, {}, clear=True):
            mgr = AccountManager()

            assert mgr.account_count() == 0
            assert not mgr.has_accounts()
            assert mgr.get_default_account() is None

    def test_get_client_no_config_error(self):
        """Test error when getting client with no config."""
        with patch.dict(os.environ, {}, clear=True):
            mgr = AccountManager()

            with pytest.raises(AuthenticationError) as exc_info:
                mgr.get_client()

            assert "No accounts configured" in str(exc_info.value)

    def test_incomplete_legacy_config(self):
        """Test that incomplete legacy config is not loaded."""
        env_vars = {
            "GEOTAB_API_USERNAME": "user@example.com",
            # Missing password and database
        }

        with patch.dict(os.environ, env_vars, clear=True):
            mgr = AccountManager()

            assert mgr.account_count() == 0
            assert not mgr.has_accounts()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
