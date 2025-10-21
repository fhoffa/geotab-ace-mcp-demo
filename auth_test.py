#!/usr/bin/env python3
"""
Geotab Authentication Comparison Test

This script tests both your original working method and the async method
to identify any differences causing the authentication failure.
"""

import json
import requests
import aiohttp
import asyncio
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()

def test_original_method():
    """Test using your exact original authentication method"""
    print("=== Testing Original Method (requests + sync) ===")
    
    api_url = os.getenv("GEOTAB_API_URL", "https://my.geotab.com/apiv1")
    headers = {"Content-Type": "application/json"}
    
    username = os.getenv("GEOTAB_API_USERNAME")
    password = os.getenv("GEOTAB_API_PASSWORD")
    database = os.getenv("GEOTAB_API_DATABASE")
    
    print(f"Username: {username}")
    print(f"Database: {database}")
    print(f"Password length: {len(password)} chars")
    
    auth_data = {
        "method": "Authenticate",
        "params": {
            "userName": username,
            "password": password,
            "database": database
        }
    }

    try:
        print("\nSending request with requests library...")
        response = requests.post(api_url, data=json.dumps(auth_data), headers=headers)
        print(f"Status: {response.status_code}")
        print(f"Headers: {dict(response.headers)}")
        
        response.raise_for_status()
        auth_result = response.json()

        if "error" in auth_result:
            print("❌ Original method failed!")
            print(f"Error: {json.dumps(auth_result['error'], indent=2)}")
            return False
        else:
            print("✅ Original method successful!")
            print(f"Credentials: {auth_result['result']['credentials']}")
            return True
            
    except Exception as e:
        print(f"❌ Original method error: {e}")
        return False

async def test_async_method():
    """Test using the async method from MCP server"""
    print("\n=== Testing Async Method (aiohttp) ===")
    
    api_url = os.getenv("GEOTAB_API_URL", "https://my.geotab.com/apiv1")
    
    username = os.getenv("GEOTAB_API_USERNAME")
    password = os.getenv("GEOTAB_API_PASSWORD")
    database = os.getenv("GEOTAB_API_DATABASE")
    
    auth_data = {
        "method": "Authenticate",
        "params": {
            "userName": username,
            "password": password,
            "database": database
        }
    }

    try:
        print("Sending request with aiohttp library...")
        async with aiohttp.ClientSession(
            headers={"Content-Type": "application/json"},
            timeout=aiohttp.ClientTimeout(total=30)
        ) as session:
            async with session.post(api_url, data=json.dumps(auth_data)) as response:
                print(f"Status: {response.status}")
                print(f"Headers: {dict(response.headers)}")
                
                response_text = await response.text()
                print(f"Raw response: {response_text}")
                
                response.raise_for_status()
                auth_result = json.loads(response_text)

        if "error" in auth_result:
            print("❌ Async method failed!")
            print(f"Error: {json.dumps(auth_result['error'], indent=2)}")
            return False
        else:
            print("✅ Async method successful!")
            print(f"Credentials: {auth_result['result']['credentials']}")
            return True
            
    except Exception as e:
        print(f"❌ Async method error: {e}")
        return False

async def test_with_different_encodings():
    """Test different ways of encoding the request body"""
    print("\n=== Testing Different Encodings ===")
    
    api_url = os.getenv("GEOTAB_API_URL", "https://my.geotab.com/apiv1")
    username = os.getenv("GEOTAB_API_USERNAME")
    password = os.getenv("GEOTAB_API_PASSWORD")
    database = os.getenv("GEOTAB_API_DATABASE")
    
    auth_data = {
        "method": "Authenticate",
        "params": {
            "userName": username,
            "password": password,
            "database": database
        }
    }
    
    # Test 1: JSON string body (current method)
    print("\n1. Testing with JSON string body...")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                api_url,
                data=json.dumps(auth_data),
                headers={"Content-Type": "application/json"}
            ) as response:
                print(f"JSON string - Status: {response.status}")
                response_text = await response.text()
                print(f"JSON string - Response: {response_text[:200]}...")
    except Exception as e:
        print(f"JSON string method error: {e}")
    
    # Test 2: JSON object body
    print("\n2. Testing with JSON object body...")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                api_url,
                json=auth_data  # This automatically sets content-type and serializes
            ) as response:
                print(f"JSON object - Status: {response.status}")
                response_text = await response.text()
                print(f"JSON object - Response: {response_text[:200]}...")
    except Exception as e:
        print(f"JSON object method error: {e}")
    
    # Test 3: Try different headers
    print("\n3. Testing with additional headers...")
    try:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "Geotab-MCP-Server/1.0"
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(
                api_url,
                data=json.dumps(auth_data),
                headers=headers
            ) as response:
                print(f"Extra headers - Status: {response.status}")
                response_text = await response.text()
                print(f"Extra headers - Response: {response_text[:200]}...")
    except Exception as e:
        print(f"Extra headers method error: {e}")

async def main():
    """Run all tests"""
    # Test original method
    original_works = test_original_method()
    
    # Test async method  
    async_works = await test_async_method()
    
    # Test different encodings
    await test_with_different_encodings()
    
    print(f"\n=== Summary ===")
    print(f"Original method (requests): {'✅ Works' if original_works else '❌ Failed'}")
    print(f"Async method (aiohttp): {'✅ Works' if async_works else '❌ Failed'}")
    
    if original_works and not async_works:
        print("\n💡 The issue is with the async implementation!")
        print("This suggests a difference in how aiohttp vs requests handles the request.")
    elif not original_works:
        print("\n💡 Both methods failed - this is a credentials issue.")
    else:
        print("\n🎉 Both methods work!")

if __name__ == "__main__":
    asyncio.run(main())