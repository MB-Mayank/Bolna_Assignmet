
# 📞 Bolna-Google Sheets Integration

A robust **Flask-based integration** that automates voice calls using **Bolna AI** and tracks call data in **real-time** through Google Sheets.  
This system provides **intelligent call management** with retry logic, real-time updates, and comprehensive call tracking.

---

## 📋 Prerequisites

- A Flask server set up to receive webhook events  
- An account with [Ngrok](https://ngrok.com)

---

## ⚡ Steps

### 1. Install Ngrok
Download and install Ngrok from [here](https://ngrok.com/download).

### 2. Start Your Flask Server
Run your Flask integration locally:


python app.py


By default, Flask runs on:
`http://127.0.0.1:5000`

### 3. Expose Flask with Ngrok

In a new terminal, start an Ngrok tunnel:

```bash
ngrok http 5000
```

Ngrok will provide a public URL, such as:

```
Forwarding https://a1b2c3d4.ngrok.io -> http://localhost:5000
```

### 4. Configure Webhook in Bolna Dashboard

* Go to the **Bolna Dashboard**
* Navigate to **Your Agent → Webhooks**
* Add the Ngrok URL with your webhook endpoint, for example:

```
https://a1b2c3d4.ngrok.io/webhook/bolna
```

### 5. Test the Webhook

* Trigger a call using the Bolna sheet or API
* Bolna will send webhook updates to your Flask server via Ngrok
* Check your Flask console to confirm that webhook events are being logged

⚠️ **Important:** Ngrok URLs change each time you restart the tunnel unless you use a paid plan with reserved domains.
👉 Update the webhook URL in the Bolna Dashboard whenever the Ngrok URL changes.

---

## 🚀 Features

### Core Functionality

* **Automated Voice Calls**: Initiates calls through Bolna AI API to phone numbers listed in Google Sheets
* **Real-time Tracking**: Updates call status, duration, and results instantly via webhooks
* **Smart Retry Logic**: Intelligently retries failed calls while avoiding duplicates
* **Background Processing**: Continuous monitoring and processing of pending calls
* **Thread-Safe Operations**: Prevents duplicate calls and ensures data consistency

### Call Management

* **Status Tracking**: Monitors call progression from initiation to completion
* **Duplicate Prevention**: Active call tracking prevents multiple calls to the same number
* **Comprehensive Logging**: Detailed logs for debugging and monitoring
* **Error Handling**: Robust error handling with automatic recovery

### Data Integration

* **Google Sheets Integration**: Direct read/write access to spreadsheet data
* **Real-time Updates**: Instant status updates via webhook callbacks
* **Transcript Storage**: Saves call transcripts and summaries to the sheet
* **Call Analytics**: Tracks call duration, outcomes, and detailed notes

---

## 🏗️ System Architecture

### Components

* **Flask Web Server** → Handles webhook callbacks and provides API endpoints
* **Background Worker** → Continuously processes pending calls and cleanup tasks
* **Google Sheets Client** → Manages spreadsheet operations and data synchronization
* **Bolna API Client** → Handles voice call initiation and management

### Data Flow

```
Google Sheets → Background Worker → Bolna API → Voice Call → Webhook → Google Sheets
```

---

## 📋 Prerequisites

### Required Services

* **Bolna AI Account** → For voice call capabilities
* **Google Cloud Project** → For Sheets API access
* **Google Sheets** → Pre-configured spreadsheet with proper columns

### Python Dependencies

```
flask
gspread
oauth2client
requests
threading
logging
```

---

## ⚙️ Configuration

### Environment Variables

```python
CREDENTIALS_FILE = "eminent-crane-434217-a2-8bc0bb699e19.json"  # Google Service Account
SHEET_URL       = "https://docs.google.com/spreadsheets/d/..."  # Target Google Sheet
API_TOKEN       = "bn-f9c"                                      # Bolna API Token
AGENT_ID        = "5c73"                                        # Bolna Agent ID
```

### Google Sheets Structure

Required columns:

| Column | Field               | Description                    |
| ------ | ------------------- | ------------------------------ |
| A      | Name                | Customer name                  |
| B      | Phone Number        | Format: +1234567890            |
| C      | Status              | Call status                    |
| D      | Latest Execution ID | Bolna execution ID             |
| E      | Duration            | Call duration in seconds       |
| F      | Last Attempt Time   | Timestamp                      |
| G      | Notes               | Error messages, hangup reasons |
| H      | Transcript          | Call transcript                |
| I      | Summary             | Call summary                   |

---

## 🔄 How It Works

### 1. Call Initiation Process

* Background worker scans Google Sheets every **2 minutes**
* Identifies pending calls based on status and timing rules
* Normalizes phone numbers for consistency
* Initiates calls through Bolna API with customer data
* Updates sheet with **"initiating" → "initiated"** status

### 2. Smart Retry Logic

**Retry Conditions:**

* New/Empty Status → Immediate processing
* Failed Calls → Retry after **10+ minutes**
* No Answer/Busy → Retry after **10+ minutes**
* Active Calls → No retry if recent (<5 minutes)
* Completed Calls → ❌ Never retry

### 3. Real-time Updates via Webhooks

* Bolna sends webhook notifications for call events
* System processes status changes, duration, transcripts
* Google Sheets updated immediately with new data
* Active call tracking prevents duplicates

### 4. Status Management

**Call Statuses:**

```
pending/new       → Ready for calling
initiating        → Call being set up
initiated         → Call in progress
ringing           → Phone ringing
answered          → Call connected
completed         → Call finished successfully
failed/busy/no-answer → Retry eligible
call-disconnected → Call ended
```

### 5. Background Maintenance

* Cleans up stale active calls (>15 minutes)
* Processes **one call per cycle** to avoid overwhelming
* Rate limiting between calls (**5-second intervals**)
* Comprehensive error logging and recovery

---

## 📊 Webhook Data Processing

### Incoming Webhook Format

```json
{
  "id": "execution_id",
  "status": "completed",
  "context_details": {
    "recipient_phone_number": "+1234567890"
  },
  "telephony_data": {
    "duration": "45.2",
    "hangup_reason": "caller_hangup"
  },
  "transcript": "Call transcript...",
  "summary": "Call summary...",
  "smart_status": "successful_call"
}
```

---

```

Would you like me to also create a **GitHub badges section** (Python version, Flask, Google Sheets API, Ngrok) at the top for extra polish?
```
