#karmafy/karmafy/api_send_email_notification.py

from fastapi import FastAPI, HTTPException
from typing import Optional
import requests
import os
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

# DAILY_JOB_EMAIL_URL = "https://applywizz.onrender.com/api/send-daily-job-email/"

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
    except Exception as e:
        print(f"❌ Critical error occurred: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
