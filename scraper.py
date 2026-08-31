import os
import json
from datetime import datetime
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

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

def scrape_with_playwright(url, is_broiler=True):
    data_dict = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url, timeout=60000)
        page.wait_for_selector("table")

        # 1. Pichle 4 Months tak navigate karne ka loop
        for month_step in range(4):
            # 2. Har month ke andar 15-day pages crawl karne ka loop
            for page_step in range(3):
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

                # Upper 15 Days Page Navigation (← PREVIOUS 15 DAYS)
                prev_15_btn = page.locator("xpath=//*[contains(translate(text(), 'abcdefghijklmnopqrstuvwxyz', 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'), 'PREVIOUS 15 DAYS')]")
                if prev_15_btn.count() > 0 and prev_15_btn.first.is_visible():
                    try:
                        prev_15_btn.first.click()
                        page.wait_for_timeout(2500)
                    except Exception:
                        break
                else:
                    break

            # Lower Month Navigation (< Month Year > button click)
            prev_month_btn = page.locator("xpath=//button[contains(., '<')] | //a[contains(., '<')] | //div[contains(., '<')]").first
            if prev_month_btn.count() > 0 and prev_month_btn.is_visible():
                try:
                    prev_month_btn.click()
                    page.wait_for_timeout(3500)
                except Exception:
                    break
            else:
                break

        browser.close()
    return data_dict

def scrape_lahore_combined():
    print("Scraping Broiler Rates across months...")
    broiler_dict = scrape_with_playwright("https://www.poultrybaba.com/rates/broiler/lahore", is_broiler=True)
    
    print("Scraping DOC Rates across months...")
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

    # Merge by date
    combined_map = {item["date"]: item for item in existing_data}
    for entry in scraped_entries:
        combined_map[entry["date"]] = entry

    all_entries = list(combined_map.values())

    # Sort descending by Calendar Date
    all_entries.sort(key=lambda item: parse_date_string(item["date"]), reverse=True)

    # Strictly retain top 90 records
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
