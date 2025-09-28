#!/usr/bin/env python3
"""
check_htb_exam.py

Permissions: read HTB_EMAIL, HTB_PASSWORD, HTB_COOKIE (optional), MAILGUN_* from env (GitHub secrets)
"""

import os
import time
import random
import base64
import json
import requests
from typing import Optional

# Config from environment (GitHub Actions secrets)
HTB_EMAIL = os.getenv("HTB_EMAIL", "")
HTB_PASSWORD = os.getenv("HTB_PASSWORD", "")
HTB_COOKIE = os.getenv("HTB_COOKIE", "")  # optional fallback for Academy if needed
MAILGUN_API_KEY = os.getenv("MAILGUN_API_KEY", "")
MAILGUN_DOMAIN = os.getenv("MAILGUN_DOMAIN", "")
MAILGUN_TO = os.getenv("MAILGUN_TO", "")
MAILGUN_FROM = os.getenv("MAILGUN_FROM", "HTB Notifier <mailgun@YOUR_DOMAIN>")
HTB_EXAM = os.getenv("HTB_EXAM", "CBBH").upper()

# Behavior tuning
MAX_POLL_ATTEMPTS = 40        # maximum number of "In Review" polls before giving up
MIN_NETWORK_RETRY_DELAY = 60  # seconds between network retries
MAX_NETWORK_RETRIES = 3       # network error retries
REQUEST_TIMEOUT = 15          # seconds

def print_env_warnings():
    missing = []
    if not HTB_EMAIL or not HTB_PASSWORD:
        missing.append("HTB_EMAIL/HTB_PASSWORD")
    if not MAILGUN_API_KEY or not MAILGUN_DOMAIN or not MAILGUN_TO:
        missing.append("MAILGUN_ (API_KEY / DOMAIN / TO)")
    if missing:
        print("WARNING: missing secrets:", ", ".join(missing))
        # Do not exit here; script will likely fail later with clearer error.

def decode_jwt_payload(token: str) -> dict:
    """
    Return the JWT payload as dict without verifying signature.
    Safe for reading exp claim.
    """
    try:
        parts = token.split('.')
        if len(parts) < 2:
            return {}
        payload_b64 = parts[1]
        # Add padding if necessary
        padding = '=' * (-len(payload_b64) % 4)
        payload_b64 += padding
        payload_bytes = base64.urlsafe_b64decode(payload_b64.encode('utf-8'))
        return json.loads(payload_bytes)
    except Exception as e:
        print("Failed to decode token payload:", e)
        return {}

def get_v4_access_token(email: str, password: str) -> Optional[str]:
    """
    Replicates JS: POST https://www.hackthebox.eu/api/v4/login
    Expects response.body.message.access_token (based on community docs / examples).
    """
    url = "https://www.hackthebox.eu/api/v4/login"
    headers = {"Content-Type": "application/json;charset=utf-8", "User-Agent": "python-requests/HTB-checker"}
    payload = {"email": email, "password": password, "remember": True}
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        j = resp.json()
        # community doc / JS indicates access token lives under message.access_token
        token = None
        if isinstance(j, dict):
            token = j.get("message", {}).get("access_token") or j.get("access_token")
        if token:
            payload = decode_jwt_payload(token)
            exp = payload.get("exp")
            if exp:
                exp_time = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(exp))
                print(f"Acquired API v4 token (exp {exp_time})")
            else:
                print("Acquired API v4 token (no exp in token payload)")
            return token
        else:
            print("Login response did not contain access_token. Response JSON keys:", list(j.keys()) if isinstance(j, dict) else j)
            return None
    except requests.RequestException as e:
        print("Failed to get v4 token:", e)
        try:
            print("Response content:", resp.text)
        except Exception:
            pass
        return None

def mailgun_send(subject: str, text: str) -> Optional[requests.Response]:
    """Send mail via Mailgun HTTP API v3."""
    if not MAILGUN_API_KEY or not MAILGUN_DOMAIN:
        print("Mailgun not configured (MAILGUN_API_KEY or MAILGUN_DOMAIN missing). Skipping email.")
        return None
    mg_url = f"https://api.mailgun.net/v3/{MAILGUN_DOMAIN}/messages"
    auth = ("api", MAILGUN_API_KEY)
    data = {
        "from": MAILGUN_FROM,
        "to": MAILGUN_TO,
        "subject": subject,
        "text": text
    }
    try:
        r = requests.post(mg_url, auth=auth, data=data, timeout=10)
        r.raise_for_status()
        print("Mailgun: sent message, status:", r.status_code)
        return r
    except requests.RequestException as e:
        print("Mailgun send failed:", e)
        try:
            print("Mailgun response:", r.text)
        except Exception:
            pass
        return None

def exam_attempts_request_headers(access_token: Optional[str] = None):
    """
    Returns headers to use for academy API call. Prefer Bearer token, fallback to Cookie if provided.
    """
    headers = {"User-Agent": "python-requests/HTB-checker"}
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"
    if HTB_COOKIE:
        headers["Cookie"] = HTB_COOKIE
    # Academy API usually expects JSON responses
    return headers

def check_exam_status(access_token: Optional[str] = None) -> Optional[dict]:
    """
    Calls academy attempts endpoint for the chosen exam and returns the attempt object (first entry) or None.
    """
    if HTB_EXAM == 'CBBH':
        exam_id = 2
    elif HTB_EXAM == 'CDSA':
        exam_id = 4
    else:
        print("Invalid HTB_EXAM - defaulting to CBBH")
        exam_id = 2

    url = f"https://academy.hackthebox.com/api/v2/exams/{exam_id}/attempts"
    headers = exam_attempts_request_headers(access_token)

    network_retries = 0
    while network_retries < MAX_NETWORK_RETRIES:
        try:
            resp = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
            # If unauthorized and we included a Bearer token, we might try fallback to cookie (handled by caller)
            resp.raise_for_status()
            data = resp.json()
            attempts_list = data.get("data") or []
            if not attempts_list:
                print("No attempts in response (empty list). Returning None.")
                return None
            return attempts_list[0]
        except requests.HTTPError as e:
            code = getattr(e.response, "status_code", None)
            print(f"HTTP error checking exam attempts: {e} (status {code})")
            # If 401 and we used token, caller might want to retry with cookie fallback
            return {"http_error": True, "status_code": code, "text": getattr(e.response, "text", "")}
        except requests.RequestException as e:
            network_retries += 1
            print(f"Network error ({network_retries}/{MAX_NETWORK_RETRIES}): {e}")
            time.sleep(MIN_NETWORK_RETRY_DELAY)
    print("Exceeded network retries when calling exam attempts.")
    return None

def main():
    print_env_warnings()

    token = None
    if HTB_EMAIL and HTB_PASSWORD:
        token = get_v4_access_token(HTB_EMAIL, HTB_PASSWORD)
    else:
        print("HTB_EMAIL/HTB_PASSWORD not provided; skipping token fetch.")

    # Try to get attempt using bearer token first (if we have it)
    attempt_obj = check_exam_status(token) if token else None

    # If token returned an HTTP error (401) and we have a COOKIE secret, try cookie fallback
    if attempt_obj and isinstance(attempt_obj, dict) and attempt_obj.get("http_error") and HTB_COOKIE:
        print("Bearer token did not authorize Academy API; trying using provided cookie as fallback.")
        attempt_obj = check_exam_status(None)  # will include HTB_COOKIE in headers if set

    # If still None, we will poll (for "In Review") using whichever auth succeeded
    if attempt_obj is None or attempt_obj.get("http_error"):
        # We'll attempt polling by calling repeatedly (either using token or cookie)
        headers_token = token if token else None
        poll_count = 0
        while poll_count < MAX_POLL_ATTEMPTS:
            print(f"Polling attempt #{poll_count+1}...")
            attempt = check_exam_status(headers_token)
            if attempt is None:
                print("No attempt data yet. Sleeping before next poll.")
                poll_count += 1
                time.sleep(random.randint(60, 180))
                continue
            if isinstance(attempt, dict) and attempt.get("http_error"):
                print("HTTP error while polling, aborting.")
                break
            status = attempt.get("status", "")
            print("Polled status:", status)
            if status == "In Review":
                poll_count += 1
                wait_time = random.randint(300, 600)
                print(f"In Review -> sleep {wait_time}s and poll again")
                time.sleep(wait_time)
                continue
            else:
                attempt_obj = attempt
                break

        if poll_count >= MAX_POLL_ATTEMPTS:
            subject = f"HTB {HTB_EXAM} check: polling timeout"
            body = f"Polling for exam {HTB_EXAM} reached max polls ({MAX_POLL_ATTEMPTS}) with no final status."
            mailgun_send(subject, body)
            return

    # At this point attempt_obj should be a dict with final info
    if not attempt_obj or attempt_obj.get("http_error"):
        subject = f"HTB {HTB_EXAM} check: error"
        body = f"Could not retrieve attempt results. Response: {attempt_obj}"
        mailgun_send(subject, body)
        return

    status = attempt_obj.get("status", "unknown")
    review = attempt_obj.get("review", {}) or {}
    feedback = review.get("feedback", "").strip() or "(no reviewer feedback provided)"
    subject = f"HTB {HTB_EXAM} result: {status}"
    body = f"Exam: {HTB_EXAM}\nStatus: {status}\n\nFeedback:\n{feedback}\n\nRaw attempt data:\n{json.dumps(attempt_obj, indent=2)}"
    mailgun_send(subject, body)
    print("Completed check and notification.")

if __name__ == "__main__":
    main()
