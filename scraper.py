import os
import json
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

def get_recent_months(count=4):
    """Pichle N calendar months ke month-year strings generate karta hai (e.g., Aug-2026, Jul-2026)."""
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
    """Date strings ko parse karke datetime object banata hai taaki sort ho sakein."""
    date_str = date_str.strip()
    for fmt in ("%d-%m-%Y", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            pass
    return None

def scrape_lahore_combined():
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    months = get_recent_months(4) # 4 months cover 90+ days history
    broiler_dict = {}
    chick_dict = {}

    # 1. Scrape Broiler Rates across pagination months
    for m in months:
        url = f"https://www.poultrybaba.com/rates/broiler/lahore?month={m}"
        try:
            res = requests.get(url, headers=headers, timeout=15)
            if res.status_code == 200:
                soup = BeautifulSoup(res.text, "html.parser")
                table = soup.find("table")
                if table:
                    for row in table.find_all("tr")[1:]:
                        cols = row.find_all("td")
                        if len(cols) >= 4:
                            d = cols[0].text.strip()
                            if d and d not in broiler_dict:
                                broiler_dict[d] = {
                                    "broiler_announced_rate": cols[1].text.strip(),
                                    "market_position": cols[2].text.strip(),
                                    "average_rate": cols[3].text.strip()
                                }
        except Exception as e:
            print(f"Error scraping broiler data for {m}: {e}")

    # 2. Scrape Broiler Chick (DOC) Rates across pagination months
    for m in months:
        url = f"https://www.poultrybaba.com/rates/broiler-chick/lahore?month={m}"
        try:
            res = requests.get(url, headers=headers, timeout=15)
            if res.status_code == 200:
                soup = BeautifulSoup(res.text, "html.parser")
                table = soup.find("table")
                if table:
                    for row in table.find_all("tr")[1:]:
                        cols = row.find_all("td")
                        if len(cols) >= 2:
                            d = cols[0].text.strip()
                            if d and d not in chick_dict:
                                chick_dict[d] = cols[1].text.strip()
        except Exception as e:
            print(f"Error scraping chick data for {m}: {e}")

    # 3. Scraped entries combine karein
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

    # 4. Local file merge and rolling 90-day window limit
    local_file = "Lahore_Broiler_And_DOC_90Days.json"
    existing_data = []

    if os.path.exists(local_file):
        try:
            with open(local_file, "r", encoding="utf-8") as f:
                existing_data = json.load(f)
        except Exception:
            existing_data = []

    # Combine existing and new data by date
    combined_map = {item["date"]: item for item in existing_data}
    for entry in scraped_entries:
        combined_map[entry["date"]] = entry

    all_entries = list(combined_map.values())

    # Sort descending (newest date first)
    def date_key(item):
        dt = parse_date_string(item["date"])
        return dt if dt else datetime.min

    all_entries.sort(key=date_key, reverse=True)

    # Strictly keep top 90 records (rolling FIFO window)
    final_90_days_data = all_entries[:90]

    with open(local_file, "w", encoding="utf-8") as f:
        json.dump(final_90_days_data, f, indent=4, ensure_ascii=False)

    print(f"Successfully updated {local_file} with {len(final_90_days_data)} records.")
    return local_file

def upload_to_drive(file_path):
    creds_json = os.environ.get("GDRIVE_CREDENTIALS")
    folder_id = os.environ.get("GDRIVE_FOLDER_ID")

    if not creds_json or not folder_id:
        print("Error: Missing GDRIVE_CREDENTIALS or GDRIVE_FOLDER_ID environment variables!")
        return

    creds_dict = json.loads(creds_json)
    creds = Credentials.from_service_account_info(
        creds_dict,
        scopes=["https://www.googleapis.com/auth/drive"]
    )

    service = build("drive", "v3", credentials=creds)
    file_name = "Lahore_Broiler_And_DOC_90Days.json"

    query = f"'{folder_id}' in parents and name = '{file_name}' and trashed = false"
    results = service.files().list(q=query, fields="files(id)", supportsAllDrives=True, includeItemsFromAllDrives=True).execute()
    files = results.get("files", [])

    media = MediaFileUpload(file_path, mimetype="application/json")

    if files:
        service.files().update(fileId=files[0]["id"], media_body=media, supportsAllDrives=True).execute()
        print("File updated on Google Drive!")
    else:
        file_metadata = {"name": file_name, "parents": [folder_id]}
        service.files().create(body=file_metadata, media_body=media, fields="id", supportsAllDrives=True).execute()
        print("File created on Google Drive!")

if __name__ == "__main__":
    file_path = scrape_lahore_combined()
    upload_to_drive(file_path)
