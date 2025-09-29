# Geotab Ace API - Complete Developer Documentation

## Table of Contents
1. [Overview](#overview)
2. [Architecture & Core Concepts](#architecture--core-concepts)
3. [Authentication & Prerequisites](#authentication--prerequisites)
4. [API Reference](#api-reference)
5. [Workflow & Usage Patterns](#workflow--usage-patterns)
6. [Prompt Engineering Guide](#prompt-engineering-guide)
7. [Response Handling](#response-handling)
8. [Data Domains & Query Examples](#data-domains--query-examples)
9. [Error Handling](#error-handling)
10. [Rate Limits & Monitoring](#rate-limits--monitoring)
11. [Best Practices & Anti-Patterns](#best-practices--anti-patterns)
12. [Code Examples](#code-examples)

---

## Overview

**Geotab Ace** is an AI-powered analytics service that converts natural language questions into SQL queries, executes them against Google BigQuery (GBQ), and returns structured results with reasoning.

### Key Capabilities
- Natural language to SQL query generation
- Access to comprehensive fleet telematics data
- Multi-stage validation (Audit Layer → Knowledge Layer → Query Execution)
- Contextual reasoning and data interpretation
- RESTful API access via MyGeotab platform

### Design Philosophy
Ace uses a defensive multi-layer architecture:
1. **Audit Layer**: Validates query appropriateness and security
2. **Knowledge Layer**: Matches questions to relevant schemas
3. **Generative AI**: Constructs BigQuery-compatible SQL
4. **Reasoning Engine**: Synthesizes results into human-readable responses

---

## Architecture & Core Concepts

### Object Model Hierarchy

```
Chat (Conversation Session)
  └── Message Group (One Q&A Exchange)
        └── Message (Individual Communication)
              ├── UserPrompt
              ├── COTMessage (Chain of Thought)
              ├── AssistantMessage
              └── UserDataReference
```

### Object Definitions

#### **Chat**
- Represents a complete conversation thread
- Contains all message groups for a session
- Identified by unique `chat_id`
- New topics should create new chats

#### **Message Group**
- One complete question-answer cycle
- Contains user prompt + processing messages + final response
- Identified by `message_group_id`
- Has status: `PROCESSING`, `DONE`, or `FAILED`

#### **Message Types**

| Type | Role | Purpose | Contains |
|------|------|---------|----------|
| `UserPrompt` | user | Original question | Prompt text |
| `COTMessage` | assistant | Thinking process | Masked tool inputs/outputs |
| `AssistantMessage` | assistant | Direct response | Text response (no data) |
| `UserDataReference` | system | Data response | SQL, results, reasoning |

### Data Flow

```
User Question
    ↓
[Audit Layer] ← Validation
    ↓
[Knowledge Layer] ← Schema Matching
    ↓
[LLM] ← Query Generation
    ↓
[BigQuery] ← Execution
    ↓
[Reasoning Engine] ← Result Synthesis
    ↓
User Response (with data + reasoning)
```

---

## Authentication & Prerequisites

### Account Setup Requirements

#### 1. Account Configuration
- **Data Access Level**: Must be set to **Everything**
- **Account Type**: Must be a **Service Account**
  - Location: Authentication and Security section
  - Standard user accounts are being deprecated for API calls
  - Set next to security clearance

#### 2. Required Permissions

Your account must have all of the following permissions:

```
Core Access:
- ViewAceAI

Device & Diagnostics:
- DeviceList
- EngineDiagnosticList
- EngineTypeList

Analytics:
- ViewDriverAnalytics
- ViewVehicleAnalytics
- DriverIdentificationClearance

Performance & EV:
- ViewEVPerformanceData
- ViewFaultData

Exceptions & Rules:
- ExceptionsReport
- ExceptionsList

Data Views:
- ViewStatusData
- ViewGroups

Location:
- ZoneList

Reporting:
- TripsActivityReport
- FuelTransactionList
- CustomerVisitsReport
```


### Authentication Process

#### Step 1: Obtain Session ID

```http
POST https://my.geotab.com/apiv1
Content-Type: application/json

{
  "method": "Authenticate",
  "params": {
    "database": "your_database_name",
    "userName": "your_username",
    "password": "your_password"
  }
}
```

**Response:**
```json
{
  "result": {
    "credentials": {
      "sessionId": "abc123xyz...",
      "database": "your_database_name",
      "userName": "your_username"
    }
  }
}
```

#### Step 2: Use Session ID in Ace Calls

**Important**: 
- Session IDs are temporary and expire
- Do NOT use the password field in Ace API calls
- Only use `sessionId` in credentials object

---

## API Reference

### Base Endpoint

```
POST https://my.geotab.com/apiv1
Content-Type: application/json
```

### Primary Method: GetAceResults

All Ace operations use the `GetAceResults` method with varying `functionName` parameters.

#### Request Structure

```json
{
  "method": "GetAceResults",
  "params": {
    "serviceName": "dna-planet-orchestration",
    "functionName": "<function-name>",
    "customerData": true,
    "functionParameters": { 
      /* function-specific parameters */
    },
    "credentials": {
      "database": "<database-name>",
      "userName": "<username>",
      "sessionId": "<session-id>"
    }
  }
}
```

#### Required Parameters (All Calls)

| Parameter | Type | Value | Description |
|-----------|------|-------|-------------|
| `serviceName` | string | `"dna-planet-orchestration"` | Backend orchestration service (always this value) |
| `functionName` | string | varies | Specific Ace function to call |
| `customerData` | boolean | `true` | Access your own data (always true) |
| `functionParameters` | object | varies | Function-specific parameters |
| `credentials` | object | - | Authentication credentials |

#### Credentials Object

```json
{
  "database": "your_database_name",
  "userName": "your_username",
  "sessionId": "your_session_id"
}
```

**Note**: Do NOT include `password` field. Use `sessionId` only.

### Available Functions

#### 1. create-chat

**Purpose**: Initialize a new conversation session

**Function Parameters**: `{}` (empty object)

**Request Example**:
```json
{
  "method": "GetAceResults",
  "params": {
    "serviceName": "dna-planet-orchestration",
    "functionName": "create-chat",
    "customerData": true,
    "functionParameters": {},
    "credentials": {
      "database": "myfleet",
      "userName": "api_user",
      "sessionId": "abc123..."
    }
  }
}
```

**Response**:
```json
{
  "result": {
    "apiResult": {
      "results": [
        {
          "chat_id": "chat_abc123xyz"
        }
      ],
      "errors": []
    },
    "errors": []
  },
  "jsonrpc": "2.0"
}
```

**Returns**: `chat_id` (string) - Use in all subsequent calls for this conversation

---

#### 2. send-prompt

**Purpose**: Submit a question to Ace

**Function Parameters**:
```json
{
  "chat_id": "string (required)",
  "prompt": "string (required)"
}
```

**Request Example**:
```json
{
  "method": "GetAceResults",
  "params": {
    "serviceName": "dna-planet-orchestration",
    "functionName": "send-prompt",
    "customerData": true,
    "functionParameters": {
      "chat_id": "chat_abc123xyz",
      "prompt": "Show all speeding exceptions from last week with all details"
    },
    "credentials": {
      "database": "myfleet",
      "userName": "api_user",
      "sessionId": "abc123..."
    }
  }
}
```

**Response**:
```json
{
  "result": {
    "apiResult": {
      "results": [
        {
          "message_group": {
            "id": "msg_grp_xyz789"
          }
        }
      ],
      "errors": []
    },
    "errors": []
  },
  "jsonrpc": "2.0"
}
```

**Returns**: `message_group_id` (string) - Use to retrieve results

---

#### 3. get-message-group

**Purpose**: Retrieve processing status and results

**Function Parameters**:
```json
{
  "chat_id": "string (required)",
  "message_group_id": "string (required)"
}
```

**Request Example**:
```json
{
  "method": "GetAceResults",
  "params": {
    "serviceName": "dna-planet-orchestration",
    "functionName": "get-message-group",
    "customerData": true,
    "functionParameters": {
      "chat_id": "chat_abc123xyz",
      "message_group_id": "msg_grp_xyz789"
    },
    "credentials": {
      "database": "myfleet",
      "userName": "api_user",
      "sessionId": "abc123..."
    }
  }
}
```

**Response Structure**: See [Response Handling](#response-handling) section for detailed breakdown.

**Status Values**:
- `"PROCESSING"` - Query still being processed
- `"DONE"` - Results ready
- `"FAILED"` - Error occurred

---

#### 4. get-customer

**Purpose**: Check usage statistics and rate limits

**Function Parameters**: `{}` (empty object)

**Request Example**:
```json
{
  "method": "GetAceResults",
  "params": {
    "serviceName": "dna-planet-orchestration",
    "functionName": "get-customer",
    "customerData": true,
    "functionParameters": {},
    "credentials": {
      "database": "myfleet",
      "userName": "api_user",
      "sessionId": "abc123..."
    }
  }
}
```

**Response**:
```json
{
  "result": {
    "apiResult": {
      "results": [
        {
          "customer": {
            "database": "myfleet",
            "total_calls": 247,
            "monthly_limit": 1000,
            "remaining_calls": 753
          }
        }
      ],
      "errors": []
    },
    "errors": []
  },
  "jsonrpc": "2.0"
}
```

---

#### 5. update-signed-url

**Purpose**: Regenerate expired data URL (valid for 24 hours after original query)

**Function Parameters**:
```json
{
  "message_id": "string (required)"
}
```

**Request Example**:
```json
{
  "method": "GetAceResults",
  "params": {
    "serviceName": "dna-planet-orchestration",
    "functionName": "update-signed-url",
    "customerData": true,
    "functionParameters": {
      "message_id": "msg_def456ghi"
    },
    "credentials": {
      "database": "myfleet",
      "userName": "api_user",
      "sessionId": "abc123..."
    }
  }
}
```

**Use Case**: When the 24-hour `signed_urls` expiration has passed and you need to re-access query results.

---

## Workflow & Usage Patterns

### Standard Request Flow

```python
# Step 1: Authenticate
session_id = authenticate(username, password, database)

# Step 2: Create Chat
chat_id = create_chat(session_id, database, username)

# Step 3: Send Prompt
message_group_id = send_prompt(
    session_id, 
    database, 
    username, 
    chat_id, 
    "Your question here"
)

# Step 4: Poll for Results
while True:
    result = get_message_group(
        session_id,
        database,
        username,
        chat_id,
        message_group_id
    )
    
    status = result['message_group']['status']['status']
    
    if status == 'DONE':
        # Extract and process results
        break
    elif status == 'FAILED':
        # Handle error
        break
    else:  # PROCESSING
        time.sleep(5)  # Wait before next poll
```

### Polling Strategy

**Recommended Approach**:
- Poll every 5 seconds during `PROCESSING` state
- Implement exponential backoff for long-running queries
- Set maximum timeout (e.g., 2 minutes)

**Example**:
```python
import time

def poll_for_results(chat_id, msg_group_id, max_wait=120):
    """Poll with exponential backoff"""
    wait_time = 2
    elapsed = 0
    
    while elapsed < max_wait:
        result = get_message_group(chat_id, msg_group_id)
        status = result['message_group']['status']['status']
        
        if status in ['DONE', 'FAILED']:
            return result
        
        time.sleep(wait_time)
        elapsed += wait_time
        wait_time = min(wait_time * 1.5, 10)  # Cap at 10 seconds
    
    raise TimeoutError("Query exceeded maximum wait time")
```

### Multi-Question Conversations

**Same Chat, Multiple Questions**:
```python
chat_id = create_chat()

# Question 1
msg_group_1 = send_prompt(chat_id, "Which vehicle has worst fuel economy?")
result_1 = wait_for_results(chat_id, msg_group_1)

# Question 2 (in same context)
msg_group_2 = send_prompt(chat_id, "Show me its trips from last week")
result_2 = wait_for_results(chat_id, msg_group_2)
```

**New Topic, New Chat**:
```python
# Chat 1: Safety questions
chat_id_safety = create_chat()
send_prompt(chat_id_safety, "Show speeding exceptions")

# Chat 2: Fuel economy questions (separate context)
chat_id_fuel = create_chat()
send_prompt(chat_id_fuel, "Show fuel usage by vehicle")
```

---

## Prompt Engineering Guide

### Prompt Structure Formula

**Who + Metric + Time Expression + Statistic + [Group By]**

| Component | Required | Examples |
|-----------|----------|----------|
| **Who** | Yes | "vehicle X", "my fleet", "driver group A", "all vehicles" |
| **Metric** | Yes | "fuel usage", "speeding exceptions", "idling time", "trips" |
| **Time Expression** | Yes | "last week", "yesterday", "March 1-30 2024", "year to date" |
| **Statistic** | Recommended | "total", "average", "top 10", "count", "breakdown" |
| **Group By** | Optional | "by vehicle", "by day", "by driver", "by zone" |

### Quality Comparison

#### ❌ Poor Prompts
```
"Show idling"
→ Missing: who, timeframe

"How much fuel?"
→ Missing: who, timeframe

"Speeding violations"
→ Missing: timeframe, details level

"Vehicles in zones"
→ Missing: which zones, when
```

#### ✅ Good Prompts
```
"Show all idling within zone A for last week"
→ Has: location, timeframe

"How much fuel did group A use from March 1st to March 30th 2024?"
→ Has: who, metric, specific dates

"Show all speeding exceptions from yesterday with all details"
→ Has: metric, timeframe, detail level

"Which vehicles idle for more than 200s within the Geotab HQ zone?"
→ Has: threshold, specific zone name
```

### Critical Syntax Rules

#### 1. **Use @ Symbol for Name Discovery**
When you don't know exact asset, zone, rule, or diagnostic names:

```
❌ "Show speeding in downtown zone"
✅ "@ zones" → Get list of zones → "Show speeding in Downtown_District zone"
```

#### 2. **Zone References Must Include "zone"**
```
❌ "Which vehicles idle in Geotab HQ?"
✅ "Which vehicles idle in the Geotab HQ zone?"
```

#### 3. **Exception Queries Must Use "exception"**
For custom rules, always include the word "exception":

```
❌ "Show all fuel level 11% violations"
✅ "Show all fuel level 11% exceptions"

❌ "Show collision events from last week"
✅ "Show all collision exceptions from last week with details"
```

#### 4. **Request "all details" for Complete Data**
```
❌ "Show speeding exceptions from yesterday"
✅ "Show all speeding exceptions from yesterday with all details"
```

#### 5. **Specify Time Expressions Clearly**
```
❌ "recently"
✅ "in the last 7 days"

❌ "this month"
✅ "from September 1st to September 29th 2024"

❌ "last quarter"
✅ "from July 1st to September 30th 2024"
```

### Domain-Specific Prompt Patterns

#### Safety Queries
```
- "Show all speeding exceptions from [date] with all details"
- "Show all speeding exceptions from [date] by vehicle"
- "List the top 10 vehicles that had the longest speeding exception yesterday"
- "Show all harsh event exceptions of my fleet from [date]"
- "Which vehicle has the most speeding events?"
- "Show all collision exceptions from [date]"
- "What was the maximum speed in my fleet last week, which vehicle was it, and where did it take place?"
```

#### Fuel & Economy
```
- "Which vehicle has the worst fuel economy in liters?"
- "What is the average fuel usage per 100km?"
- "Which vehicle has used the most gas in the last 3 months?"
- "Top 10 vehicles with highest fuel consumption per hour"
- "What is the average MPG per manufacturer?"
- "At $1.78 per liter actual idle fuel used, what is the cost of idle fuel use year to date?"
```

#### Maintenance & Diagnostics
```
- "Show all vehicles with active faults with details"
- "Do any vehicles have pending engine faults?"
- "What vehicles have low cranking voltage?"
- "List any vehicles that have had engine faults in last 3 days and the vehicle fault codes"
- "Show me vehicles with possible battery issues"
- "Show all the current fuel tank values"
```

#### Location & Zones
```
- "What was the most visited location by vehicles in the last month?"
- "Which zones are most of the idling happening in?"
- "Top 3 zones with the most idling?"
- "What trucks were at zone [Zone name] on [date]"
- "How many vehicles crossed state lines last week?"
- "Show me a list of all zone name=[customer visits] from yesterday"
```

#### Driver Analytics
```
- "Which drivers had the highest total driving time last week?"
- "Which driver has driven the most distance in the past month?"
- "Which drivers are working more than 40 hours per week?"
- "Who is my most dangerous driver?"
- "Show the most under utilized drivers last week"
- "Which drivers have the most [exception name] incidents in [time period]?"
- "Which drivers visited Zone [name] and stayed more than 6 hours?"
```

#### Electric Vehicles
```
- "Which battery electric vehicle traveled the most distance this year?"
- "What is the average utilization of my EVs battery capacity?"
- "Which vehicles are most suited to be replaced with EVs?"
- "What is the average starting state of charge when my electric vehicles start charging?"
- "Provide a daily breakdown report of all vehicles achieving between 1 and 3 mi/kWh"
```

#### Trips
```
- "How many trips did my fleet make last week?"
- "Show all the trip details of vehicle [X] in the past week"
- "What is the average trip duration and distance for a vehicle in my fleet?"
- "Show me the top/longest trip from yesterday with start, stop and total distance covered"
- "Which vehicles drove continuously without stopping for more than 4 hours? Show the trip details"
```

### Advanced Techniques

#### Comparative Analysis
```
"Compare seatbelt usage between March 1st 2024 and April 1st 2024"
"How does driver A compare to driver B in terms of safety?"
"Compare miles driven last month per driver vs the month before"
```

#### Thresholds & Filters
```
"Show all vehicles with more than 15 speeding incidents last month"
"Which vehicles spend more than 6 hours in zone X?"
"List drivers who parked in Zone X for more than 8 hours on [date]"
```

#### Aggregations
```
"Total vehicle distance, MPG, and idling time during last month for my fleet"
"Give me a breakdown of all faults reported by [vehicle X]"
"Calculate drivers utilization time by calculating total driving time, assume full utilization of 13 hours per day"
```

---

## Response Handling

### Full Response Structure

```json
{
  "result": {
    "apiResult": {
      "results": [
        {
          "message_group": {
            "id": "msg_grp_xyz789",
            "messages": {
              "msg_001": { /* UserPrompt */ },
              "msg_002": { /* COTMessage */ },
              "msg_003": { /* UserDataReference */ }
            },
            "status": {
              "status": "DONE",
              "code": 0,
              "message": ""
            },
            "creation_date_unix_milli": 1743696866511,
            "terminal_date_unix_milli": 1743696875257
          }
        }
      ],
      "errors": []
    },
    "errors": []
  },
  "jsonrpc": "2.0"
}
```

### Message Type Details

#### UserPrompt Message
```json
{
  "type": "UserPrompt",
  "role": "user",
  "chat_id": "chat_abc123",
  "message_group_id": "msg_grp_xyz789",
  "id": "msg_001",
  "status": {
    "status": "DONE",
    "code": 0,
    "message": ""
  },
  "creation_date_unix_milli": 1743696866887,
  "content": "Give me the top 5 vehicle make/models with the worst fuel economy"
}
```

#### COTMessage (Chain of Thought)
```json
{
  "type": "COTMessage",
  "role": "assistant",
  "chat_id": "chat_abc123",
  "message_group_id": "msg_grp_xyz789",
  "id": "msg_002",
  "status": {
    "status": "DONE",
    "code": 0,
    "message": ""
  },
  "creation_date_unix_milli": 1743696867102,
  "tool": "CheckBypass",
  "tool_input": "Masked",
  "thought": "Masked",
  "output": "Masked"
}
```

**Note**: `tool_input`, `thought`, and `output` are masked for security. These messages indicate processing steps but don't expose internal logic.

#### AssistantMessage
```json
{
  "type": "AssistantMessage",
  "role": "assistant",
  "chat_id": "chat_abc123",
  "message_group_id": "msg_grp_xyz789",
  "id": "msg_003",
  "status": {
    "status": "DONE",
    "code": 200,
    "message": ""
  },
  "creation_date_unix_milli": 1743696868234,
  "content": "I found that information for you. Let me know if you need clarification."
}
```

**Use Case**: Simple text responses without data (e.g., clarification questions, acknowledgments).

#### UserDataReference (Primary Result)

This is the most important message type containing your query results.

```json
{
  "type": "UserDataReference",
  "role": "system",
  "chat_id": "chat_abc123",
  "message_group_id": "msg_grp_xyz789",
  "id": "msg_004",
  "status": {
    "status": "DONE",
    "code": 200,
    "message": ""
  },
  "creation_date_unix_milli": 1743696875047,
  "data_object_reference_id": "data_ref_001",
  
  "preview_array": [
    {
      "Manufacturer": "Kia",
      "Model": "Sorento",
      "FuelEconomy_MPG": 0.0231
    },
    {
      "Manufacturer": "Volvo",
      "Model": "S60",
      "FuelEconomy_MPG": 0.1321
    }
  ],
  
  "signed_urls": [
    "https://storage.googleapis.com/... [24-hour link to full results]"
  ],
  
  "expiration_date_unix_milli": 1743783274000,
  
  "user_credentials": {
    "email": "user@example.com",
    "guid": "guid_abc123",
    "database": "myfleet",
    "sessionId": "",
    "serverName": ""
  },
  
  "reasoning": "To answer your question about the top 5 least fuel-efficient vehicle make/models over the past year, I first looked at information about available data tables. I found two tables with relevant information: one containing daily fuel consumption data for each vehicle, and another with vehicle metadata like make, model, and active dates. I assumed \"worst fuel economy\" meant the lowest miles per gallon (MPG). I also assumed you wanted the results for the past year from the current date. I then wrote a query to calculate the MPG for each make and model by summing the total distance driven and total fuel consumed over the past year. The query only considered data where fuel consumption and distance driven were greater than zero, and where the vehicle's make and model were not null. Finally, I limited the results to the 5 lowest MPG values after sorting, giving you the top 5 make/models with the worst fuel economy.",
  
  "interpretation": "",
  
  "columns": [
    "Manufacturer",
    "Model",
    "FuelEconomy_MPG"
  ],
  
  "query": "SELECT t_meta.Manufacturer\n     , t_meta.Model\n     , ROUND(SAFE_DIVIDE(SUM(0.621 * FuelEconomy_Distance_Km), SUM(0.264 * TotalFuel_Litres)), 4) AS FuelEconomy_MPG\nFROM `VehicleKPI_Daily` t_vehicle\nJOIN `LatestVehicleMetadata` t_meta ON t_vehicle.DeviceId = t_meta.DeviceId\nAND t_vehicle.UTC_Date BETWEEN DATE(t_meta.ActiveFrom) AND DATE(t_meta.ActiveTo)\nWHERE UTC_Date >= DATE_SUB(CURRENT_DATE(), INTERVAL 1 YEAR)\n    AND Manufacturer IS NOT NULL\n    AND Model IS NOT NULL\n    AND TotalFuel_Litres > 0\n    AND FuelEconomy_Distance_Km > 0\nGROUP BY Manufacturer\n       , Model\nORDER BY FuelEconomy_MPG ASC\n       , Manufacturer\n       , Model\nLIMIT 5;\n\n-- QUESTION: Provide average fuel efficiency by vehicle make and model\n-- INTERPRETATION: Calculate the average fuel efficiency in miles per gallon for each vehicle make and model in the fleet for the last 3 months sorted by fuel efficiency.\n-- CATEGORY: Sustainability\n-- DISPLAY: False"
}
```

### Key Fields Explained

| Field | Type | Description |
|-------|------|-------------|
| `preview_array` | array | Sample rows (typically 5-10) for quick visualization |
| `signed_urls` | array | Links to full result JSON (valid 24 hours) |
| `expiration_date_unix_milli` | number | When signed URLs expire (Unix timestamp) |
| `reasoning` | string | LLM's explanation of query logic and assumptions |
| `interpretation` | string | Additional context (often empty) |
| `columns` | array | Column names in result set |
| `query` | string | Complete SQL query executed (BigQuery syntax) |
| `data_object_reference_id` | string | Internal reference ID |

### Extracting Results

#### Python Example
```python
def extract_results(message_group):
    """Extract final results from message group"""
    messages = message_group['messages']
    
    # Get last message (final result)
    last_message = list(messages.values())[-1]
    
    if last_message['type'] == 'UserDataReference':
        return {
            'data_preview': last_message['preview_array'],
            'full_data_url': last_message['signed_urls'][0],
            'sql_query': last_message['query'],
            'reasoning': last_message['reasoning'],
            'columns': last_message['columns'],
            'expires_at': last_message['expiration_date_unix_milli']
        }
    elif last_message['type'] == 'AssistantMessage':
        return {
            'message': last_message['content'],
            'type': 'text_only'
        }
    else:
        raise ValueError(f"Unexpected final message type: {last_message['type']}")
```

### Accessing Full Results

The `signed_urls` field contains links to complete result JSON files (not just preview):

```python
import requests

def download_full_results(signed_url):
    """Download complete results from signed URL"""
    response = requests.get(signed_url)
    response.raise_for_status()
    return response.json()

# Usage
result = extract_results(message_group)
if 'full_data_url' in result:
    full_data = download_full_results(result['full_data_url'])
    # Process all rows, not just preview
```

**Important**: URLs expire after 24 hours. Use `update-signed-url` to regenerate.

---

## Data Domains & Query Examples

### Available Datasets

Ace has access to the following data domains in Google BigQuery:

| Domain | Tables/Views | Key Metrics |
|--------|--------------|-------------|
| **Trips** | Trip details | Distance, duration, speed metrics, idling duration, start/end locations |
| **GPS** | GPS logs | Coordinates, speed, GPS connection status, timestamps |
| **Zones** | Zone definitions | Details, coordinates, group associations, type, boundaries |
| **Devices** | Device data | Active times, groups, timezone, type, billing info, replacement info, engine hours, odometer readings |
| **Rules & Exceptions** | Rules, Exceptions | Rule conditions, associations, exception events, timestamps, severity |
| **Diagnostics** | Diagnostic data | Status, descriptions, measures, fault classes, severity, source ECU |
| **EV Data** | EV assessments | Suitability scores, charge times, trip details, energy estimates, emissions comparisons |
| **Vehicle KPIs** | KPI aggregations | Idling, engine hours, fuel usage, fuel economy, mileage, odometer, maintenance insights |
| **Safety** | Safety analytics | Predictive analytics, collision probability, collision count, harsh events |
| **Vehicle Metadata** | Vehicle master data | Engine type, make, model, year, manufacturer, MyGeotab Groups, VIN |

### Query Examples by Category

#### Safety Queries

##### Basic Speeding
```
Prompt: "Show all speeding exceptions from yesterday with all details"

Returns:
- Vehicle name
- Speed limit
- Actual speed
- Duration
- Location
- Timestamp
- Driver (if assigned)
```

##### Top Violations
```
Prompt: "List the top 10 vehicles that had the longest speeding exception yesterday"

Returns:
- Ranked list of vehicles
- Total speeding duration per vehicle
- Number of incidents
- Average excess speed
```

##### Safety Rankings
```
Prompt: "Rank the groups from best to worst safety-wise"

Returns:
- Group name
- Total safety incidents
- Incident types breakdown
- Safety score/ranking
```

##### Location-Based Safety
```
Prompt: "What was the maximum speed in my fleet last week, which vehicle was it, and where did it take place?"

Returns:
- Maximum speed recorded
- Vehicle identification
- GPS coordinates
- Zone name (if in zone)
- Timestamp
```

#### Fuel Economy Queries

##### Vehicle Rankings
```
Prompt: "Which vehicle has the worst fuel economy in liters?"

Returns:
- Vehicle name
- Fuel economy (L/100km)
- Total fuel consumed
- Distance traveled
- Time period analyzed
```

##### Manufacturer Analysis
```
Prompt: "What is the average MPG per manufacturer?"

Returns:
- Manufacturer name
- Average MPG
- Number of vehicles
- Total distance
- Total fuel consumed
```

##### Cost Analysis
```
Prompt: "At $1.78 per liter actual idle fuel used in liters, what is the cost of idle fuel use year to date?"

Returns:
- Total idle fuel (liters)
- Cost calculation
- Breakdown by month
- Top offending vehicles
```

##### Trend Analysis
```
Prompt: "At what age do my vehicles start to see a decrease in fuel economy?"

Returns:
- Vehicle age brackets
- Average fuel economy per age
- Trend analysis
- Regression insights
```

#### Maintenance & Diagnostics

##### Active Faults
```
Prompt: "Show all vehicles with active faults with details"

Returns:
- Vehicle name
- Fault code (DTC)
- Fault description
- Severity level
- First occurrence
- Occurrence count
```

##### Predictive Issues
```
Prompt: "Show me vehicles with possible battery issues"

Returns:
- Vehicle name
- Cranking voltage readings
- Battery age (if available)
- Last reading timestamp
- Severity assessment
```

##### Fault Trends
```
Prompt: "Which make of vehicle has the most engine faults in September 2024?"

Returns:
- Manufacturer ranking
- Total fault count per make
- Common fault types
- Vehicles affected
```

##### Vehicle-Specific History
```
Prompt: "Give me a breakdown of all of the faults reported by [vehicle X]"

Returns:
- Complete fault history
- Fault codes and descriptions
- Timestamps
- Resolution status
- Pattern analysis
```

#### Idling Analysis

##### Fleet-Wide Metrics
```
Prompt: "What was the total duration of idling last month?"

Returns:
- Total idle minutes
- Total idle hours
- Percentage of total engine time
- Comparison to previous periods
```

##### Vehicle Rankings
```
Prompt: "What are the top 10 vehicles with the most idling last month?"

Returns:
- Ranked vehicle list
- Idle duration per vehicle
- Idle fuel wasted
- Percentage of drive time
```

##### Zone-Based Analysis
```
Prompt: "Which zones are most of the idling happening in?"

Returns:
- Zone rankings
- Idle time per zone
- Vehicle count per zone
- Time of day patterns
```

##### Efficiency Metrics
```
Prompt: "Give idling minutes per miles of driving for the vehicles"

Returns:
- Vehicle name
- Idle minutes per mile
- Total miles driven
- Total idle time
- Efficiency ranking
```

#### Trip Analysis

##### Basic Trip Queries
```
Prompt: "How many trips did my fleet make last week?"

Returns:
- Total trip count
- Breakdown by day
- Breakdown by vehicle
- Average trips per vehicle
```

##### Trip Details
```
Prompt: "Show all the trip details of vehicle [X] in the past week"

Returns:
- Start time and location
- End time and location
- Distance traveled
- Duration
- Average speed
- Idle time during trip
- Zones visited
```

##### Long Haul Analysis
```
Prompt: "Which vehicles drove continuously without stopping for more than 4 hours? Show the trip details"

Returns:
- Vehicle identification
- Trip start/end
- Total duration
- Distance covered
- Driver (if assigned)
- Route details
```

##### Aggregate Metrics
```
Prompt: "What is the average trip duration and distance for a vehicle in my fleet?"

Returns:
- Fleet-wide averages
- Breakdown by vehicle type
- Standard deviation
- Min/max values
```

#### Location & Zone Queries

##### Visitation Analysis
```
Prompt: "What was the most visited location by vehicles in the last month?"

Returns:
- Location/zone name
- Visit count
- Total time spent
- Vehicles that visited
- Peak visitation times
```

##### Zone Utilization
```
Prompt: "What's the most underutilized zone?"

Returns:
- Zone name
- Expected vs actual usage
- Visit count
- Total time spent
- Utilization percentage
```

##### Cross-Border Tracking
```
Prompt: "How many vehicles crossed state lines last week?"

Returns:
- Vehicle count
- State crossings breakdown
- Vehicles by state visited
- Timestamps of crossings
```

##### Zone Occupancy
```
Prompt: "What vehicles spend the most time in zone X?"

Returns:
- Ranked vehicle list
- Time spent per vehicle
- Visit frequency
- Average visit duration
```

#### Driver Analytics

##### Activity Metrics
```
Prompt: "Which drivers had the highest total driving time last week?"

Returns:
- Driver rankings
- Total drive time
- Number of trips
- Average trip duration
- Miles driven
```

##### Utilization Analysis
```
Prompt: "Calculate drivers utilization time by calculating total driving time, assume a full utilization of 13 hours per day. Analyze the data for last month, show the date: Driver name, total Driving time, Utilization percentage"

Returns:
- Daily breakdown per driver
- Actual hours vs target (13 hours)
- Utilization percentage
- Over/under utilization flags
```

##### Safety Comparison
```
Prompt: "How does driver A compare to driver B in terms of safety?"

Returns:
- Side-by-side metrics
- Speeding incidents
- Harsh events (braking, acceleration, cornering)
- Collision risk score
- Overall safety rating
```

##### Work Pattern Analysis
```
Prompt: "Which drivers are ending their day outside of the normal working hours?"

Returns:
- Driver list
- Last activity timestamp
- Expected end time
- Deviation from normal
- Pattern frequency
```

##### Unassigned Driving
```
Prompt: "Top 20 vehicles with the most unassigned driving"

Returns:
- Vehicle rankings
- Unassigned drive time
- Unassigned distance
- Percentage of total usage
- Timestamps of unassigned periods
```

#### Electric Vehicle Queries

##### Performance Metrics
```
Prompt: "Which battery electric vehicle traveled the most distance this year?"

Returns:
- Vehicle identification
- Total distance
- Average efficiency (mi/kWh)
- Total energy consumed
- Charging sessions
```

##### Charging Analysis
```
Prompt: "What is the average starting state of charge when my electric vehicles start charging?"

Returns:
- Average SOC at charge start
- Distribution histogram
- Vehicles that charge too early/late
- Optimal vs actual patterns
```

##### Suitability Assessment
```
Prompt: "Which vehicles are most suited to be replaced with EVs?"

Returns:
- Vehicle rankings
- Suitability score
- Daily mileage averages
- Route characteristics
- Estimated ROI
- Recommended EV models
```

##### Efficiency Reporting
```
Prompt: "Provide a daily breakdown report of all vehicles achieving between 1 and 3 mi/kWh"

Returns:
- Daily efficiency data
- Vehicle identification
- Weather conditions
- Route characteristics
- Driver behavior factors
```

#### Device & Fleet Management

##### Device Status
```
Prompt: "How many active devices do I currently have in my fleet?"

Returns:
- Total active count
- Active devices list
- Inactive count
- Recently disconnected
- Connection status breakdown
```

##### Offline Detection
```
Prompt: "Show me devices that are offline but have had a connection before"

Returns:
- Device list
- Last communication date
- Days since last communication
- Days since last movement
- Vehicle status
```

##### Fleet Inventory
```
Prompt: "List all my vehicles, their status, last communication date, days since last communication and days since last moved"

Returns:
- Complete vehicle roster
- Connection status
- Last communication timestamp
- Activity metrics
- Alert flags
```

##### Unplugged Devices
```
Prompt: "Which vehicles in my fleet have a GO Device that has been unplugged for multiple days?"

Returns:
- Vehicle identification
- Days unplugged
- Last known location
- Last communication
- Alert severity
```

#### Rules & Exceptions

##### Custom Rule Queries
```
Prompt: "Show all the 'fuel level 11%' exceptions"
(Assumes you have a custom rule named "fuel level 11%")

Returns:
- Exception occurrences
- Vehicle involved
- Timestamp
- Location
- Fuel level at time
- Duration
```

##### Exception Analysis
```
Prompt: "What are the top three exception rule violations generated by my fleet?"

Returns:
- Ranked exception types
- Occurrence count
- Vehicles involved
- Trend analysis
- Severity distribution
```

##### Driver-Specific Exceptions
```
Prompt: "Show me all the exceptions that driver X has had over the past week"

Returns:
- Complete exception list
- Exception types
- Timestamps
- Locations
- Vehicles driven
- Severity levels
```

##### Zone-Based Exceptions
```
Prompt: "Show all the zone A exceptions from yesterday with details"

Returns:
- All exceptions in zone A
- Exception types
- Vehicles involved
- Entry/exit times
- Rule violated
- Additional context
```

---

## Error Handling

### HTTP & Status Codes

| Code | Status | Meaning | Scope |
|------|--------|---------|-------|
| 200 | Success | Request completed successfully | HTTP Response |
| 400 | Bad Request | Invalid parameters or missing chat | API Error |
| 401 | Unauthorized | Invalid credentials | HTTP Response |
| 429 | Rate Limited | Monthly quota exceeded | API Error |
| 500 | Internal Error | Server-side processing failure | API Error |
| -32000 | JSONRPCError | Authentication or credential format error | JSONRPC Error |

### Error Response Structures

#### Orchestration Service Error
**Cause**: Malformed request structure

```json
{
  "result": {
    "apiResult": {},
    "errors": []
  },
  "jsonrpc": "2.0"
}
```

**Solution**:
- Verify `serviceName` is exactly `"dna-planet-orchestration"`
- Check `functionName` spelling (e.g., `"create-chat"`, not `"createChat"`)
- Ensure `functionParameters` structure matches function requirements
- Validate `customerData` is boolean `true`

#### Authentication Error
**Cause**: Invalid or expired session ID, malformed credentials

```json
{
  "error": {
    "message": "Incorrect login credentials @ 'Invalid credential format.'",
    "code": -32000,
    "data": {
      "id": "request_id_123",
      "type": "InvalidUserException",
      "requestIndex": 0
    },
    "name": "JSONRPCError",
    "errors": [
      {
        "message": "Incorrect login credentials @ 'Invalid credential format.'",
        "name": "InvalidUserException"
      }
    ]
  },
  "jsonrpc": "2.0",
  "requestIndex": 0
}
```

**Solutions**:
1. Re-authenticate to get fresh session ID
2. Verify credentials object structure:
   ```json
   {
     "database": "string",
     "userName": "string",
     "sessionId": "string"
   }
   ```
3. Ensure you're using `sessionId`, NOT `password`
4. Check for typos in field names

#### Chat Not Found Error
**Cause**: Invalid or non-existent chat_id

```json
{
  "result": {
    "apiResult": {
      "results": [],
      "errors": [
        {
          "code": 400,
          "domain": "API",
          "message": "Chat document does not exist",
          "reason": ""
        }
      ]
    },
    "errors": []
  },
  "jsonrpc": "2.0"
}
```

**Solutions**:
- Verify you're using `chat_id` returned from `create-chat`
- Ensure chat_id hasn't been deleted or expired
- Create new chat if needed
- Check for copy/paste errors in chat_id

#### Rate Limit Exceeded
**Cause**: Database exceeded 1,000 monthly calls

**In get-message-group response**:
```json
{
  "message_group": {
    "status": {
      "status": "FAILED",
      "code": 429,
      "message": "Usage limit exceeded"
    }
  }
}
```

**Solutions**:
- Wait until next month (resets on 1st)
- Contact Geotab Ace team to request quota increase
- Monitor usage with `get-customer` function
- Implement request caching to reduce calls

#### Internal Server Error
**Cause**: Backend processing failure

**In get-message-group response**:
```json
{
  "message_group": {
    "status": {
      "status": "FAILED",
      "code": 500,
      "message": "Internal Server Error"
    }
  }
}
```

**Solutions**:
- Contact Geotab support with:
  - `chat_id`
  - `message_group_id`
  - Timestamp of request
  - Original prompt
- Retry with simplified prompt
- Check if issue is prompt-specific


## Rate Limits & Monitoring

### Current Limits

**Database-Wide Limit**: 1,000 calls per database per month
- Limit applies to entire database, not per user
- Resets on the 1st of each month
- Exceeding limit blocks ALL users on that database

**MyGeotab Rate Limits**: Also apply (separate from Ace limits)

### Monitoring Usage

#### Check Current Usage

```python
def get_usage_stats(session_id, database, username):
    """Get current usage statistics"""
    result = call_ace_api(
        session_id,
        database,
        username,
        "dna-planet-orchestration",
        "get-customer",
        {}
    )
    
    customer_data = result['apiResult']['results'][0]['customer']
    
    return {
        'database': customer_data['database'],
        'total_calls': customer_data['total_calls'],
        'monthly_limit': customer_data['monthly_limit'],
        'remaining_calls': customer_data['remaining_calls'],
        'utilization_percent': (
            customer_data['total_calls'] / 
            customer_data['monthly_limit'] * 100
        )
    }

# Usage
stats = get_usage_stats(session_id, database, username)
print(f"Used: {stats['total_calls']}/{stats['monthly_limit']}")
print(f"Remaining: {stats['remaining_calls']}")
print(f"Utilization: {stats['utilization_percent']:.1f}%")
```



### Prompt Formula

```
WHO + METRIC + TIME + STATISTIC + [GROUP BY]

"Show all speeding exceptions from yesterday with all details"
 └──┬──┘ └────┬─────┘ └────┬──────┘ └─────┬─────┘ └─────┬──────┘
   WHO      METRIC      TIME      STATISTIC        GROUP BY
```

### Common Pitfalls

1. ❌ Using `password` instead of `sessionId` in credentials
2. ❌ Forgetting "zone" suffix on location names
3. ❌ Omitting "exception" when querying custom rules
4. ❌ Not checking `reasoning` field for assumptions
5. ❌ Ignoring rate limits (1,000/month per database)
6. ❌ Not handling 24-hour URL expiration
7. ❌ Using standard accounts instead of Service Accounts
8. ❌ Polling indefinitely without timeout
9. ❌ Vague time expressions ("recently" vs "Sept 1-7, 2024")
10. ❌ Not requesting "all details" for complete data

---

## Changelog & Version Notes

**Document Version**: 1.0  
**Last Updated**: September 2024  
**API Version**: Current (as of January 2025 knowledge cutoff)

**Key Notes**:
- MyGeotab API calls with standard user accounts being deprecated
- Service Accounts now required for API access
- Rate limit: 1,000 calls per database per month
- Signed URLs expire after 24 hours
- Always use `serviceName: "dna-planet-orchestration"`

