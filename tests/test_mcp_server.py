"""
Tests for the Geotab MCP server using FastMCP in-memory client pattern.

This module tests the MCP server tools using the recommended FastMCP testing
approach with in-memory client fixtures.
"""

import pytest
import os
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import after path modification
from fastmcp.testing import MCPTestClient


@pytest.fixture
def client():
    """
    Create an in-memory test client for the Geotab MCP server.

    This fixture provides a clean client instance for each test,
    following FastMCP best practices for testing.
    """
    # Import here to avoid issues with environment setup
    from geotab_mcp_server import mcp

    return MCPTestClient(mcp)


class TestAccountManagement:
    """Test account listing and management tools."""

    def test_list_accounts_returns_valid_response(self, client):
        """Test that listing accounts returns a valid response."""
        result = client.call_tool("geotab_list_accounts", {})

        assert result is not None
        assert isinstance(result, str)
        # Should mention either configured accounts or instructions
        assert "account" in result.lower() or "configure" in result.lower()

    def test_list_accounts_no_parameters(self, client):
        """Test that list_accounts works without parameters."""
        result = client.call_tool("geotab_list_accounts", {})
        assert result is not None


class TestConnectionTools:
    """Test connection and diagnostic tools."""

    def test_test_connection_with_no_account(self, client):
        """Test connection testing without specifying account."""
        result = client.call_tool("geotab_test_connection", {
            "account": None
        })

        assert result is not None
        assert isinstance(result, str)
        # Should either succeed or provide error message
        assert len(result) > 0

    def test_test_connection_with_invalid_account(self, client):
        """Test connection with non-existent account name."""
        result = client.call_tool("geotab_test_connection", {
            "account": "nonexistent_account_12345"
        })

        assert result is not None
        # Should contain error message about unknown account
        assert "unknown" in result.lower() or "not found" in result.lower() or "error" in result.lower()


class TestQueryTools:
    """Test query execution tools."""

    def test_ask_question_requires_question_parameter(self, client):
        """Test that ask_question requires a question parameter."""
        with pytest.raises(Exception):
            # Missing required 'question' parameter should raise error
            client.call_tool("geotab_ask_question", {})

    def test_ask_question_accepts_valid_input(self, client):
        """Test that ask_question accepts valid parameters."""
        # This may fail with auth errors, but should not fail on validation
        result = client.call_tool("geotab_ask_question", {
            "question": "How many vehicles?",
            "account": None,
            "timeout_seconds": 60
        })

        assert result is not None
        assert isinstance(result, str)

    def test_start_query_async_accepts_valid_input(self, client):
        """Test async query start accepts valid parameters."""
        result = client.call_tool("geotab_start_query_async", {
            "question": "Complex analysis query",
            "account": None
        })

        assert result is not None
        assert isinstance(result, str)

    def test_check_status_requires_tracking_ids(self, client):
        """Test that check_status requires tracking IDs."""
        with pytest.raises(Exception):
            # Missing required parameters should raise error
            client.call_tool("geotab_check_status", {})

    def test_get_results_requires_tracking_ids(self, client):
        """Test that get_results requires tracking IDs."""
        with pytest.raises(Exception):
            # Missing required parameters should raise error
            client.call_tool("geotab_get_results", {})


class TestDuckDBTools:
    """Test DuckDB integration tools."""

    def test_list_cached_datasets(self, client):
        """Test listing cached datasets."""
        result = client.call_tool("geotab_list_cached_datasets", {})

        assert result is not None
        assert isinstance(result, str)
        # Should either list datasets or say none cached
        assert len(result) > 0

    def test_query_duckdb_requires_sql(self, client):
        """Test that DuckDB query requires SQL parameter."""
        with pytest.raises(Exception):
            # Missing required 'sql_query' parameter
            client.call_tool("geotab_query_duckdb", {})

    def test_query_duckdb_rejects_dangerous_sql(self, client):
        """Test that dangerous SQL operations are rejected."""
        dangerous_queries = [
            "DROP TABLE ace_test",
            "DELETE FROM ace_test",
            "UPDATE ace_test SET col = 1",
            "INSERT INTO ace_test VALUES (1)",
            "ALTER TABLE ace_test",
            "CREATE TABLE malicious (id int)",
        ]

        for sql in dangerous_queries:
            result = client.call_tool("geotab_query_duckdb", {
                "sql_query": sql
            })

            # Should contain error message about forbidden operation
            assert "not allowed" in result.lower() or "error" in result.lower() or "forbidden" in result.lower()


class TestMemoryTools:
    """Test persistent memory system tools."""

    def test_remember_requires_parameters(self, client):
        """Test that remember requires both category and content."""
        with pytest.raises(Exception):
            client.call_tool("geotab_remember", {})

    def test_remember_accepts_valid_input(self, client):
        """Test that remember accepts valid parameters."""
        result = client.call_tool("geotab_remember", {
            "category": "test",
            "content": "Test memory content",
            "tags": "test,unit-test",
            "account": None
        })

        assert result is not None
        assert isinstance(result, str)

    def test_recall_with_empty_query(self, client):
        """Test recall with empty query string."""
        result = client.call_tool("geotab_recall", {
            "query": "",
            "category": None,
            "account": None
        })

        # Should handle empty query gracefully
        assert result is not None
        assert isinstance(result, str)

    def test_get_memory_context(self, client):
        """Test getting memory context for session."""
        result = client.call_tool("geotab_get_memory_context", {
            "account": None
        })

        assert result is not None
        assert isinstance(result, str)

    def test_list_memories(self, client):
        """Test listing all memories."""
        result = client.call_tool("geotab_list_memories", {
            "category": None,
            "account": None
        })

        assert result is not None
        assert isinstance(result, str)

    def test_export_memories(self, client):
        """Test exporting memories to JSON."""
        result = client.call_tool("geotab_export_memories", {
            "category": None,
            "account": None
        })

        assert result is not None
        assert isinstance(result, str)
        # Should be valid JSON or error message
        assert len(result) > 0


class TestDebugTools:
    """Test debugging and diagnostic tools."""

    def test_debug_query_requires_question(self, client):
        """Test that debug_query requires a question parameter."""
        with pytest.raises(Exception):
            client.call_tool("geotab_debug_query", {})

    def test_debug_query_accepts_valid_input(self, client):
        """Test that debug_query accepts valid parameters."""
        result = client.call_tool("geotab_debug_query", {
            "question": "Debug test query",
            "account": None
        })

        assert result is not None
        assert isinstance(result, str)


class TestInputValidation:
    """Test input validation and error handling."""

    def test_timeout_validation(self, client):
        """Test that timeout values are validated."""
        # Negative timeout should be handled gracefully
        result = client.call_tool("geotab_ask_question", {
            "question": "Test question",
            "timeout_seconds": -1
        })

        # Should either reject or clamp to valid range
        assert result is not None

    def test_empty_string_validation(self, client):
        """Test handling of empty string inputs."""
        result = client.call_tool("geotab_ask_question", {
            "question": "",
            "account": None
        })

        # Should handle empty questions gracefully
        assert result is not None
        assert isinstance(result, str)

    def test_none_values_are_accepted_for_optional_params(self, client):
        """Test that None is accepted for optional parameters."""
        result = client.call_tool("geotab_ask_question", {
            "question": "Valid question",
            "account": None,  # Optional parameter
            "timeout_seconds": None  # Should use default
        })

        assert result is not None


if __name__ == "__main__":
    # Allow running tests directly with: python tests/test_mcp_server.py
    pytest.main([__file__, "-v"])
