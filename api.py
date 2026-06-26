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
        "Xbox": [11],                 # Original Xbox
        "Xbox 360": [12],             # Xbox 360
        "Xbox One": [49],             # Xbox One
        "Sega Dreamcast": [23],       # Dreamcast
        "Sega Saturn": [32],          # Saturn
        "Sega Genesis": [29],         # Mega Drive / Genesis
        "Sega Master System": [64],   # Master System
        "Game Gear": [35],            # Game Gear
        "Sega 32X": [30],             # 32X
    }

    @staticmethod
    def _extract_igdb_score(game_data):
        """Return the most useful IGDB 0-100 score for display."""
        for key in ("aggregated_rating", "total_rating", "rating"):
            value = game_data.get(key)
            if isinstance(value, (int, float)) and value > 0:
                return round(float(value), 1)
        return None

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
        # Strip region / edition labels: (Europe), (USA), (Japan), (PAL), (Rev 1), etc.
        clean_title = re.sub(
            r'\s*[\(\[](Europe|USA|Japan|PAL|NTSC|World|En|Fr|De|Es|It|Nl|Pt|'
            r'Rev\s?\d*|v\d[\d\.]*|Beta|Demo|Proto|Sample|Promo|'
            r'Disc\s?\d+|CD\s?\d+|En,Fr,De|[A-Z]{2,3}(?:,[A-Z]{2,3})*)[\)\]]\s*',
            ' ', clean_title, flags=re.IGNORECASE
        ).strip()
        # Strip appended version strings like "-1.2.4.0-portable" or "-1.0-beta"
        clean_title = re.sub(r'\s*-\s*\d[\d\.]*-\S+$', '', clean_title, flags=re.IGNORECASE).strip()
        # Convert dots to spaces (but not between digits, e.g. "3.0" stays)
        # Handles cases like "DLSS.Swapper" -> "DLSS Swapper"
        clean_title = re.sub(r'(?<!\d)\.(?!\d)', ' ', clean_title).strip()
        # Split CamelCase — only when the entire title has NO spaces (compressed folder name)
        # e.g. "SaintsRowTheThird" -> "Saints Row The Third"
        # but "GoldenEye 007" stays untouched
        if ' ' not in clean_title:
            clean_title = re.sub(r'([a-z])([A-Z])', r'\1 \2', clean_title).strip()
        # Normalize multiple spaces created by the above transformations
        clean_title = re.sub(r'\s+', ' ', clean_title).strip()

        
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
        if platform:
            cache_key = f"{cache_key}_{platform.lower().strip()}"
            
        if cache_key in self.config_manager.igdb_cache:
            return self.config_manager.igdb_cache[cache_key]

        if not self.authenticate():
            return None

        url = "https://api.igdb.com/v4/games"
        headers = {
            "Client-ID": self.client_id,
            "Authorization": f"Bearer {self.access_token}"
        }
        
        # Resolve target platform IDs with normalized lookup
        target_platform_ids = []
        if platform:
            plat_lower = platform.lower().strip()
            for key, val in self.IGDB_PLATFORM_IDS.items():
                key_l = key.lower().strip()
                if (key_l == plat_lower or
                    (plat_lower in ["ps3", "playstation 3"] and key_l == "playstation 3") or
                    (plat_lower in ["ps2", "playstation 2"] and key_l == "playstation 2") or
                    (plat_lower in ["ps1", "psx", "playstation 1", "playstation"] and key_l == "playstation") or
                    (plat_lower in ["psp", "playstation portable"] and key_l == "psp") or
                    (plat_lower in ["snes", "super nintendo"] and key_l == "super nintendo") or
                    (plat_lower in ["nes", "nintendo entertainment system"] and key_l == "nes") or
                    (plat_lower in ["switch", "nintendo switch"] and key_l == "nintendo switch") or
                    (plat_lower in ["gc", "gamecube", "nintendo gamecube"] and key_l == "gamecube") or
                    (plat_lower in ["wii", "nintendo wii"] and key_l == "wii") or
                    (plat_lower in ["wiiu", "wii u"] and key_l == "wii u") or
                    (plat_lower in ["gba", "game boy advance"] and key_l == "game boy advance") or
                    (plat_lower in ["gbc", "game boy color"] and key_l == "game boy color") or
                    (plat_lower in ["gb", "game boy"] and key_l == "game boy") or
                    (plat_lower in ["ds", "nds", "nintendo ds"] and key_l == "nintendo ds") or
                    (plat_lower in ["3ds", "nintendo 3ds"] and key_l == "nintendo 3ds") or
                    (plat_lower in ["n64", "nintendo 64"] and key_l == "nintendo 64") or
                    (plat_lower in ["xbox360", "xbox 360", "x360"] and key_l == "xbox 360") or
                    (plat_lower in ["xbone", "xbox one"] and key_l == "xbox one") or
                    (plat_lower in ["xbox"] and key_l == "xbox")):
                    target_platform_ids = val
                    break

        # Safe escape title
        escaped_title = clean_title.replace('"', '\\"')
        
        # Build query variations to try
        search_targets = [clean_title]
        
        # Fallback to base title if it contains colons or hyphens
        base_title = None
        if ":" in clean_title:
            base_title = clean_title.split(":")[0].strip()
        elif " - " in clean_title:
            base_title = clean_title.split(" - ")[0].strip()
        elif "-" in clean_title:
            base_title = clean_title.split("-")[0].strip()
            
        if base_title and len(base_title) >= 3 and base_title.lower() != clean_title.lower():
            search_targets.append(base_title)
            
        results = None
        
        # We try to run the queries sequentially until we get a list of results
        for target in search_targets:
            escaped_target = target.replace('"', '\\"')
            
            # Query variations to try for this target
            queries_to_try = []
            
            # Build platform filter string
            plat_filter = None
            if target_platform_ids:
                plat_str = ",".join(str(p) for p in target_platform_ids)
                plat_filter = f"platforms = ({plat_str})"
            
            # Variation 1: Relaxed categories (Main, Remake, Remaster, Expanded, Port) + Platform filter
            where_clauses = ["category = (0, 8, 9, 10, 11)"]
            if plat_filter:
                where_clauses.append(plat_filter)
            queries_to_try.append(" & ".join(where_clauses))
            
            # Variation 2: Relaxed categories, NO platform filter
            queries_to_try.append("category = (0, 8, 9, 10, 11)")
            
            # Variation 3: Completely open search, NO category and NO platform filter
            queries_to_try.append(None)
            
            for where_str in queries_to_try:
                if where_str:
                    body = f'search "{escaped_target}"; fields name, cover.image_id, platforms, involved_companies.company.name, involved_companies.developer, first_release_date, summary, genres.name, category, rating, rating_count, aggregated_rating, aggregated_rating_count, total_rating, total_rating_count; where {where_str}; limit 50;'
                else:
                    body = f'search "{escaped_target}"; fields name, cover.image_id, platforms, involved_companies.company.name, involved_companies.developer, first_release_date, summary, genres.name, category, rating, rating_count, aggregated_rating, aggregated_rating_count, total_rating, total_rating_count; limit 50;'
                
                try:
                    response = self._session.post(url, headers=headers, data=body, timeout=8)
                    if response.status_code == 200:
                        res = response.json()
                        if res and isinstance(res, list) and len(res) > 0:
                            results = res
                            break
                    elif response.status_code == 429:
                        print("IGDB rate limited, backing off...")
                        time.sleep(0.5)
                except Exception as e:
                    print(f"IGDB API query variation failed for target '{target}' with where '{where_str}': {e}")
            
            if results:
                break
                
        if results and isinstance(results, list):
            # Smart matching: rank results based on keyword similarity and platform overlap
            def get_auto_match_score(game):
                if not isinstance(game, dict):
                    return 100
                g_name = game.get("name", "").lower().strip()
                q_name = clean_title.lower().strip()
                
                # Strip bracket metadata and trademark symbols for score comparison
                g_clean = re.sub(r'\[.*?\]|\(.*?\)', '', g_name).strip()
                g_clean = re.sub(r'[™®©℠]', '', g_clean).strip()
                
                if g_clean == q_name:
                    base_score = 0  # Exact match
                elif g_clean.startswith(q_name):
                    base_score = 1  # Prefix match
                else:
                    q_words = q_name.split()
                    g_words = g_clean.split()
                    if all(qw in g_words for qw in q_words):
                        base_score = 2  # Keyword match (all query words present)
                    elif q_name in g_clean:
                        base_score = 3  # Substring match
                    elif any(qw in g_clean for qw in q_words):
                        base_score = 4  # Partial match
                    else:
                        base_score = 5
                
                # Check platform match
                game_platforms = game.get("platforms", [])
                game_plat_ids = []
                if isinstance(game_platforms, list):
                    for gp in game_platforms:
                        if isinstance(gp, int):
                            game_plat_ids.append(gp)
                        elif isinstance(gp, dict) and "id" in gp:
                            game_plat_ids.append(gp["id"])
                
                has_plat_match = False
                if target_platform_ids and game_plat_ids:
                    has_plat_match = any(pid in target_platform_ids for pid in game_plat_ids)
                
                # Platform matching prioritization
                platform_priority = 0
                if target_platform_ids:
                    platform_priority = 0 if has_plat_match else 100
                    
                return base_score + platform_priority
                
            results.sort(key=get_auto_match_score)

            # Minimum quality gate: reject the top result if it has NO keyword overlap
            # with our query (base_score == 5). This prevents caching wrong matches
            # like "The Darkness" -> "Thief: The Dark Project".
            def _title_has_match(game):
                g_name = game.get("name", "").lower().strip()
                g_clean = re.sub(r'\[.*?\]|\(.*?\)', '', g_name).strip()
                g_clean = re.sub(r'[™®©℠]', '', g_clean).strip()
                q_name = clean_title.lower().strip()
                q_words = q_name.split()
                # Accept if any non-trivial query word appears in the game name
                stopwords = {'the', 'a', 'an', 'of', 'in', 'on', 'at', 'to', 'for', 'and', 'or'}
                significant_words = [w for w in q_words if w not in stopwords and len(w) > 1]
                if not significant_words:
                    return True  # Nothing meaningful to filter on
                return any(w in g_clean for w in significant_words)

            selected_game = None
            if target_platform_ids:
                for game in results:
                    game_platforms = game.get("platforms", [])
                    game_plat_ids = []
                    if isinstance(game_platforms, list):
                        for gp in game_platforms:
                            if isinstance(gp, int):
                                game_plat_ids.append(gp)
                            elif isinstance(gp, dict) and "id" in gp:
                                game_plat_ids.append(gp["id"])

                    if any(pid in target_platform_ids for pid in game_plat_ids):
                        if _title_has_match(game):
                            selected_game = game
                            break

                if not selected_game:
                    # No platform-exact match — fall back to best title-scored result
                    # that passes the minimum quality gate.
                    for game in results:
                        if _title_has_match(game):
                            print(f"[IGDB] No platform-exact match for '{clean_title}' on {platform} — using best title match.")
                            selected_game = game
                            break
            else:
                # No platform filter — pick best title match that passes quality gate
                for game in results:
                    if _title_has_match(game):
                        selected_game = game
                        break

            if not selected_game:
                # All results failed the quality gate — don't cache garbage
                return None
            
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
            
            igdb_score = self._extract_igdb_score(game_data)

            # Collect raw IGDB platform IDs so callers can auto-correct platform
            raw_game_plat_ids = []
            for gp in game_data.get("platforms", []):
                if isinstance(gp, int):
                    raw_game_plat_ids.append(gp)
                elif isinstance(gp, dict) and "id" in gp:
                    raw_game_plat_ids.append(gp["id"])
            
            details = {
                "name": game_data.get("name", clean_title),
                "cover_image_id": cover_id,
                "developer": developer,
                "release_date": release_date,
                "summary": game_data.get("summary", "No description available."),
                "genres": genres,
                "igdb_score": igdb_score,
                "igdb_rating_count": game_data.get("rating_count", 0),
                "igdb_aggregated_rating": game_data.get("aggregated_rating"),
                "igdb_aggregated_rating_count": game_data.get("aggregated_rating_count", 0),
                "igdb_total_rating": game_data.get("total_rating"),
                "igdb_total_rating_count": game_data.get("total_rating_count", 0),
                "igdb_platform_ids": raw_game_plat_ids,   # Raw IDs for platform correction
            }
            
            # Store in cache (batch-save later, not per-game)
            self.config_manager.igdb_cache[cache_key] = details
            self._cache_dirty = True
            return details
            
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
        We fetch up to 50 results and rank them by keyword relevance so that exact matches appear first."""
        if not requests or not self.authenticate():
            return []

        # 1. Resolve serial to title if the query is a serial code (e.g. BLES00513)
        clean_query = query.strip()
        is_probably_serial_only = bool(re.fullmatch(r'[A-Za-z]{3,4}[-_]?\d{4,5}', clean_query.replace(' ', '')))
        if is_probably_serial_only or len(clean_query) < 3:
            serial_match = re.search(r'([A-Z]{3,4})[-_]?([0-9]{4,5})', query.upper())
            if serial_match:
                prefix, num = serial_match.groups()
                serial_code = f"{prefix}-{num}"
                resolved = self.resolve_serial_to_title(serial_code)
                if resolved:
                    print(f"[IGDB Manual Search] Resolved serial '{serial_code}' to '{resolved}'")
                    query = resolved

        url = "https://api.igdb.com/v4/games"
        headers = {
            "Client-ID": self.client_id,
            "Authorization": f"Bearer {self.access_token}"
        }

        escaped_title = query.replace('"', '\\"')
        # Fetch up to 50 results for a broader list
        body = (
            f'search "{escaped_title}"; '
            f'fields name, cover.image_id, involved_companies.company.name, '
            f'involved_companies.developer, first_release_date, summary, '
            f'genres.name, category, platforms.name, rating, rating_count, '
            f'aggregated_rating, aggregated_rating_count, total_rating, total_rating_count; '
            f'limit 50;'
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
                            "igdb_score": self._extract_igdb_score(game_data),
                            "igdb_rating_count": game_data.get("rating_count", 0),
                            "igdb_aggregated_rating": game_data.get("aggregated_rating"),
                            "igdb_aggregated_rating_count": game_data.get("aggregated_rating_count", 0),
                            "igdb_total_rating": game_data.get("total_rating"),
                            "igdb_total_rating_count": game_data.get("total_rating_count", 0),
                        })
            else:
                print(f"[IGDB Manual Search] Error response: {response.text}")
        except Exception as e:
            print(f"Error fetching manual search from IGDB: {e}")

        # Smart ranking of keyword results
        def get_match_score(game_title):
            g_title = game_title.lower().strip()
            q_title = query.lower().strip()
            if g_title == q_title:
                return 0  # Exact match
            if g_title.startswith(q_title):
                return 1  # Prefix match
            q_words = q_title.split()
            g_words = g_title.split()
            if all(qw in g_words for qw in q_words):
                return 2  # Keyword match (all query words present)
            if q_title in g_title:
                return 3  # Substring match
            if any(qw in g_title for qw in q_words):
                return 4  # Partial match
            return 5

        results_formatted.sort(key=lambda x: get_match_score(x["title"]))
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

    def test_connection(self) -> tuple[bool, str]:
        """Tests the credentials and connection to Twitch and IGDB.
        Returns a tuple of (success_boolean, detail_string).
        """
        if not requests:
            return False, "Python 'requests' library is not installed."
        
        if not self.is_configured():
            return False, "Twitch Client ID and Client Secret are not configured."
            
        url = "https://id.twitch.tv/oauth2/token"
        params = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "grant_type": "client_credentials"
        }
        
        # Test Auth
        try:
            response = self._session.post(url, params=params, timeout=8)
            if response.status_code != 200:
                return False, f"Twitch OAuth Authentication failed with status code {response.status_code}: {response.text}"
            
            data = response.json()
            token = data.get("access_token")
            if not token:
                return False, f"Access token not found in Twitch response: {response.text}"
        except Exception as e:
            return False, f"Twitch Authentication connection error: {e}"
            
        # Test IGDB Query
        query_url = "https://api.igdb.com/v4/games"
        headers = {
            "Client-ID": self.client_id,
            "Authorization": f"Bearer {token}"
        }
        body = 'search "Super Mario Sunshine"; fields name; limit 1;'
        try:
            response = self._session.post(query_url, headers=headers, data=body, timeout=8)
            if response.status_code != 200:
                return False, f"IGDB API query failed with status code {response.status_code}: {response.text}"
            
            res = response.json()
            if not res or not isinstance(res, list) or len(res) == 0:
                return False, f"IGDB query returned unexpected or empty response: {response.text}"
            
            return True, f"Successfully authenticated and retrieved game '{res[0].get('name')}'."
        except Exception as e:
            return False, f"IGDB API connection error: {e}"
