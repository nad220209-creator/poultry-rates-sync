import os
import re
import json
import time
from datetime import datetime
from pypdf import PdfReader
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

def get_recent_months(count=4):
    months = []
    now = datetime.now()
    for i in range(count):
        year = now.year
        month = now.month - i
        while month <= 0:
            month += 12
            year -= 1
        dt = datetime(year, month, 1)
        months.append(dt.strftime("%b-%Y"))
    return months

def parse_date_string(date_str):
    if not date_str:
        return datetime.min
    date_str = date_str.strip()
    m = re.search(r'(\d{1,2}[-/]\d{1,2}[-/]\d{4}|\d{1,2}\s+[A-Za-z]{3}\s+\d{4})', date_str)
    if m:
        date_str = m.group(1)
    for fmt in ("%d-%m-%Y", "%d %b %Y", "%d-%b-%Y", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            pass
    return datetime.min

def normalize_date(date_str):
    dt = parse_date_string(date_str)
    if dt != datetime.min:
        return dt.strftime("%d-%m-%Y")
    return date_str.strip()

def clean_rate_text(text):
    if not text or text == "N/A":
        return "N/A"
    text = re.sub(r'\$\d+(?:\.\d+)?\s*USD', '', text, flags=re.IGNORECASE).strip()
    m = re.search(r'(?:RS\.?\s*)?(\d+(?:\.\d+)?)', text, re.IGNORECASE)
    if m:
        return f"RS. {m.group(1)}"
    return text.strip() if text.strip() else "N/A"

def parse_pdf_broiler(pdf_path):
    data = {}
    try:
        reader = PdfReader(pdf_path)
        full_text = ""
        for page in reader.pages:
            full_text += (page.extract_text() or "") + "\n"

        for line in full_text.splitlines():
            date_match = re.search(r'(\d{1,2}[-/]\d{1,2}[-/]\d{4})', line)
            if date_match:
                norm_d = normalize_date(date_match.group(1))
                after_date = line[date_match.end():]
                rates = re.findall(r'(?:RS\.?\s*)?\d+(?:\.\d+)?', after_date, re.IGNORECASE)
                cleaned = [clean_rate_text(r) for r in rates if clean_rate_text(r) != "N/A"]
                if len(cleaned) >= 3:
                    data[norm_d] = {
                        "broiler_announced_rate": cleaned[0],
                        "market_position": cleaned[1],
                        "average_rate": cleaned[2]
                    }
                elif len(cleaned) == 2:
                    data[norm_d] = {
                        "broiler_announced_rate": cleaned[0],
                        "market_position": cleaned[1],
                        "average_rate": "N/A"
                    }
    except Exception as e:
        print(f"Error parsing Broiler PDF {pdf_path}: {e}")
    return data

def parse_pdf_chick(pdf_path):
    data = {}
    try:
        reader = PdfReader(pdf_path)
        full_text = ""
        for page in reader.pages:
            full_text += (page.extract_text() or "") + "\n"

        for line in full_text.splitlines():
            date_match = re.search(r'(\d{1,2}[-/]\d{1,2}[-/]\d{4})', line)
            if date_match:
                norm_d = normalize_date(date_match.group(1))
                after_date = line[date_match.end():]
                rates = re.findall(r'(?:RS\.?\s*)?\d+(?:\.\d+)?', after_date, re.IGNORECASE)
                cleaned = [clean_rate_text(r) for r in rates if clean_rate_text(r) != "N/A"]
                if cleaned:
                    data[norm_d] = cleaned[0]
    except Exception as e:
        print(f"Error parsing Chick PDF {pdf_path}: {e}")
    return data

def download_pdf_with_retry(page, pdf_btn, temp_pdf, max_retries=10):
    """Retries downloading PDF up to 10 times with 1.5 sec delay on failure."""
    for attempt in range(1, max_retries + 1):
        try:
            with page.expect_download(timeout=15000) as download_info:
                pdf_btn.first.click(force=True)
            download = download_info.value
            download.save_as(temp_pdf)
            if os.path.exists(temp_pdf) and os.path.getsize(temp_pdf) > 0:
                print(f"Download successful on attempt {attempt}: {temp_pdf}")
                return True
        except Exception as e:
            print(f"PDF Download attempt {attempt}/{max_retries} failed: {e}")
            page.wait_for_timeout(1500)
    return False

def scrape_table_fallback(page, is_broiler=True):
    data_dict = {}
    soup = BeautifulSoup(page.content(), "html.parser")
    table = soup.find("table")
    if table:
        for row in table.find_all("tr")[1:]:
            cols = row.find_all("td")
            if len(cols) >= 2:
                d = cols[0].text.strip()
                if d:
                    norm_d = normalize_date(d)
                    if is_broiler and len(cols) >= 4:
                        data_dict[norm_d] = {
                            "broiler_announced_rate": clean_rate_text(cols[1].text),
                            "market_position": clean_rate_text(cols[2].text),
                            "average_rate": clean_rate_text(cols[3].text)
                        }
                    elif not is_broiler:
                        data_dict[norm_d] = clean_rate_text(cols[1].text)
    return data_dict

def scrape_today_cards(page):
    today_data = {"broiler": {}, "chick": {}}
    
    # Broiler Card
    try:
        page.goto("https://www.poultrybaba.com/rates/broiler/lahore", timeout=60000)
        page.wait_for_selector("table", timeout=15000)
        soup = BeautifulSoup(page.content(), "html.parser")
        
        date_match = re.search(r'(\d{1,2}\s+[A-Za-z]{3}\s+\d{4})', soup.text)
        if date_match:
            norm_d = normalize_date(date_match.group(1))
            announced = "N/A"
            actual = "N/A"
            
            ann_elem = soup.find(text=re.compile(r'ANNOUNCED RATE', re.I))
            if ann_elem and ann_elem.parent:
                rate_match = re.search(r'(\d+[\.\d]*)', ann_elem.parent.parent.text)
                if rate_match:
                    announced = f"RS. {rate_match.group(1)}"
                    
            act_elem = soup.find(text=re.compile(r'ACTUAL POSITION', re.I))
            if act_elem and act_elem.parent:
                rate_match = re.search(r'(\d+[\.\d]*)', act_elem.parent.parent.text)
                if rate_match:
                    actual = f"RS. {rate_match.group(1)}"
                    
            today_data["broiler"][norm_d] = {
                "broiler_announced_rate": announced,
                "market_position": actual,
                "average_rate": "N/A"
            }
    except Exception as e:
        print(f"Error scraping today broiler card: {e}")

    # Chick Card
    try:
        page.goto("https://www.poultrybaba.com/rates/broiler-chick/lahore", timeout=60000)
        page.wait_for_selector("table", timeout=15000)
        soup = BeautifulSoup(page.content(), "html.parser")
        
        date_match = re.search(r'(\d{1,2}\s+[A-Za-z]{3}\s+\d{4})', soup.text)
        if date_match:
            norm_d = normalize_date(date_match.group(1))
            chick_rate = "N/A"
            ann_elem = soup.find(text=re.compile(r'ANNOUNCED RATE', re.I))
            if ann_elem and ann_elem.parent:
                rate_match = re.search(r'(\d+[\.\d]*)', ann_elem.parent.parent.text)
                if rate_match:
                    chick_rate = f"RS. {rate_match.group(1)}"
                    
            today_data["chick"][norm_d] = chick_rate
    except Exception as e:
        print(f"Error scraping today chick card: {e}")
        
    return today_data

def scrape_lahore_combined():
    broiler_dict = {}
    chick_dict = {}
    download_failures = []
    recent_months = get_recent_months(4)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()

        print("Scraping Today's Live Rates...")
        today_cards = scrape_today_cards(page)
        broiler_dict.update(today_cards["broiler"])
        chick_dict.update(today_cards["chick"])

        # 1. Download Broiler PDFs with Retry
        print("Downloading Broiler PDFs with retries...")
        for m_str in recent_months:
            url = f"https://www.poultrybaba.com/rates/broiler/lahore?month={m_str}"
            try:
                page.goto(url, timeout=60000)
                page.wait_for_selector("table", timeout=15000)
                
                t_data = scrape_table_fallback(page, is_broiler=True)
                for k, v in t_data.items():
                    if k not in broiler_dict:
                        broiler_dict[k] = v

                pdf_btn = page.get_by_text("Download PDF", exact=False)
                if pdf_btn.count() > 0 and pdf_btn.first.is_visible():
                    temp_pdf = f"broiler_{m_str}.pdf"
                    success = download_pdf_with_retry(page, pdf_btn, temp_pdf, max_retries=10)
                    if success:
                        parsed = parse_pdf_broiler(temp_pdf)
                        broiler_dict.update(parsed)
                        if os.path.exists(temp_pdf):
                            os.remove(temp_pdf)
                    else:
                        download_failures.append(f"Broiler PDF download failed after 10 retries for month {m_str}")
            except Exception as e:
                download_failures.append(f"Broiler page error for month {m_str}: {e}")

        # 2. Download Chick PDFs with Retry
        print("Downloading Chick PDFs with retries...")
        for m_str in recent_months:
            url = f"https://www.poultrybaba.com/rates/broiler-chick/lahore?month={m_str}"
            try:
                page.goto(url, timeout=60000)
                page.wait_for_selector("table", timeout=15000)
                
                t_data = scrape_table_fallback(page, is_broiler=False)
                for k, v in t_data.items():
                    if k not in chick_dict:
                        chick_dict[k] = v

                pdf_btn = page.get_by_text("Download PDF", exact=False)
                if pdf_btn.count() > 0 and pdf_btn.first.is_visible():
                    temp_pdf = f"chick_{m_str}.pdf"
                    success = download_pdf_with_retry(page, pdf_btn, temp_pdf, max_retries=10)
                    if success:
                        parsed = parse_pdf_chick(temp_pdf)
                        chick_dict.update(parsed)
                        if os.path.exists(temp_pdf):
                            os.remove(temp_pdf)
                    else:
                        download_failures.append(f"Chick PDF download failed after 10 retries for month {m_str}")
            except Exception as e:
                download_failures.append(f"Chick page error for month {m_str}: {e}")

        browser.close()

    all_dates = list(dict.fromkeys(list(broiler_dict.keys()) + list(chick_dict.keys())))
    scraped_entries = []

    for d in all_dates:
        b_info = broiler_dict.get(d, {})
        doc_rate = chick_dict.get(d, "N/A")
        
        b_ann = b_info.get("broiler_announced_rate", "N/A") if isinstance(b_info, dict) else "N/A"
        m_pos = b_info.get("market_position", "N/A") if isinstance(b_info, dict) else "N/A"
        a_rate = b_info.get("average_rate", "N/A") if isinstance(b_info, dict) else "N/A"

        scraped_entries.append({
            "date": d,
            "doc_announced_rate": doc_rate,
            "broiler_announced_rate": b_ann,
            "market_position": m_pos,
            "average_rate": a_rate
        })

    local_file = "Lahore_Broiler_And_DOC_90Days.json"
    existing_data = []

    if os.path.exists(local_file):
        try:
            with open(local_file, "r", encoding="utf-8") as f:
                existing_data = json.load(f)
                # Filter out previous status log objects if present
                existing_data = [item for item in existing_data if "date" in item and item["date"] != "STATUS_LOG"]
        except Exception:
            existing_data = []

    combined_map = {item["date"]: item for item in existing_data}
    for entry in scraped_entries:
        if entry["date"] not in combined_map:
            combined_map[entry["date"]] = entry
        else:
            existing = combined_map[entry["date"]]
            for key in ["doc_announced_rate", "broiler_announced_rate", "market_position", "average_rate"]:
                if entry[key] != "N/A":
                    existing[key] = entry[key]

    all_entries = list(combined_map.values())
    all_entries.sort(key=lambda item: parse_date_string(item["date"]), reverse=True)

    final_90_days_data = all_entries[:90]

    # If any download failures occurred after 10 retries, prepend a status log entry at index 0
    if download_failures:
        failure_log_entry = {
            "date": "STATUS_LOG",
            "status": "PARTIAL_FAILURE",
            "failures": download_failures,
            "timestamp": datetime.now().strftime("%d-%m-%Y %H:%M:%S")
        }
        final_90_days_data.insert(0, failure_log_entry)

    with open(local_file, "w", encoding="utf-8") as f:
        json.dump(final_90_days_data, f, indent=4, ensure_ascii=False)

    print(f"Successfully updated {local_file} with {len(final_90_days_data)} records.")
    return local_file

def upload_to_drive(file_path):
    client_id = os.environ.get("GDRIVE_CLIENT_ID")
    client_secret = os.environ.get("GDRIVE_CLIENT_SECRET")
    refresh_token = os.environ.get("GDRIVE_REFRESH_TOKEN")
    folder_id = os.environ.get("GDRIVE_FOLDER_ID")

    if not all([client_id, client_secret, refresh_token, folder_id]):
        print("Missing required Drive OAuth credentials in environment variables!")
        return

    creds = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id,
        client_secret=client_secret,
        scopes=["https://www.googleapis.com/auth/drive.file"]
    )

    if creds.expired or not creds.valid:
        creds.refresh(Request())

    service = build("drive", "v3", credentials=creds)
    file_name = "Lahore_Broiler_And_DOC_90Days.json"

    query = f"'{folder_id}' in parents and name = '{file_name}' and trashed = false"
    results = service.files().list(q=query, fields="files(id)").execute()
    files = results.get("files", [])

    media = MediaFileUpload(file_path, mimetype="application/json")

    if files:
        service.files().update(fileId=files[0]["id"], media_body=media).execute()
        print("File updated on Google Drive successfully!")
    else:
        file_metadata = {"name": file_name, "parents": [folder_id]}
        service.files().create(body=file_metadata, media_body=media, fields="id").execute()
        print("File created on Google Drive successfully!")

if __name__ == "__main__":
    file_path = scrape_lahore_combined()
    upload_to_drive(file_path)
