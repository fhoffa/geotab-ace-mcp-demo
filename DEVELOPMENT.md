# Development Guide

This guide covers development workflows, testing strategies, and best practices for contributing to the Geotab ACE MCP Server.

## Table of Contents

- [Development Setup](#development-setup)
- [Development Workflow](#development-workflow)
- [Testing](#testing)
- [Code Quality](#code-quality)
- [Debugging](#debugging)
- [MCP Server Development](#mcp-server-development)
- [Contributing](#contributing)

## Development Setup

### Prerequisites

- Python 3.10 or higher
- [uv](https://github.com/astral-sh/uv) package manager
- Geotab API credentials

### Initial Setup

```bash
# Clone the repository
git clone <repository-url>
cd geotab-ace-mcp-demo

# Install dependencies (including dev dependencies)
uv sync --all-groups

# Create environment configuration
cp .env.example .env
# Edit .env with your Geotab credentials

# Verify installation
uv run python geotab_ace.py --test
```

### Project Structure

```
geotab-ace-mcp-demo/
├── geotab_mcp_server.py      # Main MCP server implementation
├── geotab_ace.py              # Core API client library
├── duckdb_manager.py          # Dataset caching system
├── memory_manager.py          # Persistent memory storage
├── pyproject.toml             # Dependencies and configuration
├── .env                       # Credentials (gitignored)
├── tests/                     # Test suite
│   ├── __init__.py
│   └── test_mcp_server.py     # MCP server tests
├── docs/                      # Documentation
│   ├── api-context.md
│   ├── MEMORY_SYSTEM_DESIGN.md
│   └── improvements.md
├── .claude/                   # Claude Code configuration
│   └── mcp-config.example.json
└── .vscode/                   # VSCode configuration
    └── mcp-config.example.json
```

## Development Workflow

### 1. Make Changes

Edit the relevant files:
- **MCP tools**: Modify `geotab_mcp_server.py`
- **API client**: Modify `geotab_ace.py`
- **Data caching**: Modify `duckdb_manager.py`
- **Memory system**: Modify `memory_manager.py`

### 2. Run Tests

```bash
# Run all tests
pytest

# Run with verbose output
pytest -v

# Run specific test file
pytest tests/test_mcp_server.py

# Run specific test class
pytest tests/test_mcp_server.py::TestAccountManagement

# Run specific test
pytest tests/test_mcp_server.py::TestAccountManagement::test_list_accounts_returns_valid_response

# Run with coverage report
pytest --cov=geotab_mcp_server --cov=geotab_ace --cov=duckdb_manager --cov=memory_manager

# Run only fast tests (skip slow integration tests)
pytest -m "not slow"
```

### 3. Check Code Quality

```bash
# Format code with Black
uv run black geotab_*.py duckdb_manager.py memory_manager.py

# Lint with Ruff
uv run ruff check .

# Type check with MyPy
uv run mypy geotab_mcp_server.py geotab_ace.py

# Run all quality checks
uv run black --check . && uv run ruff check . && uv run mypy .
```

### 4. Test Locally

#### Test the Core Library

```bash
# Test connection
uv run python geotab_ace.py --test

# Ask a question
uv run python geotab_ace.py --question "How many vehicles do we have?"

# Enable verbose logging
uv run python geotab_ace.py --question "Show active vehicles" --verbose
```

#### Test the MCP Server

```bash
# Run server test mode
uv run python geotab_mcp_server.py test

# Start server with debug logging
export GEOTAB_LOG_LEVEL=DEBUG
uv run geotab-mcp-server
```

#### Test with MCP Inspector (Recommended)

The FastMCP development server provides an interactive UI for testing:

```bash
# Start development server with inspector
uv run fastmcp dev geotab_mcp_server.py

# Open browser to http://localhost:8000
# Test tools interactively in the web UI
```

### 5. Test with Claude Code / VSCode

#### Option A: Claude Code CLI

```bash
# Create local MCP configuration
mkdir -p ~/.claude
cp .claude/mcp-config.example.json ~/.claude/mcp.json

# Edit the config with absolute paths
# Then test in Claude Code CLI
```

#### Option B: VSCode

1. Copy `.vscode/mcp-config.example.json` to your VSCode settings
2. Update paths to absolute paths
3. Reload VSCode
4. Test in GitHub Copilot Chat

#### Option C: Claude Desktop

1. Copy configuration to Claude Desktop config file:
   - macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
   - Windows: `%APPDATA%\Claude\claude_desktop_config.json`

2. Restart Claude Desktop

3. Test in chat interface

### 6. Debug Issues

See [Debugging](#debugging) section below.

## Testing

### Test Organization

Tests are organized by component:

- `tests/test_mcp_server.py` - MCP server tools and integration
- `test_duckdb.py` - DuckDB caching functionality
- `test_memory.py` - Memory system persistence
- `test_multi_account.py` - Multi-account configuration
- `auth_test.py` - Authentication and API connection

### Writing Tests

#### FastMCP In-Memory Testing Pattern

```python
import pytest
from fastmcp.testing import MCPTestClient
from geotab_mcp_server import mcp

@pytest.fixture
def client():
    """Create an in-memory test client."""
    return MCPTestClient(mcp)

def test_tool_behavior(client):
    """Test a specific tool."""
    result = client.call_tool("geotab_list_accounts", {})
    assert result is not None
    assert isinstance(result, str)
```

#### Async Testing

```python
import pytest

@pytest.mark.asyncio
async def test_async_operation():
    """Test async functionality."""
    from geotab_ace import GeotabACEClient

    client = GeotabACEClient(username="test", password="test", database="test")
    # Your async test code here
```

#### Integration Tests

Mark slow integration tests:

```python
@pytest.mark.slow
@pytest.mark.integration
def test_full_workflow(client):
    """Test complete workflow (marked as slow)."""
    # Full integration test
```

Run without slow tests:
```bash
pytest -m "not slow"
```

### Test Coverage

```bash
# Generate coverage report
pytest --cov=. --cov-report=html

# View report
open htmlcov/index.html  # macOS
xdg-open htmlcov/index.html  # Linux
```

## Code Quality

### Code Formatting

We use **Black** with 100 character line length:

```bash
# Format all Python files
uv run black .

# Check formatting without changes
uv run black --check .
```

### Linting

We use **Ruff** for fast linting:

```bash
# Lint all files
uv run ruff check .

# Auto-fix issues
uv run ruff check --fix .
```

### Type Checking

We use **MyPy** for type checking:

```bash
# Type check main files
uv run mypy geotab_mcp_server.py geotab_ace.py

# Type check with stricter settings
uv run mypy --strict geotab_mcp_server.py
```

### Pre-commit Checklist

Before committing:

```bash
# 1. Format code
uv run black .

# 2. Run linter
uv run ruff check --fix .

# 3. Type check
uv run mypy geotab_mcp_server.py geotab_ace.py

# 4. Run tests
pytest

# 5. Check coverage
pytest --cov=. --cov-report=term-missing
```

## Debugging

### Enable Debug Logging

```bash
# Enable debug logging for all components
export GEOTAB_LOG_LEVEL=DEBUG

# Run server with debug logs
uv run python geotab_mcp_server.py
```

### Common Issues

#### "Authentication failed"

```bash
# Verify credentials
cat .env

# Test connection directly
uv run python geotab_ace.py --test --verbose

# Check account manager
uv run python -c "
from geotab_ace import AccountManager
mgr = AccountManager()
print(f'Accounts: {list(mgr.accounts.keys())}')
print(f'Default: {mgr.default_account}')
"
```

#### "Module not found"

```bash
# Reinstall dependencies
uv sync --reinstall

# Verify installation
uv run python -c "import geotab_ace; import fastmcp; print('OK')"
```

#### "MCP server won't start"

```bash
# Test server directly
uv run python geotab_mcp_server.py test

# Check for syntax errors
uv run python -m py_compile geotab_mcp_server.py

# Run with full traceback
uv run python geotab_mcp_server.py 2>&1 | tee server.log
```

### Debugging Tools

```bash
# Interactive Python shell with project context
uv run python

>>> from geotab_ace import GeotabACEClient
>>> import asyncio
>>> # Test code interactively
```

### VS Code Debugging

Create `.vscode/launch.json`:

```json
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "Debug MCP Server",
      "type": "python",
      "request": "launch",
      "program": "${workspaceFolder}/geotab_mcp_server.py",
      "console": "integratedTerminal",
      "env": {
        "GEOTAB_LOG_LEVEL": "DEBUG"
      }
    },
    {
      "name": "Run Tests",
      "type": "python",
      "request": "launch",
      "module": "pytest",
      "args": ["-v"],
      "console": "integratedTerminal"
    }
  ]
}
```

## MCP Server Development

### Adding New Tools

1. **Define the tool** with `@mcp.tool()` decorator:

```python
@mcp.tool()
async def geotab_new_tool(param: str, optional_param: Optional[str] = None) -> str:
    """
    Tool description that Claude will see.

    Args:
        param: Description of required parameter
        optional_param: Description of optional parameter

    Returns:
        Formatted response string
    """
    try:
        client = get_ace_client()
        # Implementation
        return "Success: result"
    except AuthenticationError as e:
        return f"Authentication failed: {e}"
    except Exception as e:
        logger.error(f"Error in geotab_new_tool: {e}", exc_info=True)
        return f"Error: {e}"
```

2. **Write tests** for the new tool:

```python
def test_new_tool(client):
    """Test the new tool."""
    result = client.call_tool("geotab_new_tool", {
        "param": "test_value"
    })
    assert result is not None
    assert "Success" in result
```

3. **Update documentation** in README.md

4. **Test interactively** with MCP inspector:

```bash
uv run fastmcp dev geotab_mcp_server.py
```

### Adding New Resources

```python
@mcp.resource("geotab://resource/path")
def get_resource_data() -> str:
    """
    Resource description.

    Resources provide static or dynamic data that Claude can access.
    """
    return json.dumps({
        "data": "value"
    })
```

### Best Practices

1. **Error Handling**: Always catch specific exceptions and return user-friendly messages
2. **Logging**: Log errors with context for debugging
3. **Type Hints**: Use proper type hints for all parameters and return values
4. **Documentation**: Include comprehensive docstrings with examples
5. **Testing**: Write tests before implementing (TDD recommended)
6. **Validation**: Validate inputs and handle edge cases
7. **Async**: Use async/await for all I/O operations

## Contributing

### Contribution Workflow

1. **Fork** the repository
2. **Create a branch** for your feature: `git checkout -b feature/my-feature`
3. **Make changes** following the development workflow above
4. **Write tests** for new functionality
5. **Run quality checks** (format, lint, type check, test)
6. **Commit** with clear messages
7. **Push** to your fork
8. **Create a Pull Request** with description

### Commit Messages

Use clear, descriptive commit messages:

```
Add support for custom timeout per account

- Add timeout_override field to GeotabCredentials
- Update AccountManager to handle per-account timeouts
- Add tests for timeout configuration
- Update documentation
```

### Code Review

All changes require:
- [ ] Tests passing
- [ ] Code formatted with Black
- [ ] No linting errors
- [ ] Type checking passing
- [ ] Documentation updated
- [ ] No breaking changes (or clearly documented)

## Resources

- [FastMCP Documentation](https://github.com/jlowin/fastmcp)
- [Model Context Protocol Specification](https://github.com/modelcontextprotocol/specification)
- [Geotab API Documentation](https://geotab.github.io/sdk/software/api/reference/)
- [Project Issue Tracker](../../issues)

## Getting Help

- **Issues**: Check existing issues or create a new one
- **Documentation**: Review docs/ folder for detailed guides
- **Logs**: Enable debug logging for troubleshooting
- **Community**: Ask questions in discussions

## Next Steps

After setting up your development environment:

1. Read [docs/api-context.md](docs/api-context.md) for Geotab ACE API details
2. Review [docs/MEMORY_SYSTEM_DESIGN.md](docs/MEMORY_SYSTEM_DESIGN.md) for memory system architecture
3. Check [docs/improvements.md](docs/improvements.md) for contribution ideas
4. Run the test suite to ensure everything works
5. Try making a small change and testing it end-to-end

Happy coding! 🚀
