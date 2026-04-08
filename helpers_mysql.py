import hashlib
import os
import pymysql
import re
import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from telegram import Bot
from dotenv import load_dotenv

load_dotenv()

# === MySQL Configuration ===
MYSQL_HOST = os.getenv("MYSQL_HOST")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", 3306))  # রেলওয়েতে ডিফল্ট পোর্ট সাধারণত ৩৩০৬
MYSQL_DB = os.getenv("MYSQL_DB")
MYSQL_USER = os.getenv("MYSQL_USER")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD")

# ✅ ইউনিক হ্যাশ জেনারেটর
def get_notice_hash(text: str, link: str) -> str:
    return hashlib.sha256((text.strip() + link.strip()).encode()).hexdigest()

# ✅ MySQL Connection (Railway হোস্টিং এর জন্য অপ্টিমাইজড)
def get_connection():
    if not all([MYSQL_HOST, MYSQL_DB, MYSQL_USER, MYSQL_PASSWORD]):
        raise ValueError("MySQL database credentials are missing.")

    return pymysql.connect(
        host=MYSQL_HOST,
        port=MYSQL_PORT,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        database=MYSQL_DB,
        charset='utf8mb4',
        cursorclass=pymysql.cursors.DictCursor,
        connect_timeout=15,
        autocommit=True
    )

# ✅ কানেকশন ফেইল করলে পুনরায় চেষ্টা করার ফাংশন
def get_connection_retry(retries=3, delay=2):
    for i in range(retries):
        try:
            return get_connection()
        except Exception as e:
            print(f"❌ MySQL retry {i+1} failed: {e}")
            time.sleep(delay)
    raise Exception("❌ Database connection failed after retries")

# ✅ টেবিল তৈরি করা
def init_db():
    try:
        with get_connection_retry() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS sent_notices (
                        site VARCHAR(255),
                        link_hash VARCHAR(64),
                        PRIMARY KEY (site, link_hash)
                    )
                """)
            conn.commit()
            print("✅ Database initialized successfully on Railway.")
    except Exception as e:
        print(f"❌ init_db Error: {e}")

# ✅ ডাটাবেজ থেকে হ্যাশ লোড করা
def load_sent_notice_hashes(site):
    try:
        with get_connection_retry() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT link_hash FROM sent_notices WHERE site = %s",
                    (site,)
                )
                return {row['link_hash'] for row in cur.fetchall()}
    except Exception:
        return set()

# ✅ নতুন নোটিশ ডাটাবেজে সেভ করা
def add_sent_notice(site, link_hash):
    try:
        with get_connection_retry() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT IGNORE INTO sent_notices (site, link_hash) VALUES (%s, %s)",
                    (site, link_hash)
                )
            conn.commit()
    except Exception as e:
        print(f"❌ Error adding notice: {e}")

# ✅ ডাটাবেজ পরিষ্কার করা
def clear_all_sent_notices():
    try:
        with get_connection_retry() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM sent_notices")
            conn.commit()
    except Exception as e:
        print(f"❌ Error clearing table: {e}")

# === Telegram Config ===
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
bot = Bot(token=BOT_TOKEN)

# ✅ মেসেজ ফরম্যাট ঠিক করা
def escape_markdown(text: str) -> str:
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    return re.sub(r'([%s])' % re.escape(escape_chars), r'\\\1', text)

# ✅ টেলিগ্রামে মেসেজ পাঠানো
def send_telegram_message(message: str):
    try:
        # Markdown মোডে মেসেজ পাঠানো (লিংক সহ)
        bot.send_message(
            chat_id=CHAT_ID,
            text=message,
            parse_mode="Markdown",
            disable_web_page_preview=True
        )
    except Exception as e:
        print(f"❌ Telegram send error: {e}")

# === Selenium WebDriver (Human-Like Mode) ===
def get_webdriver(headless=True) -> webdriver.Chrome:
    chrome_options = Options()
    if headless:
        chrome_options.add_argument("--headless=new")
    
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    
    driver = webdriver.Chrome(options=chrome_options)
    
    # বট ডিটেকশন বাইপাস করতে জাভাস্ক্রিপ্ট রান করা
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    })
    
    return driver

def close_webdriver(driver):
    try:
        driver.quit()
    except Exception:
        pass
