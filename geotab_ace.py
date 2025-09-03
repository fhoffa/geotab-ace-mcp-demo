#!/usr/bin/env python3
"""
Geotab ACE Utility Library

A clean, standalone utility for interacting with the Geotab ACE API.
Can be used independently or imported by other applications.
"""

import asyncio
import json
import logging
import os
import time
import traceback
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from enum import Enum

import aiohttp
import pandas as pd
from dotenv import load_dotenv
from io import StringIO

# Load environment variables
load_dotenv()

# Configure logging
logger = logging.getLogger("geotab-ace")

class QueryStatus(Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    DONE = "DONE"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"

@dataclass
class GeotabCredentials:
    username: str
    password: str
    database: str

@dataclass
class QueryResult:
    status: QueryStatus
    text_response: str = ""
    data_frame: Optional[pd.DataFrame] = None
    preview_data: Optional[List[Dict]] = None
    signed_urls: Optional[List[str]] = None
    error: Optional[str] = None
    raw_response: Optional[Dict] = None

class GeotabACEError(Exception):
    """Base exception for Geotab ACE operations."""
    pass

class AuthenticationError(GeotabACEError):
    """Raised when authentication fails."""
    pass

class APIError(GeotabACEError):
    """Raised when API calls fail."""
    pass

class TimeoutError(GeotabACEError):
    """Raised when operations timeout."""
    pass

class GeotabACEClient:
    """
    A client for interacting with the Geotab ACE API.
    
    Example usage:
        client = GeotabACEClient()
        result = await client.ask_question("How many vehicles do we have?")
        print(result.text_response)
        if result.data_frame is not None:
            print(result.data_frame.head())
    """
    
    def __init__(self, credentials: Optional[GeotabCredentials] = None, api_url: str = "https://alpha.geotab.com/apiv1"):
        """
        Initialize the client.
        
        Args:
            credentials: Geotab credentials. If None, will load from environment variables.
            api_url: The Geotab API endpoint URL.
        """
        self.api_url = api_url
        self.credentials = credentials or self._load_credentials_from_env()
        self.session_credentials: Optional[Dict] = None
        self.last_auth_time: Optional[float] = None
        
    def _load_credentials_from_env(self) -> GeotabCredentials:
        """Load credentials from environment variables."""
        username = os.getenv("GEOTAB_API_USERNAME")
        password = os.getenv("GEOTAB_API_PASSWORD")
        database = os.getenv("GEOTAB_API_DATABASE")
        
        if not all([username, password, database]):
            missing = []
            if not username: missing.append("GEOTAB_API_USERNAME")
            if not password: missing.append("GEOTAB_API_PASSWORD")
            if not database: missing.append("GEOTAB_API_DATABASE")
            raise AuthenticationError(f"Missing environment variables: {', '.join(missing)}")
            
        return GeotabCredentials(username=username, password=password, database=database)
    
    async def authenticate(self) -> Dict:
        """
        Authenticate with Geotab and return session credentials.
        
        Returns:
            Session credentials dictionary
            
        Raises:
            AuthenticationError: If authentication fails
        """
        # Check if we have valid cached credentials (valid for 1 hour)
        if (self.session_credentials and self.last_auth_time and 
            time.time() - self.last_auth_time < 3600):
            logger.debug("Using cached credentials")
            return self.session_credentials
            
        auth_data = {
            "method": "Authenticate",
            "params": {
                "userName": self.credentials.username,
                "password": self.credentials.password,
                "database": self.credentials.database
            }
        }
        
        logger.info(f"Authenticating with database: {self.credentials.database}")
        
        try:
            connector = aiohttp.TCPConnector(
                limit=10,
                ttl_dns_cache=300,
                use_dns_cache=True,
                keepalive_timeout=30,
                enable_cleanup_closed=True
            )
            
            timeout = aiohttp.ClientTimeout(
                total=60,
                connect=15,
                sock_read=45
            )
            
            async with aiohttp.ClientSession(
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": "GeotabACEClient/1.0",
                    "Accept": "application/json"
                },
                timeout=timeout,
                connector=connector
            ) as session:
                async with session.post(self.api_url, data=json.dumps(auth_data)) as response:
                    response.raise_for_status()
                    auth_result = await response.json()
                    
        except aiohttp.ClientError as e:
            raise AuthenticationError(f"Network error during authentication: {e}")
        except json.JSONDecodeError as e:
            raise AuthenticationError(f"Invalid JSON response: {e}")
            
        if "error" in auth_result:
            error_msg = auth_result["error"].get("message", "Unknown authentication error")
            error_code = auth_result["error"].get("code", "Unknown")
            raise AuthenticationError(f"Authentication failed (Code: {error_code}): {error_msg}")
            
        if "result" not in auth_result or "credentials" not in auth_result["result"]:
            raise AuthenticationError("Invalid authentication response structure")
            
        self.session_credentials = auth_result["result"]["credentials"]
        self.last_auth_time = time.time()
        logger.info(f"✅ Successfully authenticated with database '{self.credentials.database}'")
        
        return self.session_credentials
    
    async def _make_api_call(self, function_name: str, function_parameters: Dict, timeout_seconds: int = 90) -> Dict:
        """
        Make an authenticated API call to Geotab ACE.
        
        Args:
            function_name: The API function to call
            function_parameters: Parameters for the function  
            timeout_seconds: Request timeout in seconds
            
        Returns:
            API response dictionary
            
        Raises:
            APIError: If the API call fails
        """
        credentials = await self.authenticate()
        
        request_data = {
            "method": "GetAceResults",
            "params": {
                "serviceName": "dna-planet-orchestration",
                "functionName": function_name,
                "customerData": True,
                "functionParameters": function_parameters,
                "credentials": credentials
            }
        }
        
        logger.debug(f"Making API call: {function_name} (timeout: {timeout_seconds}s)")
        
        try:
            connector = aiohttp.TCPConnector(
                limit=10,
                ttl_dns_cache=300,
                use_dns_cache=True,
                keepalive_timeout=60,
                enable_cleanup_closed=True
            )
            
            timeout = aiohttp.ClientTimeout(
                total=timeout_seconds,
                connect=15,
                sock_read=timeout_seconds - 15
            )
            
            async with aiohttp.ClientSession(
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": "GeotabACEClient/1.0",
                    "Accept": "application/json"
                },
                timeout=timeout,
                connector=connector
            ) as session:
                async with session.post(self.api_url, data=json.dumps(request_data)) as response:
                    response.raise_for_status()
                    result = await response.json()
                    
        except aiohttp.ClientError as e:
            raise APIError(f"Network error in API call '{function_name}': {e}")
        except json.JSONDecodeError as e:
            raise APIError(f"Invalid JSON response from API call '{function_name}': {e}")
            
        if "error" in result:
            error_msg = result["error"].get("message", "Unknown API error")
            error_code = result["error"].get("code", "Unknown")
            raise APIError(f"API call failed (Code: {error_code}): {error_msg}")
            
        logger.debug(f"API call successful: {function_name}")
        return result
    
    async def start_query(self, question: str) -> tuple[str, str]:
        """
        Start a query and return chat_id and message_group_id for tracking.
        
        Args:
            question: The question to ask
            
        Returns:
            Tuple of (chat_id, message_group_id)
            
        Raises:
            APIError: If starting the query fails
        """
        if not question or not question.strip():
            raise ValueError("Question cannot be empty")
            
        logger.info(f"Starting query: {question[:100]}...")
        
        # Create chat
        create_chat_result = await self._make_api_call("create-chat", {}, timeout_seconds=60)
        
        chat_id_path = create_chat_result.get("result", {}).get("apiResult", {}).get("results", [])
        if not chat_id_path:
            raise APIError("Failed to create chat session")
            
        chat_id = chat_id_path[0]["chat_id"]
        logger.debug(f"Created chat with ID: {chat_id}")
        
        # Send prompt
        send_prompt_result = await self._make_api_call("send-prompt", {
            "chat_id": chat_id,
            "prompt": question.strip()
        }, timeout_seconds=60)
        
        msg_group_path = send_prompt_result.get("result", {}).get("apiResult", {}).get("results", [])
        if not msg_group_path:
            raise APIError("Failed to send prompt")
            
        msg_group_id = msg_group_path[0]["message_group"]["id"]
        logger.debug(f"Created message group with ID: {msg_group_id}")
        
        return chat_id, msg_group_id
    
    async def get_query_status(self, chat_id: str, message_group_id: str) -> QueryResult:
        """
        Get the current status of a query.
        
        Args:
            chat_id: Chat ID from start_query
            message_group_id: Message group ID from start_query
            
        Returns:
            QueryResult with current status
            
        Raises:
            APIError: If the status check fails
        """
        try:
            result = await self._make_api_call("get-message-group", {
                "chat_id": chat_id,
                "message_group_id": message_group_id
            }, timeout_seconds=45)
            
            status_path = result.get("result", {}).get("apiResult", {}).get("results", [])
            if not status_path:
                raise APIError("Invalid response structure from status check")
                
            message_group = status_path[0].get("message_group", {})
            status_obj = message_group.get("status", {})
            status_str = status_obj.get("status", "UNKNOWN")
            
            # Map string status to enum
            try:
                status = QueryStatus(status_str)
            except ValueError:
                logger.warning(f"Unknown status received: {status_str}")
                status = QueryStatus.UNKNOWN
            
            query_result = QueryResult(status=status, raw_response=result)
            
            if status == QueryStatus.FAILED:
                query_result.error = status_obj.get("error", "Unknown error")
            elif status == QueryStatus.DONE:
                # Extract response data - ACE API has a complex message structure
                messages = message_group.get("messages", {})
                
                # Look for the final response message (usually UserDataReference type)
                text_responses = []
                data_messages = []
                
                logger.debug(f"Processing {len(messages)} messages for extraction")
                
                for msg_id, msg_data in messages.items():
                    if isinstance(msg_data, dict):
                        msg_type = msg_data.get('type', '')
                        logger.debug(f"Message {msg_id}: type={msg_type}")
                        
                        # Collect reasoning/text from UserDataReference messages
                        if msg_type == 'UserDataReference':
                            logger.debug(f"Found UserDataReference message with keys: {list(msg_data.keys())}")
                            
                            if 'reasoning' in msg_data and msg_data['reasoning']:
                                text_responses.append(msg_data['reasoning'])
                                logger.debug(f"Added reasoning: {len(msg_data['reasoning'])} chars")
                            if 'interpretation' in msg_data and msg_data['interpretation']:
                                text_responses.append(msg_data['interpretation'])
                                logger.debug(f"Added interpretation: {len(msg_data['interpretation'])} chars")
                            if 'insight' in msg_data and msg_data['insight']:
                                text_responses.append(msg_data['insight'])
                                logger.debug(f"Added insight: {len(msg_data['insight'])} chars")
                            
                            # Store the entire data message for further processing
                            data_messages.append(msg_data)
                
                # Combine text responses
                query_result.text_response = '\n\n'.join(text_responses) if text_responses else ""
                logger.debug(f"Combined text response: {len(query_result.text_response)} chars")
                
                # Extract data from the most recent UserDataReference message
                if data_messages:
                    latest_data_msg = max(data_messages, key=lambda x: x.get('creation_date_unix_milli', 0))
                    query_result.preview_data = latest_data_msg.get('preview_array')
                    query_result.signed_urls = latest_data_msg.get('signed_urls')
                    
                    logger.debug(f"Preview data: {query_result.preview_data}")
                    logger.debug(f"Signed URLs: {bool(query_result.signed_urls)}")
                    
                    # Try to create DataFrame from preview data if available
                    if query_result.preview_data:
                        try:
                            query_result.data_frame = pd.DataFrame(query_result.preview_data)
                            logger.debug(f"Created DataFrame with shape: {query_result.data_frame.shape}")
                        except Exception as e:
                            logger.warning(f"Failed to create DataFrame from preview data: {e}")
                
                # Fallback: look for any text_response field (legacy format)
                if not query_result.text_response:
                    for msg_data in messages.values():
                        if isinstance(msg_data, dict) and msg_data.get('text_response'):
                            query_result.text_response = msg_data['text_response'].strip()
                            logger.debug("Used fallback text_response extraction")
                            break
            
            return query_result
            
        except Exception as e:
            if isinstance(e, (APIError, GeotabACEError)):
                raise
            raise APIError(f"Unexpected error checking query status: {e}")
    
    async def wait_for_completion(self, chat_id: str, message_group_id: str, 
                                  max_wait_seconds: int = 300, 
                                  poll_interval_start: float = 2.0) -> QueryResult:
        """
        Wait for a query to complete by polling its status.
        
        Args:
            chat_id: Chat ID from start_query
            message_group_id: Message group ID from start_query
            max_wait_seconds: Maximum time to wait for completion
            poll_interval_start: Starting poll interval in seconds
            
        Returns:
            QueryResult when query completes
            
        Raises:
            TimeoutError: If query doesn't complete within max_wait_seconds
            APIError: If polling fails
        """
        logger.info(f"Waiting for query completion (max {max_wait_seconds} seconds)...")
        
        start_time = time.time()
        poll_interval = poll_interval_start
        consecutive_errors = 0
        max_consecutive_errors = 5
        
        while time.time() - start_time < max_wait_seconds:
            try:
                await asyncio.sleep(poll_interval)
                
                result = await self.get_query_status(chat_id, message_group_id)
                elapsed = time.time() - start_time
                
                logger.debug(f"Query status: {result.status.value} (elapsed: {elapsed:.1f}s)")
                
                if result.status == QueryStatus.DONE:
                    logger.info(f"✅ Query completed after {elapsed:.1f} seconds")
                    return result
                elif result.status == QueryStatus.FAILED:
                    logger.error(f"Query failed after {elapsed:.1f} seconds: {result.error}")
                    return result
                elif result.status in [QueryStatus.PROCESSING, QueryStatus.PENDING]:
                    # Log progress every 30 seconds
                    if int(elapsed) % 30 == 0 and elapsed > 0:
                        logger.info(f"Still processing... ({elapsed:.0f}s elapsed)")
                    
                    # Progressive delay - start fast, then slow down
                    if elapsed > 20:  # After 20 seconds, slow down
                        poll_interval = min(5.0, poll_interval * 1.1)
                    elif elapsed > 10:  # After 10 seconds, medium speed
                        poll_interval = min(3.0, poll_interval * 1.05)
                
                # Reset error counter on successful call
                consecutive_errors = 0
                
            except APIError as e:
                consecutive_errors += 1
                elapsed = time.time() - start_time
                logger.warning(f"API error during polling (attempt {consecutive_errors}, elapsed {elapsed:.1f}s): {e}")
                
                if consecutive_errors >= max_consecutive_errors:
                    raise APIError(f"Too many consecutive polling errors: {e}")
                
                # Exponential backoff for retries
                backoff_delay = min(poll_interval * (2 ** consecutive_errors), 30)
                await asyncio.sleep(backoff_delay)
                
            except Exception as e:
                consecutive_errors += 1
                elapsed = time.time() - start_time
                logger.error(f"Unexpected error during polling (elapsed {elapsed:.1f}s): {e}")
                
                if consecutive_errors >= max_consecutive_errors:
                    raise APIError(f"Polling failed with unexpected error: {e}")
                    
                await asyncio.sleep(min(10, poll_interval * 2))
        
        elapsed = time.time() - start_time
        raise TimeoutError(f"Query did not complete within {max_wait_seconds} seconds (elapsed: {elapsed:.1f}s)")
    
    async def get_full_dataset(self, query_result: QueryResult) -> Optional[pd.DataFrame]:
        """
        Download the full dataset from signed URLs if available.
        
        Args:
            query_result: QueryResult from a completed query
            
        Returns:
            DataFrame with full dataset, or None if not available
        """
        if not query_result.signed_urls:
            logger.debug("No signed URLs available for full dataset")
            return query_result.data_frame  # Return preview data if available
        
        try:
            logger.debug("Downloading full dataset from signed URL")
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=120)) as session:
                async with session.get(query_result.signed_urls[0]) as response:
                    response.raise_for_status()
                    csv_content = await response.text()
                    return pd.read_csv(StringIO(csv_content))
        except Exception as e:
            logger.warning(f"Failed to download full dataset: {e}")
            return query_result.data_frame  # Fallback to preview data
    
    async def ask_question(self, question: str, max_wait_seconds: int = 300) -> QueryResult:
        """
        Ask a question and wait for the complete response.
        
        Args:
            question: The question to ask
            max_wait_seconds: Maximum time to wait for completion
            
        Returns:
            QueryResult with the complete response
            
        Raises:
            TimeoutError: If query doesn't complete within max_wait_seconds
            APIError: If the query fails
        """
        chat_id, message_group_id = await self.start_query(question)
        return await self.wait_for_completion(chat_id, message_group_id, max_wait_seconds)
    
    async def test_connection(self) -> Dict[str, Any]:
        """
        Test the connection and authentication.
        
        Returns:
            Dictionary with test results
        """
        result = {
            "config_valid": False,
            "auth_successful": False,
            "api_working": False,
            "errors": []
        }
        
        try:
            # Test configuration
            result["config_valid"] = True
            
            # Test authentication
            credentials = await self.authenticate()
            result["auth_successful"] = True
            result["session_id"] = credentials.get("sessionId", "Unknown")[:20] + "..."
            
            # Test API call
            await self._make_api_call("create-chat", {}, timeout_seconds=30)
            result["api_working"] = True
            
        except AuthenticationError as e:
            result["errors"].append(f"Authentication failed: {e}")
        except APIError as e:
            result["errors"].append(f"API test failed: {e}")
        except Exception as e:
            result["errors"].append(f"Unexpected error: {e}")
            
        return result

# Convenience functions for simple usage
async def ask_question_simple(question: str, max_wait_seconds: int = 300) -> QueryResult:
    """
    Simple function to ask a question using environment variables for credentials.
    
    Args:
        question: The question to ask
        max_wait_seconds: Maximum time to wait for completion
        
    Returns:
        QueryResult with the response
    """
    client = GeotabACEClient()
    return await client.ask_question(question, max_wait_seconds)

async def test_connection_simple() -> Dict[str, Any]:
    """
    Simple function to test connection using environment variables.
    
    Returns:
        Dictionary with test results
    """
    client = GeotabACEClient()
    return await client.test_connection()

# Command line interface for testing
if __name__ == "__main__":
    import argparse
    
    async def main():
        parser = argparse.ArgumentParser(description="Geotab ACE Utility")
        parser.add_argument("--test", action="store_true", help="Test connection")
        parser.add_argument("--question", type=str, help="Ask a question")
        parser.add_argument("--timeout", type=int, default=300, help="Timeout in seconds")
        parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")
        parser.add_argument("--dump-response", action="store_true", help="Dump full raw response")
        
        args = parser.parse_args()
        
        # Configure logging
        level = logging.DEBUG if args.verbose else logging.INFO
        logging.basicConfig(
            level=level,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        
        try:
            if args.test:
                print("Testing connection...")
                result = await test_connection_simple()
                print(json.dumps(result, indent=2))
                
            elif args.question:
                print(f"Asking question: {args.question}")
                result = await ask_question_simple(args.question, args.timeout)
                
                print(f"\nStatus: {result.status.value}")
                
                if result.error:
                    print(f"Error: {result.error}")
                    
                if result.text_response:
                    print(f"\nResponse:\n{result.text_response}")
                else:
                    print("\nNo text response received.")
                    
                if result.data_frame is not None:
                    print(f"\nData shape: {result.data_frame.shape}")
                    print("\nData preview:")
                    print(result.data_frame.head(10).to_string(index=False))
                    
                    if len(result.data_frame) > 10:
                        print(f"\n... and {len(result.data_frame) - 10} more rows")
                else:
                    print("\nNo data returned.")
                    
                # Debug: Show raw response structure
                if args.verbose and result.raw_response:
                    print(f"\nDEBUG: Raw response structure:")
                    print(f"Top level keys: {list(result.raw_response.keys())}")
                    
                    if 'result' in result.raw_response:
                        result_data = result.raw_response['result']
                        print(f"Result keys: {list(result_data.keys()) if isinstance(result_data, dict) else 'Not a dict'}")
                        
                        if isinstance(result_data, dict) and 'apiResult' in result_data:
                            api_result = result_data['apiResult']
                            print(f"API Result keys: {list(api_result.keys()) if isinstance(api_result, dict) else 'Not a dict'}")
                            
                            if isinstance(api_result, dict) and 'results' in api_result:
                                results = api_result['results']
                                print(f"Results type: {type(results)}")
                                if isinstance(results, list) and len(results) > 0:
                                    first_result = results[0]
                                    print(f"First result keys: {list(first_result.keys()) if isinstance(first_result, dict) else 'Not a dict'}")
                                    
                                    if isinstance(first_result, dict) and 'message_group' in first_result:
                                        msg_group = first_result['message_group']
                                        print(f"Message group keys: {list(msg_group.keys()) if isinstance(msg_group, dict) else 'Not a dict'}")
                                        
                                        if isinstance(msg_group, dict) and 'messages' in msg_group:
                                            messages = msg_group['messages']
                                            print(f"Messages keys: {list(messages.keys()) if isinstance(messages, dict) else 'Not a dict'}")
                                            print(f"Messages content: {messages}")
                                        else:
                                            print("No 'messages' in message_group")
                                    else:
                                        print("No 'message_group' in first result")
                                else:
                                    print(f"Results is empty or not a list: {results}")
                            else:
                                print("No 'results' in apiResult")
                        else:
                            print("No 'apiResult' in result")
                    else:
                        print("No 'result' in raw response")
                    
            else:
                parser.print_help()
                
        except Exception as e:
            print(f"Error: {e}")
            if args.verbose:
                traceback.print_exc()
    
    asyncio.run(main())