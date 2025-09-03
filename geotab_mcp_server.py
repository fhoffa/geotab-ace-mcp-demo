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


def get_ace_client() -> GeotabACEClient:
    """Get or create the ACE client instance."""
    global ace_client
    if ace_client is None:
        ace_client = GeotabACEClient()
    return ace_client


def format_query_result(result, chat_id: str = "", message_group_id: str = "") -> str:
    """Format a QueryResult for display."""
    parts = []
    
    if result.status == QueryStatus.DONE:
        if result.text_response:
            parts.append(f"📝 **Answer**\n{result.text_response}")
            
        if result.data_frame is not None and not result.data_frame.empty:
            df = result.data_frame
            preview_rows = min(15, len(df))
            preview_table = df.head(preview_rows).to_string(index=False)
            
            parts.append(f"📊 **Data Preview** (showing {preview_rows}/{len(df)} rows)\n```\n{preview_table}\n```")
            
            if len(df) > preview_rows:
                parts.append(f"📈 *Full dataset has {len(df)} rows and {len(df.columns)} columns*")
                
            if result.signed_urls:
                parts.append("💾 *Full dataset available - use get_full_data to download complete CSV*")
        
        # If we have preview data but no DataFrame, show it directly
        elif result.preview_data:
            parts.append(f"📊 **Data**\n```\n{result.preview_data}\n```")
                
        if not parts:
            parts.append("Query completed successfully but no content returned.")
            
    elif result.status == QueryStatus.FAILED:
        parts.append(f"❌ **Query Failed**: {result.error or 'Unknown error'}")
        
    elif result.status in [QueryStatus.PROCESSING, QueryStatus.PENDING]:
        status_msg = f"🔄 **Query Status**: {result.status.value.title()}"
        parts.append(f"{status_msg}\n\n⏳ Still processing... Check again in a few moments.")
        
        if chat_id and message_group_id:
            parts.append(f"📋 **Tracking**: Chat ID `{chat_id}`, Message Group ID `{message_group_id}`")
    else:
        parts.append(f"❓ **Unknown Status**: {result.status.value}")
        
    return "\n\n".join(parts)


@mcp.tool()
async def geotab_ask_question(question: str, timeout_seconds: int = 60) -> str:
    """
    Ask a question to Geotab ACE AI and wait for the response.
    
    Args:
        question (str): The question to ask the Geotab AI service
        timeout_seconds (int): Maximum time to wait for response (default: 60 seconds)
        
    Returns:
        str: The response from Geotab AI, including any data and analysis
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

Question: {question[:100]}{'...' if len(question) > 100 else ''}

📋 **Tracking Information**:
• Chat ID: `{chat_id}`  
• Message Group ID: `{message_group_id}`

🔄 **Next Steps**:
Use `geotab_check_status('{chat_id}', '{message_group_id}')` to check progress
Use `geotab_get_results('{chat_id}', '{message_group_id}')` to get results when ready"""
            
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
        str: Current status of the query
    """
    try:
        if not chat_id or not message_group_id:
            return "❌ Error: Both chat_id and message_group_id are required"
            
        logger.debug(f"Checking status for {chat_id}/{message_group_id}")
        
        client = get_ace_client()
        result = await client.get_query_status(chat_id, message_group_id)
        
        response = format_query_result(result, chat_id, message_group_id)
        
        if result.status == QueryStatus.DONE:
            response += f"\n\n🎯 **Get Full Results**: `geotab_get_results('{chat_id}', '{message_group_id}')`"
            
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
        str: Complete results including analysis and full dataset
    """
    try:
        if not chat_id or not message_group_id:
            return "❌ Error: Both chat_id and message_group_id are required"
            
        logger.info(f"Getting results for {chat_id}/{message_group_id}")
        
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
        
        # Add text analysis
        if result.text_response:
            parts.append(f"📝 **Analysis**\n{result.text_response}")
        
        # Add dataset
        if result.data_frame is not None and not result.data_frame.empty:
            df = result.data_frame
            
            # Show more data for full results
            preview_rows = min(50, len(df))
            preview_table = df.head(preview_rows).to_string(index=False)
            
            data_source = "complete dataset" if result.signed_urls and include_full_data else "preview data"
            dataset_info = f"📊 **Dataset** ({data_source}: {len(df)} rows × {len(df.columns)} columns)"
            
            if len(df) <= preview_rows:
                parts.append(f"{dataset_info}\n```\n{preview_table}\n```")
            else:
                parts.append(f"{dataset_info}\n```\n{preview_table}\n\n... and {len(df) - preview_rows} more rows\n```")
            
            # Add column info for large datasets
            if len(df.columns) > 5:
                parts.append(f"📋 **Columns**: {', '.join(df.columns.astype(str))}")
        
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

📋 **Question**: {question[:200]}{'...' if len(question) > 200 else ''}

🆔 **Tracking Information**:
• Chat ID: `{chat_id}`
• Message Group ID: `{message_group_id}`

🔄 **Next Steps**:
1. **Check Status**: `geotab_check_status('{chat_id}', '{message_group_id}')`
2. **Get Results**: `geotab_get_results('{chat_id}', '{message_group_id}')` (when ready)

⏱️ **Expected Processing Time**: 1-5 minutes for complex queries"""
        
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
            parts.append(f"📋 **Session ID**: {session_info}")
        else:
            parts.append("❌ **Authentication**: Failed")
        
        # API check
        if test_result["api_working"]:
            parts.append("✅ **API Calls**: Working")
        else:
            parts.append("❌ **API Calls**: Failed")
        
        # Overall status
        all_good = test_result["config_valid"] and test_result["auth_successful"] and test_result["api_working"]
        if all_good:
            parts.append("\n🎉 **Overall Status**: All systems operational!")
        else:
            parts.append("\n⚠️ **Overall Status**: Issues detected")
        
        # Errors
        if test_result["errors"]:
            parts.append("\n🚨 **Errors**:")
            for error in test_result["errors"]:
                parts.append(f"• {error}")
                
            parts.append("\n🛠️ **Troubleshooting**:")
            parts.append("1. Verify environment variables are set correctly:")
            parts.append("   - GEOTAB_API_USERNAME")
            parts.append("   - GEOTAB_API_PASSWORD") 
            parts.append("   - GEOTAB_API_DATABASE")
            parts.append("2. Check your Geotab account has API access")
            parts.append("3. Verify network connectivity")
        
        return "\n".join(parts)
        
    except Exception as e:
        logger.error(f"Error in connection test: {e}")
        logger.error(traceback.format_exc())
        return f"""💥 **Connection Test Failed**

Error: {str(e)}

🛠️ **Setup Instructions**:
1. Create a `.env` file with:
```
GEOTAB_API_USERNAME=your_username
GEOTAB_API_PASSWORD=your_password
GEOTAB_API_DATABASE=your_database
```
2. Restart the MCP server
3. Check server logs for detailed error information"""


@mcp.tool()
async def geotab_debug_query(chat_id: str, message_group_id: str) -> str:
    """
    Debug function to see raw response data from a query.
    
    Args:
        chat_id (str): Chat ID from a previous question
        message_group_id (str): Message group ID from a previous question
        
    Returns:
        str: Raw debug information about the query response
    """
    try:
        if not chat_id or not message_group_id:
            return "❌ Error: Both chat_id and message_group_id are required"
            
        logger.info(f"Debug query for {chat_id}/{message_group_id}")
        
        client = get_ace_client()
        result = await client.get_query_status(chat_id, message_group_id)
        
        debug_info = []
        debug_info.append(f"**Status**: {result.status.value}")
        debug_info.append(f"**Has text_response**: {bool(result.text_response)} (length: {len(result.text_response) if result.text_response else 0})")
        debug_info.append(f"**Has data_frame**: {result.data_frame is not None}")
        if result.data_frame is not None:
            debug_info.append(f"**Data shape**: {result.data_frame.shape}")
        debug_info.append(f"**Has preview_data**: {bool(result.preview_data)}")
        if result.preview_data:
            debug_info.append(f"**Preview data**: {result.preview_data}")
        debug_info.append(f"**Has signed_urls**: {bool(result.signed_urls)}")
        debug_info.append(f"**Has error**: {bool(result.error)}")
        
        if result.text_response:
            debug_info.append(f"**Text Response Preview**: {result.text_response[:200]}...")
            
        return "\n".join(debug_info)
        
    except Exception as e:
        logger.error(f"Error in debug query: {e}")
        return f"💥 **Debug Error**: {str(e)}"


@mcp.resource("geotab://status")
def get_server_status():
    """Get current server status."""
    try:
        global ace_client
        return {
            "server": "geotab-mcp-server",
            "status": "running",
            "client_initialized": ace_client is not None,
            "tools_available": [
                "geotab_ask_question",
                "geotab_check_status", 
                "geotab_get_results",
                "geotab_start_query_async",
                "geotab_test_connection",
                "geotab_debug_query"
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
        logger.info("Starting Geotab MCP Server...")
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
        logger.info("🚀 MCP Server starting...")
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