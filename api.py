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
        # Persistent HTTP session for connection pooling (reuses TCP/TLS)
        self._session = requests.Session() if requests else None
        self._cache_dirty = False

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
            response = self._session.post(url, params=params, timeout=8)
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
            response = self._session.get(url_station, headers=headers, timeout=4)
            if response.status_code == 200:
                html = response.text
                match = re.search(r'href="/titles/[A-Za-z]+/\d+/">([^<]+)</a>', html)
                if match:
                    title = match.group(1).strip()
                    if title and "serial" not in title.lower():
                        return title
        except Exception as e:
            print(f"SerialStation lookup failed for {serial_clean}: {e}")
            
        # 2. Try RPCS3 compatibility (PS3 specific)
        is_ps3_serial = any(serial_clean.startswith(prefix) for prefix in ["BLES", "BLUS", "NPUB", "NPEB", "BCUS", "BCJS", "BCAS", "BLJM", "NPJA", "NPJH"])
        if is_ps3_serial:
            url_rpcs3 = f"https://rpcs3.net/compatibility?g={serial_clean}"
            try:
                response = self._session.get(url_rpcs3, headers=headers, timeout=4)
                if response.status_code == 200:
                    html = response.text
                    match = re.search(r'class="game_title">([^<]+)</td>', html)
                    if match:
                        return match.group(1).strip()
            except Exception as e:
                print(f"RPCS3 lookup failed for {serial_clean}: {e}")
                
        return None

    # IGDB platform ID mapping for targeted search
    IGDB_PLATFORM_IDS = {
        "PC": [6],                    # PC (Microsoft Windows)
        "PlayStation 4": [48],        # PS4
        "PlayStation 3": [9],         # PS3
        "PlayStation 2": [8],         # PS2
        "PlayStation": [7],           # PS1
        "PSP": [38],                  # PSP
        "Nintendo Switch": [130],     # Switch
        "Wii": [5],                   # Wii
        "Wii U": [41],               # Wii U
        "GameCube": [21],             # GameCube
        "Nintendo 64": [4],           # N64
        "Super Nintendo": [19],       # SNES
        "NES": [18],                  # NES
        "Nintendo DS": [20],          # NDS
        "Nintendo 3DS": [37],         # 3DS
        "Game Boy Advance": [24],     # GBA
        "Game Boy Color": [22],       # GBC
        "Game Boy": [33],             # GB
        "Xbox": [11, 12, 49, 169],    # Xbox, Xbox 360, Xbox One, Xbox Series
    }

    def fetch_game_details(self, title, platform=None):
        if not requests:
            return None
            
        # 1. Aggressively clean the title first
        clean_title = re.sub(r'\[.*?\]|\(.*?\)', '', title).strip()
        clean_title = re.sub(r'\.(iso|pkg|cso|cue|bin|rom|sfb)$', '', clean_title, flags=re.IGNORECASE).strip()
        clean_title = clean_title.replace('_', ' ').strip()
        # Remove trademark/legal symbols that block API search
        clean_title = re.sub(r'[™®©℠]', '', clean_title).strip()
        # Remove trailing disc/version numbers like "- Disc 1" or "v1.02"
        clean_title = re.sub(r'\s*[-–]\s*Disc\s*\d+', '', clean_title, flags=re.IGNORECASE).strip()
        clean_title = re.sub(r'\s+v\d+\.\d+.*$', '', clean_title).strip()
        
        # 2. Only perform expensive serial lookups if the title is just a serial code
        is_probably_serial_only = bool(re.fullmatch(r'[A-Za-z]{3,4}[-_]?\d{4,5}', clean_title.replace(' ', '')))
        
        if len(clean_title) < 3 or is_probably_serial_only:
            serial_match = re.search(r'([A-Z]{3,4})[-_]?([0-9]{4,5})', title.upper())
            if serial_match:
                prefix, num = serial_match.groups()
                serial_code = f"{prefix}-{num}"
                resolved = self.resolve_serial_to_title(serial_code)
                if resolved:
                    print(f"Successfully resolved serial '{serial_code}' to game title: '{resolved}'")
                    clean_title = resolved
                    
        if not clean_title:
            clean_title = title
        
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
        
        # Build query: exclude DLCs/addons (category 0 = main game) and optionally filter by platform
        where_clauses = ["category = 0"]
        if platform and platform in self.IGDB_PLATFORM_IDS:
            plat_ids = self.IGDB_PLATFORM_IDS[platform]
            plat_str = ",".join(str(p) for p in plat_ids)
            where_clauses.append(f"platforms = ({plat_str})")
        
        where_str = " & ".join(where_clauses)
        body = f'search "{escaped_title}"; fields name, cover.image_id, involved_companies.company.name, involved_companies.developer, first_release_date, summary, genres.name, category; where {where_str}; limit 5;'
        
        try:
            response = self._session.post(url, headers=headers, data=body, timeout=8)
            if response.status_code == 200:
                results = response.json()
                
                # If platform filter returned no results, retry without platform filter
                if (not results or len(results) == 0) and platform and platform in self.IGDB_PLATFORM_IDS:
                    body_fallback = f'search "{escaped_title}"; fields name, cover.image_id, involved_companies.company.name, involved_companies.developer, first_release_date, summary, genres.name, category; where category = 0; limit 5;'
                    response = self._session.post(url, headers=headers, data=body_fallback, timeout=8)
                    if response.status_code == 200:
                        results = response.json()
                
                if results and isinstance(results, list):
                    # Smart matching: prefer exact case-insensitive match
                    selected_game = results[0]
                    target_clean = clean_title.lower()
                    for game in results:
                        if not isinstance(game, dict):
                            continue
                        g_name = game.get("name", "").lower()
                        g_clean = re.sub(r'\[.*?\]|\(.*?\)', '', g_name).strip()
                        # Also strip trademark symbols from IGDB result names
                        g_clean = re.sub(r'[™®©℠]', '', g_clean).strip()
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
                    
                    # Store in cache (batch-save later, not per-game)
                    self.config_manager.igdb_cache[cache_key] = details
                    self._cache_dirty = True
                    return details
            elif response.status_code == 429:
                # Rate limited — back off briefly
                print(f"IGDB rate limited, backing off...")
                time.sleep(0.5)
        except Exception as e:
            print(f"IGDB API query failed for '{clean_title}': {e}")
        return None

    # IGDB category enum -> human-readable name
    IGDB_CATEGORY_NAMES = {
        0: "Main Game",
        1: "DLC / Addon",
        2: "Expansion",
        3: "Bundle",
        4: "Standalone Expansion",
        5: "Mod",
        6: "Episode",
        7: "Season",
        8: "Remake",
        9: "Remaster",
        10: "Expanded Game",
        11: "Port",
        12: "Fork",
        13: "Pack",
        14: "Update",
    }

    def search_games_manual(self, query):
        """Returns a list of raw search results from IGDB for a user to choose from manually.
        NOTE: IGDB does not support combining 'search' with 'where' field-filters.
        We fetch all results and let the UI filter by category."""
        if not requests or not self.authenticate():
            return []

        url = "https://api.igdb.com/v4/games"
        headers = {
            "Client-ID": self.client_id,
            "Authorization": f"Bearer {self.access_token}"
        }

        escaped_title = query.replace('"', '\\"')
        # No 'where' clause — search + where on game fields is unsupported by IGDB
        body = (
            f'search "{escaped_title}"; '
            f'fields name, cover.image_id, involved_companies.company.name, '
            f'involved_companies.developer, first_release_date, summary, '
            f'genres.name, category, platforms.name; '
            f'limit 20;'
        )

        results_formatted = []
        try:
            response = self._session.post(url, headers=headers, data=body, timeout=10)
            print(f"[IGDB Manual Search] status={response.status_code} body={body!r}")
            if response.status_code == 200:
                results = response.json()
                if results and isinstance(results, list):
                    for game_data in results:
                        if not isinstance(game_data, dict):
                            continue

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
                                release_date = datetime.fromtimestamp(game_data["first_release_date"]).strftime('%b %d, %Y')
                            except Exception:
                                pass

                        # Extract platforms
                        plat_list = []
                        if "platforms" in game_data and isinstance(game_data["platforms"], list):
                            for p in game_data["platforms"]:
                                if isinstance(p, dict) and "name" in p:
                                    plat_list.append(p["name"])
                        plat_str = ", ".join(plat_list) if plat_list else "Unknown"

                        # Category (game type)
                        cat_id = game_data.get("category", 0)
                        cat_name = self.IGDB_CATEGORY_NAMES.get(cat_id, f"Type {cat_id}")

                        # Cover
                        cover_data = game_data.get("cover")
                        cover_id = cover_data.get("image_id", "") if isinstance(cover_data, dict) else ""

                        results_formatted.append({
                            "title": game_data.get("name", "Unknown Title"),
                            "cover_image_id": cover_id,
                            "developer": developer,
                            "release_date": release_date,
                            "summary": game_data.get("summary", "No description available."),
                            "platforms_str": plat_str,
                            "category_id": cat_id,
                            "category_name": cat_name,
                        })
            else:
                print(f"[IGDB Manual Search] Error response: {response.text}")
        except Exception as e:
            print(f"Error fetching manual search from IGDB: {e}")

        return results_formatted

    def flush_cache(self):
        """Batch-save the IGDB cache to disk. Call once after a batch of fetches."""
        if self._cache_dirty:
            self.config_manager.save_igdb_cache()
            self._cache_dirty = False

    def download_cover(self, image_id, dest_path):
        if not requests or not image_id:
            return False
        url = f"https://images.igdb.com/igdb/image/upload/t_720p/{image_id}.jpg"
        try:
            response = self._session.get(url, stream=True, timeout=10)
            if response.status_code == 200:
                with open(dest_path, 'wb') as f:
                    shutil.copyfileobj(response.raw, f)
                return True
        except Exception as e:
            print(f"Error downloading cover {image_id}: {e}")
        return False
