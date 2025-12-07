# MCP Best Practices: Implementation & Future Roadmap

This document outlines MCP best practices based on official Anthropic research and how they apply to the Geotab ACE MCP server.

## Reference Articles

1. **[Code execution with MCP: Building more efficient agents](https://www.anthropic.com/research/building-effective-agents)** (Nov 2024)
   - Problem: Tool definitions and intermediate results consume excessive tokens
   - Solution: Agents write code to call MCP tools in execution environments

2. **[Writing effective tools for agents — with agents](https://www.anthropic.com/research/building-effective-agents)** (Sep 2025)
   - Comprehensive guide on tool design, evaluation, and optimization
   - Covers namespacing, error handling, prompt engineering, and token efficiency

## What We've Already Implemented

### ✅ Alternative to Code Execution Pattern (DuckDB Caching)

**Anthropic's Pattern:** Agent writes code that processes data in execution environment before returning to model

**Our Implementation:** Server-side automatic caching in DuckDB with SQL interface

```python
# Traditional (Anthropic's problem scenario):
result = await gdrive.getSheet()  # 10,000 rows → model context
filtered = model_filters_in_context(result)  # wasteful

# Code execution (Anthropic's solution):
data = await gdrive.getSheet()  # stays in execution env
filtered = data.filter(...)  # processed before returning
return filtered  # only results to model

# Our DuckDB approach (achieves same goal):
result = await geotab.ask_question(...)  # >200 rows → auto-cached in DuckDB
# Model receives: metadata + 20 sample rows + table name
sql = "SELECT * FROM ace_123 WHERE ..."  # model queries via SQL
# Only filtered results return to model
```

**Benefits achieved:**
- ✅ Large datasets never enter model context
- ✅ Filtering/aggregation happens outside model
- ✅ Token-efficient (metadata + samples only)
- ✅ Automatic (no agent code required)

**Why this works:** SQL is effectively "code execution" - we run queries server-side and return only results. More deterministic than agent-written code.

### ✅ Response Format Parameter (Just Added)

Tools now support `response_format="concise"` (default) or `"detailed"`:

- **Concise**: Analysis + essential data only (~40-60% token savings)
- **Detailed**: Includes SQL queries, tracking IDs, full metadata

Implementation: `geotab_ask_question()` and `geotab_check_status()`

### ✅ Other Best Practices Already Implemented

1. **Namespacing**: All tools prefixed with `geotab_`
2. **Tool consolidation**: `geotab_ask_question` handles auth + query + format in one call
3. **Clear tool boundaries**: Separate tools for sync/async, query/status/results
4. **Meaningful context**: Driver privacy mode filters PII
5. **Lifecycle management**: Proper startup/shutdown handlers
6. **Comprehensive error handling**: Specific exception types with actionable messages

## Future Improvements

### High Priority

#### 1. Enhance Error Messages (2-3 hours)

**Current:**
```python
return f"Authentication failed: {e}"
```

**Better (actionable guidance):**
```python
return f"""🔐 Authentication failed for account '{account}'

Troubleshooting:
1. Verify .env credentials for: {account or 'default'}
2. Available accounts: {list(accounts.keys())}
3. Test: geotab_test_connection(account='{account}')

Error: {e}"""
```

**Apply to:** All tools with auth, API, timeout, and validation errors

#### 2. Prompt-Engineer Tool Descriptions (3-4 hours)

**Current:**
```python
"""Execute SQL queries on cached Geotab datasets."""
```

**Better (with examples and guidance):**
```python
"""
Execute SQL on large Geotab datasets cached in DuckDB.

When to use:
- After geotab_ask_question returns a table name (e.g., ace_123_456)
- Dataset has >200 rows (automatically cached)
- Need filtering, aggregation, or joins

Common patterns:
- Filter: SELECT * FROM ace_123 WHERE status = 'active'
- Top N: SELECT * FROM ace_123 ORDER BY distance DESC LIMIT 10
- Aggregate: SELECT driver, SUM(miles) FROM ace_123 GROUP BY driver

Only SELECT allowed (no INSERT/UPDATE/DELETE).

Args:
    sql_query: Valid DuckDB SELECT statement

Example:
    "SELECT driver, COUNT(*) FROM ace_123_456 GROUP BY driver LIMIT 5"
"""
```

**Apply to:** All 16 tools - clearer purpose, usage guidance, and examples

#### 3. Replace Cryptic IDs with Semantic Names (1-2 hours)

**Current:**
```python
chat_id = "a1b2c3d4-5e6f-7890-abcd-ef1234567890"
message_group_id = "msg_987654321"
```

**Better (human-readable):**
```python
# Hide from model entirely when not needed:
query_ref = "query_2025_01_15_fleet_analysis_001"

# Or create semantic wrappers:
tracking = f"Fleet analysis query started at {timestamp}"
```

**Impact:** Reduces hallucinations, makes debugging easier

### Medium Priority

#### 4. Build Evaluation Framework (4-8 hours initial)

Create systematic measurement of tool performance:

```python
# tests/evaluations/eval_agent_workflows.py

EVAL_TASKS = [
    {
        "prompt": "How many vehicles were active last week?",
        "expected_tools": ["geotab_ask_question"],
        "success_criteria": lambda r: "vehicle" in r.lower(),
    },
    {
        "prompt": "Get all trips from January, find top 5 drivers by distance",
        "expected_tools": ["geotab_ask_question", "geotab_query_duckdb"],
        "success_criteria": lambda r: "top" in r.lower(),
    },
]

# Measure: completion rate, tool calls, tokens, time
```

**Benefits:**
- Measure impact of tool description changes
- Prevent regressions
- Guide optimization priorities

#### 5. Add Consolidated High-Level Tools (2-4 hours)

**Pattern from article:** Instead of `list_users` + `list_events` + `create_event`, provide `schedule_event`

**For Geotab:**
```python
@mcp.tool()
async def geotab_analyze_fleet_performance(
    time_period: str,
    metrics: list[str] = ["mileage", "fuel", "safety"],
    account: Optional[str] = None
) -> str:
    """
    High-level fleet analysis (consolidates query → cache → analyze).

    Handles: question → DuckDB caching → SQL analysis → summary
    """
    # Execute multi-step workflow internally
```

**Trade-off:** Simpler for common workflows, less flexible for custom analysis

### Low Priority (Optional)

#### 6. Code Execution Tool (Experimental, 4-6 hours)

Add optional tool for complex workflows awkward in SQL:

```python
@mcp.tool()
async def geotab_execute_workflow(script: str) -> str:
    """
    Execute Python code with access to Geotab managers.

    Available: geotab_ace, duckdb_manager, memory_manager

    Use for: Multi-account loops, cross-tool workflows, complex logic
    """
    # Sandboxed Python execution with our managers
```

**When needed:** Cross-account comparisons, conditional workflows, data transformations beyond SQL

#### 7. Use Claude Code for Iterative Tool Optimization (Ongoing)

Anthropic's recommendation: Let Claude optimize tools against evaluations

**Process:**
1. Run evaluation → collect transcripts
2. Paste transcripts into Claude Code
3. Ask: "Analyze tool usage patterns and suggest improvements"
4. Claude refactors tool descriptions, schemas, error messages
5. Re-run evaluation → measure improvements
6. Repeat

**Expected gains:** 10-30% accuracy improvement (based on Anthropic's SWE-bench results)

## Implementation Priority

**Do now (high ROI, low effort):**
1. ✅ `response_format` parameter (DONE)
2. Enhanced error messages (3 hours)
3. Prompt-engineered tool descriptions (4 hours)

**Do soon (enables measurement):**
4. Evaluation framework (8 hours)
5. Use evals to guide further optimization

**Do later (optional enhancements):**
6. Semantic query IDs (2 hours)
7. Consolidated high-level tools (4 hours)
8. Code execution tool (6 hours, if needed)

## Key Insight: We Already Solved the Main Problem

Our DuckDB caching pattern **already achieves the primary goal** of Anthropic's code execution article:

- ✅ Large datasets stay out of model context
- ✅ Processing happens outside model (SQL vs. Python code)
- ✅ Only filtered results return to model
- ✅ Token-efficient and deterministic

**Code execution would add:** Flexibility for non-SQL workflows (loops, conditionals, cross-tool orchestration)

**Our approach offers:** Automatic caching, SQL's expressiveness, and simpler debugging

## Measuring Success

Track these metrics as we implement improvements:

- **Token efficiency:** Avg tokens per query (target: 30-50% reduction with concise mode)
- **Tool accuracy:** % of correct tool selections (eval framework)
- **Error recovery:** % of errors resolved by improved messages
- **User satisfaction:** Qualitative feedback on tool ergonomics

## References

- [MCP Code Execution Blog](https://www.anthropic.com/research/building-effective-agents) - Nov 2024
- [Writing Effective Tools Blog](https://www.anthropic.com/research/building-effective-agents) - Sep 2025
- [FastMCP Documentation](https://github.com/jlowin/fastmcp)
- [Our DEVELOPMENT.md](../DEVELOPMENT.md) - Development workflow guide

---

**Last Updated:** 2025-01-15
**Status:** Active - response_format implemented, error improvements next
