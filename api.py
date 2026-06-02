# api.py

import time
import re
import shutil
from datetime import datetime

try:
    import requests
except ImportError:
    requests = None

from config import ConfigManager

class IGDBClient:
    def __init__(self, client_id, client_secret, config_manager: ConfigManager):
        self.client_id = client_id
        self.client_secret = client_secret
        self.config_manager = config_manager
        self.access_token = None
        self.token_expiry = 0

    def is_configured(self):
        return bool(self.client_id and self.client_secret)

    def authenticate(self):
        if not requests:
            return False
        if self.access_token and time.time() < self.token_expiry:
            return True
        if not self.is_configured():
            return False
            
        url = "https://id.twitch.tv/oauth2/token"
        params = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "grant_type": "client_credentials"
        }
        try:
            response = requests.post(url, params=params, timeout=5)
            if response.status_code == 200:
                data = response.json()
                self.access_token = data["access_token"]
                self.token_expiry = time.time() + data["expires_in"] - 60
                return True
        except Exception as e:
            print(f"IGDB Authentication failed: {e}")
        return False

    def resolve_serial_to_title(self, serial):
        if not requests or not serial:
            return None
            
        serial_clean = serial.replace("-", "").replace("_", "").replace(".", "").upper().strip()
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"}
        
        # 1. Try SerialStation (PS1, PS2, PS3, PSP)
        url_station = f"https://serialstation.com/search/?q={serial_clean}"
        try:
            response = requests.get(url_station, headers=headers, timeout=5)
            if response.status_code == 200:
                html = response.text
                match = re.search(r'href="/titles/[A-Za-z]+/\d+/">([^<]+)</a>', html)
                if match:
                    title = match.group(1).strip()
                    if title and "serial" not in title.lower():
                        return title
        except Exception as e:
            print(f"SerialStation lookup failed for {serial_clean}: {e}")
            
        # 2. Try RPCS3 compatibility (PS3 specific: BLES, BLUS, NPUB, NPEB, BCUS, BCJS, BCAS, BLJM, NPJA, NPJH)
        is_ps3_serial = any(serial_clean.startswith(prefix) for prefix in ["BLES", "BLUS", "NPUB", "NPEB", "BCUS", "BCJS", "BCAS", "BLJM", "NPJA", "NPJH"])
        if is_ps3_serial:
            url_rpcs3 = f"https://rpcs3.net/compatibility?g={serial_clean}"
            try:
                response = requests.get(url_rpcs3, headers=headers, timeout=5)
                if response.status_code == 200:
                    html = response.text
                    match = re.search(r'class="game_title">([^<]+)</td>', html)
                    if match:
                        return match.group(1).strip()
            except Exception as e:
                print(f"RPCS3 lookup failed for {serial_clean}: {e}")
                
        return None

    def fetch_game_details(self, title):
        if not requests:
            return None
            
        # Detect and resolve game serial codes if present
        serial_match = re.search(r'([A-Z]{3,4})[-_]?([0-9]{4,5})', title.upper())
        if serial_match:
            prefix, num = serial_match.groups()
            serial_code = f"{prefix}-{num}"
            resolved = self.resolve_serial_to_title(serial_code)
            if resolved:
                print(f"Successfully resolved serial '{serial_code}' to game title: '{resolved}'")
                title = resolved
                
        # Clean title for searching
        clean_title = re.sub(r'\[.*?\]|\(.*?\)', '', title).strip()
        
        # Check cache first
        cache_key = clean_title.lower()
        if cache_key in self.config_manager.igdb_cache:
            return self.config_manager.igdb_cache[cache_key]

        if not self.authenticate():
            return None

        url = "https://api.igdb.com/v4/games"
        headers = {
            "Client-ID": self.client_id,
            "Authorization": f"Bearer {self.access_token}"
        }
        
        # Safe escape title
        escaped_title = clean_title.replace('"', '\\"')
        body = f'search "{escaped_title}"; fields name, cover.image_id, involved_companies.company.name, involved_companies.developer, first_release_date, summary, genres.name; limit 10;'
        
        try:
            response = requests.post(url, headers=headers, data=body, timeout=5)
            if response.status_code == 200:
                results = response.json()
                if results and isinstance(results, list):
                    # Smart matching logic: search for exact case-insensitive match
                    selected_game = results[0]
                    target_clean = clean_title.lower()
                    for game in results:
                        if not isinstance(game, dict):
                            continue
                        g_name = game.get("name", "").lower()
                        # Clean name of brackets/parentheses too
                        g_clean = re.sub(r'\[.*?\]|\(.*?\)', '', g_name).strip()
                        if g_clean == target_clean:
                            selected_game = game
                            break
                    
                    game_data = selected_game
                    
                    # Extract developer safely
                    developer = "Unknown Developer"
                    companies = game_data.get("involved_companies")
                    if isinstance(companies, list):
                        for company_wrapper in companies:
                            if isinstance(company_wrapper, dict) and company_wrapper.get("developer", False):
                                company = company_wrapper.get("company")
                                if isinstance(company, dict):
                                    developer = company.get("name", "Unknown Developer")
                                    break
                    
                    # Format release date
                    release_date = "N/A"
                    if "first_release_date" in game_data:
                        try:
                            release_date = datetime.fromtimestamp(game_data["first_release_date"]).strftime('%Y-%m-%d')
                        except:
                            pass
                    
                    # Format genres safely
                    genres = []
                    genre_list = game_data.get("genres")
                    if isinstance(genre_list, list):
                        for g in genre_list:
                            if isinstance(g, dict) and "name" in g:
                                genres.append(g["name"])
                    
                    # Safe cover extraction
                    cover_data = game_data.get("cover")
                    cover_id = ""
                    if isinstance(cover_data, dict):
                        cover_id = cover_data.get("image_id", "")
                    
                    details = {
                        "name": game_data.get("name", clean_title),
                        "cover_image_id": cover_id,
                        "developer": developer,
                        "release_date": release_date,
                        "summary": game_data.get("summary", "No description available."),
                        "genres": genres
                    }
                    
                    # Store in cache
                    self.config_manager.igdb_cache[cache_key] = details
                    self.config_manager.save_igdb_cache()
                    return details
        except Exception as e:
            print(f"IGDB API query failed for '{clean_title}': {e}")
        return None

    def download_cover(self, image_id, dest_path):
        if not requests or not image_id:
            return False
        # t_720p or t_cover_big
        url = f"https://images.igdb.com/igdb/image/upload/t_720p/{image_id}.jpg"
        try:
            response = requests.get(url, stream=True, timeout=10)
            if response.status_code == 200:
                with open(dest_path, 'wb') as f:
                    shutil.copyfileobj(response.raw, f)
                return True
        except Exception as e:
            print(f"Error downloading cover {image_id}: {e}")
        return False
