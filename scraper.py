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
    """Pichle 4 calendar months (e.g. Aug-2026, Jul-2026) generate karta hai."""
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
                cleaned = []
                for r in rates:
                    val = r.strip()
                    if val and not val.upper().startswith("RS"):
                        val = f"RS. {val}"
                    cleaned.append(val)
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
                    if not val.upper().startswith("RS"):
                        val = f"RS. {val}"
                    data[date_str] = val
    except Exception as e:
        print(f"Error parsing Chick PDF {pdf_path}: {e}")
    return data

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
                    if is_broiler and len(cols) >= 4:
                        data_dict[d] = {
                            "broiler_announced_rate": cols[1].text.strip(),
                            "market_position": cols[2].text.strip(),
                            "average_rate": cols[3].text.strip()
                        }
                    elif not is_broiler:
                        data_dict[d] = cols[1].text.strip()
    return data_dict

def scrape_lahore_combined():
    broiler_dict = {}
    chick_dict = {}
    recent_months = get_recent_months(4)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()

        # 1. Download & Parse Broiler PDFs
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
                    broiler_dict.update(parsed)
                    if os.path.exists(temp_pdf):
                        os.remove(temp_pdf)
                
                # HTML Table Fallback merge
                table_data = scrape_table_fallback(page, is_broiler=True)
                for k, v in table_data.items():
                    if k not in broiler_dict:
                        broiler_dict[k] = v
            except Exception as e:
                print(f"Error processing Broiler page for {m_str}: {e}")

        # 2. Download & Parse Broiler Chick (DOC) PDFs
        print("Downloading Broiler Chick PDFs...")
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
                    chick_dict.update(parsed)
                    if os.path.exists(temp_pdf):
                        os.remove(temp_pdf)

                # HTML Table Fallback merge
                table_data = scrape_table_fallback(page, is_broiler=False)
                for k, v in table_data.items():
                    if k not in chick_dict:
                        chick_dict[k] = v
            except Exception as e:
                print(f"Error processing Chick page for {m_str}: {e}")

        browser.close()

    # Combine extracted entries
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

    # Merge by date key
    combined_map = {item["date"]: item for item in existing_data}
    for entry in scraped_entries:
        combined_map[entry["date"]] = entry

    all_entries = list(combined_map.values())

    # Sort descending by Calendar Date
    all_entries.sort(key=lambda item: parse_date_string(item["date"]), reverse=True)

    # Strictly retain top 90 records (drops 91st oldest date)
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
