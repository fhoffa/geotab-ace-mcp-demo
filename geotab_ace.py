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
    """Status values for ACE queries."""
    PENDING = "PENDING"
    PROCESSING = "PROCESSING" 
    DONE = "DONE"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"


@dataclass
class GeotabCredentials:
    """Credentials for Geotab authentication."""
    username: str
    password: str
    database: str
    api_url: Optional[str] = None


@dataclass
class QueryResult:
    """Result object containing query response data."""
    status: QueryStatus
    text_response: str = ""
    data_frame: Optional[pd.DataFrame] = None
    preview_data: Optional[List[Dict]] = None
    signed_urls: Optional[List[str]] = None
    error: Optional[str] = None
    raw_response: Optional[Dict] = None
    # Enhanced fields for better data extraction
    sql_query: Optional[str] = None
    reasoning: Optional[str] = None
    interpretation: Optional[str] = None
    insight: Optional[str] = None
    process: Optional[str] = None
    understanding: Optional[str] = None
    analysis: Optional[str] = None
    all_messages: Optional[Dict] = None


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


class AccountManager:
    """
    Manages multiple Geotab accounts for multi-tenant support.

    Supports two configuration modes:
    1. Legacy single account: GEOTAB_API_USERNAME, GEOTAB_API_PASSWORD, GEOTAB_API_DATABASE
    2. Multi-account: GEOTAB_ACCOUNT_1_NAME, GEOTAB_ACCOUNT_1_USERNAME, etc.

    Example .env for multi-account:
        GEOTAB_ACCOUNT_1_NAME=fleet1
        GEOTAB_ACCOUNT_1_USERNAME=user1@example.com
        GEOTAB_ACCOUNT_1_PASSWORD=secret1
        GEOTAB_ACCOUNT_1_DATABASE=db1
        GEOTAB_ACCOUNT_1_API_URL=https://my.geotab.com/apiv1  # optional

        GEOTAB_ACCOUNT_2_NAME=fleet2
        GEOTAB_ACCOUNT_2_USERNAME=user2@example.com
        GEOTAB_ACCOUNT_2_PASSWORD=secret2
        GEOTAB_ACCOUNT_2_DATABASE=db2
        GEOTAB_ACCOUNT_2_API_URL=https://mypreview.geotab.com/apiv1  # optional
    """

    def __init__(self):
        """Initialize the account manager and load all configured accounts."""
        self._clients: Dict[str, 'GeotabACEClient'] = {}
        self._account_configs: Dict[str, GeotabCredentials] = {}
        self._default_account: Optional[str] = None
        self._load_accounts()

    def _load_accounts(self) -> None:
        """Load account configurations from environment variables."""
        # First, try to load multi-account configuration
        account_num = 1
        while True:
            prefix = f"GEOTAB_ACCOUNT_{account_num}_"
            name = os.getenv(f"{prefix}NAME")
            username = os.getenv(f"{prefix}USERNAME")
            password = os.getenv(f"{prefix}PASSWORD")
            database = os.getenv(f"{prefix}DATABASE")
            api_url = os.getenv(f"{prefix}API_URL")

            if not name:
                # No more accounts
                break

            if not all([username, password, database]):
                logger.warning(f"Incomplete configuration for account {account_num} ({name}). Skipping.")
                account_num += 1
                continue

            self._account_configs[name] = GeotabCredentials(
                username=username,
                password=password,
                database=database,
                api_url=api_url
            )

            # First account becomes default
            if self._default_account is None:
                self._default_account = name

            logger.info(f"Loaded account configuration: {name} (database: {database})")
            account_num += 1

        # If no multi-account config found, fall back to legacy single account
        if not self._account_configs:
            username = os.getenv("GEOTAB_API_USERNAME")
            password = os.getenv("GEOTAB_API_PASSWORD")
            database = os.getenv("GEOTAB_API_DATABASE")

            if all([username, password, database]):
                self._account_configs["default"] = GeotabCredentials(
                    username=username,
                    password=password,
                    database=database
                )
                self._default_account = "default"
                logger.info(f"Loaded legacy single account configuration (database: {database})")
            else:
                logger.warning("No account configuration found. Set environment variables to configure accounts.")

    def get_client(self, account: Optional[str] = None) -> 'GeotabACEClient':
        """
        Get or create a GeotabACEClient for the specified account.

        Args:
            account: Account name. If None, uses the default account.

        Returns:
            GeotabACEClient instance for the account

        Raises:
            AuthenticationError: If account not found or not configured
        """
        if not self._account_configs:
            raise AuthenticationError(
                "No accounts configured. Set GEOTAB_ACCOUNT_1_NAME, GEOTAB_ACCOUNT_1_USERNAME, "
                "GEOTAB_ACCOUNT_1_PASSWORD, GEOTAB_ACCOUNT_1_DATABASE environment variables, "
                "or use legacy GEOTAB_API_USERNAME, GEOTAB_API_PASSWORD, GEOTAB_API_DATABASE."
            )

        # Use default account if none specified
        account_name = account or self._default_account

        if account_name not in self._account_configs:
            available = list(self._account_configs.keys())
            raise AuthenticationError(
                f"Account '{account_name}' not found. Available accounts: {', '.join(available)}"
            )

        # Create client if not cached
        if account_name not in self._clients:
            credentials = self._account_configs[account_name]
            self._clients[account_name] = GeotabACEClient(
                credentials=credentials,
                api_url=credentials.api_url
            )
            logger.debug(f"Created client for account: {account_name}")

        return self._clients[account_name]

    def list_accounts(self) -> List[Dict[str, str]]:
        """
        List all configured accounts.

        Returns:
            List of account info dictionaries with name, database, and is_default
        """
        accounts = []
        for name, creds in self._account_configs.items():
            accounts.append({
                "name": name,
                "database": creds.database,
                "username": creds.username,
                "is_default": name == self._default_account
            })
        return accounts

    def get_default_account(self) -> Optional[str]:
        """Get the name of the default account."""
        return self._default_account

    def set_default_account(self, account: str) -> None:
        """
        Set the default account.

        Args:
            account: Account name to set as default

        Raises:
            AuthenticationError: If account not found
        """
        if account not in self._account_configs:
            available = list(self._account_configs.keys())
            raise AuthenticationError(
                f"Account '{account}' not found. Available accounts: {', '.join(available)}"
            )
        self._default_account = account
        logger.info(f"Default account set to: {account}")

    def has_accounts(self) -> bool:
        """Check if any accounts are configured."""
        return len(self._account_configs) > 0

    def account_count(self) -> int:
        """Get the number of configured accounts."""
        return len(self._account_configs)


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

    # Class constants
    DEFAULT_API_URL = "https://my.geotab.com/apiv1"
    DEFAULT_TIMEOUT = 60
    SESSION_TIMEOUT = 3600  # 1 hour
    DRIVER_NAME_COLUMNS = ["DisplayName", "Display Name", "LastName", "Last Name", "FirstName", "First Name"]

    def __init__(self, credentials: Optional[GeotabCredentials] = None,
                 api_url: Optional[str] = None,
                 driver_privacy_mode: Optional[bool] = None):
        """
        Initialize the client.

        Args:
            credentials: Geotab credentials. If None, will load from environment variables.
            api_url: The Geotab API endpoint URL. If None, will load from GEOTAB_API_URL environment variable or use DEFAULT_API_URL.
            driver_privacy_mode: Enable driver name redaction. If None, reads from GEOTAB_DRIVER_PRIVACY_MODE env var (default: True).
        """
        self.api_url = api_url or os.getenv("GEOTAB_API_URL", self.DEFAULT_API_URL)
        self.credentials = credentials or self._load_credentials_from_env()
        self.session_credentials: Optional[Dict] = None
        self.last_auth_time: Optional[float] = None

        # Driver privacy mode: default to True unless explicitly disabled
        if driver_privacy_mode is None:
            env_value = os.getenv("GEOTAB_DRIVER_PRIVACY_MODE", "true").lower()
            self.driver_privacy_mode = env_value not in ["false", "0", "no", "off"]
        else:
            self.driver_privacy_mode = driver_privacy_mode
        
    def _load_credentials_from_env(self) -> GeotabCredentials:
        """Load credentials from environment variables."""
        required_vars = {
            "GEOTAB_API_USERNAME": "username",
            "GEOTAB_API_PASSWORD": "password", 
            "GEOTAB_API_DATABASE": "database"
        }
        
        values = {}
        missing = []
        
        for env_var, field_name in required_vars.items():
            value = os.getenv(env_var)
            if value:
                values[field_name] = value
            else:
                missing.append(env_var)
        
        if missing:
            raise AuthenticationError(f"Missing environment variables: {', '.join(missing)}")
            
        return GeotabCredentials(**values)
    
    def _is_session_valid(self) -> bool:
        """Check if current session credentials are still valid."""
        return (self.session_credentials is not None and 
                self.last_auth_time is not None and
                time.time() - self.last_auth_time < self.SESSION_TIMEOUT)
    
    async def authenticate(self) -> Dict:
        """
        Authenticate with Geotab and return session credentials.
        
        Returns:
            Session credentials dictionary
            
        Raises:
            AuthenticationError: If authentication fails
        """
        if self._is_session_valid():
            logger.debug("Using cached authentication credentials")
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
            session_config = self._create_session_config()
            async with aiohttp.ClientSession(**session_config) as session:
                async with session.post(self.api_url, json=auth_data) as response:
                    response.raise_for_status()
                    auth_result = await response.json()
                    
        except aiohttp.ClientError as e:
            raise AuthenticationError(f"Network error during authentication: {e}")
        except json.JSONDecodeError as e:
            raise AuthenticationError(f"Invalid JSON response: {e}")
        
        self._validate_auth_response(auth_result)
        
        self.session_credentials = auth_result["result"]["credentials"]
        self.last_auth_time = time.time()
        logger.info(f"Successfully authenticated with database '{self.credentials.database}'")
        
        return self.session_credentials
    
    def _create_session_config(self, timeout: int = DEFAULT_TIMEOUT) -> Dict[str, Any]:
        """Create aiohttp session configuration."""
        connector = aiohttp.TCPConnector(
            limit=10,
            ttl_dns_cache=300,
            use_dns_cache=True,
            keepalive_timeout=30,
            enable_cleanup_closed=True
        )
        
        timeout_config = aiohttp.ClientTimeout(
            total=timeout,
            connect=15,
            sock_read=timeout - 15
        )
        
        return {
            "headers": {
                "Content-Type": "application/json",
                "User-Agent": "GeotabACEClient/1.0",
                "Accept": "application/json"
            },
            "timeout": timeout_config,
            "connector": connector
        }
    
    def _validate_auth_response(self, auth_result: Dict) -> None:
        """Validate authentication response structure."""
        if "error" in auth_result:
            error_msg = auth_result["error"].get("message", "Unknown authentication error")
            error_code = auth_result["error"].get("code", "Unknown")
            raise AuthenticationError(f"Authentication failed (Code: {error_code}): {error_msg}")
            
        if "result" not in auth_result or "credentials" not in auth_result["result"]:
            raise AuthenticationError("Invalid authentication response structure")
    
    async def _make_api_call(self, function_name: str, function_parameters: Dict, 
                           timeout_seconds: int = DEFAULT_TIMEOUT) -> Dict:
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
            session_config = self._create_session_config(timeout_seconds)
            async with aiohttp.ClientSession(**session_config) as session:
                async with session.post(self.api_url, json=request_data) as response:
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
            ValueError: If question is empty
        """
        if not question or not question.strip():
            raise ValueError("Question cannot be empty")
            
        logger.info(f"Starting query: {question[:100]}...")
        
        # Create chat
        create_chat_result = await self._make_api_call("create-chat", {})
        chat_id = self._extract_chat_id(create_chat_result)
        
        # Send prompt
        send_prompt_result = await self._make_api_call("send-prompt", {
            "chat_id": chat_id,
            "prompt": question.strip()
        })
        message_group_id = self._extract_message_group_id(send_prompt_result)
        
        logger.debug(f"Query started: chat_id={chat_id}, message_group_id={message_group_id}")
        return chat_id, message_group_id
    
    def _extract_chat_id(self, response: Dict) -> str:
        """Extract chat ID from create-chat response."""
        results = response.get("result", {}).get("apiResult", {}).get("results", [])
        if not results:
            raise APIError("Failed to create chat session - no results returned")
        return results[0]["chat_id"]
    
    def _extract_message_group_id(self, response: Dict) -> str:
        """Extract message group ID from send-prompt response."""
        results = response.get("result", {}).get("apiResult", {}).get("results", [])
        if not results:
            raise APIError("Failed to send prompt - no results returned")
        return results[0]["message_group"]["id"]
    
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
            })
            
            return self._parse_query_result(result)
            
        except (APIError, GeotabACEError):
            raise
        except Exception as e:
            raise APIError(f"Unexpected error checking query status: {e}")
    
    def _parse_query_result(self, api_response: Dict) -> QueryResult:
        """Parse API response into QueryResult object with enhanced data extraction."""
        results = api_response.get("result", {}).get("apiResult", {}).get("results", [])
        if not results:
            raise APIError("Invalid response structure from status check")
            
        message_group = results[0].get("message_group", {})
        status_obj = message_group.get("status", {})
        status_str = status_obj.get("status", "UNKNOWN")
        
        # Map string status to enum
        try:
            status = QueryStatus(status_str)
        except ValueError:
            logger.warning(f"Unknown status received: {status_str}")
            status = QueryStatus.UNKNOWN
        
        query_result = QueryResult(status=status, raw_response=api_response)
        
        if status == QueryStatus.FAILED:
            query_result.error = status_obj.get("error", "Unknown error")
        elif status == QueryStatus.DONE:
            self._extract_enhanced_response_data(message_group, query_result)
        
        return query_result
    
    def _extract_enhanced_response_data(self, message_group: Dict, query_result: QueryResult) -> None:
        """Extract response data from UserDataReference or AssistantMessage."""
        messages = message_group.get("messages", {})
        query_result.all_messages = messages

        logger.debug(f"Processing {len(messages)} messages")

        # Find the UserDataReference message (contains SQL query results)
        user_data_msg = None
        assistant_msg = None

        for msg_data in messages.values():
            if isinstance(msg_data, dict):
                msg_type = msg_data.get('type')
                if msg_type == 'UserDataReference':
                    user_data_msg = msg_data
                elif msg_type == 'AssistantMessage':
                    assistant_msg = msg_data

        if user_data_msg:
            # Extract SQL query from 'query' field
            query_result.sql_query = user_data_msg.get('query')

            # Extract reasoning from 'reasoning' field
            query_result.reasoning = user_data_msg.get('reasoning')

            # Extract interpretation from 'interpretation' field
            query_result.interpretation = user_data_msg.get('interpretation')

            # Use reasoning as main text response if no other text
            query_result.text_response = query_result.reasoning or ""

            # Extract data
            query_result.preview_data = user_data_msg.get('preview_array')
            query_result.signed_urls = user_data_msg.get('signed_urls')

            # Create DataFrame
            self._create_dataframe(query_result)

            logger.debug(f"Extracted: SQL={bool(query_result.sql_query)}, "
                        f"reasoning={bool(query_result.reasoning)}, "
                        f"data={bool(query_result.preview_data)}")
        elif assistant_msg:
            # For non-SQL queries, extract the assistant's text response
            query_result.text_response = assistant_msg.get('content', '')
            query_result.reasoning = query_result.text_response
            logger.debug(f"Extracted AssistantMessage content (length: {len(query_result.text_response)})")
        else:
            logger.warning("No UserDataReference or AssistantMessage found")
    

    
    def _redact_driver_names(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Redact driver name columns by replacing values with '*'.

        This feature protects against accidental exposure of driver names in query
        results by redacting known driver name columns. However, it is NOT a
        security boundary:

        - It only redacts columns with specific names (DisplayName, LastName, etc.)
        - It cannot prevent malicious prompts that rename columns or extract data
          in other ways
        - It is designed to prevent accidental leaks, not deliberate data exfiltration

        For true data protection, implement access controls at the API/database level.

        Args:
            df: DataFrame to redact

        Returns:
            DataFrame with redacted driver names (modified in place)
        """
        if not self.driver_privacy_mode or df is None or df.empty:
            return df

        redacted_columns = []
        for col in df.columns:
            if col in self.DRIVER_NAME_COLUMNS:
                df[col] = "*"
                redacted_columns.append(col)

        if redacted_columns:
            logger.info(f"Driver privacy mode: Redacted columns {redacted_columns}")

        return df

    def _create_dataframe(self, query_result: QueryResult) -> None:
        """Create DataFrame from preview data if available."""
        if query_result.preview_data:
            try:
                query_result.data_frame = pd.DataFrame(query_result.preview_data)
                logger.debug(f"Created DataFrame with shape: {query_result.data_frame.shape}")
                # Apply driver privacy redaction
                query_result.data_frame = self._redact_driver_names(query_result.data_frame)
            except Exception as e:
                logger.warning(f"Failed to create DataFrame from preview data: {e}")
    
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
                
                if result.status in [QueryStatus.DONE, QueryStatus.FAILED]:
                    if result.status == QueryStatus.DONE:
                        logger.info(f"Query completed after {elapsed:.1f} seconds")
                    else:
                        logger.error(f"Query failed after {elapsed:.1f} seconds: {result.error}")
                    return result
                    
                # Update polling strategy based on elapsed time
                poll_interval = self._calculate_poll_interval(elapsed, poll_interval)
                
                # Log progress periodically
                if int(elapsed) % 30 == 0 and elapsed > 0:
                    logger.info(f"Still processing... ({elapsed:.0f}s elapsed)")
                
                consecutive_errors = 0  # Reset error counter on success
                
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
    
    def _calculate_poll_interval(self, elapsed: float, current_interval: float) -> float:
        """Calculate next polling interval based on elapsed time."""
        if elapsed > 20:  # After 20 seconds, slow down
            return min(5.0, current_interval * 1.1)
        elif elapsed > 10:  # After 10 seconds, medium speed
            return min(3.0, current_interval * 1.05)
        else:
            return current_interval
    
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
            return query_result.data_frame

        try:
            logger.debug("Downloading full dataset from signed URL")
            timeout = aiohttp.ClientTimeout(total=120)

            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(query_result.signed_urls[0]) as response:
                    response.raise_for_status()
                    csv_content = await response.text()
                    df = pd.read_csv(StringIO(csv_content))
                    # Apply driver privacy redaction
                    return self._redact_driver_names(df)

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
            ValueError: If question is invalid
        """
        chat_id, message_group_id = await self.start_query(question)
        return await self.wait_for_completion(chat_id, message_group_id, max_wait_seconds)
    
    async def test_connection(self) -> Dict[str, Any]:
        """
        Test the connection and authentication.
        
        Returns:
            Dictionary with test results including success/failure status
        """
        result = {
            "config_valid": False,
            "auth_successful": False,
            "api_working": False,
            "errors": [],
            "database": self.credentials.database
        }
        
        try:
            # Test configuration
            result["config_valid"] = True
            
            # Test authentication
            credentials = await self.authenticate()
            result["auth_successful"] = True
            result["session_id"] = credentials.get("sessionId", "Unknown")[:20] + "..."
            
            # Test API call
            await self._make_api_call("create-chat", {})
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
    import sys
    
    def configure_logging(verbose: bool = False) -> None:
        """Configure logging for CLI usage."""
        level = logging.DEBUG if verbose else logging.INFO
        logging.basicConfig(
            level=level,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
    
    def print_data_preview(df: pd.DataFrame, max_rows: int = 10) -> None:
        """Print a nicely formatted data preview."""
        preview_rows = min(max_rows, len(df))
        print(f"\nData shape: {df.shape}")
        print("\nData preview:")
        print(df.head(preview_rows).to_string(index=False))
        
        if len(df) > preview_rows:
            print(f"\n... and {len(df) - preview_rows} more rows")
    
    async def run_cli():
        """Run the command line interface."""
        parser = argparse.ArgumentParser(description="Geotab ACE Utility")
        parser.add_argument("--test", action="store_true", help="Test connection")
        parser.add_argument("--question", type=str, help="Ask a question")
        parser.add_argument("--timeout", type=int, default=300, help="Timeout in seconds")
        parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")
        
        args = parser.parse_args()
        
        configure_logging(args.verbose)
        
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
                    return
                
                # Show SQL query if available
                if result.sql_query:
                    print(f"\nSQL Query:\n{result.sql_query}")
                
                # Show reasoning/analysis if available
                if result.reasoning:
                    print(f"\nReasoning:\n{result.reasoning}")
                if result.interpretation:
                    print(f"\nInterpretation:\n{result.interpretation}")
                    
                if result.text_response:
                    print(f"\nResponse:\n{result.text_response}")
                else:
                    print("\nNo text response received.")
                    
                if result.data_frame is not None:
                    print_data_preview(result.data_frame)
                else:
                    print("\nNo data returned.")
                    
            else:
                parser.print_help()
                
        except KeyboardInterrupt:
            print("\nOperation cancelled by user")
        except Exception as e:
            print(f"Error: {e}")
            if args.verbose:
                import traceback
                traceback.print_exc()
            sys.exit(1)
    
    asyncio.run(run_cli())