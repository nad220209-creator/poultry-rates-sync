import requests
from bs4 import BeautifulSoup
from datetime import datetime

def get_today_agbro_lahore():
    """Primary Source: Scrape today's Lahore rates from Agbro"""
    url = "https://www.agbro.com/"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    
    try:
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code != 200:
            return None

        soup = BeautifulSoup(response.text, 'html.parser')
        today_date_str = datetime.now().strftime("%d-%b") # e.g. "9-Sep" or matching Agbro format
        
        tables = soup.find_all('table')
        for table in tables:
            rows = table.find_all('tr')
            for row in rows:
                cols = [col.text.strip() for col in row.find_all(['td', 'th'])]
                if len(cols) >= 10:
                    date_str = cols[0] # e.g. "9-Sep-26"
                    
                    # Check if row belongs to today
                    if datetime.now().strftime("%d-%b").lower() in date_str.lower():
                        doc = cols[6] if cols[6] != "–" else "N/A"
                        farm_rate = cols[7] if cols[7] != "–" else "N/A"
                        close_rate = cols[9] if cols[9] != "–" else "N/A"
                        
                        parsed_date = datetime.strptime(date_str, "%d-%b-%y")
                        formatted_date = parsed_date.strftime("%d-%m-%Y")
                        
                        print("Data successfully fetched from Agbro (Primary)!")
                        return {
                            "date": formatted_date,
                            "doc": f"RS. {doc}",
                            "broiler_rate": f"RS. {farm_rate}",
                            "market_position": f"RS. {close_rate}"
                        }
    except Exception as e:
        print(f"Agbro scraping error: {e}")
        
    return None

def get_today_poultry_baba():
    """Fallback Source: Scrape only present day from Poultry Baba if Agbro misses it"""
    print("Agbro missing today's data. Falling back to Poultry Baba for current day...")
    # Add your existing Poultry Baba single-day scraping/PDF extraction logic here
    # Return today's data dictionary in the exact same format
    return None

def main():
    # Step 1: Try Agbro first (Primary)
    today_data = get_today_agbro_lahore()
    
    # Step 2: If Agbro doesn't have today's data, use Poultry Baba fallback
    if not today_data:
        today_data = get_today_poultry_baba()
        
    if today_data:
        print(f"Today's active rates ready for sync: {today_data}")
        # Proceed with updating your JSON files, saving to Repo, and uploading to Google Drive
    else:
        print("Warning: Rates not available on Agbro or Poultry Baba for today.")

if __name__ == "__main__":
    main()
