from datetime import datetime
import threading
import time
import os
import json
import pytz
import logging
import requests
from flask import Flask, jsonify
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from urllib3.exceptions import InsecureRequestWarning
from typing import List, Tuple, Dict, Any
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from helpers_mysql import (
    init_db, load_sent_notice_hashes, add_sent_notice,
    send_telegram_message, get_webdriver, close_webdriver,
    clear_all_sent_notices, get_notice_hash
)

# === Flask App ===
app = Flask(__name__)
last_check_time = None
bot_start_time = datetime.now(pytz.utc)  # বট রান হওয়ার সময়টি এখানে সেভ হবে

@app.route('/')
def home():
    return "✅ Job Notice Bot is Running!"

@app.route('/last-check')
def show_last_check():
    global last_check_time, bot_start_time
    dhaka_tz = pytz.timezone('Asia/Dhaka')
    
    # বটের স্টার্ট টাইম (ঢাকা টাইম অনুযায়ী)
    start_time_local = bot_start_time.astimezone(dhaka_tz)
    start_str = start_time_local.strftime('%Y-%m-%d %H:%M:%S')
    
    response_html = f"🚀 <b>Bot Started At:</b> {start_str} (Asia/Dhaka)<br>"
    
    if last_check_time:
        local_time = last_check_time.astimezone(dhaka_tz)
        response_html += f"🕒 <b>Last Check At:</b> {local_time.strftime('%Y-%m-%d %H:%M:%S')} (Asia/Dhaka)"
    else:
        response_html += "❌ <b>Last Check:</b> No check performed yet."
        
    return response_html

@app.route('/clear-sent-notices')
def clear_sent_notices_api():
    clear_all_sent_notices()
    return jsonify({"status": "success", "message": "✅ All sent_notices data cleared."})

def run_flask():
    app.run(host='0.0.0.0', port=10000)

threading.Thread(target=run_flask).start()

# === Initial Setup ===
requests.packages.urllib3.disable_warnings(category=InsecureRequestWarning)
init_db()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

KEYWORDS = [
    "recruitment", "job", "নিয়োগ", "নিয়োগ", "নিয়োগের", "নিয়োগ বিজ্ঞপ্তি", "career", "advertisement",
    "নিয়োগ", "শূন্যপদ", "শূন্য পদ", "নিয়োগ বিজ্ঞপ্তি", "চাকরি", "চাকরির", "পদে", "পরীক্ষা", "পরীক্ষার",
    "ফলাফল", "job circular", "vacancy", "appointment", "প্রবেশ পত্র", "প্রবেশপত্র", 
    "এডমিট কার্ড", "নির্বাচিত", "পরীক্ষায়", "পরীক্ষার", "নিয়োগের", "opportunity"
]
# ✅ Updated Human-like Headers
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9,bn;q=0.8',
    'Referer': 'https://www.google.com/',
    'Connection': 'keep-alive'
}

def is_relevant(text: str) -> bool:
    try:
        text_lc = text.strip().lower()
        return any(keyword.lower() in text_lc for keyword in KEYWORDS)
    except Exception as e:
        logging.warning(f"Keyword match error: {e}")
        return False

def fetch_site_data(site: Dict[str, Any]) -> List[Tuple[str, str]]:
    notices = []
    site_name = site.get("name", "Unknown Site")
    site_url = site["url"]
    site_base_url = site.get("base_url", site_url)
    selenium_enabled = site.get("selenium_enabled", False)
    wait_time = site.get("wait_time", 15)
    driver = None

    logging.info(f"Fetching data from {site_name} ({site_url}) using {'Selenium' if selenium_enabled else 'Requests'}")

    try:
        if selenium_enabled:
            driver = get_webdriver()
            driver.get(site_url)
            WebDriverWait(driver, wait_time).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "table tbody tr"))
            )
            soup = BeautifulSoup(driver.page_source, "html.parser")
        else:
            response = requests.get(site_url, verify=False, timeout=20, headers=HEADERS)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")

        rows = soup.select("table tbody tr")
        if not rows:
            logging.warning(f"No rows found for {site_name}")
            return []

        for row in rows:
            cols = row.find_all("td")
            if len(cols) < 3:
                continue
            
            title = cols[1].get_text(strip=True)
            pdf_link = ""
            a_tag = cols[2].find("a", href=True)
            if a_tag:
                pdf_link = urljoin(site_base_url, a_tag["href"])

            if title and is_relevant(title):
                notices.append((title, pdf_link))

    except Exception as e:
        logging.error(f"Error processing {site_name}: {e}", exc_info=True)
    finally:
        if driver:
            close_webdriver(driver)

    return notices

def check_all_sites():
    global last_check_time
    last_check_time = datetime.now(pytz.utc)

    print(f"\n🕒 Checking all sites at {last_check_time.strftime('%Y-%m-%d %H:%M:%S')} UTC")

    config_path = "config.json"
    if not os.path.exists(config_path):
        logging.error(f"Config file not found: {config_path}")
        return

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
    except Exception as e:
        logging.error(f"Failed to load config.json: {e}")
        return

    for site in config:
        site_id = site.get("id")
        site_name = site.get("name", site_id)

        if not site_id:
            logging.warning(f"Skipping site due to missing 'id': {site_name}")
            continue

        notices = fetch_site_data(site)
        if not notices:
            logging.info(f"No relevant notices for {site_name}")
            continue

        sent_hashes = load_sent_notice_hashes(site_id)
        new_notices = []

        for text, link in notices:
            notice_hash = get_notice_hash(text, link)
            if notice_hash not in sent_hashes:
                new_notices.append((text, link, notice_hash))

        if not new_notices:
            logging.info(f"No new notices for {site_name}")
            continue

        new_notices.reverse()
        for text, link, notice_hash in new_notices:
            msg = f"📢 *{site_name}*\n\n📝 {text}"
            if link:
                msg += f"\n\n📥 [PDF Download]({link})"
            else:
                msg += f"\n\n❌ PDF পাওয়া যায়নি"

            send_telegram_message(msg)
            add_sent_notice(site_id, notice_hash)
            logging.info(f"Sent Telegram message for {site_name}: {text}")

# === Scheduler ===
from apscheduler.schedulers.background import BackgroundScheduler

scheduler = BackgroundScheduler(timezone=pytz.timezone("Asia/Dhaka"))
scheduler.add_job(check_all_sites, 'interval', minutes=60)
scheduler.start()

# প্রথম রান
check_all_sites()

while True:
    time.sleep(60)
