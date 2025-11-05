"""
DuckDB Manager Module

Standalone module for storing and querying large datasets in DuckDB.
This is extracted from geotab_mcp_server.py for easier testing and reusability.
"""

import logging
from datetime import datetime
from typing import Dict, List, Tuple, Optional

import duckdb
import pandas as pd

logger = logging.getLogger(__name__)


class DuckDBManager:
    """
    Manager for storing and querying large datasets in DuckDB.

    When Ace returns large result sets (>1000 rows), instead of sending all data to Claude,
    we load it into DuckDB and provide SQL query capabilities.
    """

    def __init__(self):
        """Initialize in-memory DuckDB connection."""
        self.conn = duckdb.connect(":memory:")
        self.datasets: Dict[str, Dict] = {}  # Metadata about stored datasets
        logger.info("DuckDB manager initialized with in-memory database")

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
        """
        # Create a clean table name
        table_name = f"ace_{chat_id}_{message_group_id}".replace("-", "_")

        # Store the DataFrame as a DuckDB table
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

        Args:
            sql: SQL query to execute
            limit: Maximum rows to return (safety limit)

        Returns:
            Tuple of (DataFrame with results, metadata dict)
        """
        try:
            # Add LIMIT if not present for safety
            sql_upper = sql.upper().strip()
            if "LIMIT" not in sql_upper:
                sql = f"{sql.strip().rstrip(';')} LIMIT {limit}"

            # Execute query
            result_df = self.conn.execute(sql).fetchdf()

            metadata = {
                "row_count": len(result_df),
                "column_count": len(result_df.columns),
                "columns": list(result_df.columns),
                "query_executed": sql
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
        """Get a sample of data from a table."""
        if not self.table_exists(table_name):
            raise ValueError(f"Table '{table_name}' not found")

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
                self.conn.execute(f"DROP TABLE IF EXISTS {table_name}")
                del self.datasets[table_name]
                logger.info(f"Cleaned up old dataset: {table_name}")
            except Exception as e:
                logger.warning(f"Failed to cleanup {table_name}: {e}")
