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
        """
        Create an in-memory DuckDB connection and initialize the dataset metadata store.
        
        Sets self.conn to an in-memory DuckDB connection and self.datasets to an empty dictionary for tracking stored dataset metadata.
        """
        self.conn = duckdb.connect(":memory:")
        self.datasets: Dict[str, Dict] = {}  # Metadata about stored datasets
        logger.info("DuckDB manager initialized with in-memory database")

    def store_dataframe(self, chat_id: str, message_group_id: str, df: pd.DataFrame,
                       question: str = "", sql_query: str = "") -> str:
        """
                       Store a Pandas DataFrame in the in-memory DuckDB instance and record metadata for later querying.
                       
                       Stores the DataFrame as a DuckDB table named "ace_<chat_id>_<message_group_id>" with hyphens replaced by underscores, and records metadata including chat_id, message_group_id, question, sql_query, row_count, column_count, columns, dtypes, and created_at.
                       
                       Parameters:
                           chat_id (str): Identifier of the chat associated with the dataset.
                           message_group_id (str): Identifier of the message group associated with the dataset.
                           df (pd.DataFrame): DataFrame to store.
                           question (str): Optional original question associated with the data.
                           sql_query (str): Optional SQL query that produced the DataFrame.
                       
                       Returns:
                           str: The name of the DuckDB table where the DataFrame was stored (format: "ace_<chat_id>_<message_group_id>" with "-" replaced by "_").
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
        Execute a SQL query against stored DuckDB datasets.
        
        If the provided SQL contains no LIMIT clause, a `LIMIT {limit}` clause will be appended to enforce a safety cap.
        
        Parameters:
            sql (str): SQL query to execute.
            limit (int): Maximum number of rows to return when no LIMIT is present in `sql`.
        
        Returns:
            tuple: A pair (result_df, metadata) where `result_df` is a pandas DataFrame of query results and `metadata` is a dict containing `row_count`, `column_count`, `columns`, and `query_executed`.
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
        """
        Retrieve stored metadata for a dataset table by name.
        
        Parameters:
            table_name (str): The DuckDB table name for the dataset (e.g. "ace_<chat_id>_<message_group_id>").
        
        Returns:
            dict or None: Metadata dictionary for the dataset if found (contains keys like `chat_id`, `message_group_id`, `row_count`, `column_count`, `columns`, `dtypes`, `created_at`), or `None` if no matching dataset exists.
        """
        return self.datasets.get(table_name)

    def list_datasets(self) -> List[Dict]:
        """
        Return a list of stored dataset entries with their metadata.
        
        Returns:
            List[Dict]: A list where each element is a dictionary containing:
                - "table_name" (str): The DuckDB table name for the dataset.
                - other keys: Metadata recorded when the dataset was stored (e.g., "chat_id", "message_group_id", "question", "sql_query", "row_count", "column_count", "columns", "dtypes", "created_at").
        """
        return [
            {
                "table_name": table_name,
                **metadata
            }
            for table_name, metadata in self.datasets.items()
        ]

    def table_exists(self, table_name: str) -> bool:
        """
        Determine whether a stored dataset table exists in the manager.
        
        @returns `True` if a table with the given name is registered, `False` otherwise.
        """
        return table_name in self.datasets

    def get_sample_data(self, table_name: str, limit: int = 10) -> pd.DataFrame:
        """
        Retrieve a small sample of rows from a stored table.
        
        Parameters:
            table_name (str): Name of the DuckDB table to sample.
            limit (int): Maximum number of rows to return.
        
        Returns:
            pd.DataFrame: A DataFrame containing up to `limit` rows from the table.
        
        Raises:
            ValueError: If the specified `table_name` does not exist.
        """
        if not self.table_exists(table_name):
            raise ValueError(f"Table '{table_name}' not found")

        return self.conn.execute(f"SELECT * FROM {table_name} LIMIT {limit}").fetchdf()

    def cleanup_old_datasets(self, max_age_minutes: int = 60):
        """
        Remove stored DuckDB tables and their metadata that are older than the specified age.
        
        Parameters:
            max_age_minutes (int): Age threshold in minutes; datasets older than this value will be dropped and their metadata removed. Defaults to 60.
        """
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