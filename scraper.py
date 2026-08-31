import os
import json
import requests
from bs4 import BeautifulSoup
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

def scrape_lahore_combined():
    headers = {"User-Agent": "Mozilla/5.0"}
    
    broiler_url = "https://www.poultrybaba.com/rates/broiler/lahore?month=Aug-2026"
    res_broiler = requests.get(broiler_url, headers=headers)
    broiler_dict = {}
    
    if res_broiler.status_code == 200:
        soup = BeautifulSoup(res_broiler.text, "html.parser")
        table = soup.find("table")
        if table:
            for row in table.find_all("tr")[1:]:
                cols = row.find_all("td")
                if len(cols) >= 4:
                    d = cols[0].text.strip()
                    broiler_dict[d] = {
                        "broiler_announced_rate": cols[1].text.strip(),
                        "market_position": cols[2].text.strip(),
                        "average_rate": cols[3].text.strip()
                    }

    chick_url = "https://www.poultrybaba.com/rates/broiler-chick/lahore"
    res_chick = requests.get(chick_url, headers=headers)
    chick_dict = {}
    
    if res_chick.status_code == 200:
        soup = BeautifulSoup(res_chick.text, "html.parser")
        table = soup.find("table")
        if table:
            for row in table.find_all("tr")[1:]:
                cols = row.find_all("td")
                if len(cols) >= 2:
                    d = cols[0].text.strip()
                    chick_dict[d] = cols[1].text.strip()

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

    existing_dates = {item["date"] for item in existing_data}
    for entry in scraped_entries:
        if entry["date"] not in existing_dates:
            existing_data.append(entry)

    final_90_days_data = existing_data[:90]

    with open(local_file, "w", encoding="utf-8") as f:
        json.dump(final_90_days_data, f, indent=4, ensure_ascii=False)
        
    return local_file

def upload_to_drive(file_path):
    creds_json = os.environ.get("GDRIVE_CREDENTIALS")
    folder_id = os.environ.get("GDRIVE_FOLDER_ID")
    
    if not creds_json or not folder_id:
        print("Missing credentials/folder_id!")
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
        print("File updated on Drive!")
    else:
        file_metadata = {"name": file_name, "parents": [folder_id]}
        service.files().create(body=file_metadata, media_body=media, fields="id", supportsAllDrives=True).execute()
        print("File created on Drive!")

if __name__ == "__main__":
    file_path = scrape_lahore_combined()
    upload_to_drive(file_path)
