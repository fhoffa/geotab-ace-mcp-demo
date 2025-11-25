"""
Memory Manager Module

Persistent memory storage for Geotab MCP server using DuckDB.
Allows Claude to remember findings, patterns, and gotchas across sessions.
"""

import json
import logging
import os
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import duckdb

logger = logging.getLogger(__name__)

# Default storage location
DEFAULT_DB_PATH = os.path.expanduser("~/.geotab_mcp_memories.db")


class MemoryManager:
    """
    Manager for persistent memory storage using DuckDB.

    Stores learnings, patterns, and gotchas discovered while working
    with the Geotab ACE API for retrieval in future sessions.
    """

    # Valid memory categories
    VALID_CATEGORIES = [
        'gotcha',           # API quirks, unexpected behaviors
        'pattern',          # Successful query patterns
        'schema',           # Table/column information
        'account-info',     # Fleet-specific characteristics
        'error-resolution', # How errors were resolved
        'performance'       # Performance insights
    ]

    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        """
        Initialize memory manager with persistent DuckDB storage.

        Args:
            db_path: Path to the DuckDB database file
        """
        self.db_path = db_path
        self.conn = duckdb.connect(db_path)
        self._init_db()
        logger.info(f"Memory manager initialized with database at {db_path}")

    def _init_db(self):
        """Initialize database schema and FTS index."""
        # Create main memories table
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS memories (
                id TEXT PRIMARY KEY,
                content TEXT NOT NULL,
                category TEXT NOT NULL,
                tags TEXT,
                account TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_verified TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                usage_count INTEGER DEFAULT 0
            )
        """)

        # Create indexes for common queries
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_memories_category
            ON memories(category)
        """)
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_memories_account
            ON memories(account)
        """)
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_memories_created
            ON memories(created_at DESC)
        """)

        # Install and load FTS extension
        try:
            self.conn.execute("INSTALL fts")
            self.conn.execute("LOAD fts")

            # Create FTS index on content and tags
            # Check if index already exists by trying to create it
            try:
                self.conn.execute("""
                    PRAGMA create_fts_index(
                        'memories', 'id', 'content', 'tags',
                        stemmer = 'porter',
                        stopwords = 'english'
                    )
                """)
                logger.info("Created FTS index on memories table")
            except duckdb.CatalogException:
                # Index already exists
                pass
        except Exception as e:
            logger.warning(f"Could not initialize FTS: {e}. Falling back to LIKE search.")

    def remember(
        self,
        content: str,
        category: str,
        tags: List[str] = None,
        account: str = None
    ) -> str:
        """
        Store a memory.

        Args:
            content: The finding/learning to remember
            category: Type of memory (gotcha, pattern, schema, etc.)
            tags: Optional searchable tags
            account: Which account this applies to (None = global)

        Returns:
            Memory ID

        Raises:
            ValueError: If category is invalid or content is empty
        """
        if not content or not content.strip():
            raise ValueError("Memory content cannot be empty")

        if category not in self.VALID_CATEGORIES:
            raise ValueError(
                f"Invalid category: '{category}'. "
                f"Must be one of: {', '.join(self.VALID_CATEGORIES)}"
            )

        mem_id = str(uuid.uuid4())[:8]
        tags_json = json.dumps(tags or [])

        self.conn.execute("""
            INSERT INTO memories (id, content, category, tags, account)
            VALUES (?, ?, ?, ?, ?)
        """, [mem_id, content.strip(), category, tags_json, account])

        logger.info(f"Stored memory [{mem_id}]: {category} - {content[:50]}...")
        return mem_id

    def recall(
        self,
        search: str = None,
        category: str = None,
        account: str = None,
        limit: int = 20
    ) -> List[Dict]:
        """
        Search and retrieve memories.

        Args:
            search: Full-text search on content and tags
            category: Filter by category
            account: Filter by account (also includes global memories)
            limit: Maximum results to return

        Returns:
            List of memory dictionaries
        """
        conditions = ["1=1"]
        params = []

        if category:
            if category not in self.VALID_CATEGORIES:
                raise ValueError(f"Invalid category: '{category}'")
            conditions.append("category = ?")
            params.append(category)

        if account:
            # Include account-specific and global memories
            conditions.append("(account = ? OR account IS NULL)")
            params.append(account)

        where_clause = " AND ".join(conditions)

        # Try FTS search first, fall back to LIKE
        if search:
            try:
                # Use FTS match
                query = f"""
                    SELECT id, content, category, tags, account,
                           created_at, last_verified, usage_count,
                           fts_main_memories.match_bm25(id, ?) AS score
                    FROM memories
                    WHERE {where_clause}
                      AND score IS NOT NULL
                    ORDER BY score DESC
                    LIMIT ?
                """
                params_with_search = [search] + params + [limit]
                results = self.conn.execute(query, params_with_search).fetchall()

                # If FTS returns no results, fall back to LIKE
                if not results:
                    raise Exception("FTS returned no results, falling back to LIKE")
            except Exception:
                # Fallback to LIKE search
                conditions.append("(content ILIKE ? OR tags ILIKE ?)")
                params.extend([f"%{search}%", f"%{search}%"])
                where_clause = " AND ".join(conditions)

                query = f"""
                    SELECT id, content, category, tags, account,
                           created_at, last_verified, usage_count
                    FROM memories
                    WHERE {where_clause}
                    ORDER BY created_at DESC
                    LIMIT ?
                """
                params.append(limit)
                results = self.conn.execute(query, params).fetchall()
        else:
            query = f"""
                SELECT id, content, category, tags, account,
                       created_at, last_verified, usage_count
                FROM memories
                WHERE {where_clause}
                ORDER BY created_at DESC
                LIMIT ?
            """
            params.append(limit)
            results = self.conn.execute(query, params).fetchall()

        # Format results and increment usage
        memories = []
        for row in results:
            mem_id = row[0]

            # Parse tags JSON
            try:
                tags = json.loads(row[3]) if row[3] else []
            except json.JSONDecodeError:
                tags = []

            memory = {
                "id": mem_id,
                "content": row[1],
                "category": row[2],
                "tags": tags,
                "account": row[4],
                "created_at": row[5].strftime("%Y-%m-%d %H:%M") if row[5] else None,
                "last_verified": row[6].strftime("%Y-%m-%d %H:%M") if row[6] else None,
                "usage_count": row[7],
                "age_days": (datetime.now() - row[5]).days if row[5] else 0
            }
            memories.append(memory)

            # Increment usage count
            self._increment_usage(mem_id)

        return memories

    def _increment_usage(self, mem_id: str):
        """Increment usage count for a memory."""
        try:
            self.conn.execute(
                "UPDATE memories SET usage_count = usage_count + 1 WHERE id = ?",
                [mem_id]
            )
        except Exception as e:
            logger.warning(f"Failed to increment usage for {mem_id}: {e}")

    def get_context(self, account: str = None) -> Dict:
        """
        Get relevant memories for session context.

        Returns:
            - Recent memories (last 7 days)
            - Account-specific info
            - All gotchas (critical warnings)

        Args:
            account: Focus on this account's memories

        Returns:
            Dictionary with categorized memories
        """
        context = {
            "recent": [],
            "gotchas": [],
            "account_info": []
        }

        # Recent memories (last 7 days)
        seven_days_ago = datetime.now() - timedelta(days=7)
        recent_query = """
            SELECT id, content, category, tags, account, created_at
            FROM memories
            WHERE created_at >= ?
            ORDER BY created_at DESC
            LIMIT 10
        """
        recent = self.conn.execute(recent_query, [seven_days_ago]).fetchall()
        for row in recent:
            context["recent"].append({
                "id": row[0],
                "content": row[1],
                "category": row[2],
                "account": row[4],
                "created": row[5].strftime("%Y-%m-%d") if row[5] else None
            })

        # All gotchas (always important)
        gotcha_query = """
            SELECT id, content, tags, account, created_at
            FROM memories
            WHERE category = 'gotcha'
            ORDER BY usage_count DESC, created_at DESC
        """
        gotchas = self.conn.execute(gotcha_query).fetchall()
        for row in gotchas:
            context["gotchas"].append({
                "id": row[0],
                "content": row[1],
                "account": row[3],
                "created": row[4].strftime("%Y-%m-%d") if row[4] else None
            })

        # Account-specific info
        if account:
            account_query = """
                SELECT id, content, category, created_at
                FROM memories
                WHERE account = ?
                ORDER BY created_at DESC
                LIMIT 10
            """
            account_memories = self.conn.execute(account_query, [account]).fetchall()
            for row in account_memories:
                context["account_info"].append({
                    "id": row[0],
                    "content": row[1],
                    "category": row[2],
                    "created": row[3].strftime("%Y-%m-%d") if row[3] else None
                })

        return context

    def list_memories(
        self,
        category: str = None,
        account: str = None,
        limit: int = 50
    ) -> List[Dict]:
        """
        List all memories with optional filtering.

        Args:
            category: Filter by category
            account: Filter by account
            limit: Maximum results

        Returns:
            List of memory dictionaries with full metadata
        """
        conditions = ["1=1"]
        params = []

        if category:
            conditions.append("category = ?")
            params.append(category)

        if account:
            conditions.append("account = ?")
            params.append(account)

        where_clause = " AND ".join(conditions)

        query = f"""
            SELECT id, content, category, tags, account,
                   created_at, last_verified, usage_count
            FROM memories
            WHERE {where_clause}
            ORDER BY created_at DESC
            LIMIT ?
        """
        params.append(limit)

        results = self.conn.execute(query, params).fetchall()

        memories = []
        for row in results:
            try:
                tags = json.loads(row[3]) if row[3] else []
            except json.JSONDecodeError:
                tags = []

            memories.append({
                "id": row[0],
                "content": row[1],
                "category": row[2],
                "tags": tags,
                "account": row[4],
                "created_at": row[5].strftime("%Y-%m-%d %H:%M") if row[5] else None,
                "last_verified": row[6].strftime("%Y-%m-%d %H:%M") if row[6] else None,
                "usage_count": row[7]
            })

        return memories

    def update_memory(
        self,
        mem_id: str,
        content: str = None,
        verified: bool = False
    ) -> bool:
        """
        Update a memory's content or mark as verified.

        Args:
            mem_id: Memory ID to update
            content: New content (optional)
            verified: If True, update last_verified timestamp

        Returns:
            True if memory was found and updated
        """
        # Check if memory exists
        exists = self.conn.execute(
            "SELECT 1 FROM memories WHERE id = ?", [mem_id]
        ).fetchone()

        if not exists:
            return False

        if content:
            self.conn.execute(
                "UPDATE memories SET content = ? WHERE id = ?",
                [content.strip(), mem_id]
            )

        if verified:
            self.conn.execute(
                "UPDATE memories SET last_verified = CURRENT_TIMESTAMP WHERE id = ?",
                [mem_id]
            )

        logger.info(f"Updated memory [{mem_id}]")
        return True

    def forget(self, mem_id: str) -> bool:
        """
        Delete a memory.

        Args:
            mem_id: Memory ID to delete

        Returns:
            True if memory was found and deleted
        """
        result = self.conn.execute(
            "DELETE FROM memories WHERE id = ? RETURNING id",
            [mem_id]
        ).fetchone()

        if result:
            logger.info(f"Deleted memory [{mem_id}]")
            return True
        return False

    def get_stats(self) -> Dict:
        """Get memory statistics."""
        stats = {}

        # Total count
        total = self.conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
        stats["total_memories"] = total

        # By category
        by_category = self.conn.execute("""
            SELECT category, COUNT(*)
            FROM memories
            GROUP BY category
        """).fetchall()
        stats["by_category"] = {row[0]: row[1] for row in by_category}

        # By account
        by_account = self.conn.execute("""
            SELECT COALESCE(account, 'global'), COUNT(*)
            FROM memories
            GROUP BY account
        """).fetchall()
        stats["by_account"] = {row[0]: row[1] for row in by_account}

        # Most used
        most_used = self.conn.execute("""
            SELECT id, content, usage_count
            FROM memories
            ORDER BY usage_count DESC
            LIMIT 5
        """).fetchall()
        stats["most_used"] = [
            {"id": row[0], "content": row[1][:50], "usage_count": row[2]}
            for row in most_used
        ]

        return stats

    def format_context_summary(self, account: str = None) -> str:
        """
        Format context as a readable summary string.

        Args:
            account: Focus on this account

        Returns:
            Formatted markdown summary
        """
        context = self.get_context(account)

        parts = ["## Geotab Memory Context\n"]

        if context["gotchas"]:
            parts.append("### Critical Gotchas")
            for g in context["gotchas"]:
                account_str = f" [{g['account']}]" if g['account'] else ""
                parts.append(f"- {g['content']}{account_str}")
            parts.append("")

        if context["recent"]:
            parts.append("### Recent Learnings (Last 7 Days)")
            for m in context["recent"]:
                parts.append(f"- [{m['category']}] {m['content']}")
            parts.append("")

        if context["account_info"]:
            parts.append(f"### Account Info: {account}")
            for m in context["account_info"]:
                parts.append(f"- [{m['category']}] {m['content']}")
            parts.append("")

        if not context["gotchas"] and not context["recent"] and not context["account_info"]:
            parts.append("*No memories stored yet. Use geotab_remember to store learnings.*")

        return "\n".join(parts)

    def export_memories(self, file_path: str = None) -> str:
        """
        Export all memories to a JSON file.

        Args:
            file_path: Path to export file. Defaults to ~/geotab_memories_export.json

        Returns:
            Path to the exported file
        """
        if file_path is None:
            file_path = os.path.expanduser("~/geotab_memories_export.json")

        # Get all memories with full data
        results = self.conn.execute("""
            SELECT id, content, category, tags, account,
                   created_at, last_verified, usage_count
            FROM memories
            ORDER BY created_at DESC
        """).fetchall()

        memories = []
        for row in results:
            try:
                tags = json.loads(row[3]) if row[3] else []
            except json.JSONDecodeError:
                tags = []

            memories.append({
                "id": row[0],
                "content": row[1],
                "category": row[2],
                "tags": tags,
                "account": row[4],
                "created_at": row[5].isoformat() if row[5] else None,
                "last_verified": row[6].isoformat() if row[6] else None,
                "usage_count": row[7]
            })

        export_data = {
            "exported_at": datetime.now().isoformat(),
            "total_memories": len(memories),
            "memories": memories
        }

        with open(file_path, 'w') as f:
            json.dump(export_data, f, indent=2)

        logger.info(f"Exported {len(memories)} memories to {file_path}")
        return file_path

    def close(self):
        """Close the database connection."""
        if self.conn:
            self.conn.close()
            logger.info("Memory manager connection closed")
