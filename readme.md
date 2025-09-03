# README.md
# Geotab MCP Server

An MCP (Model Context Protocol) server that provides tools for interacting with the Geotab API with automatic authentication.

## Features

- **Auto-authentication**: Automatically authenticates when needed using environment variables
- **Secure credential management**: Uses .env files or environment variables  
- **No manual auth needed**: Claude doesn't need to call authenticate - it's handled transparently
- **Full dataset retrieval**: Can download complete datasets from Geotab queries

## Installation

1. Install the package:
```bash
pip install -r requirements.txt
```

2. Make the server executable:
```bash
chmod +x geotab_mcp_server.py
```

## Credential Setup

### Method 1: .env File (Recommended)

Create a `.env` file in the same directory as the server:

```env
GEOTAB_API_USERNAME=your_username_here
GEOTAB_API_PASSWORD=your_password_here  
GEOTAB_API_DATABASE=your_database_here
```

### Method 2: System Environment Variables

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

## Security & Credential Management

### How Claude Desktop Keeps Credentials Safe

Claude Desktop handles credentials securely through several mechanisms:

1. **Environment Variables in Process Isolation**: When you set credentials in the MCP server configuration, they're passed as environment variables to the server process. Claude Desktop itself never sees or stores your actual credentials.

2. **Process Separation**: The MCP server runs as a separate process from Claude Desktop. Your credentials only exist in the server's memory space.

3. **Local Configuration**: Your `claude_desktop_config.json` file is stored locally on your machine and never transmitted to Anthropic's servers.

### Recommended Setup Methods

#### Method 1: Environment Variables (Most Secure)

Set your credentials as system environment variables:

**macOS/Linux:**
```bash
export GEOTAB_API_USERNAME="your_username"
export GEOTAB_API_PASSWORD="your_password"
export GEOTAB_API_DATABASE="your_database"
```

Then configure Claude Desktop **without** credentials in the env section:

```json
{
  "mcpServers": {
    "geotab": {
      "command": "python",
      "args": ["/path/to/geotab_mcp_server.py"]
    }
  }
}
```

**Windows:**
```cmd
setx GEOTAB_API_USERNAME "your_username"
setx GEOTAB_API_PASSWORD "your_password" 
setx GEOTAB_API_DATABASE "your_database"
```

#### Method 2: Configuration File Environment Variables (Convenient)

If you prefer to keep credentials with the configuration:

```json
{
  "mcpServers": {
    "geotab": {
      "command": "python",
      "args": ["/path/to/geotab_mcp_server.py"],
      "env": {
        "GEOTAB_API_USERNAME": "your_username",
        "GEOTAB_API_PASSWORD": "your_password",
        "GEOTAB_API_DATABASE": "your_database"
      }
    }
  }
}
```

### What Happens to Your Credentials

1. **Never sent to Anthropic**: Your credentials are only used locally between Claude Desktop and your MCP server
2. **Not logged**: The server is designed not to log sensitive information
3. **Memory only**: Credentials are stored in the server process memory, not written to disk
4. **Process termination**: When Claude Desktop closes, the server process terminates and credentials are cleared from memory

### Additional Security Tips

- Use dedicated Geotab API accounts with minimal necessary permissions
- Regularly rotate your API credentials
- Consider using API keys instead of username/password if Geotab supports them
- Set appropriate file permissions on your configuration file (e.g., `chmod 600`)

## Configuration

Add this server to your Claude Desktop configuration:

### macOS
Edit `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "geotab": {
      "command": "python",
      "args": ["/path/to/geotab_mcp_server.py"],
      "env": {
        "GEOTAB_API_USERNAME": "your_username",
        "GEOTAB_API_PASSWORD": "your_password",
        "GEOTAB_API_DATABASE": "your_database"
      }
    }
  }
}
```

### Windows
Edit `%APPDATA%\Claude\claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "geotab": {
      "command": "python",
      "args": ["C:\\path\\to\\geotab_mcp_server.py"],
      "env": {
        "GEOTAB_API_USERNAME": "your_username",
        "GEOTAB_API_PASSWORD": "your_password",
        "GEOTAB_API_DATABASE": "your_database"
      }
    }
  }
}
```

## Usage

The server provides three main tools:

1. **geotab_authenticate** - Authenticate with the Geotab API
2. **geotab_ask_question** - Ask questions to the Geotab AI service
3. **geotab_get_chat_data** - Retrieve full datasets from previous questions

## Environment Variables

You can set these environment variables instead of passing credentials directly:

- `GEOTAB_API_USERNAME`
- `GEOTAB_API_PASSWORD` 
- `GEOTAB_API_DATABASE`

## Example Usage in Claude

Once configured, you can use commands like:

```
Please authenticate with Geotab using the configured credentials.

Ask Geotab: "Show me the top 5 vehicles with the highest fuel consumption this month"

Get the full data from the previous query.
```

Note: You no longer need to provide credentials directly to Claude - they're securely loaded from environment variables.

## Security Notes

- Store credentials as environment variables rather than hardcoding them
- The server handles authentication securely and doesn't log sensitive information
- Consider using encrypted storage for production deployments

## Development

To run the server directly for testing:

```bash
python geotab_mcp_server.py
```

The server will start and listen for MCP protocol messages on stdin/stdout.