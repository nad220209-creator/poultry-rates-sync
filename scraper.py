import os
import re
import json
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
    for fmt in ("%d-%m-%Y", "%d %b %Y", "%d-%b-%Y", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            pass
    return datetime.min

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
                date_str = date_match.group(1)
                after_date = line[date_match.end():]
                rates = re.findall(r'(?:RS\.?\s*)?[\d\.]+', after_date, re.IGNORECASE)
                cleaned = [r.strip() if r.strip().upper().startswith("RS") else f"RS. {r.strip()}" for r in rates]
                if len(cleaned) >= 3:
                    data[date_str] = {
                        "broiler_announced_rate": cleaned[0],
                        "market_position": cleaned[1],
                        "average_rate": cleaned[2]
                    }
                elif len(cleaned) == 2:
                    data[date_str] = {
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
                date_str = date_match.group(1)
                after_date = line[date_match.end():]
                rates = re.findall(r'(?:RS\.?\s*)?[\d\.]+', after_date, re.IGNORECASE)
                if rates:
                    val = rates[0].strip()
                    data[date_str] = val if val.upper().startswith("RS") else f"RS. {val}"
    except Exception as e:
        print(f"Error parsing Chick PDF {pdf_path}: {e}")
    return data

def scrape_today_cards(page):
    """Scrapes today's live rate from the top card of the page."""
    today_data = {"broiler": {}, "chick": {}}
    
    # 1. Scrape Today Broiler Card
    try:
        page.goto("https://www.poultrybaba.com/rates/broiler/lahore", timeout=60000)
        page.wait_for_selector("h1, h2", timeout=10000)
        text = page.content()
        soup = BeautifulSoup(text, "html.parser")
        
        # Look for today's date e.g., 31 Aug 2026
        date_match = re.search(r'(\d{1,2}\s+[A-Za-z]{3}\s+\d{4})', soup.text)
        if date_match:
            dt_obj = datetime.strptime(date_match.group(1), "%d %b %Y")
            formatted_date = dt_obj.strftime("%d-%m-%Y")
            
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
                    
            today_data["broiler"][formatted_date] = {
                "broiler_announced_rate": announced,
                "market_position": actual,
                "average_rate": "N/A"
            }
    except Exception as e:
        print(f"Error scraping today broiler card: {e}")

    # 2. Scrape Today Chick Card
    try:
        page.goto("https://www.poultrybaba.com/rates/broiler-chick/lahore", timeout=60000)
        page.wait_for_selector("h1, h2", timeout=10000)
        text = page.content()
        soup = BeautifulSoup(text, "html.parser")
        
        date_match = re.search(r'(\d{1,2}\s+[A-Za-z]{3}\s+\d{4})', soup.text)
        if date_match:
            dt_obj = datetime.strptime(date_match.group(1), "%d %b %Y")
            formatted_date = dt_obj.strftime("%d-%m-%Y")
            
            chick_rate = "N/A"
            ann_elem = soup.find(text=re.compile(r'ANNOUNCED RATE', re.I))
            if ann_elem and ann_elem.parent:
                rate_match = re.search(r'(\d+[\.\d]*)', ann_elem.parent.parent.text)
                if rate_match:
                    chick_rate = f"RS. {rate_match.group(1)}"
                    
            today_data["chick"][formatted_date] = chick_rate
    except Exception as e:
        print(f"Error scraping today chick card: {e}")
        
    return today_data

def scrape_lahore_combined():
    broiler_dict = {}
    chick_dict = {}
    recent_months = get_recent_months(4)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()

        # Scrape Today's Live Rate Top Cards
        print("Scraping Today's Live Rates...")
        today_cards = scrape_today_cards(page)
        broiler_dict.update(today_cards["broiler"])
        chick_dict.update(today_cards["chick"])

        # 1. Download Broiler PDFs
        print("Downloading Broiler PDFs...")
        for m_str in recent_months:
            url = f"https://www.poultrybaba.com/rates/broiler/lahore?month={m_str}"
            try:
                page.goto(url, timeout=60000)
                page.wait_for_selector("table", timeout=15000)
                
                pdf_btn = page.get_by_text("Download PDF", exact=False)
                if pdf_btn.count() > 0 and pdf_btn.first.is_visible():
                    with page.expect_download(timeout=20000) as download_info:
                        pdf_btn.first.click(force=True)
                    download = download_info.value
                    temp_pdf = f"broiler_{m_str}.pdf"
                    download.save_as(temp_pdf)
                    parsed = parse_pdf_broiler(temp_pdf)
                    for k, v in parsed.items():
                        if k not in broiler_dict:
                            broiler_dict[k] = v
                    if os.path.exists(temp_pdf):
                        os.remove(temp_pdf)
            except Exception as e:
                print(f"Error processing Broiler page for {m_str}: {e}")

        # 2. Download Chick PDFs
        print("Downloading Chick PDFs...")
        for m_str in recent_months:
            url = f"https://www.poultrybaba.com/rates/broiler-chick/lahore?month={m_str}"
            try:
                page.goto(url, timeout=60000)
                page.wait_for_selector("table", timeout=15000)
                
                pdf_btn = page.get_by_text("Download PDF", exact=False)
                if pdf_btn.count() > 0 and pdf_btn.first.is_visible():
                    with page.expect_download(timeout=20000) as download_info:
                        pdf_btn.first.click(force=True)
                    download = download_info.value
                    temp_pdf = f"chick_{m_str}.pdf"
                    download.save_as(temp_pdf)
                    parsed = parse_pdf_chick(temp_pdf)
                    for k, v in parsed.items():
                        if k not in chick_dict:
                            chick_dict[k] = v
                    if os.path.exists(temp_pdf):
                        os.remove(temp_pdf)
            except Exception as e:
                print(f"Error processing Chick page for {m_str}: {e}")

        browser.close()

    all_dates = list(dict.fromkeys(list(broiler_dict.keys()) + list(chick_dict.keys())))
    scraped_entries = []

    for d in all_dates:
        b_info = broiler_dict.get(d, {})
        doc_rate = chick_dict.get(d, "N/A")
        scraped_entries.append({
            "date": d,
            "doc_announced_rate": doc_rate,
            "broiler_announced_rate": b_info.get("broiler_announced_rate", "N/A"),
            "market_position": b_info.get("market_position", "N/A"),
            "average_rate": b_info.get("average_rate", "N/A")
        })

    local_file = "Lahore_Broiler_And_DOC_90Days.json"
    existing_data = []

    if os.path.exists(local_file):
        try:
            with open(local_file, "r", encoding="utf-8") as f:
                existing_data = json.load(f)
        except Exception:
            existing_data = []

    combined_map = {item["date"]: item for item in existing_data}
    for entry in scraped_entries:
        combined_map[entry["date"]] = entry

    all_entries = list(combined_map.values())
    all_entries.sort(key=lambda item: parse_date_string(item["date"]), reverse=True)

    final_90_days_data = all_entries[:90]

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
