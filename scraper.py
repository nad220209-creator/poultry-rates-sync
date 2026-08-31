import os
import json
from datetime import datetime
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

def get_recent_months(count=4):
    """Pichle N calendar months ke month-year strings generate karta hai (e.g. Aug-2026, Jul-2026)."""
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

def scrape_with_playwright(base_url, is_broiler=True):
    data_dict = {}
    recent_months = get_recent_months(4)  # Pichle 4 months cover 90+ days

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        for m_str in recent_months:
            month_url = f"{base_url}?month={m_str}"
            try:
                page.goto(month_url, timeout=60000)
                page.wait_for_selector("table", timeout=15000)
            except Exception as e:
                print(f"Skipping month URL {month_url}: {e}")
                continue

            # Har month ke andar 15-day chunks iterate karne ka loop
            while True:
                soup = BeautifulSoup(page.content(), "html.parser")
                table = soup.find("table")
                if table:
                    for row in table.find_all("tr")[1:]:
                        cols = row.find_all("td")
                        if len(cols) >= 2:
                            d = cols[0].text.strip()
                            if d and d not in data_dict:
                                if is_broiler and len(cols) >= 4:
                                    data_dict[d] = {
                                        "broiler_announced_rate": cols[1].text.strip(),
                                        "market_position": cols[2].text.strip(),
                                        "average_rate": cols[3].text.strip()
                                    }
                                elif not is_broiler:
                                    data_dict[d] = cols[1].text.strip()

                # Upper "PREVIOUS 15 DAYS" button ka state check
                prev_btn = page.get_by_text("PREVIOUS 15 DAYS", exact=False)
                if prev_btn.count() > 0 and prev_btn.first.is_visible():
                    btn_element = prev_btn.first
                    btn_class = btn_element.get_attribute("class") or ""
                    
                    # Agar button disabled ya greyed out ho jaye toh inner loop end karke agla month load karein
                    if btn_element.is_disabled() or "disabled" in btn_class.lower() or "grey" in btn_class.lower():
                        break

                    try:
                        old_content = page.content()
                        btn_element.click(force=True, timeout=3000)
                        page.wait_for_timeout(2500)
                        # Agar click ke baad content change na ho (month ka start aa gaya) toh loop break karein
                        if page.content() == old_content:
                            break
                    except Exception:
                        break
                else:
                    break

        browser.close()
    return data_dict

def scrape_lahore_combined():
    print("Scraping 90 days Broiler Rates...")
    broiler_dict = scrape_with_playwright("https://www.poultrybaba.com/rates/broiler/lahore", is_broiler=True)
    
    print("Scraping 90 days Chick Rates...")
    chick_dict = scrape_with_playwright("https://www.poultrybaba.com/rates/broiler-chick/lahore", is_broiler=False)

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

    # Date ke mutabiq descending sort (latest date pehle)
    all_entries.sort(key=lambda item: parse_date_string(item["date"]), reverse=True)

    # Strictly top 90 records preserve honge (91st oldest date drop ho jayegi)
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
