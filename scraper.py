import os
import json
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

def scrape_agbro_lahore():
    """Primary Source: Scrapes today's Lahore rates from Agbro Group"""
    url = "https://www.agbro.com/"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    
    try:
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code != 200:
            print("Failed to reach Agbro website.")
            return None

        soup = BeautifulSoup(response.text, 'html.parser')
        tables = soup.find_all('table')
        
        current_day = str(datetime.now().day)
        current_month = datetime.now().strftime("%b")
        current_year = datetime.now().strftime("%y")
        
        for table in tables:
            rows = table.find_all('tr')
            for row in rows:
                cols = [col.text.strip() for col in row.find_all(['td', 'th'])]
                if len(cols) >= 10:
                    date_str = cols[0]
                    
                    if f"{current_day}-{current_month}" in date_str and current_year in date_str:
                        doc = cols[6] if cols[6] != "–" else "N/A"
                        farm_rate = cols[7] if cols[7] != "–" else "N/A"
                        close_rate = cols[9] if cols[9] != "–" else "N/A"
                        
                        formatted_date = datetime.now().strftime("%d-%m-%Y")
                        
                        print("Data successfully fetched from Agbro (Primary Source)!")
                        return {
                            "date": formatted_date,
                            "doc_announced_rate": f"RS. {doc}",
                            "broiler_announced_rate": f"RS. {farm_rate}",
                            "market_position": f"RS. {close_rate}"
                        }
    except Exception as e:
        print(f"Agbro scraping error: {e}")
        
    return None

def upload_to_google_drive(filename):
    """Uploads or updates the JSON file on Google Drive using OAuth secrets"""
    client_id = os.environ.get("GDRIVE_CLIENT_ID")
    client_secret = os.environ.get("GDRIVE_CLIENT_SECRET")
    refresh_token = os.environ.get("GDRIVE_REFRESH_TOKEN")
    folder_id = os.environ.get("GDRIVE_FOLDER_ID")

    if not client_id or not client_secret or not refresh_token:
        print("Google Drive credentials missing in environment secrets!")
        return

    try:
        creds = Credentials(
            None,
            refresh_token=refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=client_id,
            client_secret=client_secret
        )

        service = build('drive', 'v3', credentials=creds)

        query = f"name = '{filename}' and trashed = false"
        if folder_id:
            query += f" and '{folder_id}' in parents"

        results = service.files().list(q=query, spaces='drive', fields='files(id, name)').execute()
        items = results.get('files', [])

        media = MediaFileUpload(filename, resumable=True)

        if items:
            file_id = items[0]['id']
            updated_file = service.files().update(
                fileId=file_id,
                media_body=media
            ).execute()
            print(f"File successfully updated on Google Drive! ID: {updated_file.get('id')}")
        else:
            file_metadata = {'name': filename}
            if folder_id:
                file_metadata['parents'] = [folder_id]
            
            uploaded_file = service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id'
            ).execute()
            print(f"File successfully created on Google Drive! ID: {uploaded_file.get('id')}")
    except Exception as e:
        print(f"Google Drive upload error: {e}")

def main():
    json_filename = "Lahore_Broiler_And_DOC_90Days.json"
    
    today_data = scrape_agbro_lahore()
    
    if today_data:
        print(f"Today's Rates Found: {today_data}")
        
        if os.path.exists(json_filename):
            with open(json_filename, "r") as f:
                data_list = json.load(f)
        else:
            data_list = []
            
        exists = False
        for item in data_list:
            if item.get("date") == today_data["date"]:
                item.update(today_data)
                exists = True
                break
                
        if not exists:
            data_list.insert(0, today_data)
            
        with open(json_filename, "w") as f:
            json.dump(data_list, f, indent=4)
        print("JSON file updated locally successfully!")
        
        # Upload updated file to Google Drive
        upload_to_google_drive(json_filename)
    else:
        print("Error: Rates not available on Agbro for today.")

if __name__ == "__main__":
    main()
