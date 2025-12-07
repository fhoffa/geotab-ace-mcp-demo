# Geotab MCP Memory System Design

## Overview

Add persistent memory capabilities to the Geotab MCP server, allowing Claude to remember findings, patterns, and gotchas discovered while working with the Geotab ACE API.

---

## Goals

### Primary Goals
1. **Reduce repeated discovery** - Don't re-learn the same gotchas every session
2. **Improve query quality** - Apply learned patterns to craft better questions
3. **Account-specific context** - Remember characteristics of each fleet/account
4. **Error resolution** - Recall how past errors were resolved

### Secondary Goals
- Help Claude verify if old learnings are still valid
- Enable knowledge transfer across sessions
- Provide audit trail of what was learned and when

---

## What Should Be Remembered

| Category | Examples | Value |
|----------|----------|-------|
| **gotcha** | "Fuel queries default to 24h without explicit dates" | Prevent repeated mistakes |
| **pattern** | "For monthly trends, ask for 'daily averages for [month]'" | Reusable query templates |
| **schema** | "Vehicle table has columns: id, name, vin, licensePlate" | Faster query formulation |
| **account-info** | "Fleet1 has 450 vehicles, mostly in EST timezone" | Context for analysis |
| **error-resolution** | "Error X means Y, fix by Z" | Faster troubleshooting |
| **performance** | "Queries spanning >90 days are slow" | Set expectations |

---

## Design Alternatives

### Alternative 1: Simple Key-Value Store

**Approach:** Basic remember/recall with keyword search

```python
geotab_remember(content: str, category: str)
geotab_recall(search: str) -> List[Memory]
geotab_forget(id: str)
```

**Pros:**
- Simple to implement
- Easy for Claude to use
- Low cognitive overhead

**Cons:**
- Keyword search is brittle
- No context awareness
- Claude must know what to search for
- No verification/freshness tracking

---

### Alternative 2: Rich Metadata with SQL Search

**Approach:** Detailed schema with powerful querying

```python
geotab_remember(
    content: str,
    category: str,
    account: str = None,
    tags: List[str] = [],
    source_question: str = None,
    verification_hint: str = None
)
geotab_recall(
    search: str = None,
    category: str = None,
    account: str = None,
    tags: List[str] = None,
    since_days: int = None
)
geotab_get_context(account: str = None) -> List[Memory]
geotab_verify_memory(id: str)
geotab_forget(id: str)
```

**Pros:**
- Powerful filtering (category + account + recency)
- Verification tracking helps with trust
- Session context bootstrapping
- Tags enable flexible organization

**Cons:**
- More complex API
- Claude needs to use it correctly
- More fields to populate when remembering
- Risk of over-engineering

---

### Alternative 3: Automatic Memory with Suggestions

**Approach:** System suggests memories, Claude confirms

```python
# After each query, system analyzes and suggests
geotab_suggest_memory() -> SuggestedMemory
geotab_confirm_memory(suggestion_id: str, edits: dict = None)

# Recall is context-aware
geotab_recall_relevant(current_question: str) -> List[Memory]
```

**Pros:**
- Reduces burden on Claude to identify what's memorable
- Context-aware recall is more useful
- Could use embeddings for semantic search

**Cons:**
- Complex to implement well
- Suggestions may be low quality
- Semantic search adds dependencies (embeddings)
- Less transparent to user

---

### Alternative 4: Hybrid - Rich Storage, Simple Interface

**Approach:** Store rich metadata but provide simple + advanced interfaces

```python
# Simple interface (most common)
geotab_remember(content: str, category: str, tags: List[str] = [])
geotab_recall(search: str = None, category: str = None)
geotab_forget(id: str)

# Session helper
geotab_get_context(account: str = None) -> ContextSummary

# Advanced (when needed)
geotab_update_memory(id: str, verified: bool = None, content: str = None)
geotab_list_memories(category: str = None, account: str = None, limit: int = 50)
```

**Auto-captured metadata:**
- `created_at` - automatic timestamp
- `last_verified` - updated via `update_memory`
- `account` - inferred from current session if not specified

**Pros:**
- Simple for common cases
- Power available when needed
- Less friction to remember things
- Still enables good search/filtering

**Cons:**
- Loses some metadata (source_question, verification_hint)
- Account inference might be wrong
- Middle-ground may satisfy neither goal fully

---

## Preferred Approach: Alternative 4 (Hybrid)

### Rationale

1. **Low friction remembering** - If it's hard to remember things, Claude won't do it
2. **Useful recall** - Category + keyword + account filtering covers most needs
3. **Session bootstrapping** - `get_context` solves "what do I know?" problem
4. **Pragmatic** - Can add complexity later if needed

### Detailed Design

#### Storage: DuckDB

File: `~/.geotab_mcp_memories.db`

```sql
CREATE TABLE memories (
    id TEXT PRIMARY KEY,
    content TEXT NOT NULL,
    category TEXT NOT NULL,
    tags TEXT,  -- JSON array
    account TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_verified TIMESTAMP,

    -- Indexes for common queries
    INDEX idx_category (category),
    INDEX idx_account (account),
    INDEX idx_created (created_at DESC)
);

-- Full-text search
CREATE VIRTUAL TABLE memories_fts USING fts5(content, tags);
```

#### Tools

##### `geotab_remember`
```python
def geotab_remember(
    content: str,           # The finding/learning
    category: str,          # gotcha|pattern|schema|account-info|error-resolution|performance
    tags: List[str] = [],   # Searchable tags
    account: str = None     # Which account this applies to (None = all)
) -> str:
    """Store a memory. Returns the memory ID."""
```

##### `geotab_recall`
```python
def geotab_recall(
    search: str = None,     # Full-text search on content
    category: str = None,   # Filter by category
    account: str = None,    # Filter by account (includes None/global memories)
    limit: int = 20
) -> str:
    """Search memories. Returns formatted list with IDs, content, age."""
```

##### `geotab_get_context`
```python
def geotab_get_context(
    account: str = None     # Focus on this account
) -> str:
    """
    Get relevant memories for session start.
    Returns:
    - Recent memories (last 7 days)
    - Account-specific info (if account specified)
    - All gotchas (important to always surface)
    """
```

##### `geotab_list_memories`
```python
def geotab_list_memories(
    category: str = None,
    account: str = None,
    limit: int = 50
) -> str:
    """List memories with filtering. Shows all metadata."""
```

##### `geotab_update_memory`
```python
def geotab_update_memory(
    id: str,
    content: str = None,    # Update content
    verified: bool = False  # Mark as re-verified now
) -> str:
    """Update a memory's content or mark it as verified."""
```

##### `geotab_forget`
```python
def geotab_forget(id: str) -> str:
    """Delete a memory by ID."""
```

#### Usage Patterns

**Session start:**
```
Claude: Let me check what I know about this Geotab setup.
[calls geotab_get_context(account="fleet1")]
→ Gets recent memories, fleet1-specific info, all gotchas
```

**Before a query:**
```
User: Show me fuel consumption trends
Claude: Let me check for relevant patterns...
[calls geotab_recall(search="fuel", category="pattern")]
[calls geotab_recall(category="gotcha", search="fuel")]
→ Finds "fuel queries need explicit dates" gotcha
→ Asks user for date range before querying
```

**After unexpected behavior:**
```
Claude: Interesting - the API returned daily granularity even though I asked for hourly.
[calls geotab_remember(
    content="Hourly granularity not available for fuel data, only daily",
    category="gotcha",
    tags=["fuel", "granularity"]
)]
```

**On error resolution:**
```
Claude: I figured out this error - it happens when...
[calls geotab_remember(
    content="'Invalid date range' error occurs when end_date < start_date, also when range > 1 year",
    category="error-resolution",
    tags=["date-range", "error"]
)]
```

---

## Potential Flaws & Mitigations

### Flaw 1: Claude Forgets to Remember

**Risk:** Claude doesn't proactively call `geotab_remember` after discoveries.

**Mitigations:**
- Add prompting in tool descriptions encouraging memory use
- Could add a "memory suggestions" feature later (Alternative 3)
- User can remind Claude: "remember that for next time"

**Severity:** Medium - reduces value but doesn't break anything

---

### Flaw 2: Memory Rot

**Risk:** Old memories become outdated/wrong as API changes.

**Mitigations:**
- `last_verified` field tracks freshness
- `get_context` could flag old unverified memories
- Claude can verify and update when reusing old memories
- User can periodically review with `list_memories`

**Severity:** Medium - wrong memories worse than no memories

---

### Flaw 3: Poor Recall

**Risk:** Claude doesn't find relevant memories when needed.

**Mitigations:**
- Full-text search helps
- Category filtering narrows results
- Tags provide additional hooks
- `get_context` surfaces important stuff automatically

**Severity:** Medium - memories exist but aren't used

---

### Flaw 4: Duplicate/Conflicting Memories

**Risk:** Same thing remembered multiple times with slight variations.

**Mitigations:**
- Could add duplicate detection (fuzzy match on content)
- User can review and clean up with `list_memories` + `forget`
- Claude could check before remembering: "Do I already know this?"

**Severity:** Low - annoying but not harmful

---

### Flaw 5: Account Confusion

**Risk:** Memory saved for wrong account or applied to wrong account.

**Mitigations:**
- Explicit `account` parameter
- `recall` includes global memories (account=None) for any account
- Clear display of which account a memory applies to

**Severity:** Low - easy to fix by updating memory

---

### Flaw 6: Over-Reliance on Memories

**Risk:** Claude trusts old memories instead of verifying current behavior.

**Mitigations:**
- Display age prominently in recall results
- `get_context` could warn about old unverified memories
- Claude should verify critical memories before relying on them

**Severity:** Medium - could lead to wrong assumptions

---

### Flaw 7: Storage Bloat

**Risk:** Memories accumulate without cleanup.

**Mitigations:**
- DuckDB handles large datasets efficiently
- Could add auto-cleanup of very old unverified memories
- User can review and prune

**Severity:** Low - DuckDB scales well

---

## Implementation Plan

1. **Create `memory_manager.py`**
   - DuckDB setup and schema
   - CRUD operations
   - Search functionality

2. **Add tools to `geotab_mcp_server.py`**
   - 6 new tools with consistent patterns
   - Good descriptions for Claude

3. **Testing**
   - Unit tests for memory manager
   - Integration tests for tools

4. **Documentation**
   - Update README with memory features
   - Usage examples

---

## Open Questions

1. **Should `get_context` run automatically at session start?**
   - Could be a resource endpoint Claude checks
   - Or just rely on Claude calling it

2. **Should we track which memories are actually useful?**
   - Could add "used_count" to track which get recalled
   - Helps identify valuable vs noise

3. **Should memories be exportable/importable?**
   - Share learnings across teams/instances
   - JSON export of memories table

4. **Per-user vs shared memories?**
   - Current design is single-user (one DB file)
   - Multi-user would need different architecture

---

## Architectural Refinements (Post-Review)

### A. Resource Endpoint for Context

Add MCP Resource `geotab://memory/context` alongside the `get_context` tool.

**Why:** If client supports resource attachment, Claude starts with context already loaded—no initial tool round-trip needed.

### B. Enhanced Schema

```sql
CREATE TABLE memories (
    id TEXT PRIMARY KEY,
    content TEXT NOT NULL,
    category TEXT NOT NULL,
    tags TEXT,  -- JSON array
    account TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_verified TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    usage_count INTEGER DEFAULT 0  -- Track which memories are useful
);
```

- `usage_count`: Incremented on recall. Memories with count=0 after months are candidates for pruning.

### C. System Prompt Injection

To mitigate "Claude forgets to remember", add to MCP server instructions:

> "You have access to a persistent memory system. You are **required** to check this memory (`geotab_recall`) before constructing complex queries. You are **required** to save (`geotab_remember`) any API anomalies, schema quirks, or successful patterns you discover for future use."

---

## Answered Open Questions

1. **Should `get_context` run automatically?**
   - **No** as a tool call. Use MCP Resource pattern—attach `geotab://memory/context` so context loads automatically.

2. **Should we track which memories are useful?**
   - **Yes.** Add `usage_count` column, increment on recall.

3. **Should memories be exportable?**
   - **Yes.** DuckDB makes this trivial: `COPY (SELECT * FROM memories) TO 'export.json'`. Add `geotab_export_memories` tool later.

4. **Per-user vs shared?**
   - **Single user for V1.** Multi-user needs locking/privacy solutions. Keep local (`~/.geotab_mcp_memories.db`).

---

## Decision

Proceeding with **Alternative 4 (Hybrid)** - rich storage with simple interface.

Key characteristics:
- DuckDB storage at `~/.geotab_mcp_memories.db`
- 6 tools: remember, recall, get_context, list_memories, update_memory, forget
- 1 resource: `geotab://memory/context`
- Categories: gotcha, pattern, schema, account-info, error-resolution, performance
- Full-text search + category/account/tag filtering
- Usage tracking for memory relevance
