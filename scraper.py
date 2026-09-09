import os
import json
import requests
from bs4 import BeautifulSoup
from datetime import datetime

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
        
        for table in tables:
            rows = table.find_all('tr')
            for row in rows:
                cols = [col.text.strip() for col in row.find_all(['td', 'th'])]
                if len(cols) >= 10:
                    date_str = cols[0]  # e.g., "9-Sep-26"
                    
                    # Match today's date dynamically
                    today_match = datetime.now().strftime("%d-%b")
                    if today_match.lower() in date_str.lower():
                        doc = cols[6] if cols[6] != "–" else "N/A"
                        farm_rate = cols[7] if cols[7] != "–" else "N/A"
                        close_rate = cols[9] if cols[9] != "–" else "N/A"
                        
                        parsed_date = datetime.strptime(date_str, "%d-%b-%y")
                        formatted_date = parsed_date.strftime("%d-%m-%Y")
                        
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

def main():
    json_filename = "Lahore_Broiler_And_DOC_90Days.json"
    
    # Fetch today's rates directly from Agbro
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
        print("JSON file updated successfully!")
    else:
        print("Error: Rates not available on Agbro for today.")

if __name__ == "__main__":
    main()
