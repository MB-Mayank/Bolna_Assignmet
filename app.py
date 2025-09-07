from flask import Flask, request, jsonify
import threading
import time
from datetime import datetime, timedelta
import requests
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

# =========================
# Config
# =========================
CREDENTIALS_FILE = "eminent-crane-434217-a2-8bc0bb699e19.json"
SHEET_URL = "https://docs.google.com/spreadsheets/d/1YSAGwAp5OYlYde_l2DTrmd1gM3M7wy5ARCIi2ZglYaA/edit?usp=sharing"
API_TOKEN = "bn-f96272d7c22a44959ff9ed5562a6cacc"
AGENT_ID = "5c73ee44-4ed0-464a-ab44-dd6949cd51bd"


integration = None
active_calls = {}  # Track active calls to prevent duplicates
call_lock = threading.Lock()  # Thread safety for active_calls

# =========================
# Google Sheets integration
# =========================
class BolnaGoogleSheetsIntegration:
    def __init__(self, credentials_file, sheet_url, api_token):
        self.api_token = api_token
        self.base_url = "https://api.bolna.ai"

        # Google Sheets setup
        scope = ['https://spreadsheets.google.com/feeds',
                 'https://www.googleapis.com/auth/drive']
        creds = ServiceAccountCredentials.from_json_keyfile_name(credentials_file, scope)
        self.gc = gspread.authorize(creds)
        self.sheet = self.gc.open_by_url(sheet_url).sheet1
        logger.info("Google Sheets integration initialized successfully")

    def normalize_phone_number(self, phone):
        """Normalize phone number for consistent comparison"""
        if not phone:
            return ""
        
        phone = str(phone).strip()
        phone = ''.join(c for c in phone if c.isdigit() or c == '+')
        
        if phone and not phone.startswith('+'):
            phone = "+" + phone
            
        return phone

    def make_call(self, agent_id, recipient_phone, user_data=None):
        """Make a call and track it"""
        with call_lock:
            # Prevent duplicate calls
            if recipient_phone in active_calls:
                logger.warning(f"Call already active for {recipient_phone}, skipping")
                return None
        
        url = f"{self.base_url}/call"
        payload = {
            "agent_id": agent_id,
            "recipient_phone_number": recipient_phone,
            "user_data": user_data or {}
        }
        headers = {"Authorization": f"Bearer {self.api_token}", "Content-Type": "application/json"}
        
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=15)
            response.raise_for_status()
            result = response.json()
            
            execution_id = result.get('execution_id')
            if execution_id:
                # Track active call
                with call_lock:
                    active_calls[recipient_phone] = {
                        'execution_id': execution_id,
                        'started_at': datetime.now(),
                        'status': 'initiated'
                    }
                logger.info(f"Call initiated to {recipient_phone} - execution_id: {execution_id}")
            
            return result
        except Exception as e:
            logger.error(f"Error making call to {recipient_phone}: {e}")
            return None

    def update_sheet_row(self, row_index, execution_id=None, status=None, duration=None, notes=None, transcript=None, summary=None):
        """Update Google Sheet row with real-time data"""
        try:
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            updates = []
            
            if status:
                updates.append({
                    'range': f'C{row_index}',  # Status column
                    'values': [[status]]
                })
            
            if execution_id:
                updates.append({
                    'range': f'D{row_index}',  # Latest Execution ID column
                    'values': [[execution_id]]
                })
            
            if duration is not None:
                updates.append({
                    'range': f'E{row_index}',  # Duration column
                    'values': [[f"{duration} sec"]]
                })
            
            # Always update last attempt time
            updates.append({
                'range': f'F{row_index}',  # Last Attempt Time column
                'values': [[current_time]]
            })
            
            if notes:
                updates.append({
                    'range': f'G{row_index}',  # Notes column
                    'values': [[notes]]
                })
            
            if transcript:
                updates.append({
                    'range': f'H{row_index}',  # Transcript column
                    'values': [[transcript]]
                })
            
            if summary:
                updates.append({
                    'range': f'I{row_index}',  # Summary column
                    'values': [[summary]]
                })
            
            
            if updates:
                self.sheet.batch_update(updates)
                logger.info(f"Sheet updated - Row {row_index}: Status={status}, Duration={duration}")
                
        except Exception as e:
            logger.error(f"Error updating sheet row {row_index}: {e}")

    def find_row_by_phone_number(self, phone_number):
        """Find row index by phone number"""
        try:
            normalized_phone = self.normalize_phone_number(phone_number)
            if not normalized_phone:
                return None
                
            records = self.sheet.get_all_records()
            for index, record in enumerate(records, start=2):
                sheet_phone = self.normalize_phone_number(record.get("Phone Number", ""))
                if sheet_phone == normalized_phone:
                    return index
            
            return None
        except Exception as e:
            logger.error(f"Error finding row by phone_number {phone_number}: {e}")
            return None

    def should_retry_call(self, record):
        """Determine if a call should be retried based on status and timing"""
        status = str(record.get("Status", "")).strip().lower()
        execution_id = str(record.get("Latest Execution ID", "")).strip()
        last_attempt = record.get("Last Attempt Time", "")
        
        # NEVER retry completed calls - this was the main issue
        if status in ["completed"]:
            logger.debug(f"Skipping completed call for record: {record.get('Phone Number', 'unknown')}")
            return False
            
        # Don't retry successful calls
        if status in ["answered", "call-disconnected"]:
            logger.debug(f"Skipping answered/disconnected call for record: {record.get('Phone Number', 'unknown')}")
            return False
            
        # If no execution_id, it's a new call (but check if status suggests it should be called)
        if not execution_id or execution_id == "":
            return status in ["", "pending", "new"] or not status
            
        # For failed calls, wait at least 10 minutes before retry (increased from 5)
        if status in ["failed", "busy", "no-answer", "no_answer"] and last_attempt:
            try:
                last_time = datetime.strptime(last_attempt, "%Y-%m-%d %H:%M:%S")
                minutes_since_last = (datetime.now() - last_time).total_seconds() / 60
                should_retry = minutes_since_last >= 10  # Increased retry interval
                if should_retry:
                    logger.info(f"Retrying failed call for {record.get('Phone Number', 'unknown')} after {minutes_since_last:.1f} minutes")
                return should_retry
            except Exception as e:
                logger.error(f"Error parsing last attempt time: {e}")
                return False  # Don't retry if we can't parse the time
                
        # For initiated/queued/in-progress calls, don't retry if recent (within 5 minutes)
        if status in ["initiated", "queued", "in_progress", "in-progress", "ringing"] and last_attempt:
            try:
                last_time = datetime.strptime(last_attempt, "%Y-%m-%d %H:%M:%S")
                minutes_since_last = (datetime.now() - last_time).total_seconds() / 60
                if minutes_since_last < 5:  # Don't retry recent active calls
                    return False
                # If it's been more than 5 minutes and still showing as active, something might be wrong
                logger.warning(f"Call showing as {status} for {minutes_since_last:.1f} minutes, allowing retry")
                return True
            except:
                return False
                
        # Only retry empty/pending statuses
        return status in ["", "pending", "new"]

    def get_current_sheet_data(self):
        """Get fresh data from sheet to avoid stale data issues"""
        try:
            return self.sheet.get_all_records()
        except Exception as e:
            logger.error(f"Error getting sheet data: {e}")
            return []

    def process_pending_calls(self, agent_id):
        """Process calls that need to be initiated or retried"""
        try:
            # Get fresh data from sheet
            records = self.get_current_sheet_data()
            if not records:
                logger.warning("No records found in sheet")
                return
                
            processed_count = 0
            
            for index, record in enumerate(records, start=2):
                phone = self.normalize_phone_number(record.get("Phone Number", ""))
                
                if not phone:
                    continue
                    
                # Skip if call is currently active
                with call_lock:
                    if phone in active_calls:
                        logger.debug(f"Skipping active call for {phone}")
                        continue
                    
                if self.should_retry_call(record):
                    logger.info(f"Processing call for {phone} with status: {record.get('Status', 'empty')}")
                    
                    user_data = {
                        "customer_name": record.get("Name", ""),
                        "phone_number": phone
                    }
                    
                    # Update status to 'initiating'
                    self.update_sheet_row(index, status="initiating")
                    
                    call_result = self.make_call(agent_id, phone, user_data)
                    if call_result and call_result.get("execution_id"):
                        execution_id = call_result["execution_id"]
                        self.update_sheet_row(index, execution_id=execution_id, status="initiated")
                        processed_count += 1
                        time.sleep(5)  # Increased rate limiting between calls
                    else:
                        self.update_sheet_row(index, status="failed", notes="Failed to initiate call")
                        
                    # Process only one call per cycle to avoid overwhelming
                    # break
            
            if processed_count > 0:
                logger.info(f"Processed {processed_count} call(s)")
            else:
                logger.debug("No calls needed processing")
                
        except Exception as e:
            logger.error(f"Error processing pending calls: {e}")


# =========================
# Webhook endpoint for real-time updates
# =========================
@app.route("/webhook/bolna", methods=["POST"])
def bolna_webhook():
    try:
        data = request.json
        logger.info(f"Webhook received: {data.get('id')} - Status: {data.get('status')}")
        print(f"Received webhook: {data}")

        # Extract phone number
        phone_number = None
        if "context_details" in data and "recipient_phone_number" in data["context_details"]:
            phone_number = data["context_details"]["recipient_phone_number"]
        elif "telephony_data" in data and "to_number" in data["telephony_data"]:
            phone_number = data["telephony_data"]["to_number"]
        
        if not phone_number:
            logger.warning("No phone number found in webhook data")
            return jsonify({"status": "error", "message": "Missing phone number"}), 400

        execution_id = data.get("id") or data.get("execution_id")
        status = data.get("status", "").lower()
        
        # Comprehensive final statuses - calls that should NOT be retried
        final_statuses = ["completed", "failed", "busy", "no-answer", "answered", "call-disconnected"]
        
        # Map specific statuses
        if status in ["answered", "call-disconnected"]:
            mapped_status = "completed"
        elif status == "no_answer":
            mapped_status = "no-answer"
        else:
            mapped_status = status
        
        # Extract duration and notes
        duration = 0.0
        if "telephony_data" in data:
            try:
                duration = float(data["telephony_data"].get("duration", "0.0"))
            except (ValueError, TypeError):
                duration = 0.0
        
        notes = ""
        if data.get("error_message"):
            notes = data["error_message"]
        elif "telephony_data" in data and data["telephony_data"].get("hangup_reason"):
            notes = data["telephony_data"]["hangup_reason"]
        
        # Add smart status if available
        if data.get("smart_status"):
            notes = f"{notes} | Smart Status: {data['smart_status']}" if notes else f"Smart Status: {data['smart_status']}"

        # Extract transcript and summary
        transcript = data.get("transcript", "")
        summary = data.get("summary", "")

        if not integration:
            return jsonify({"status": "ignored", "message": "Integration not initialized"}), 202

        # Update active calls tracking
        with call_lock:
            if phone_number in active_calls:
                active_calls[phone_number]['status'] = mapped_status
                
                # Remove from active calls if it's a final status
                if mapped_status in final_statuses:
                    del active_calls[phone_number]
                    logger.info(f"Call completed for {phone_number} - Status: {mapped_status}, removed from active calls")

        # Process webhook in background
        threading.Thread(
            target=update_sheet_from_webhook,
            args=(phone_number, execution_id, mapped_status, duration, notes, transcript, summary),
            daemon=True
        ).start()
        
        return jsonify({"status": "received"}), 200
        
    except Exception as e:
        logger.error(f"Webhook processing error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


def update_sheet_from_webhook(phone_number, execution_id, status, duration, notes, transcript, summary):
    """Update sheet from webhook data"""
    try:
        row_index = integration.find_row_by_phone_number(phone_number)
        
        if row_index:
            integration.update_sheet_row(
                row_index=row_index,
                execution_id=execution_id,
                status=status,
                duration=duration,
                notes=notes,
                transcript=transcript,
                summary=summary
            )
        else:
            logger.warning(f"No row found for phone number: {phone_number}")
            
    except Exception as e:
        logger.error(f"Error updating sheet from webhook: {e}")

# =========================
# Background worker
# =========================
def background_worker():
    """Background worker to process pending calls"""
    logger.info("Background worker started")
    
    while True:
        try:
            if integration:
                # Clean up old active calls (over 15 minutes old)
                current_time = datetime.now()
                phones_to_remove = []
                
                with call_lock:
                    for phone, call_data in active_calls.items():
                        if (current_time - call_data['started_at']).total_seconds() > 900:  # 15 minutes
                            phones_to_remove.append(phone)
                    
                    for phone in phones_to_remove:
                        logger.warning(f"Removing stale active call for {phone}")
                        del active_calls[phone]
                
                # Process pending calls (less frequently to avoid spam)
                integration.process_pending_calls(AGENT_ID)
                
            time.sleep(120)  # Check every 2 minutes instead of 1 minute
        except Exception as e:
            logger.error(f"Background worker error: {e}")
            time.sleep(120)


# =========================
# Main
# =========================
if __name__ == "__main__":
    print("🚀 Initializing Fixed Bolna-Google Sheets Integration...")
    try:
        integration = BolnaGoogleSheetsIntegration(CREDENTIALS_FILE, SHEET_URL, API_TOKEN)
        print("✅ Integration ready!")
    
        # Start background worker
        threading.Thread(target=background_worker, daemon=True).start()
        
        # Start Flask app
        app.run(debug=True, host="0.0.0.0", port=5000, threaded=True)
        
    except Exception as e:
        logger.error(f"Failed to initialize: {e}")
        print("❌ Failed to start server. Check your credentials and configuration.")