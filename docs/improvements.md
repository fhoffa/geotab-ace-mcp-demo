# MCP Server Improvements

This document outlines potential improvements to make the Geotab ACE MCP server more robust, performant, and feature-rich.

## Priority Legend
- 🔴 **High Priority** - Significant impact on usability or reliability
- 🟡 **Medium Priority** - Nice-to-have improvements
- 🟢 **Low Priority** - Future enhancements

---

## Architecture & MCP Protocol (🟡)

### 1. Add MCP Resources
**Status**: Not implemented
**Priority**: 🟡 Medium

Currently the server only implements MCP tools. Adding resources would provide read-only access to:

- **Recent query history** - `geotab://history` - Last 10 queries with status
- **Cached results** - `geotab://cache/{query_id}` - Access to cached query results
- **Active queries** - `geotab://active` - List of currently running queries
- **Configuration** - `geotab://config` - Current connection and server settings

**Benefits**:
- Better observability into server state
- Allows Claude to understand context without making API calls
- Follows MCP best practices

**Implementation**: Add `@mcp.resource()` decorators in [geotab_mcp_server.py](../geotab_mcp_server.py)

### 2. Implement MCP Prompts
**Status**: Not implemented
**Priority**: 🟢 Low

Define reusable prompt templates for common workflows:

```python
@mcp.prompt()
def analyze_fleet_efficiency():
    """Template for fleet efficiency analysis"""

@mcp.prompt()
def safety_report():
    """Template for safety and compliance reporting"""

@mcp.prompt()
def maintenance_review():
    """Template for vehicle maintenance analysis"""
```

**Benefits**:
- Standardized queries for common use cases
- Easier onboarding for new users
- Consistent output formats

---

## Error Handling & Reliability (🔴)

### 3. Better Error Recovery
**Status**: Partial - basic retry in polling only
**Priority**: 🔴 High

**Current Issues**:
- Single API call failures abort entire operation
- No retry logic for transient network errors
- No circuit breaker for degraded services

**Proposed Solution**:
```python
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10)
)
async def _make_api_call_with_retry(self, ...):
    """API call with automatic retry logic"""
```

**Implementation**:
- Add `tenacity` dependency to [pyproject.toml](../pyproject.toml)
- Wrap critical API calls in retry decorator
- Add circuit breaker for repeated failures
- Better error messages with suggested recovery actions

### 4. Input Validation Layer
**Status**: Basic validation only
**Priority**: 🔴 High

**Current**: Only checks for empty questions and basic length limits

**Proposed**: Comprehensive validation before API calls:
- Question length limits with clear error messages
- Character encoding validation
- Injection attack prevention
- Parameter type checking
- Rate limiting per client

**Benefits**: Fail fast, better error messages, prevent API abuse

### 5. Graceful Degradation
**Status**: Partial - falls back to preview data
**Priority**: 🟡 Medium

**Enhancement**: Better handling when full dataset unavailable:
- Always return preview data + metadata about full dataset
- Provide download link/instructions when auto-download fails
- Option to download later via separate tool call
- Clear indication of partial vs complete results

---

## Performance (🔴)

### 6. Result Caching
**Status**: Not implemented
**Priority**: 🔴 High

**Current**: Every status check makes fresh API call

**Proposed**:
```python
from cachetools import TTLCache

class GeotabACEClient:
    def __init__(self):
        self._result_cache = TTLCache(maxsize=100, ttl=300)  # 5 min
        self._query_cache = TTLCache(maxsize=1000, ttl=3600)  # 1 hour
```

**Cache Strategy**:
- Cache completed queries for 1 hour
- Cache in-progress status for 30 seconds
- LRU eviction for old queries
- Optional persistent cache to disk

**Benefits**: Reduced API calls, faster responses, lower costs

### 7. Connection Pooling Enhancement
**Status**: Basic implementation exists
**Priority**: 🟡 Medium

**Current**: Creates new session for each request group

**Enhancement**:
- Persistent session across requests
- Connection keep-alive tuning
- DNS caching improvements
- HTTP/2 support if available

### 8. Streaming Support
**Status**: Not implemented
**Priority**: 🟡 Medium

**Current**: Loads entire dataset into memory

**Proposed**: Stream large datasets
```python
async def stream_dataset(self, query_result) -> AsyncIterator[pd.DataFrame]:
    """Stream dataset in chunks to avoid memory issues"""
    async for chunk in download_in_chunks(query_result.signed_urls[0]):
        yield pd.read_csv(StringIO(chunk))
```

**Benefits**: Handle datasets larger than memory, faster time-to-first-byte

### 9. Batch Operations
**Status**: Not implemented
**Priority**: 🟢 Low

Support multiple questions in parallel:
```python
@mcp.tool()
async def geotab_ask_multiple(questions: List[str]) -> List[str]:
    """Process multiple questions concurrently"""
```

---

## Developer Experience (🟡)

### 10. Dataset Sampling
**Status**: Not implemented
**Priority**: 🟡 Medium

**New Tool**: Preview dataset schema without downloading full data
```python
@mcp.tool()
async def geotab_preview_schema(chat_id: str, message_group_id: str) -> str:
    """Get dataset schema and sample rows without full download"""
```

**Returns**:
- Column names and types
- Row count
- Sample of 5-10 rows
- Data size estimate

**Use Case**: Let Claude understand data structure before deciding to download full dataset

### 11. Progress Notifications
**Status**: Not implemented
**Priority**: 🔴 High

**Current**: Silent polling, no feedback during long operations

**Proposed**: Real-time progress updates
- Percentage complete (if available from API)
- Estimated time remaining
- Current processing stage
- Callback mechanism for progress updates

**Implementation**: Use MCP server notifications or logging

### 12. Query Builder Helpers
**Status**: Not implemented
**Priority**: 🟢 Low

Tools to help construct queries:
```python
@mcp.tool()
async def geotab_list_available_metrics() -> str:
    """List all available metrics and dimensions"""

@mcp.tool()
async def geotab_suggest_query(intent: str) -> str:
    """Suggest query structure based on user intent"""
```

### 13. Enhanced Debugging
**Status**: Basic debug tool exists
**Priority**: 🟡 Medium

**Current**: `geotab_debug_query` shows raw API response

**Enhancement**: Structured debug output with:
- Request/response timing breakdown
- API call chain visualization
- Network latency analysis
- Data extraction diagnostics
- Performance metrics (time to first byte, total time, etc.)

---

## Security & Operations (🔴)

### 14. Rate Limiting
**Status**: Not implemented
**Priority**: 🔴 High

**Risk**: Accidental API abuse could impact account

**Proposed**:
```python
from aiolimiter import AsyncLimiter

class GeotabACEClient:
    def __init__(self):
        self._rate_limiter = AsyncLimiter(max_rate=10, time_period=60)  # 10/min
```

**Features**:
- Configurable rate limits via environment variables
- Per-endpoint rate limits
- Burst allowance for quick operations
- Clear error messages when rate limited

### 15. Audit Logging
**Status**: Basic logging only
**Priority**: 🟡 Medium

**Enhancement**: Comprehensive audit trail
- Log all queries with timestamps
- Track user actions (via Claude Desktop)
- Data access logging
- Export audit logs to file
- Compliance-ready format

**File**: `~/.geotab-mcp/audit.log`

### 16. Configuration Validation
**Status**: Basic check on startup
**Priority**: 🔴 High

**Current**: Only validates when first API call is made

**Enhancement**: Comprehensive startup validation
- Pre-flight checks before server starts
- Validate all environment variables
- Test API connectivity
- Check API permissions
- Validate API URL format
- Clear setup instructions in error messages

### 17. Health Checks
**Status**: Manual test tool only
**Priority**: 🟡 Medium

**Proposed**: Automated health monitoring
```python
@mcp.resource("geotab://health")
def get_health_status():
    """Real-time health status"""
    return {
        "api_status": "healthy",
        "last_successful_auth": "2025-10-21T10:30:00Z",
        "active_queries": 2,
        "error_rate": 0.01
    }
```

**Features**:
- Periodic connectivity checks
- Session expiration monitoring
- Alert on degraded performance

---

## Data Handling (🟡)

### 18. Multiple Output Formats
**Status**: Only string/DataFrame
**Priority**: 🟡 Medium

Support multiple export formats:
```python
@mcp.tool()
async def geotab_get_results(
    chat_id: str,
    message_group_id: str,
    format: str = "markdown"  # markdown, json, csv, parquet
) -> str:
```

**Formats**:
- **Markdown tables** (current default)
- **JSON** - for programmatic access
- **CSV** - for Excel/spreadsheet import
- **Parquet** - for big data tools

### 19. Data Transformation
**Status**: Not implemented
**Priority**: 🟢 Low

Built-in data operations before returning results:
```python
@mcp.tool()
async def geotab_query_and_transform(
    question: str,
    filters: Optional[Dict] = None,
    aggregations: Optional[List[str]] = None,
    limit: Optional[int] = None
) -> str:
    """Query with post-processing"""
```

**Operations**:
- Filter rows by condition
- Aggregate (sum, avg, count)
- Sort results
- Limit rows
- Select specific columns

### 20. Pagination
**Status**: Shows first N rows only
**Priority**: 🟡 Medium

**Current**: Returns preview of large datasets

**Enhancement**: True pagination support
```python
@mcp.tool()
async def geotab_get_page(
    chat_id: str,
    message_group_id: str,
    page: int = 1,
    page_size: int = 100
) -> str:
    """Get specific page of results"""
```

**Benefits**: Access to complete dataset without memory constraints

---

## Implementation Priority

### Phase 1: Stability & Reliability (🔴 High Priority)
1. ✅ Result caching (#6)
2. ✅ Better error recovery (#3)
3. ✅ Input validation (#4)
4. ✅ Rate limiting (#14)
5. ✅ Configuration validation (#16)
6. ✅ Progress notifications (#11)

### Phase 2: Performance & Scale (🟡 Medium Priority)
1. ✅ Streaming support (#8)
2. ✅ Dataset sampling (#10)
3. ✅ Graceful degradation (#5)
4. ✅ Enhanced debugging (#13)
5. ✅ MCP resources (#1)
6. ✅ Multiple output formats (#18)

### Phase 3: Developer Experience (🟢 Low Priority)
1. ✅ Pagination (#20)
2. ✅ MCP prompts (#2)
3. ✅ Batch operations (#9)
4. ✅ Query builder helpers (#12)
5. ✅ Data transformation (#19)

---

## Contributing

If you'd like to implement any of these improvements:

1. **Check existing issues** - Someone may already be working on it
2. **Create an issue** - Discuss the approach before implementing
3. **Follow coding standards** - Match existing style in [geotab_ace.py](../geotab_ace.py) and [geotab_mcp_server.py](../geotab_mcp_server.py)
4. **Add tests** - Include test coverage for new features
5. **Update documentation** - Update README.md with new features

## Questions?

Open a GitHub issue to discuss any of these improvements or suggest new ones!
