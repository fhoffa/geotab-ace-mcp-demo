"""
DuckDB Manager Module

Standalone module for storing and querying large datasets in DuckDB.
This is extracted from geotab_mcp_server.py for easier testing and reusability.
"""

import json
import logging
import os
import re
from datetime import datetime, timedelta
from pathlib import Path
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
        'INSERT', 'UPDATE', 'GRANT', 'REVOKE',
        'ATTACH', 'DETACH', 'PRAGMA', 'COPY', 'EXPORT', 'IMPORT'
    ]

    def __init__(self, db_path: str = "./data/geotab_cache.duckdb", max_size_mb: int = 500):
        """
        Initialize persistent DuckDB connection with cache management.

        Args:
            db_path: Path to persistent DuckDB file (default: ./data/geotab_cache.duckdb)
            max_size_mb: Maximum cache size in MB before LRU cleanup (default: 500MB)

        Raises:
            ValueError: If db_path contains path traversal attempts or is absolute
        """
        # Validate db_path to prevent path traversal attacks
        # Allow absolute paths but prevent directory traversal with '..'
        if ".." in db_path:
            raise ValueError(
                f"Invalid db_path: '{db_path}'. "
                "Path must not contain '..' directory traversal sequences"
            )

        # Normalize and validate the path
        normalized_path = Path(db_path).resolve()

        # Ensure path doesn't escape to parent directories if it's a relative path
        if not Path(db_path).is_absolute():
            try:
                normalized_path.relative_to(Path.cwd().resolve())
            except ValueError:
                raise ValueError(
                    f"Invalid db_path: '{db_path}'. "
                    "Relative path escapes current directory"
                )

        # Create data directory if it doesn't exist (handle edge case of no directory)
        db_dir = os.path.dirname(db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)

        self.db_path = db_path
        self.max_size_mb = max_size_mb
        self.conn = duckdb.connect(db_path)
        self.datasets: Dict[str, Dict] = {}  # In-memory metadata cache

        # Initialize metadata tracking table
        self._init_metadata_table()

        # Load existing metadata into memory
        self._load_metadata()

        logger.info(f"DuckDB manager initialized with persistent database at {db_path}")
        logger.info(f"Loaded {len(self.datasets)} existing datasets from cache")

    def _init_metadata_table(self):
        """Create metadata tracking table for cache management with proper indexes."""
        # Create metadata table with JSON columns instead of VARCHAR for safety
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS _cache_metadata (
                table_name VARCHAR PRIMARY KEY,
                chat_id VARCHAR,
                message_group_id VARCHAR,
                question VARCHAR,
                sql_query VARCHAR,
                created_at TIMESTAMP,
                last_accessed_at TIMESTAMP,
                access_count INTEGER DEFAULT 0,
                row_count INTEGER,
                column_count INTEGER,
                columns JSON,
                dtypes JSON,
                size_bytes BIGINT
            )
        """)

        # Create indexes for performance on cleanup queries
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_last_accessed
            ON _cache_metadata(last_accessed_at)
        """)

        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_access_count
            ON _cache_metadata(access_count)
        """)

        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_chat_id
            ON _cache_metadata(chat_id)
        """)

        logger.debug("Metadata table and indexes initialized")

    def _load_metadata(self):
        """Load existing metadata from database into memory using safe JSON parsing."""
        try:
            result = self.conn.execute("""
                SELECT table_name, chat_id, message_group_id, question, sql_query,
                       created_at, last_accessed_at, access_count, row_count,
                       column_count, columns, dtypes
                FROM _cache_metadata
            """).fetchall()

            for row in result:
                table_name = row[0]
                # Check if table actually exists using parameterized query
                table_check = self.conn.execute("""
                    SELECT COUNT(*) FROM information_schema.tables
                    WHERE table_name = ?
                """, [table_name]).fetchone()[0]

                if table_check > 0:
                    # Parse JSON columns safely (no eval()!)
                    try:
                        columns = json.loads(row[10]) if row[10] else []
                    except (json.JSONDecodeError, TypeError):
                        # Fallback for old VARCHAR data
                        columns = []
                        logger.warning(f"Failed to parse columns JSON for {table_name}")

                    try:
                        dtypes = json.loads(row[11]) if row[11] else {}
                    except (json.JSONDecodeError, TypeError):
                        # Fallback for old VARCHAR data
                        dtypes = {}
                        logger.warning(f"Failed to parse dtypes JSON for {table_name}")

                    self.datasets[table_name] = {
                        "chat_id": row[1],
                        "message_group_id": row[2],
                        "question": row[3],
                        "sql_query": row[4],
                        "created_at": row[5].isoformat() if row[5] else datetime.now().isoformat(),
                        "last_accessed_at": row[6].isoformat() if row[6] else datetime.now().isoformat(),
                        "access_count": row[7] or 0,
                        "row_count": row[8],
                        "column_count": row[9],
                        "columns": columns,
                        "dtypes": dtypes
                    }
                else:
                    # Orphaned metadata - clean it up using parameterized query
                    self.conn.execute("DELETE FROM _cache_metadata WHERE table_name = ?", [table_name])
                    logger.debug(f"Removed orphaned metadata for {table_name}")

        except Exception as e:
            logger.error(f"Error loading metadata: {e}", exc_info=True)
            raise  # Re-raise to make initialization failures visible

    def _track_access(self, table_name: str):
        """Update last accessed time and increment access counter."""
        try:
            self.conn.execute("""
                UPDATE _cache_metadata
                SET last_accessed_at = CURRENT_TIMESTAMP,
                    access_count = access_count + 1
                WHERE table_name = ?
            """, [table_name])

            # Update in-memory cache
            if table_name in self.datasets:
                self.datasets[table_name]["last_accessed_at"] = datetime.now().isoformat()
                self.datasets[table_name]["access_count"] = self.datasets[table_name].get("access_count", 0) + 1

        except Exception as e:
            # Log but don't fail - access tracking is non-critical
            logger.warning(f"Error tracking access for {table_name}: {e}")

    def _get_table_size(self, table_name: str) -> int:
        """
        Get table size in bytes using DuckDB's size estimation.

        Args:
            table_name: Name of the table (must be validated before calling)

        Returns:
            Estimated size in bytes, or 0 if calculation fails
        """
        try:
            # Validate table name before using in query
            self._validate_table_name(table_name)

            # Use DuckDB's built-in table size estimation
            # This is much more accurate than row * column * 100
            result = self.conn.execute(f"""
                SELECT estimated_size
                FROM duckdb_tables()
                WHERE table_name = ?
            """, [table_name]).fetchone()

            if result and result[0]:
                return int(result[0])

            # Fallback: use a more reasonable estimation if duckdb_tables() doesn't work
            # Get actual data size by querying column statistics
            result = self.conn.execute(f"""
                SELECT
                    COUNT(*) as row_count,
                    (SELECT COUNT(*) FROM information_schema.columns WHERE table_name = ?) as col_count
                FROM {table_name}
            """, [table_name]).fetchone()

            if result:
                # Rough estimate: assume 50 bytes average per field
                return int(result[0] * result[1] * 50)

            return 0

        except Exception as e:
            logger.warning(f"Failed to calculate size for {table_name}: {e}")
            return 0

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

        # Calculate table size
        size_bytes = self._get_table_size(table_name)

        # Store metadata in memory
        metadata = {
            "chat_id": chat_id,
            "message_group_id": message_group_id,
            "question": question,
            "sql_query": sql_query,
            "row_count": len(df),
            "column_count": len(df.columns),
            "columns": list(df.columns),
            "dtypes": {col: str(dtype) for col, dtype in df.dtypes.items()},
            "created_at": datetime.now().isoformat(),
            "last_accessed_at": datetime.now().isoformat(),
            "access_count": 0
        }
        self.datasets[table_name] = metadata

        # Persist metadata to database using JSON for columns and dtypes
        self.conn.execute("""
            INSERT OR REPLACE INTO _cache_metadata
            (table_name, chat_id, message_group_id, question, sql_query,
             created_at, last_accessed_at, access_count, row_count, column_count,
             columns, dtypes, size_bytes)
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 0, ?, ?, ?, ?, ?)
        """, [
            table_name, chat_id, message_group_id, question, sql_query,
            len(df), len(df.columns),
            json.dumps(list(df.columns)),  # Use JSON, not str()
            json.dumps({col: str(dtype) for col, dtype in df.dtypes.items()}),  # Use JSON, not str()
            size_bytes
        ])

        logger.info(f"Stored {len(df)} rows in DuckDB table '{table_name}' (~{size_bytes // 1024}KB)")
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

            # Track access for any tables referenced in the query
            # Extract table names matching our pattern
            for table_name in self.datasets.keys():
                if table_name in sql:
                    self._track_access(table_name)

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

    def list_datasets(self) -> Dict:
        """
        List all stored datasets with their metadata and cache status hints.

        Returns:
            Dict with 'datasets' list and 'cache_info' dict containing cleanup hints
        """
        datasets = [
            {
                "table_name": table_name,
                **metadata
            }
            for table_name, metadata in self.datasets.items()
        ]

        # Calculate cache status for cleanup hints
        total_size = self._get_total_cache_size()
        total_size_mb = total_size // 1024 // 1024

        # Find oldest dataset
        oldest_age_days = 0
        if self.datasets:
            now = datetime.now()
            for metadata in self.datasets.values():
                last_accessed = datetime.fromisoformat(
                    metadata.get('last_accessed_at', metadata['created_at'])
                )
                age_days = (now - last_accessed).days
                oldest_age_days = max(oldest_age_days, age_days)

        # Determine if cleanup recommended
        cleanup_recommended = False
        cleanup_reason = None

        if total_size_mb > self.max_size_mb * 0.8:  # 80% threshold
            cleanup_recommended = True
            cleanup_reason = f"Cache size approaching limit ({total_size_mb}/{self.max_size_mb} MB)"
        elif oldest_age_days > 14:
            cleanup_recommended = True
            cleanup_reason = f"Old datasets detected (oldest: {oldest_age_days} days)"

        return {
            "datasets": datasets,
            "cache_info": {
                "total_datasets": len(datasets),
                "total_size_mb": total_size_mb,
                "max_size_mb": self.max_size_mb,
                "oldest_dataset_age_days": oldest_age_days,
                "cleanup_recommended": cleanup_recommended,
                "cleanup_reason": cleanup_reason
            }
        }

    def cleanup_cache(self, max_age_days: int = 14, max_size_mb: int = 500,
                     keep_frequently_used: bool = True, min_access_count: int = 5):
        """
        Clean up cache with multiple strategies:
        1. Remove datasets not accessed in max_age_days (default: 2 weeks)
        2. Apply LRU eviction if total cache exceeds max_size_mb
        3. Preserve frequently accessed tables (access_count >= min_access_count)

        Args:
            max_age_days: Remove datasets not accessed in this many days (default: 14)
            max_size_mb: Maximum cache size in MB before LRU cleanup (default: 500)
            keep_frequently_used: Preserve tables with high access count (default: True)
            min_access_count: Minimum access count to preserve (default: 5)

        Returns:
            Dict with cleanup statistics
        """
        removed_count = 0
        removed_size = 0
        current_time = datetime.now()
        cutoff_time = current_time - timedelta(days=max_age_days)

        # Strategy 1: Remove datasets not accessed within max_age_days
        tables_to_remove = []
        for table_name, metadata in self.datasets.items():
            last_accessed = datetime.fromisoformat(metadata.get("last_accessed_at", metadata["created_at"]))

            # Skip frequently used tables if configured
            access_count = metadata.get("access_count", 0)
            if keep_frequently_used and access_count >= min_access_count:
                continue

            # Check if last access is beyond cutoff
            if last_accessed < cutoff_time:
                tables_to_remove.append(table_name)

        for table_name in tables_to_remove:
            size = self._drop_table(table_name)
            removed_count += 1
            removed_size += size

        logger.info(f"Removed {removed_count} inactive datasets ({removed_size // 1024 // 1024}MB)")

        # Strategy 2: Check total cache size and apply LRU if needed
        total_size = self._get_total_cache_size()
        total_size_mb = total_size // 1024 // 1024

        if total_size_mb > max_size_mb:
            logger.info(f"Cache size ({total_size_mb}MB) exceeds limit ({max_size_mb}MB), applying LRU cleanup")

            # Get tables sorted by last access (oldest first), excluding frequently used
            lru_candidates = []
            for table_name, metadata in self.datasets.items():
                access_count = metadata.get("access_count", 0)
                if keep_frequently_used and access_count >= min_access_count:
                    continue  # Skip hot cache

                last_accessed = datetime.fromisoformat(metadata.get("last_accessed_at", metadata["created_at"]))
                lru_candidates.append((table_name, last_accessed))

            # Sort by last accessed (oldest first)
            lru_candidates.sort(key=lambda x: x[1])

            # Remove oldest until we're under the limit
            for table_name, _ in lru_candidates:
                if total_size_mb <= max_size_mb:
                    break

                size = self._drop_table(table_name)
                removed_count += 1
                removed_size += size
                total_size_mb = self._get_total_cache_size() // 1024 // 1024

            logger.info(f"LRU cleanup removed {removed_count} tables, cache now {total_size_mb}MB")

        # Vacuum to reclaim space
        try:
            self.conn.execute("VACUUM")
            logger.debug("Database vacuumed")
        except Exception as e:
            logger.warning(f"Vacuum failed: {e}")

        return {
            "removed_count": removed_count,
            "removed_size_mb": removed_size // 1024 // 1024,
            "remaining_datasets": len(self.datasets),
            "cache_size_mb": self._get_total_cache_size() // 1024 // 1024
        }

    def _drop_table(self, table_name: str) -> int:
        """Drop a table and its metadata. Returns size in bytes."""
        try:
            self._validate_table_name(table_name)
            size = self._get_table_size(table_name)

            self.conn.execute(f"DROP TABLE IF EXISTS {table_name}")
            self.conn.execute("DELETE FROM _cache_metadata WHERE table_name = ?", [table_name])

            if table_name in self.datasets:
                del self.datasets[table_name]

            logger.debug(f"Dropped table {table_name} ({size // 1024}KB)")
            return size
        except Exception as e:
            logger.warning(f"Failed to drop {table_name}: {e}")
            return 0

    def _get_total_cache_size(self) -> int:
        """Get total cache size in bytes."""
        try:
            result = self.conn.execute("""
                SELECT COALESCE(SUM(size_bytes), 0) as total
                FROM _cache_metadata
            """).fetchone()
            return result[0] if result else 0
        except Exception as e:
            logger.warning(f"Failed to get total cache size: {e}")
            return 0

    def consolidate_datasets(self, chat_id: str = None, max_tables: int = 5) -> Dict:
        """
        Consolidate multiple related datasets into fewer tables.
        Useful when multiple queries from the same chat create many small tables.

        Args:
            chat_id: If provided, only consolidate datasets from this chat.
                    If None, consolidate across all chats.
            max_tables: Maximum number of tables to consolidate in one operation (default: 5)

        Returns:
            Dict with consolidation statistics
        """
        consolidated_count = 0
        space_saved = 0

        # Find groups of related tables (same chat_id, similar time period)
        table_groups = {}
        for table_name, metadata in self.datasets.items():
            tid = metadata.get("chat_id", "unknown")

            # Filter by chat_id if specified
            if chat_id and tid != chat_id:
                continue

            if tid not in table_groups:
                table_groups[tid] = []
            table_groups[tid].append(table_name)

        # Consolidate each group if it has multiple tables
        for tid, tables in table_groups.items():
            if len(tables) <= 1:
                continue  # Skip single-table groups

            # Limit consolidation to prevent overwhelming operations
            tables_to_consolidate = tables[:max_tables]

            # Check if all tables have compatible schemas
            schemas = []
            for table_name in tables_to_consolidate:
                try:
                    # Use parameterized query for safety
                    result = self.conn.execute("""
                        SELECT column_name, data_type
                        FROM information_schema.columns
                        WHERE table_name = ?
                        ORDER BY ordinal_position
                    """, [table_name]).fetchall()
                    schemas.append((table_name, result))
                except Exception as e:
                    logger.warning(f"Failed to get schema for {table_name}: {e}")
                    continue

            if len(schemas) < 2:
                continue  # Need at least 2 tables to consolidate

            # Check schema compatibility (simplified - could be more sophisticated)
            first_schema = schemas[0][1]
            compatible = all(schema[1] == first_schema for schema in schemas[1:])

            if not compatible:
                logger.debug(f"Skipping consolidation for {tid} - incompatible schemas")
                continue

            # Create consolidated table name
            consolidated_name = f"ace_{self._sanitize_identifier(tid)}_consolidated_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

            # Validate the consolidated name before use
            try:
                self._validate_table_name(consolidated_name)
            except ValueError:
                logger.warning(f"Generated invalid consolidated name: {consolidated_name}, skipping")
                continue

            try:
                # Union all tables
                union_query = " UNION ALL ".join([
                    f"SELECT * FROM {table_name}" for table_name, _ in schemas
                ])

                self.conn.execute(f"""
                    CREATE TABLE {consolidated_name} AS
                    SELECT DISTINCT * FROM ({union_query})
                """)

                # Get consolidated metadata
                row_count = self.conn.execute(f"SELECT COUNT(*) FROM {consolidated_name}").fetchone()[0]

                # Store consolidated metadata
                self.datasets[consolidated_name] = {
                    "chat_id": tid,
                    "message_group_id": "consolidated",
                    "question": f"Consolidated from {len(schemas)} tables",
                    "sql_query": "",
                    "row_count": row_count,
                    "column_count": len(first_schema),
                    "columns": [col[0] for col in first_schema],
                    "dtypes": {},
                    "created_at": datetime.now().isoformat(),
                    "last_accessed_at": datetime.now().isoformat(),
                    "access_count": 0
                }

                # Persist to metadata table
                size_bytes = self._get_table_size(consolidated_name)
                self.conn.execute("""
                    INSERT INTO _cache_metadata
                    (table_name, chat_id, message_group_id, question, sql_query,
                     created_at, last_accessed_at, access_count, row_count, column_count,
                     columns, dtypes, size_bytes)
                    VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 0, ?, ?, ?, ?, ?)
                """, [
                    consolidated_name, tid, "consolidated",
                    f"Consolidated from {len(schemas)} tables", "",
                    row_count, len(first_schema),
                    json.dumps([col[0] for col in first_schema]),  # Use JSON, not str()
                    json.dumps({}),  # Use JSON, not string literal
                    size_bytes
                ])

                # Drop original tables
                for table_name, _ in schemas:
                    original_size = self._drop_table(table_name)
                    space_saved += original_size

                consolidated_count += 1
                logger.info(f"Consolidated {len(schemas)} tables into {consolidated_name} ({row_count} rows)")

            except Exception as e:
                logger.warning(f"Failed to consolidate tables for {tid}: {e}")

        return {
            "consolidated_count": consolidated_count,
            "space_saved_mb": space_saved // 1024 // 1024
        }

    def cleanup_old_datasets(self, max_age_minutes: int = 60):
        """
        Deprecated: Use cleanup_cache() instead.
        Remove datasets older than specified age.
        """
        logger.warning("cleanup_old_datasets is deprecated, use cleanup_cache() instead")
        max_age_days = max_age_minutes / (60 * 24)
        return self.cleanup_cache(max_age_days=max_age_days)
