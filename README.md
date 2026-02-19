# Geotab ACE MCP Server

An MCP (Model Context Protocol) server that provides Claude with tools to interact with the Geotab ACE AI service. This server enables Claude to ask questions about your fleet data and retrieve structured responses including datasets.

**Note**: This is an experimental project by Geotab's Felipe Hoffa (https://www.linkedin.com/in/hoffa). No official support is provided, but we welcome your feedback through GitHub issues.

## Features

- **Multi-Account Support**: Connect to multiple Geotab databases simultaneously
- **Automatic Authentication**: Handles Geotab API authentication transparently
- **Async Query Support**: Start long-running queries and check their progress
- **Full Dataset Retrieval**: Downloads complete datasets when available
- **DuckDB Integration**: Large datasets (>200 rows) are automatically cached in DuckDB for SQL analysis
- **SQL Query Interface**: Query cached datasets with SQL instead of retrieving thousands of rows
- **Multiple Query Workflows**: Synchronous and asynchronous query patterns
- **Debug Tools**: Built-in debugging for troubleshooting queries
- **Secure Credential Management**: Uses environment variables for credentials

## Quick Start

### 1. Install Dependencies

```bash
uv sync
```

### 2. Set Up Credentials

Create a `.env` file in the project directory:

**Single Account:**
```env
GEOTAB_API_USERNAME=your_username
GEOTAB_API_PASSWORD=your_password
GEOTAB_API_DATABASE=your_database_name
# GEOTAB_API_URL=https://alpha.geotab.com/apiv1  # Optional: for alpha.geotab.com access
```

**Multiple Accounts:**
```env
GEOTAB_ACCOUNT_1_NAME=fleet1
GEOTAB_ACCOUNT_1_USERNAME=user1@example.com
GEOTAB_ACCOUNT_1_PASSWORD=secret1
GEOTAB_ACCOUNT_1_DATABASE=db1

GEOTAB_ACCOUNT_2_NAME=fleet2
GEOTAB_ACCOUNT_2_USERNAME=user2@example.com
GEOTAB_ACCOUNT_2_PASSWORD=secret2
GEOTAB_ACCOUNT_2_DATABASE=db2
```

### 3. Test the Connection

```bash
uv run python geotab_ace.py --test
```

### 4. Configure Claude Desktop

Add to your Claude Desktop configuration file:

**macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
**Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "geotab": {
      "command": "uv",
      "args": ["run", "python", "/absolute/path/to/geotab_mcp_server.py"]
    }
  }
}
```

Alternative using the installed script:
```json
{
  "mcpServers": {
    "geotab": {
      "command": "uv",
      "args": ["run", "geotab-mcp-server"],
      "cwd": "/absolute/path/to/project"
    }
  }
}
```

### 5. Restart Claude Desktop

The server will automatically load credentials from your `.env` file.

## Available Tools

### `geotab_ask_question`
Ask a question and wait for the complete response (up to 60 seconds by default).

**Example**: "How many vehicles were active last week?"

### `geotab_start_query_async`
Start a complex query that may take several minutes to process. Returns tracking IDs immediately.

**Use for**: Complex analytics, large data exports, multi-step analyses

### `geotab_check_status`
Check the progress of an async query using its tracking IDs.

### `geotab_get_results`
Retrieve complete results from a finished query, including full datasets.

### `geotab_test_connection`
Test API connectivity and authentication - useful for troubleshooting.

### `geotab_debug_query`
Get detailed debug information about a query's response structure.

### `geotab_query_duckdb`
Execute SQL queries on large datasets cached in DuckDB. When Ace returns more than 200 rows, the data is automatically loaded into DuckDB instead of being sent to Claude.

**Example**: "Query the cached trip data with: SELECT driver_id, COUNT(*) as trips FROM ace_123_456 GROUP BY driver_id ORDER BY trips DESC LIMIT 10"

### `geotab_list_cached_datasets`
List all datasets currently cached in DuckDB with their metadata, including row counts, columns, and table names.

**Example**: "Show me what datasets are cached in DuckDB"

### `geotab_list_accounts`
List all configured Geotab accounts. Shows which accounts are available and which is the default.

**Example**: "List my Geotab accounts"

### Multi-Account Usage

All query tools accept an optional `account` parameter to specify which account to use:

```
Ask Geotab using fleet2: "How many vehicles do we have?"
```

If no account is specified, the default account is used (first account in multi-account setup, or "default" for single account).

## DuckDB Caching for Large Datasets

When Ace returns datasets with more than 200 rows, instead of sending all that data to Claude, the MCP server:

1. **Automatically loads** the data into an in-memory DuckDB database
2. **Returns metadata** including row count, column names, data types, and a sample of 20 rows
3. **Provides a table name** for querying the cached data
4. **Offers SQL capabilities** to analyze the data efficiently

This approach:
- Prevents overwhelming Claude with thousands of rows
- Enables powerful SQL-based analysis
- Keeps the full dataset accessible for complex queries
- Works transparently without manual configuration

**Example workflow:**
```
User: "Get all trips from last month"
→ Ace returns 10,000 rows
→ Server caches in DuckDB as table 'ace_chat123_msg456'
→ Claude sees: metadata + 20 sample rows + instructions

User: "Show me the top 10 drivers by trip count"
→ Claude queries: SELECT driver_id, COUNT(*) as trips FROM ace_chat123_msg456 GROUP BY driver_id ORDER BY trips DESC LIMIT 10
→ Returns aggregated results instantly
```

## Usage Patterns

### Simple Questions
```
Ask Geotab: "What's our total mileage for this month?"
```

### Complex Analysis
```
Start a complex Geotab analysis: "Generate a detailed fuel efficiency report for all vehicles, broken down by driver and route, for the past 3 months"

[Wait a few minutes, then:]

Check the status of my Geotab query with chat ID [chat_id] and message group ID [message_group_id]

Get the complete results from chat ID [chat_id] and message group ID [message_group_id]
```

### Troubleshooting
```
Test my Geotab connection
```

## Configuration Options

### Environment Variables

#### Single Account (Legacy)

| Variable | Description | Required |
|----------|-------------|----------|
| `GEOTAB_API_USERNAME` | Your Geotab username | Yes |
| `GEOTAB_API_PASSWORD` | Your Geotab password | Yes |
| `GEOTAB_API_DATABASE` | Your Geotab database name | Yes |
| `GEOTAB_API_URL` | Geotab API endpoint URL (default: `https://my.geotab.com/apiv1`) | No |
| `GEOTAB_DRIVER_PRIVACY_MODE` | Redact driver names in results (default: `true`) | No |

#### Multiple Accounts

Use numbered environment variables for each account:

| Variable | Description | Required |
|----------|-------------|----------|
| `GEOTAB_ACCOUNT_N_NAME` | Friendly name for the account (e.g., "fleet1") | Yes |
| `GEOTAB_ACCOUNT_N_USERNAME` | Geotab username for account N | Yes |
| `GEOTAB_ACCOUNT_N_PASSWORD` | Geotab password for account N | Yes |
| `GEOTAB_ACCOUNT_N_DATABASE` | Geotab database name for account N | Yes |

Where N is 1, 2, 3, etc. The first account (N=1) becomes the default.

### Driver Privacy Preserving Mode

By default, the server automatically redacts driver name information from query results to protect privacy. When enabled, any columns named `DisplayName`, `Display Name`, `LastName`, `Last Name`, `FirstName`, or `First Name` will have their values replaced with `*`.

To disable this feature:

```env
GEOTAB_DRIVER_PRIVACY_MODE=false
```

The feature is enabled by default and redacts driver names in both preview and full dataset downloads.

**Important Limitations**: This feature is designed to prevent **accidental exposure** of driver names. It is **not a security boundary** and cannot prevent:
- Malicious prompts that ask the AI to rename columns before returning data
- Queries that extract driver information through other column names or methods
- Deliberate attempts to circumvent the redaction

For true data protection, implement proper access controls at the Geotab API or database level. This feature provides a helpful safety net for accidental leaks, not a security guarantee.

### Alternative: System Environment Variables

Instead of using a `.env` file, you can set system environment variables:

**macOS/Linux:**
```bash
export GEOTAB_API_USERNAME="your_username"
export GEOTAB_API_PASSWORD="your_password"
export GEOTAB_API_DATABASE="your_database"
```

**Windows:**
```cmd
setx GEOTAB_API_USERNAME "your_username"
setx GEOTAB_API_PASSWORD "your_password"
setx GEOTAB_API_DATABASE "your_database"
```

## Security Considerations

### How Credentials Are Handled

1. **Local Only**: Credentials are only used locally between Claude Desktop and the MCP server
2. **Never Transmitted**: Your credentials are never sent to Anthropic's servers
3. **Process Isolation**: The MCP server runs as a separate process with its own memory space
4. **Session Management**: Authentication tokens are cached for efficiency but expire automatically

### Best Practices

- Use dedicated API accounts with minimal required permissions
- Rotate credentials regularly
- Set restrictive file permissions on your `.env` file: `chmod 600 .env`
- Monitor API usage through your Geotab account
- Use the test connection tool to verify setup before first use

## Troubleshooting

### Common Issues

**"Authentication failed"**
- Verify your credentials are correct in the `.env` file
- Check that your Geotab account has API access
- Ensure the database name is exact (case-sensitive)

**"No module named 'geotab_ace'"**
- Make sure both files are in the same directory
- If using uv, try: `uv run python -c "import geotab_ace"`
- Ensure you've run `uv sync` to install dependencies

**"Connection timeout"**
- Check your internet connection
- Verify Geotab services are operational
- Try increasing timeout values

**MCP Server Won't Start**
- Run `uv run python geotab_mcp_server.py test` to diagnose issues
- Check Claude Desktop logs for error messages
- Verify the file path in your configuration is correct and uses forward slashes

### Debug Commands

Test the utility directly:
```bash
# Test connection
uv run python geotab_ace.py --test

# Ask a simple question
uv run python geotab_ace.py --question "How many vehicles do we have?"

# Enable verbose logging
uv run python geotab_ace.py --question "Show me active vehicles" --verbose
```

Test the MCP server:
```bash
uv run python geotab_mcp_server.py test
```

## File Structure

```
geotab-mcp-server/
├── geotab_ace.py          # Core API client library
├── geotab_mcp_server.py   # MCP server implementation
├── pyproject.toml         # Project configuration and dependencies
├── .env                   # Your credentials (create this)
└── README.md             # This file
```

## Project Setup with uv

This project uses `uv` for modern Python dependency management. Here's how to work with it:

### Install uv (if you haven't already)
```bash
# macOS (using Homebrew - recommended)
brew install uv

# macOS/Linux (using curl)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"

# Or using pip
pip install uv
```

### Project Commands
```bash
# Install all dependencies
uv sync

# Run the server directly
uv run geotab-mcp-server

# Run with arguments
uv run python geotab_ace.py --test

# Add a new dependency
uv add some-package

# Update dependencies
uv sync --upgrade
```

## API Limits and Timeouts

- **Default question timeout**: 60 seconds
- **Async query timeout**: 300 seconds (5 minutes)
- **Session cache**: 1 hour
- **Connection timeout**: 60 seconds
- **Polling interval**: Starts at 2 seconds, increases progressively

## Dependencies

This project uses `pyproject.toml` for dependency management. Key dependencies:

- **aiohttp**: Async HTTP client for API calls
- **pandas**: Data manipulation and CSV processing
- **python-dotenv**: Environment variable loading
- **fastmcp**: MCP server framework

All dependencies are automatically managed by `uv sync`.

## Development

### Running Tests
```bash
# Test the core library
uv run python geotab_ace.py --test --verbose

# Test the MCP server
uv run python geotab_mcp_server.py test
```

### Logging

Enable verbose logging by setting the log level:
```bash
export GEOTAB_LOG_LEVEL=DEBUG
```

Or modify the logging configuration in the code.

## Roadmap

See [docs/improvements.md](docs/improvements.md) for planned enhancements and future features. We welcome contributions and feedback on priorities!

## Support

For issues with:
- **Geotab API access**: Contact your Geotab administrator
- **Credential setup**: Follow the security section above  
- **MCP integration**: Check the Claude Desktop documentation
- **This server**: Check the troubleshooting section or review server logs

## Further Documentation

For a comprehensive guide on building custom MCP servers for Geotab, see the [Custom MCP Guide](https://github.com/fhoffa/geotab-vibe-guide/blob/main/guides/CUSTOM_MCP_GUIDE.md).

## Version Information

- **API Version**: Uses Geotab API v1
- **MCP Protocol**: Compatible with Claude Desktop MCP implementation
- **Python**: Requires Python 3.7+

## License

This project is licensed under the Apache License 2.0 - see the [LICENSE](LICENSE) file for details.