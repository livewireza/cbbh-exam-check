# HTB Academy Certificate Exams Results Monitoring
# Original author was RBPi and modified by LiveWire

import requests
import time
import random
import os
import urllib.parse
import urllib.request

# Config from environment (GitHub Actions secrets)
HTB_EMAIL = os.getenv("HTB_EMAIL", "")
HTB_PASSWORD = os.getenv("HTB_PASSWORD", "")
HTB_COOKIE = os.getenv("HTB_COOKIE", "")  # optional fallback for Academy if needed
MAILGUN_API_KEY = os.getenv("MAILGUN_API_KEY", "")
MAILGUN_DOMAIN = os.getenv("MAILGUN_DOMAIN", "")
MAILGUN_TO = os.getenv("MAILGUN_TO", "")
MAILGUN_FROM = os.getenv("MAILGUN_FROM", "")
HTB_EXAM = os.getenv("HTB_EXAM", "CBBH").upper()
BROWSER_UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:143.0) Gecko/20100101 Firefox/143.0' # Replace with your browser User-Agent value

def send_get_request():
    if HTB_EXAM == 'CBBH':
        exam_id = 2
    elif HTB_EXAM == 'CDSA':
        exam_id = 4
    else:
        print("Invalid exam type. Please redefine the exam as 'CBBH' or 'CDSA'.")
        return

    url = f'https://academy.hackthebox.com/api/v2/exams/{exam_id}/attempts'
    headers = {
        'User-Agent': BROWSER_UA,
        'Cookie': HTB_COOKIE_VALUE,
        'Referer': f'https://academy.hackthebox.com/exams/{exam_id}/'
    }

    attempts = 1

    while attempts != 3:
        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            data = response.json()
            status = data['data'][0]['status']

            if status == 'In Review':
                wait_time = 60 # wait time 
                print(f"Status is 'In Review'. Waiting {wait_time} seconds before sending the request again...")
                #review_data = data['data'][0]['review']
                #feedback = review_data['feedback']
                #print(ret)
                subject = f"HTB {HTB_EXAM} result: {status}"
                body = f"Exam: {HTB_EXAM}\nStatus: {status}\n\n"
                mailgun_send(subject, body)
                #send_simple_message()
                print("Completed check and notification.")
                
                break
            elif status in ['In Review','Failed', 'Certified']:
                if 'review' in data['data'][0]:
                    review_data = data['data'][0]['review']
                    feedback = review_data['feedback']
                #ret = sc_send(status, f'{feedback}\n\n第二行', key)
                print(ret)
                
                subject = f"HTB {HTB_EXAM} result: {status}"
                body = f"Exam: {HTB_EXAM}\nStatus: {status}\n\nFeedback:\n{feedback}\n\n"
                mailgun_send(subject, body)
                print("Completed check and notification.")
                break
            else:
                print("Invalid status received.")
                break

        except requests.exceptions.RequestException as e:
            print(f"An error occurred: {e}")
            print("Response content:", response.content)
            attempts += 1
            print(f"Retrying in 60 seconds... (Attempt {attempts})")
            time.sleep(60)  # Wait for 60 seconds

    if attempts == 3:
        print("Request error exceeded 3 attempts. Exiting the script.")

#data = {}
#with open(os.path.join(os.path.dirname(__file__), '..', '.env'), 'r') as f:
#    for line in f:
#        key, value = line.strip().split('=')
#        data[key] = value
#key = data['SENDKEY']

def send_simple_message():
  	return requests.post(
  		"https://api.mailgun.net/v3/sandboxc9e3cef52f2d48afb6e5115816ca8ea0.mailgun.org/messages",
  		auth=("api", MAILGUN_API_KEY),
  		data={"from": "Mailgun Sandbox <postmaster@sandboxc9e3cef52f2d48afb6e5115816ca8ea0.mailgun.org>",
			"to": "",
  			"subject": "Hello",
  			"text": "Congratulations, you just sent an email with Mailgun! You are truly awesome!"})

def mailgun_send(subject: str, text: str):
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

def sc_send(text, desp='', key='[SENDKEY]'):
    postdata = urllib.parse.urlencode({'text': text, 'desp': desp}).encode('utf-8')
    url = f'https://sctapi.ftqq.com/{key}.send'
    req = urllib.request.Request(url, data=postdata, method='POST')
    with urllib.request.urlopen(req) as response:
        result = response.read().decode('utf-8')
    return result


send_get_request()
