#karmafy/karmafy/api_send_email_notification.py

from fastapi import FastAPI, HTTPException
from typing import Optional
import requests
import os
import time
from datetime import datetime
import psycopg2
from psycopg2.extras import RealDictCursor

# -----------------------
# Config - Load from environment variables
# -----------------------
# Load .env file from parent directory
from pathlib import Path
from dotenv import load_dotenv

env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)

# Database configuration - REQUIRED
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError(
        "Missing required DATABASE_URL environment variable. "
        "Please set it in your .env file."
    )

DAILY_JOB_EMAIL_URL = "https://dashboard.apply-wizz.com/api/send-daily-job-email/"
BULK_JOB_EMAIL_URL = "https://dashboard.apply-wizz.com/api/send-bulk-daily-job-emails/"

# FastAPI app
app = FastAPI()


# -----------------------
# Database Connection
# -----------------------
def get_db_connection():
    """Get PostgreSQL database connection"""
    try:
        conn = psycopg2.connect(DATABASE_URL)
        return conn
    except Exception as e:
        print(f"❌ Database connection error: {e}")
        raise HTTPException(status_code=500, detail="Database connection failed")


# -----------------------
# Query Active Job Board Leads
# -----------------------
def get_active_job_board_leads():
    """
    Query the karmafy_lead table to find all active leads who have opted for "job-links".
    
    Returns list of dicts with lead info.
    """
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            # Query for leads that are active and have 'job-links' in servicesOpted
            query = """
                SELECT 
                    id,
                    name,
                    email,
                    "apwId" AS apw_id
                FROM karmafy_lead
                WHERE LOWER(status) IN ('active', 'in progress', 'inprogress')
                AND "servicesOpted" @> '["job-links"]'::jsonb
            """
            cursor.execute(query)
            results = cursor.fetchall()
            
            return [dict(row) for row in results]
    
    except psycopg2.Error as e:
        print(f"❌ Database query error: {e}")
        raise HTTPException(status_code=500, detail="Database query failed")
    finally:
        conn.close()


# -----------------------
# Trigger Daily Emails API
# -----------------------
def trigger_daily_job_emails():
    """
    Fetches all active job board leads and triggers the daily job email API for each.
    """
    leads = get_active_job_board_leads()
    
    if not leads:
        print("ℹ️ No active job board leads found.")
        return {
            "success": True, 
            "message": "No active job board leads found.", 
            "total_leads": 0,
            "triggered_count": 0, 
            "failed_count": 0,
            "triggered_leads": [],
            "failed_leads": []
        }

    print(f"🚀 Found {len(leads)} active job board leads. Starting API triggers...")
    
    triggered_leads = []
    failed_leads = []

    for lead in leads:
        apw_id = lead.get('apw_id')
        if not apw_id:
            print(f"⚠️ Skipping lead {lead.get('name')} - missing apwId")
            continue

        try:
            # Hit the daily job email endpoint for this specific lead
            payload = {"apwId": apw_id}
            response = requests.post(DAILY_JOB_EMAIL_URL, json=payload, timeout=15)
            
            if response.ok:
                print(f"✅ Successfully triggered email for {lead['name']} ({apw_id})")
                triggered_leads.append({"name": lead['name'], "apw_id": apw_id})
            else:
                print(f"❌ Failed to trigger email for {lead['name']} ({apw_id}): {response.status_code} - {response.text}")
                failed_leads.append({"name": lead['name'], "apw_id": apw_id, "error": response.text})
            # --- ADD THIS LINE BELOW ---
            print(f"Waiting 6 seconds to respect Azure rate limits...")
            time.sleep(6)
        
        except Exception as e:
            print(f"❌ Error triggering API for {lead['name']} ({apw_id}): {e}")
            failed_leads.append({"name": lead['name'], "apw_id": apw_id, "error": str(e)})

    return {
        "success": True,
        "total_leads": len(leads),
        "triggered_count": len(triggered_leads),
        "failed_count": len(failed_leads),
        "triggered_leads": triggered_leads,
        "failed_leads": failed_leads
    }

# def trigger_daily_job_emails():
#     """
#     Fetches active leads and triggers the BULK API in batches of 2 with detailed logging.
#     """
#     # 1. Fetch data
#     leads = get_active_job_board_leads()
    
#     if not leads:
#         print("ℹ️ [SKIP] No active job board leads found in database.")
#         return {"success": True, "message": "No leads found."}

#     total_leads = len(leads)
#     print(f"🚀 [START] Found {total_leads} active leads. Splitting into batches of 2...")

#     # 2. Preparation
#     batch_size = 2
#     # Create batches of the full lead objects so we can log names/emails
#     batches = [leads[i:i + batch_size] for i in range(0, total_leads, batch_size)]
    
#     final_results = {"successful": [], "failed": []}

#     # 3. Processing Loop
#     for i, batch in enumerate(batches):
#         batch_num = i + 1
#         # Extract just the IDs for the API payload
#         batch_ids = [lead.get('apw_id') for lead in batch if lead.get('apw_id')]
        
#         print(f"\n--- 📦 Processing Batch {batch_num}/{len(batches)} ---")
#         for lead in batch:
#             print(f"👉 Target: {lead.get('name')} | Email: {lead.get('email')} | ID: {lead.get('apw_id')}")

#         try:
#             payload = {"apwIds": batch_ids}
#             response = requests.post(BULK_JOB_EMAIL_URL, json=payload, timeout=45)
            
#             if response.ok:
#                 res_data = response.json()
#                 batch_res = res_data.get("results", {})
                
#                 success_list = batch_res.get("successful", [])
#                 fail_list = batch_res.get("failed", [])

#                 # Detailed logging for this batch
#                 if success_list:
#                     print(f"✅ SUCCESS: Sent to {len(success_list)} leads: {', '.join(success_list)}")
#                     final_results["successful"].extend(success_list)
                
#                 if fail_list:
#                     for f in fail_list:
#                         print(f"⚠️  FAILED: Lead {f.get('apwId')} | Reason: {f.get('error')}")
#                     final_results["failed"].extend(fail_list)
#             else:
#                 print(f"❌ CRITICAL: Batch {batch_num} API Error {response.status_code}: {response.text}")
#                 for bid in batch_ids:
#                     final_results["failed"].append({"apwId": bid, "error": f"HTTP {response.status_code}"})
        
#         except Exception as e:
#             print(f"❌ CONNECTION ERROR: Batch {batch_num} failed to reach server: {e}")
#             for bid in batch_ids:
#                 final_results["failed"].append({"apwId": bid, "error": str(e)})

#         # Optional: Sleep for 1 second to prevent hitting Azure too fast
#         time.sleep(1)

#     # 4. Final Summary Console Log
#     print("\n" + "="*40)
#     print("🏁 FINAL EXECUTION SUMMARY")
#     print("="*40)
#     print(f"Total Leads Found:    {total_leads}")
#     print(f"Successfully Sent:    {len(final_results['successful'])}")
#     print(f"Failed/Skipped:       {len(final_results['failed'])}")
    
#     if final_results['failed']:
#         print("\n❌ FAILED LIST:")
#         for f in final_results['failed']:
#             print(f" - {f}")
#     print("="*40 + "\n")

#     return {
#         "success": True,
#         "total": total_leads,
#         "results": final_results
#     }

# -----------------------
# NEW ENDPOINT: Trigger daily job emails for all active job board clients
# -----------------------
@app.post("/trigger-daily-job-emails")
def trigger_all_emails():
    """
    Manual trigger to run the daily job email process for all active job board clients.
    """
    return trigger_daily_job_emails()


# Health check endpoint
@app.get("/")
def health_check():
    return {"status": "ok", "service": "Daily Job Board Email Trigger Service"}


# -----------------------
# Main execution when run as script (for cron jobs)
# -----------------------
if __name__ == "__main__":
    print("🚀 Starting Daily Job Board Email Trigger...")
    try:
        result = trigger_daily_job_emails()
        print(f"✅ Execution completed!")
        print(f"   Summary: Total={result['total_leads']}, Triggered={result['triggered_count']}, Failed={result['failed_count']}")
        # print(f"Summary: Total={result['total']}, Success={len(result['results']['successful'])}, Failed={len(result['results']['failed'])}")
    except Exception as e:
        print(f"❌ Critical error occurred: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
