#!/usr/bin/env python3
"""
Geotab MCP Server

A focused MCP server that provides tools for interacting with the Geotab ACE API.
Uses the geotab_ace utility library for clean separation of concerns.
"""

import asyncio
import json
import logging
import sys
import traceback
from typing import Optional

from fastmcp import FastMCP
from geotab_ace import (
    GeotabACEClient, QueryStatus,
    GeotabACEError, AuthenticationError, APIError, TimeoutError
)
from duckdb_manager import DuckDBManager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stderr)]
)
logger = logging.getLogger("geotab-mcp-server")

# Create MCP server instance
mcp = FastMCP("geotab-mcp-server")

# Global client instance
ace_client: Optional[GeotabACEClient] = None

# Global DuckDB manager instance
duckdb_manager: Optional[DuckDBManager] = None


def get_duckdb_manager() -> DuckDBManager:
    """Get or create the DuckDB manager instance."""
    global duckdb_manager
    if duckdb_manager is None:
        duckdb_manager = DuckDBManager()
    return duckdb_manager


def get_ace_client() -> GeotabACEClient:
    """Get or create the ACE client instance."""
    global ace_client
    if ace_client is None:
        ace_client = GeotabACEClient()
    return ace_client


def format_query_result(result, chat_id: str = "", message_group_id: str = "") -> str:
    """Format a QueryResult for display focusing on key information."""
    parts = []
    
    if result.status == QueryStatus.DONE:
        # Show SQL query first if available
        if result.sql_query:
            parts.append(f"**SQL Query:**\n```sql\n{result.sql_query}\n```")
        
        # Show reasoning 
        if result.reasoning:
            parts.append(f"**Analysis:**\n{result.reasoning}")
        
        # Show interpretation if different from reasoning
        if result.interpretation and result.interpretation != result.reasoning:
            parts.append(f"**Interpretation:**\n{result.interpretation}")

        # Data results
        if result.data_frame is not None and not result.data_frame.empty:
            df = result.data_frame
            preview_rows = min(20, len(df))
            preview_table = df.head(preview_rows).to_string(index=False, max_colwidth=40)
            
            parts.append(f"**Data Results ({len(df)} rows):**")
            parts.append(f"```\n{preview_table}\n```")

            if len(df) > preview_rows:
                parts.append(f"*Showing {preview_rows} of {len(df)} total rows*")

            if result.signed_urls:
                parts.append("*Full dataset available via signed URL*")

        elif result.preview_data:
            parts.append(f"**Data Preview:**\n```json\n{json.dumps(result.preview_data[:3], indent=2)}\n```")

        if not parts:
            parts.append("Query completed but no results returned.")
            
    elif result.status == QueryStatus.FAILED:
        parts.append(f"**Query Failed:** {result.error or 'Unknown error'}")
        
    elif result.status in [QueryStatus.PROCESSING, QueryStatus.PENDING]:
        parts.append(f"**Status:** {result.status.value} - Still processing...")
        if chat_id and message_group_id:
            parts.append(f"**Tracking:** Chat `{chat_id}`, Message Group `{message_group_id}`")
    else:
        parts.append(f"**Unknown Status:** {result.status.value}")
        
    return "\n\n".join(parts)


@mcp.tool()
async def geotab_ask_question(question: str, timeout_seconds: int = 60) -> str:
    """
    Ask a question to Geotab ACE AI and wait for the response.
    
    Args:
        question (str): The question to ask the Geotab AI service
        timeout_seconds (int): Maximum time to wait for response (default: 60 seconds)
        
    Returns:
        str: The response from Geotab AI, including SQL query, analysis, and data
    """
    try:
        if not question or not question.strip():
            return "❌ Error: Question cannot be empty"
            
        if len(question) > 10000:
            return "❌ Error: Question too long (max 10,000 characters)"
            
        logger.info(f"Asking question (timeout: {timeout_seconds}s): {question[:100]}...")
        
        client = get_ace_client()
        
        # Start the query
        chat_id, message_group_id = await client.start_query(question.strip())
        logger.info(f"Started query: chat_id={chat_id}, message_group_id={message_group_id}")
        
        try:
            # Wait for completion
            result = await client.wait_for_completion(chat_id, message_group_id, timeout_seconds)
            
            # Format the response
            response = format_query_result(result, chat_id, message_group_id)
            
            # Add timing info and tracking
            response += f"\n\n📋 **Query IDs**: Chat `{chat_id}`, Message Group `{message_group_id}`"
            
            return response
            
        except TimeoutError:
            return f"""⏱️ Query is taking longer than {timeout_seconds} seconds to process.

❓ **Question**: {question[:200]}{'...' if len(question) > 200 else ''}

📋 **Tracking Information**:
• Chat ID: `{chat_id}`  
• Message Group ID: `{message_group_id}`

🔄 **Next Steps**:
• Use `geotab_check_status('{chat_id}', '{message_group_id}')` to check progress
• Use `geotab_get_results('{chat_id}', '{message_group_id}')` to get results when ready"""
            
    except AuthenticationError as e:
        logger.error(f"Authentication error: {e}")
        return f"🔐 **Authentication Error**: {e}\n\nPlease check your Geotab credentials in environment variables."
    except APIError as e:
        logger.error(f"API error: {e}")
        return f"🌐 **API Error**: {e}"
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        logger.error(traceback.format_exc())
        return f"💥 **Unexpected Error**: {str(e)}\n\nPlease check the server logs for details."


@mcp.tool()
async def geotab_check_status(chat_id: str, message_group_id: str) -> str:
    """
    Check the status of a running Geotab query.
    
    Args:
        chat_id (str): Chat ID from a previous question
        message_group_id (str): Message group ID from a previous question
        
    Returns:
        str: Current status of the query with any available partial results
    """
    try:
        if not chat_id or not message_group_id:
            return "❌ Error: Both chat_id and message_group_id are required"
            
        logger.debug(f"Checking status for {chat_id}/{message_group_id}")
        
        client = get_ace_client()
        result = await client.get_query_status(chat_id, message_group_id)
        
        response = format_query_result(result, chat_id, message_group_id)
        
        if result.status == QueryStatus.DONE:
            response += f"\n\n🎯 **Get Full Results**: Use `geotab_get_results('{chat_id}', '{message_group_id}')` for complete data"
            
        return response
        
    except AuthenticationError as e:
        return f"🔐 **Authentication Error**: {e}"
    except APIError as e:
        return f"🌐 **API Error**: {e}"
    except Exception as e:
        logger.error(f"Error checking status: {e}")
        logger.error(traceback.format_exc())
        return f"💥 **Error**: {str(e)}"


@mcp.tool()
async def geotab_get_results(chat_id: str, message_group_id: str, include_full_data: bool = True) -> str:
    """
    Get the complete results from a completed Geotab query.
    
    Args:
        chat_id (str): Chat ID from a previous question
        message_group_id (str): Message group ID from a previous question
        include_full_data (bool): Whether to download the full dataset (default: True)
        
    Returns:
        str: Complete results including SQL query, analysis, and full dataset
    """
    try:
        if not chat_id or not message_group_id:
            return "❌ Error: Both chat_id and message_group_id are required"
            
        logger.info(f"Getting results for {chat_id}/{message_group_id} (full_data={include_full_data})")
        
        client = get_ace_client()
        result = await client.get_query_status(chat_id, message_group_id)
        
        if result.status != QueryStatus.DONE:
            if result.status == QueryStatus.FAILED:
                return f"❌ **Query Failed**: {result.error or 'Unknown error'}"
            else:
                return f"🔄 **Query Not Ready**: Status is {result.status.value}. Please wait and try again."
            
        # Get full dataset if requested and available
        if include_full_data and result.signed_urls:
            try:
                logger.debug("Downloading full dataset...")
                full_df = await client.get_full_dataset(result)
                if full_df is not None:
                    result.data_frame = full_df
                    logger.info(f"Downloaded full dataset: {len(full_df)} rows")
            except Exception as e:
                logger.warning(f"Failed to download full dataset: {e}")
        
        parts = []
        
        # Add SQL query first
        if result.sql_query:
            parts.append(f"🗄️ **SQL Query**\n```sql\n{result.sql_query}\n```")
        
        # Add all available analysis
        analysis_parts = []
        if result.reasoning:
            analysis_parts.append(f"**Reasoning**: {result.reasoning}")
        if result.analysis:
            analysis_parts.append(f"**Analysis**: {result.analysis}")
        if result.interpretation:
            analysis_parts.append(f"**Interpretation**: {result.interpretation}")
        if result.insight:
            analysis_parts.append(f"**Insight**: {result.insight}")
        if result.understanding:
            analysis_parts.append(f"**Understanding**: {result.understanding}")
        if result.process:
            analysis_parts.append(f"**Process**: {result.process}")
        
        if analysis_parts:
            parts.append(f"🧠 **AI Analysis**\n{chr(10).join(analysis_parts)}")
        
        # Add main text response
        if result.text_response:
            parts.append(f"📝 **Summary**\n{result.text_response}")
        
        # Add comprehensive dataset information
        if result.data_frame is not None and not result.data_frame.empty:
            df = result.data_frame

            # For large datasets (>200 rows), load into DuckDB instead of returning all data
            # Threshold rationale:
            # - Claude can handle ~200 rows efficiently in context without overwhelming tokens
            # - Larger datasets overwhelm token limits and reduce analysis quality
            # - DuckDB enables SQL-based analysis which is more appropriate for large data
            # - Provides better UX by showing metadata + sample instead of flooding with data
            DUCKDB_THRESHOLD = 200
            if len(df) > DUCKDB_THRESHOLD:
                # Store in DuckDB
                db_manager = get_duckdb_manager()
                table_name = db_manager.store_dataframe(
                    chat_id=chat_id,
                    message_group_id=message_group_id,
                    df=df,
                    question=result.text_response[:200] if result.text_response else "",
                    sql_query=result.sql_query or ""
                )

                # Show sample data
                sample_size = 20
                sample_df = df.head(sample_size)
                preview_table = sample_df.to_string(index=False, max_colwidth=40)

                parts.append(f"📊 **Large Dataset Loaded into DuckDB**")
                parts.append(f"• **Total Rows**: {len(df):,}")
                parts.append(f"• **Columns**: {len(df.columns)}")
                parts.append(f"• **Table Name**: `{table_name}`")
                parts.append(f"\n**Sample Data** (first {sample_size} of {len(df):,} rows):")
                parts.append(f"```\n{preview_table}\n```")

                # Add column information
                parts.append(f"\n📋 **All Columns ({len(df.columns)})**:")
                parts.append(f"{', '.join(df.columns.astype(str))}")

                # Add basic statistics for numeric columns
                numeric_cols = df.select_dtypes(include=['number']).columns
                if len(numeric_cols) > 0:
                    parts.append(f"\n📊 **Numeric Columns ({len(numeric_cols)})**:")
                    stats_info = []
                    for col in numeric_cols[:10]:  # Limit to first 10 numeric columns
                        try:
                            stats_info.append(f"  • {col}: min={df[col].min():,.1f}, max={df[col].max():,.1f}, avg={df[col].mean():,.1f}")
                        except Exception:
                            continue
                    if stats_info:
                        parts.append("\n".join(stats_info))

                # Instructions for querying
                parts.append(f"\n💡 **Query this data with SQL**:")
                parts.append(f"Use `geotab_query_duckdb('{table_name}', 'YOUR SQL QUERY')` to analyze this dataset.")
                parts.append(f"Example: `geotab_query_duckdb('{table_name}', 'SELECT * FROM {table_name} WHERE column_name > 100 ORDER BY date DESC LIMIT 50')`")

            else:
                # Normal flow for smaller datasets
                preview_rows = min(100 if include_full_data else 50, len(df))
                preview_table = df.head(preview_rows).to_string(index=False, max_colwidth=40)

                data_source = "complete dataset" if result.signed_urls and include_full_data else "preview data"
                dataset_info = f"📊 **Dataset** ({data_source}: {len(df)} rows × {len(df.columns)} columns)"

                if len(df) <= preview_rows:
                    parts.append(f"{dataset_info}\n```\n{preview_table}\n```")
                else:
                    parts.append(f"{dataset_info}\n```\n{preview_table}\n\n... and {len(df) - preview_rows} more rows\n```")

                # Add column information for datasets with many columns
                if len(df.columns) > 10:
                    parts.append(f"📋 **All Columns**: {', '.join(df.columns.astype(str))}")

                # Add basic statistics for numeric columns
                numeric_cols = df.select_dtypes(include=['number']).columns
                if len(numeric_cols) > 0 and len(numeric_cols) <= 5:
                    stats_info = []
                    for col in numeric_cols:
                        try:
                            total = df[col].sum()
                            avg = df[col].mean()
                            stats_info.append(f"{col}: Total={total:,.0f}, Avg={avg:.1f}")
                        except Exception:
                            continue
                    if stats_info:
                        parts.append(f"📊 **Quick Stats**: {'; '.join(stats_info)}")
        
        if not parts:
            parts.append("✅ Query completed successfully but no data or analysis returned.")
            
        return "\n\n".join(parts)
        
    except AuthenticationError as e:
        return f"🔐 **Authentication Error**: {e}"
    except APIError as e:
        return f"🌐 **API Error**: {e}"
    except Exception as e:
        logger.error(f"Error getting results: {e}")
        logger.error(traceback.format_exc())
        return f"💥 **Error**: {str(e)}"


@mcp.tool()
async def geotab_start_query_async(question: str) -> str:
    """
    Start a Geotab query asynchronously and return tracking IDs immediately.
    Use this for complex queries that need extended processing time.
    
    Args:
        question (str): The question to ask the Geotab AI service
        
    Returns:
        str: Tracking information for the started query
    """
    try:
        if not question or not question.strip():
            return "❌ Error: Question cannot be empty"
            
        if len(question) > 50000:
            return "❌ Error: Question too long (max 50,000 characters)"
            
        logger.info(f"Starting async query: {question[:100]}...")
        
        client = get_ace_client()
        chat_id, message_group_id = await client.start_query(question.strip())
        
        return f"""🚀 **Query Started Successfully**

❓ **Question**: {question[:300]}{'...' if len(question) > 300 else ''}

🆔 **Tracking Information**:
• Chat ID: `{chat_id}`
• Message Group ID: `{message_group_id}`

🔄 **Next Steps**:
1. **Check Status**: `geotab_check_status('{chat_id}', '{message_group_id}')`
2. **Get Results**: `geotab_get_results('{chat_id}', '{message_group_id}')` (when ready)

⏱️ **Expected Processing Time**: 30 seconds to 5 minutes depending on query complexity"""
        
    except AuthenticationError as e:
        return f"🔐 **Authentication Error**: {e}"
    except APIError as e:
        return f"🌐 **API Error**: {e}"
    except Exception as e:
        logger.error(f"Error starting async query: {e}")
        logger.error(traceback.format_exc())
        return f"💥 **Error**: {str(e)}"


@mcp.tool()
async def geotab_test_connection() -> str:
    """
    Test the connection to Geotab API and verify authentication.
    Use this to diagnose connection issues.
    
    Returns:
        str: Connection test results and diagnostic information
    """
    try:
        logger.info("Testing Geotab connection...")
        
        client = get_ace_client()
        test_result = await client.test_connection()
        
        parts = ["🔧 **Connection Test Results**"]
        
        # Configuration check
        if test_result["config_valid"]:
            parts.append("✅ **Configuration**: Environment variables found")
        else:
            parts.append("❌ **Configuration**: Missing environment variables")
        
        # Authentication check
        if test_result["auth_successful"]:
            session_info = test_result.get("session_id", "Unknown")
            parts.append(f"✅ **Authentication**: Successful")
            parts.append(f"📋 **Database**: {test_result.get('database', 'Unknown')}")
            parts.append(f"🔑 **Session ID**: {session_info}")
        else:
            parts.append("❌ **Authentication**: Failed")
        
        # API check
        if test_result["api_working"]:
            parts.append("✅ **API Calls**: Working properly")
        else:
            parts.append("❌ **API Calls**: Failed")
        
        # Overall status
        all_good = test_result["config_valid"] and test_result["auth_successful"] and test_result["api_working"]
        if all_good:
            parts.append("\n🎉 **Overall Status**: All systems operational! Ready to process queries.")
        else:
            parts.append("\n⚠️ **Overall Status**: Issues detected - see troubleshooting below")
        
        # Errors and troubleshooting
        if test_result["errors"]:
            parts.append("\n🚨 **Errors Detected**:")
            for error in test_result["errors"]:
                parts.append(f"• {error}")
                
            parts.append("\n🛠️ **Troubleshooting Steps**:")
            parts.append("1. **Environment Variables**: Verify these are set correctly:")
            parts.append("   • `GEOTAB_API_USERNAME` - Your Geotab username")
            parts.append("   • `GEOTAB_API_PASSWORD` - Your Geotab password") 
            parts.append("   • `GEOTAB_API_DATABASE` - Your Geotab database name")
            parts.append("2. **Account Access**: Ensure your Geotab account has API access permissions")
            parts.append("3. **Network**: Check internet connectivity and firewall settings")
            parts.append("4. **Credentials**: Verify username/password work in Geotab web interface")
        
        return "\n".join(parts)
        
    except Exception as e:
        logger.error(f"Error in connection test: {e}")
        logger.error(traceback.format_exc())
        return f"""💥 **Connection Test Failed**

🚨 **Error**: {str(e)}

🛠️ **Quick Setup Guide**:
1. Create a `.env` file in your project directory:
```env
GEOTAB_API_USERNAME=your_username
GEOTAB_API_PASSWORD=your_password
GEOTAB_API_DATABASE=your_database
```

2. Or set environment variables in your system:
```bash
export GEOTAB_API_USERNAME="your_username"
export GEOTAB_API_PASSWORD="your_password" 
export GEOTAB_API_DATABASE="your_database"
```

3. Restart the MCP server after setting variables
4. Check server logs for detailed error information"""


@mcp.tool()
async def geotab_debug_query(chat_id: str, message_group_id: str) -> str:
    """
    Debug function to see raw response data and detailed extraction info from a query.
    
    Args:
        chat_id (str): Chat ID from a previous question
        message_group_id (str): Message group ID from a previous question
        
    Returns:
        str: Raw debug information about the query response and data extraction
    """
    try:
        if not chat_id or not message_group_id:
            return "❌ Error: Both chat_id and message_group_id are required"

        logger.info(f"Debug query for {chat_id}/{message_group_id}")

        client = get_ace_client()
        result = await client.get_query_status(chat_id, message_group_id)

        # Return the full raw API response as formatted JSON
        debug_info = []
        debug_info.append(f"🔍 **Raw API Response for Query {message_group_id}**\n")
        debug_info.append(f"**Status**: {result.status.value}\n")
        debug_info.append("**Full Response**:")
        debug_info.append(f"```json\n{json.dumps(result.raw_response, indent=2)}\n```")

        return "\n".join(debug_info)
        
    except Exception as e:
        logger.error(f"Error in debug query: {e}")
        return f"💥 **Debug Error**: {str(e)}"


@mcp.tool()
async def geotab_query_duckdb(table_name: str, sql_query: str, limit: int = 1000) -> str:
    """
    Execute a SQL query on a dataset cached in DuckDB.

    When Ace returns large datasets (>200 rows), they are automatically loaded into
    DuckDB. Use this tool to run SQL queries and analyze the data.

    Args:
        table_name (str): Name of the table to query (provided when dataset was loaded)
        sql_query (str): SQL query to execute (DuckDB SQL syntax)
        limit (int): Maximum rows to return (default: 1000, safety limit)

    Returns:
        str: Query results formatted as a table with metadata

    Example:
        geotab_query_duckdb('ace_123_456', 'SELECT device_id, COUNT(*) as trips FROM ace_123_456 GROUP BY device_id ORDER BY trips DESC')
    """
    try:
        if not table_name or not sql_query:
            return "Error: Both table_name and sql_query are required"

        db_manager = get_duckdb_manager()

        # Check if table exists
        if not db_manager.table_exists(table_name):
            available = db_manager.list_datasets()
            if available:
                table_list = "\n".join([f"• `{ds['table_name']}` ({ds['row_count']:,} rows)" for ds in available])
                return f"Table '{table_name}' not found.\n\nAvailable tables:\n{table_list}\n\nUse geotab_list_cached_datasets() for more details."
            else:
                return "No cached datasets available. Large datasets (>200 rows) are automatically cached when retrieved from Ace."

        logger.info(f"Executing DuckDB query on {table_name}: {sql_query[:100]}...")

        # Execute query
        result_df, metadata = db_manager.query(sql_query, limit=limit)

        parts = []
        parts.append(f"**Query Results**")
        parts.append(f"• Table: `{table_name}`")
        parts.append(f"• Rows returned: {metadata['row_count']:,}")
        parts.append(f"• Columns: {metadata['column_count']}")

        if len(result_df) == 0:
            parts.append("\nNo rows matched your query.")
        else:
            # Show results
            max_display_rows = min(100, len(result_df))
            result_table = result_df.head(max_display_rows).to_string(index=False, max_colwidth=50)

            parts.append(f"\n**Results:**\n```\n{result_table}\n```")

            if len(result_df) > max_display_rows:
                parts.append(f"\n*Showing {max_display_rows} of {len(result_df)} rows*")

            # Add statistics for numeric columns
            numeric_cols = result_df.select_dtypes(include=['number']).columns
            if len(numeric_cols) > 0 and len(numeric_cols) <= 5:
                parts.append(f"\n**Statistics:**")
                for col in numeric_cols:
                    try:
                        parts.append(f"• {col}: min={result_df[col].min():,.1f}, max={result_df[col].max():,.1f}, avg={result_df[col].mean():,.1f}, total={result_df[col].sum():,.1f}")
                    except Exception:
                        continue

        # Show the original dataset info
        dataset_info = db_manager.get_dataset_info(table_name)
        if dataset_info and dataset_info.get('sql_query'):
            parts.append(f"\n**Original Ace Query:**\n```sql\n{dataset_info['sql_query']}\n```")

        return "\n".join(parts)

    except Exception as e:
        logger.error(f"Error querying DuckDB: {e}")
        logger.error(traceback.format_exc())
        return f"Error executing query: {str(e)}\n\nMake sure your SQL syntax is correct and the table name exists."


@mcp.tool()
async def geotab_list_cached_datasets() -> str:
    """
    List all datasets currently cached in DuckDB.

    Shows metadata about each cached dataset including row counts, columns,
    and the original question that generated the data.

    Returns:
        str: List of cached datasets with their metadata
    """
    try:
        db_manager = get_duckdb_manager()
        datasets = db_manager.list_datasets()

        if not datasets:
            return """No cached datasets available.

Large datasets (>200 rows) from Ace queries are automatically cached in DuckDB.
When you retrieve results with more than 200 rows, they will appear here."""

        parts = [f"**Cached Datasets in DuckDB** ({len(datasets)} total)\n"]

        for ds in datasets:
            parts.append(f"**Table: `{ds['table_name']}`**")
            parts.append(f"• Rows: {ds['row_count']:,}")
            parts.append(f"• Columns: {ds['column_count']} ({', '.join(ds['columns'][:5])}{'...' if ds['column_count'] > 5 else ''})")
            if ds.get('question'):
                parts.append(f"• Original question: {ds['question'][:100]}...")
            if ds.get('sql_query'):
                parts.append(f"• Ace SQL: `{ds['sql_query'][:100]}...`")
            parts.append(f"• Created: {ds['created_at']}")
            parts.append(f"• Query IDs: Chat `{ds['chat_id']}`, Message Group `{ds['message_group_id']}`")
            parts.append("")

        parts.append("**Usage:**")
        parts.append("Use `geotab_query_duckdb('table_name', 'SQL QUERY')` to analyze any of these datasets.")
        parts.append("\nExample: `geotab_query_duckdb('ace_123_456', 'SELECT * FROM ace_123_456 LIMIT 10')`")

        return "\n".join(parts)

    except Exception as e:
        logger.error(f"Error listing datasets: {e}")
        return f"Error listing datasets: {str(e)}"


@mcp.resource("geotab://status")
def get_server_status():
    """Get current server status and capability information."""
    try:
        global ace_client, duckdb_manager
        db_info = {}
        if duckdb_manager is not None:
            datasets = duckdb_manager.list_datasets()
            db_info = {
                "duckdb_enabled": True,
                "cached_datasets": len(datasets),
                "total_cached_rows": sum(ds['row_count'] for ds in datasets)
            }
        else:
            db_info = {"duckdb_enabled": False}

        return {
            "server": "geotab-mcp-server",
            "version": "3.0-duckdb",
            "status": "running",
            "client_initialized": ace_client is not None,
            **db_info,
            "features": [
                "SQL query extraction",
                "Enhanced reasoning capture",
                "Full dataset download",
                "Async query processing",
                "Comprehensive debugging",
                "DuckDB caching for large datasets",
                "SQL querying on cached data"
            ],
            "tools_available": [
                "geotab_ask_question",
                "geotab_check_status",
                "geotab_get_results",
                "geotab_start_query_async",
                "geotab_test_connection",
                "geotab_debug_query",
                "geotab_query_duckdb",
                "geotab_list_cached_datasets"
            ]
        }
    except Exception as e:
        return {
            "server": "geotab-mcp-server",
            "status": "error",
            "error": str(e)
        }


def main():
    """Main function to run the MCP server."""
    try:
        logger.info("Starting Enhanced Geotab MCP Server...")
        logger.info(f"Python version: {sys.version}")
        
        # Test if we can create a client (this will validate env vars)
        try:
            test_client = GeotabACEClient()
            logger.info("✅ Client initialization successful")
        except AuthenticationError as e:
            logger.warning(f"⚠️ Client initialization failed: {e}")
            logger.warning("Server will start but authentication will fail until environment variables are set")
        except Exception as e:
            logger.error(f"❌ Unexpected error during client initialization: {e}")
        
        # Run the MCP server
        logger.info("🚀 Enhanced MCP Server starting with SQL extraction and full data support...")
        mcp.run()
        
    except KeyboardInterrupt:
        logger.info("Server shutdown requested")
    except Exception as e:
        logger.error(f"Fatal error in main: {e}")
        logger.error(traceback.format_exc())
        raise


if __name__ == "__main__":
    try:
        # For direct testing of the utility
        if len(sys.argv) > 1 and sys.argv[1] == "test":
            async def test_utility():
                from geotab_ace import test_connection_simple
                try:
                    result = await test_connection_simple()
                    print("Test results:", result)
                except Exception as e:
                    print(f"Test failed: {e}")
                    traceback.print_exc()
            
            asyncio.run(test_utility())
        else:
            # Normal MCP server run
            main()
            
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)