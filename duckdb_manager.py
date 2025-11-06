"""
DuckDB Manager Module

Standalone module for storing and querying large datasets in DuckDB.
This is extracted from geotab_mcp_server.py for easier testing and reusability.
"""

import logging
import re
from datetime import datetime
from typing import Dict, List, Tuple, Optional

import duckdb
import pandas as pd

logger = logging.getLogger(__name__)


class DuckDBManager:
    """
    Manager for storing and querying large datasets in DuckDB.

    When Ace returns large result sets (>200 rows), instead of sending all data to Claude,
    we load it into DuckDB and provide SQL query capabilities.
    """

    # Regex for validating table names (alphanumeric and underscores only)
    TABLE_NAME_PATTERN = re.compile(r'^ace_[a-zA-Z0-9_]+$')

    # Regex for detecting LIMIT clause with word boundaries
    LIMIT_PATTERN = re.compile(r'\bLIMIT\b', re.IGNORECASE)

    # Dangerous SQL keywords that should not be allowed in queries
    DANGEROUS_KEYWORDS = [
        'DROP', 'DELETE', 'TRUNCATE', 'ALTER', 'CREATE',
        'INSERT', 'UPDATE', 'GRANT', 'REVOKE'
    ]

    def __init__(self):
        """Initialize in-memory DuckDB connection."""
        self.conn = duckdb.connect(":memory:")
        self.datasets: Dict[str, Dict] = {}  # Metadata about stored datasets
        logger.info("DuckDB manager initialized with in-memory database")

    def _sanitize_identifier(self, value: str) -> str:
        """
        Sanitize an identifier (table name, column name) for safe SQL usage.

        Args:
            value: The identifier to sanitize

        Returns:
            Sanitized identifier safe for SQL queries

        Raises:
            ValueError: If identifier contains invalid characters
        """
        # Remove any characters that are not alphanumeric or underscore
        sanitized = re.sub(r'[^a-zA-Z0-9_]', '_', value)

        # Ensure it doesn't start with a number
        if sanitized and sanitized[0].isdigit():
            sanitized = '_' + sanitized

        return sanitized

    def _validate_table_name(self, table_name: str) -> None:
        """
        Validate that a table name is safe and follows expected format.

        Args:
            table_name: The table name to validate

        Raises:
            ValueError: If table name is invalid or potentially malicious
        """
        if not self.TABLE_NAME_PATTERN.match(table_name):
            raise ValueError(
                f"Invalid table name: '{table_name}'. "
                f"Table names must match pattern: ace_[a-zA-Z0-9_]+"
            )

    def _validate_sql_query(self, sql: str) -> None:
        """
        Validate that a SQL query is safe for execution.

        Allows SELECT statements and CTEs (WITH...SELECT).
        Blocks dangerous operations like DROP, DELETE, UPDATE.

        Args:
            sql: The SQL query to validate

        Raises:
            ValueError: If query contains dangerous operations
        """
        # Convert to uppercase for case-insensitive checking
        sql_upper = sql.upper().strip()

        # Must start with SELECT or WITH (for CTEs)
        if not (sql_upper.startswith('SELECT') or sql_upper.startswith('WITH')):
            raise ValueError("Only SELECT queries and CTEs (WITH...SELECT) are allowed")

        # Check for dangerous keywords
        for keyword in self.DANGEROUS_KEYWORDS:
            # Use word boundary to avoid false positives
            pattern = re.compile(r'\b' + re.escape(keyword) + r'\b', re.IGNORECASE)
            if pattern.search(sql):
                raise ValueError(f"Dangerous SQL keyword detected: {keyword}")

    def store_dataframe(self, chat_id: str, message_group_id: str, df: pd.DataFrame,
                       question: str = "", sql_query: str = "") -> str:
        """
        Store a DataFrame in DuckDB for querying.

        Args:
            chat_id: Chat ID from Ace query
            message_group_id: Message group ID from Ace query
            df: DataFrame to store
            question: Original question asked
            sql_query: SQL query that generated this data

        Returns:
            Table name where data is stored

        Raises:
            ValueError: If table name cannot be safely created
        """
        # Sanitize identifiers to prevent SQL injection
        safe_chat_id = self._sanitize_identifier(chat_id)
        safe_msg_id = self._sanitize_identifier(message_group_id)

        # Create a clean table name
        table_name = f"ace_{safe_chat_id}_{safe_msg_id}"

        # Validate the final table name
        self._validate_table_name(table_name)

        # Store the DataFrame as a DuckDB table
        # Using parameterized approach with pandas DataFrame directly
        self.conn.execute(f"CREATE OR REPLACE TABLE {table_name} AS SELECT * FROM df")

        # Store metadata
        self.datasets[table_name] = {
            "chat_id": chat_id,
            "message_group_id": message_group_id,
            "question": question,
            "sql_query": sql_query,
            "row_count": len(df),
            "column_count": len(df.columns),
            "columns": list(df.columns),
            "dtypes": {col: str(dtype) for col, dtype in df.dtypes.items()},
            "created_at": datetime.now().isoformat()
        }

        logger.info(f"Stored {len(df)} rows in DuckDB table '{table_name}'")
        return table_name

    def query(self, sql: str, limit: int = 1000) -> Tuple[pd.DataFrame, Dict]:
        """
        Execute a SQL query on stored datasets.

        Only SELECT queries and CTEs are allowed for safety. Dangerous operations
        like DROP, DELETE, UPDATE are blocked.

        The safety limit is always enforced regardless of user-supplied LIMIT clauses.
        If the user supplies a LIMIT higher than the safety limit, it will be capped.

        Args:
            sql: SQL query to execute (SELECT or WITH...SELECT)
            limit: Maximum rows to return (safety limit, always enforced)

        Returns:
            Tuple of (DataFrame with results, metadata dict)

        Raises:
            ValueError: If query contains dangerous operations
        """
        try:
            # Validate the SQL query for safety
            self._validate_sql_query(sql)

            # Enforce safety limit by wrapping query in a subquery
            # This ensures the limit is always applied regardless of user-supplied LIMIT
            original_sql = sql.strip().rstrip(';')

            # Wrap in subquery to enforce absolute limit
            # This prevents bypass if user supplies their own LIMIT clause
            enforced_sql = f"SELECT * FROM ({original_sql}) AS subquery LIMIT {limit}"

            # Execute query with enforced limit
            result_df = self.conn.execute(enforced_sql).fetchdf()

            metadata = {
                "row_count": len(result_df),
                "column_count": len(result_df.columns),
                "columns": list(result_df.columns),
                "query_executed": enforced_sql,
                "original_query": original_sql
            }

            return result_df, metadata

        except Exception as e:
            logger.error(f"DuckDB query error: {e}")
            raise

    def get_dataset_info(self, table_name: str) -> Optional[Dict]:
        """Get metadata about a stored dataset."""
        return self.datasets.get(table_name)

    def list_datasets(self) -> List[Dict]:
        """List all stored datasets with their metadata."""
        return [
            {
                "table_name": table_name,
                **metadata
            }
            for table_name, metadata in self.datasets.items()
        ]

    def table_exists(self, table_name: str) -> bool:
        """Check if a table exists in DuckDB."""
        return table_name in self.datasets

    def get_sample_data(self, table_name: str, limit: int = 10) -> pd.DataFrame:
        """
        Get a sample of data from a table.

        Args:
            table_name: Name of the table to sample
            limit: Number of rows to return

        Returns:
            DataFrame with sample data

        Raises:
            ValueError: If table doesn't exist or name is invalid
        """
        if not self.table_exists(table_name):
            raise ValueError(f"Table '{table_name}' not found")

        # Validate table name before using in query
        self._validate_table_name(table_name)

        # Safe to use table_name in query after validation
        return self.conn.execute(f"SELECT * FROM {table_name} LIMIT {limit}").fetchdf()

    def cleanup_old_datasets(self, max_age_minutes: int = 60):
        """Remove datasets older than specified age."""
        current_time = datetime.now()
        tables_to_remove = []

        for table_name, metadata in self.datasets.items():
            created_at = datetime.fromisoformat(metadata["created_at"])
            age_minutes = (current_time - created_at).total_seconds() / 60

            if age_minutes > max_age_minutes:
                tables_to_remove.append(table_name)

        for table_name in tables_to_remove:
            try:
                # Validate table name before dropping
                self._validate_table_name(table_name)
                self.conn.execute(f"DROP TABLE IF EXISTS {table_name}")
                del self.datasets[table_name]
                logger.info(f"Cleaned up old dataset: {table_name}")
            except Exception as e:
                logger.warning(f"Failed to cleanup {table_name}: {e}")
