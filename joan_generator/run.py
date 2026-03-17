import os
import json
import logging
import requests
from flask import Flask, render_template, request, send_file, Response
from pathlib import Path
import io
from datetime import datetime, timedelta

# Configure logging **before** first use
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# Application Initialization
logger.info("Initializing Joan 6 Generator app...")
app = Flask(__name__)

def safe_int(val, default):
    if val is None:
        return default
    s = str(val).strip().lower()
    if not s or s == 'undefined' or s == 'none':
        return default
    try:
        # Handle cases like "12.0" or "undefined"
        return int(float(s))
    except (ValueError, TypeError):
        return default

# -------------------------------------------------------------------------
# API AND TOKEN CONFIGURATION
# -------------------------------------------------------------------------
TOKEN = os.environ.get('SUPERVISOR_TOKEN')
API_URL = "http://supervisor/core/api"
SUPERVISOR_URL = "http://supervisor"
TOKEN_SOURCE = "System (Supervisor)"

# AppDaemon Slug (configurable: env APPDAEMON_SLUG or options.json)
APPDAEMON_SLUG = os.environ.get('APPDAEMON_SLUG', "a0d7b954_appdaemon")

try:
    options_path = '/data/options.json'
    if os.path.exists(options_path):
        with open(options_path, 'r') as f:
            options = json.load(f)
            manual_token = options.get('manual_token')
            if manual_token and len(manual_token) > 10:
                TOKEN = manual_token
                API_URL = "http://homeassistant:8123/api"
                TOKEN_SOURCE = "Manual (Konfiguracja)"
                print(f"🔧 Manual token detected. Switching API to: {API_URL}")
                print(f"🔑 Token loaded (starts with: {TOKEN[:10]}...)")
            opt_slug = options.get('appdaemon_slug')
            if opt_slug:
                APPDAEMON_SLUG = opt_slug
except Exception as e:
    logger.info(f"Could not read options file: {e}")

if not TOKEN:
    logger.warning("No authorization token! Entity list will be empty.")

# -------------------------------------------------------------------------
# FETCHING DATA FROM HOME ASSISTANT
# -------------------------------------------------------------------------
def get_ha_areas_and_map():
    """
    Fetches Area Registry and Entity Registry data using HA Template API.
    Returns:
        areas (list): List of area objects {id, name}
        entity_map (dict): Mapping of entity_id -> area_id
    """
    if not TOKEN:
        return [], {}
        
    headers = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
    
    # Template to fetch areas and entity mapping in one go
    template_str = """
    {
        "areas": [
            {%- for area_id in areas() %}
            {
                "id": "{{ area_id }}",
                "name": "{{ area_name(area_id) }}"
            },
            {%- endfor %}
            null
        ],
        "entity_map": {
            {%- for state in states %}
            "{{ state.entity_id }}": "{{ area_id(state.entity_id) or '' }}",
            {%- endfor %}
            "_end": null
        }
    }
    """
    
    try:
        # Try primary API_URL first
        response = requests.post(
            f"{API_URL}/template", 
            headers=headers, 
            json={"template": template_str}, 
            timeout=10
        )
        if response.status_code == 200:
            result = response.json()
            if result:
                 # Remove null terminators used for valid JSON trailing comma handling
                areas = [a for a in result.get('areas', []) if a]
                entity_map = {k: v for k, v in result.get('entity_map', {}).items() if k != "_end"}
                return areas, entity_map
        else:
            # Fallback to direct container access if supervisor proxy fails
            logger.warning(f"Primary /template API failed ({response.status_code}), trying fallback...")
            try:
                snippet = (response.text or "")[:500]
                if snippet:
                    logger.warning(f"Template API response (first 500 chars): {snippet}")
            except Exception:
                pass
            fallback_url = "http://homeassistant:8123/api/template"
            res2 = requests.post(fallback_url, headers=headers, json={"template": template_str}, timeout=10)
            if res2.status_code == 200:
                result = res2.json()
                if result:
                    areas = [a for a in result.get('areas', []) if a]
                    entity_map = {k: v for k, v in result.get('entity_map', {}).items() if k != "_end"}
                    return areas, entity_map
    except Exception as e:
        logger.error(f"Exception while fetching areas: {e}", exc_info=True)
        try:
            if 'response' in dir() and response is not None and getattr(response, 'text', None):
                logger.warning(f"Response text (first 500 chars): {response.text[:500]}")
        except Exception:
            pass
    return [], {}

def get_ha_entities():
    if not TOKEN:
        return {'entities': [], 'areas': []} # Changed return structure to include areas
        
    headers = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
    
    # Fetch Areas and Map first
    areas, entity_area_map = get_ha_areas_and_map()
    
    try:
        response = requests.get(f"{API_URL}/states", headers=headers, timeout=10)
        
        # Fallback if primary fails
        if response.status_code != 200:
            logger.warning(f"Primary /states API failed ({response.status_code}), trying fallback...")
            response = requests.get("http://homeassistant:8123/api/states", headers=headers, timeout=10)
            
        if response.status_code == 200:
            data = response.json()
            entities = []
            for state in data:
                attributes = state.get('attributes', {})
                unit = attributes.get('unit_of_measurement', '')
                e_id = state['entity_id']
                
                # Get Area ID from map
                area_id = entity_area_map.get(e_id)
                
                entity_obj = {
                    'id': e_id,
                    'area_id': area_id, # Added area_id
                    'state': state['state'],
                    'attributes': {
                        'friendly_name': attributes.get('friendly_name', e_id),
                        'device_class': attributes.get('device_class', ''),
                        'unit_of_measurement': unit
                    },
                    'unit': unit
                }
                entities.append(entity_obj)
            entities.sort(key=lambda x: x['id'])
            
            # Return both entities and areas
            return {'entities': entities, 'areas': areas}
    except Exception as e:
        logger.error(f"Exception while fetching entities: {e}", exc_info=True)
        
    return {'entities': [], 'areas': []}

# -------------------------------------------------------------------------
# .DASH FILE SAVE FUNCTION
# -------------------------------------------------------------------------
def save_dash_file(filename, content):
    """
    WARNING: In Home Assistant Supervisor, add-ons run in isolated Docker containers.
    Direct saving to another add-on's directory is not possible without specific configuration.
    
    This function informs the user they must save the file manually.
    """
    network_path = f"\\\\[HA_IP]\\addon_configs\\{APPDAEMON_SLUG}\\dashboards\\{filename}"
    unix_path = f"/addon_configs/{APPDAEMON_SLUG}/dashboards/{filename}"
    
    message = (
        f"⚠️ DIRECT SAVE NOT POSSIBLE\n\n"
        f"Home Assistant add-ons run in isolated Docker containers. "
        f"Saving files directly to another add-on's directory is not possible without specific configuration.\n\n"
        f"Save the file manually:\n"
        f"• Via Samba: {network_path}\n"
        f"• Via SSH: {unix_path}\n\n"
        f"Or copy the generated code and save it manually."
    )
    
    print(f"⚠️ {message}")
    return False, message

# -------------------------------------------------------------------------
# APPDAEMON RESTART FUNCTION
# -------------------------------------------------------------------------
def restart_appdaemon_addon():
    """Restarts AppDaemon using available token (Manual or System)."""
    if not TOKEN:
        return False, "Błąd: Brak tokena API (uzupełnij manual_token w konfiguracji)."

    target_slug = APPDAEMON_SLUG
    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json"
    }

    if "homeassistant" in API_URL or "8123" in API_URL:
        url = f"{API_URL}/services/hassio/addon_restart"
        payload = {"addon": target_slug}
        print(f"🔄 Restarting via Service Call (Manual Token): {url}")
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=30)
        except Exception as e:
            print(f"❌ Connection exception: {e}")
            return False, str(e)
    else:
        url = f"http://supervisor/addons/{target_slug}/restart"
        print(f"🔄 Restarting via Supervisor API: {url}")
        try:
            response = requests.post(url, headers=headers, timeout=30)
        except Exception as e:
            print(f"❌ Connection exception: {e}")
            return False, str(e)

    if response.status_code in [200, 201, 202]:
        print("✅ Restart successful.")
        return True, "AppDaemon restarted."
    else:
        print(f"❌ API Error: {response.status_code} - {response.text}")
        return False, f"API Error: {response.status_code} {response.text}"

# -------------------------------------------------------------------------
# CHECK HISTORY COMPONENT
# -------------------------------------------------------------------------
def check_history_active():
    """Checks if the history component is active in Home Assistant config."""
    if not TOKEN:
        return False
    try:
        headers = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
        url = f"{API_URL}/config"
        res = requests.get(url, headers=headers, timeout=5)
        if res.status_code != 200:
            res = requests.get("http://homeassistant:8123/api/config", headers=headers, timeout=5)
        if res.status_code == 200:
            data = res.json()
            components = data.get("components", [])
            return "history" in components
    except Exception as e:
        logger.error(f"Error checking history active: {e}", exc_info=True)
    return False

# -------------------------------------------------------------------------
# APPDAEMON API BRIDGE FUNCTIONS (Direct Save)
# -------------------------------------------------------------------------
def check_appdaemon_bridge():
    """Checks if dash_saver.py script is installed and active in AppDaemon."""
    host = APPDAEMON_SLUG.replace('_', '-')
    paths = ["/api/save_dash", "/api/appdaemon/save_dash"]
    
    for path in paths:
        url = f"http://{host}:5050{path}"
        print(f"🔍 Checking path: {url}")
        try:
            response = requests.get(url, timeout=3)
            if response.status_code in [200, 405]:
                print(f"✅ AppDaemon bridge detected at: {url}")
                # Save working path in global variable for save function
                global ACTIVE_BRIDGE_PATH
                ACTIVE_BRIDGE_PATH = path
                return True
            else:
                print(f"ℹ️ Path {path} returned status: {response.status_code}")
        except Exception as e:
            print(f"❌ Error for path {path}: {e}")
    
    return False

ACTIVE_BRIDGE_PATH = "/api/save_dash" # Fallback

def save_dash_file_via_api(filename, content):
    """Sends file to AppDaemon by trying various possible API paths."""
    host = APPDAEMON_SLUG.replace('_', '-')
    paths = ["/api/appdaemon/save_dash", "/api/save_dash"]
    
    last_error = "Nieznany błąd"
    for path in paths:
        url = f"http://{host}:5050{path}"
        payload = {"filename": filename, "content": content}
        
        print(f"🚀 Attempting to upload dashboard to: {url}")
        try:
            headers = {"Content-Type": "application/json"}
            if TOKEN:
                 headers["Authorization"] = f"Bearer {TOKEN}"

            response = requests.post(url, json=payload, headers=headers, timeout=10)
            
            if response.status_code == 200:
                return True, f"Success: File {filename} saved!"
            
            last_error = f"Status {response.status_code}: {response.text}"
            print(f"ℹ️ Path {path} did not work ({last_error})")
        except Exception as e:
            last_error = str(e)
            print(f"❌ Connection error with path {path}: {e}")

    return False, f"Save error (tried all paths). Last error: {last_error}"

def list_dashboards_via_api():
    """Lists available dashboard files from AppDaemon via dash_saver bridge."""
    host = APPDAEMON_SLUG.replace('_', '-')
    paths = ["/api/appdaemon/list_dir", "/api/list_dir"]
    
    for path in paths:
        url = f"http://{host}:5050{path}"
        payload = {"path": "dashboards"}
        
        print(f"📂 Attempting to list dashboards from: {url}")
        try:
            headers = {"Content-Type": "application/json"}
            if TOKEN:
                headers["Authorization"] = f"Bearer {TOKEN}"

            response = requests.post(url, json=payload, headers=headers, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                if data.get("status") == "success":
                    # Filter only .dash files
                    items = data.get("items", [])
                    dash_files = [item for item in items if item.get("name", "").endswith(".dash")]
                    return True, dash_files
            
            print(f"ℹ️ Path {path} returned: {response.status_code}")
        except Exception as e:
            print(f"❌ Error listing dashboards from {path}: {e}")
    
    return False, []

def read_dashboard_via_api(filename):
    """Reads dashboard content from AppDaemon via dash_saver bridge."""
    host = APPDAEMON_SLUG.replace('_', '-')
    paths = ["/api/appdaemon/read_file", "/api/read_file"]
    
    for path in paths:
        url = f"http://{host}:5050{path}"
        payload = {"path": f"dashboards/{filename}"}
        
        print(f"📖 Attempting to read dashboard from: {url}")
        try:
            headers = {"Content-Type": "application/json"}
            if TOKEN:
                headers["Authorization"] = f"Bearer {TOKEN}"

            response = requests.post(url, json=payload, headers=headers, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                if data.get("status") == "success":
                    return True, data.get("content", "")
            
            print(f"ℹ️ Path {path} returned: {response.status_code}")
        except Exception as e:
            print(f"❌ Error reading dashboard from {path}: {e}")
    
    return False, ""

# -------------------------------------------------------------------------
# ENTITY FREQUENCY ANALYZER
# -------------------------------------------------------------------------
def get_entity_frequency(entity_id, hours=24):
    """
    Fetches entity state history for the last X hours and calculates update frequency.
    Returns: {'changes_per_hour': float, 'total_changes': int, 'level': 'ok'|'warning'|'danger'}
    """
    if not TOKEN:
        return {'error': 'Brak tokena API', 'changes_per_hour': 0, 'total_changes': 0, 'level': 'unknown'}
    
    from datetime import datetime, timedelta
    
    # Calculate start timestamp (X hours ago)
    end_time = datetime.utcnow()
    start_time = end_time - timedelta(hours=hours)
    start_iso = start_time.strftime('%Y-%m-%dT%H:%M:%SZ')
    
    headers = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
    
    try:
        # HA History API endpoint
        url = f"{API_URL}/history/period/{start_iso}?filter_entity_id={entity_id}&minimal_response"
        response = requests.get(url, headers=headers, timeout=15)
        
        if response.status_code == 200:
            data = response.json()
            if data and len(data) > 0 and len(data[0]) > 0:
                history = data[0]
                total_changes = len(history) - 1  # -1 because first entry is initial state
                if total_changes < 0:
                    total_changes = 0
                
                changes_per_hour = total_changes / hours if hours > 0 else 0
                
                # Warning levels (relaxed thresholds)
                # < 10/h = OK
                # 10-60/h = Warning (every 1-6 min)
                # > 60/h = Danger (more frequent than every minute)
                if changes_per_hour > 60:
                    level = 'danger'
                elif changes_per_hour > 10:
                    level = 'warning'
                else:
                    level = 'ok'
                
                return {
                    'entity_id': entity_id,
                    'changes_per_hour': round(changes_per_hour, 2),
                    'total_changes': total_changes,
                    'hours_analyzed': hours,
                    'level': level
                }
            else:
                # No history - new entity or no changes
                return {
                    'entity_id': entity_id,
                    'changes_per_hour': 0,
                    'total_changes': 0,
                    'hours_analyzed': hours,
                    'level': 'ok'
                }
        else:
            print(f"❌ History API Error: {response.status_code}")
            return {'error': f'API error: {response.status_code}', 'changes_per_hour': 0, 'total_changes': 0, 'level': 'unknown'}
    except Exception as e:
        print(f"❌ Exception during frequency analysis: {e}")
        return {'error': str(e), 'changes_per_hour': 0, 'total_changes': 0, 'level': 'unknown'}



# 3. STYLES (E-INK OPTIMIZED & TWEAKED)
# -------------------------------------------------------------------------
STYLE_TITLE = "color: #000000 !important; font-size: 20px; font-weight: 700; text-align: center; padding-top: 5px; width: 100%; font-family: 'Roboto', 'Arial Black', sans-serif"
STYLE_WIDGET = "color: #000000 !important; background-color: #FFFFFF !important"
STYLE_TEXT = "color: #000000 !important; font-weight: 700 !important"
STYLE_VALUE_TEMPLATE = "color: #000000 !important; font-size: {px}px !important; font-weight: 700 !important; padding-top: 60px !important; line-height: 1.1 !important; display: inline-block !important"
STYLE_GAUGE_VALUE = "color: #000000 !important; font-size: 30px !important; font-weight: 700 !important; line-height: 1.1 !important; display: inline-block !important"
STYLE_UNIT = "color: #000000 !important; padding-top: 60px !important; display: inline-block !important"
STYLE_ICON = "color: #000000 !important"
STYLE_STATE_TEXT = "color: #000000 !important; font-weight: 700 !important; font-size: 16px !important"
STYLE_TITLE2 = "color: #000000 !important; font-size: 16px; font-weight: 700; text-align: center; width: 100%; font-family: 'Roboto', 'Arial Black', sans-serif"
STYLE_TITLE_SMALL = "color: #000000 !important; font-size: 16px; font-weight: 700; text-align: center; padding-top: 5px; width: 100%; font-family: 'Roboto', 'Arial Black', sans-serif"

def build_value_style(size_hint: str, is_small: bool = False, custom_px: str = None) -> str:
    """
    Returns style for value based on hint or custom px.
    """
    if custom_px and str(custom_px).strip():
        try:
            px = int(custom_px)
        except:
            px = 34 if is_small else 54
    elif is_small:
        px = 34
    else:
        px = {
            "normal": 54,
            "medium": 40,
            "small": 32
        }.get(size_hint, 54)
    return STYLE_VALUE_TEMPLATE.format(px=px)

def build_title_style(is_small: bool = False, custom_px: str = None) -> str:
    """
    Returns style for title with custom px if provided.
    """
    base_style = STYLE_TITLE_SMALL if is_small else STYLE_TITLE
    if custom_px and str(custom_px).strip():
        import re
        return re.sub(r'font-size: \d+px', f'font-size: {custom_px}px', base_style)
    return base_style

def pick_auto_size(value_size_hint: str, entity_id: str, entities_map: dict) -> str:
    """
    If hint == 'auto', selects size based on current entity state:
      >10000  -> small (40px)
      >1000   -> medium (48px)
      length <= 3 -> large (110px)
      else    -> normal (54px)
    If number parsing fails, falls back to text length:
      len>9 -> small, len>6 -> medium, len<=3 -> large, otherwise normal.
    """
    if value_size_hint != "auto":
        return value_size_hint

    ent = entities_map.get(entity_id)
    if ent:
        raw = str(ent.get("state", "")).replace(",", ".").strip()
        length = len(raw)
        try:
            val = float(raw)
            if abs(val) > 10000:
                return "small"
            if abs(val) > 1000:
                return "medium"
            if length <= 3:
                return "large"
            return "normal"
        except Exception:
            pass
        if length > 9:
            return "small"
        if length > 6:
            return "medium"
        if length <= 3:
            return "large"
    return "normal"

# ICON FORMAT NORMALIZATION
# -------------------------------------------------------------------------
def normalize_icon_format(icon_name):
    if not icon_name:
        return icon_name
    icon_name = icon_name.strip()
    if icon_name.startswith('mdi:'):
        return 'mdi-' + icon_name[4:]
    if icon_name.startswith('mdi-'):
        return icon_name
    return icon_name

# YAML GENERATION LOGIC
# -------------------------------------------------------------------------
def get_real_entity(w_id: str) -> str:
    """
    Removes _copyX suffix from widget ID to get real entity ID.
    E.g. sensor.temp_copy1 -> sensor.temp
    """
    import re
    return re.sub(r'_copy\d+$', '', w_id)

def generate_joan_dash_yaml(rows, title, grid_params, lang_code, custom_defs, entities_map, device_profile='joan_6', auto_nav_bar=False, available_dash_files=None):
    if available_dash_files is None:
        available_dash_files = []

    TRANS = {
        'pl': {
            'on': 'WŁĄCZONE', 'off': 'WYŁĄCZONE',
            'open': 'OTWARTE', 'closed': 'ZAMKNIĘTE',
            'opening': 'OTWIERANIE', 'closing': 'ZAMYKANIE',
            'locked': 'ZAMKNIĘTE', 'unlocked': 'OTWARTE',
            'home': 'W DOMU', 'not_home': 'POZA',
            'cover_open': 'OTWARTA', 'cover_closed': 'ZAMKNIĘTA'
        },
        'en': {
            'on': 'ON', 'off': 'OFF',
            'open': 'OPEN', 'closed': 'CLOSED',
            'opening': 'OPENING', 'closing': 'CLOSING',
            'locked': 'LOCKED', 'unlocked': 'UNLOCKED',
            'home': 'HOME', 'not_home': 'AWAY'
        }
    }
    dic = TRANS.get(lang_code, TRANS['pl'])

    ad_columns = grid_params['cols'] * grid_params['def_w']

    # device profile settings
    is_pro = (device_profile == 'joan_13_pro')

    if is_pro:
        style_title = "color: #000000 !important; font-size: 32px; font-weight: 700; text-align: center; padding-top: 5px; width: 100%; font-family: 'Roboto', 'Arial Black', sans-serif"
        style_title2 = "color: #000000 !important; font-size: 24px; font-weight: 700; text-align: center; width: 100%; font-family: 'Roboto', 'Arial Black', sans-serif"
        style_title_small = "color: #000000 !important; font-size: 24px; font-weight: 700; text-align: center; padding-top: 5px; width: 100%; font-family: 'Roboto', 'Arial Black', sans-serif"
        
        style_widget = "color: #000000 !important; background-color: #FFFFFF !important"
        style_text = "color: #000000 !important; font-weight: 700 !important; font-size: 28px !important"
        style_state_text = "color: #000000 !important; font-weight: 700 !important; font-size: 28px !important"
        
        style_gauge_val = "color: #000000 !important; font-size: 54px !important; font-weight: 700 !important; line-height: 1.1 !important; display: inline-block !important"
        style_unit = "color: #000000 !important; padding-top: 90px !important; display: inline-block !important; font-size: 30px;"
        style_icon = "color: #000000 !important; font-size: 90px;"
    else:
        style_title = "color: #000000 !important; font-size: 20px; font-weight: 700; text-align: center; padding-top: 5px; width: 100%; font-family: 'Roboto', 'Arial Black', sans-serif"
        style_title2 = "color: #000000 !important; font-size: 16px; font-weight: 700; text-align: center; width: 100%; font-family: 'Roboto', 'Arial Black', sans-serif"
        style_title_small = "color: #000000 !important; font-size: 16px; font-weight: 700; text-align: center; padding-top: 5px; width: 100%; font-family: 'Roboto', 'Arial Black', sans-serif"
        
        style_widget = "color: #000000 !important; background-color: #FFFFFF !important"
        style_text = "color: #000000 !important; font-weight: 700 !important"
        style_state_text = "color: #000000 !important; font-weight: 700 !important; font-size: 16px !important"
        
        style_gauge_val = "color: #000000 !important; font-size: 30px !important; font-weight: 700 !important; line-height: 1.1 !important; display: inline-block !important"
        style_unit = "color: #000000 !important; padding-top: 60px !important; display: inline-block !important"
        style_icon = "color: #000000 !important"

    # dynamic value/title helpers inside
    def build_val_style_local(size_hint, is_small_w, custom_px):
        if custom_px and str(custom_px).strip():
            try:
                px = int(custom_px)
            except:
                px = (60 if is_pro else 34) if is_small_w else (90 if is_pro else 54)
        else:
            if size_hint == 'small': px = 50 if is_pro else 34
            elif size_hint == 'large': px = 110 if is_pro else 64
            else: px = 90 if is_pro else 54
        tmpl = f"color: #000000 !important; font-size: {{px}}px !important; font-weight: 700 !important; padding-top: 60px !important; line-height: 1.1 !important; display: inline-block !important"
        return tmpl.format(px=px)

    def build_title_style_local(is_small_w, custom_px):
        base_style = style_title_small if is_small_w else style_title
        if custom_px and str(custom_px).strip():
            import re
            return re.sub(r'font-size: \d+px', f'font-size: {custom_px}px', base_style)
        return base_style

    output = []
    output.append(f"# Joan Dashboard: {title}")
    output.append(f"# Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    output.append(f"# Model: {'Joan 13 Pro' if is_pro else 'Joan 6'}")
    output.append("")
    output.append(f"title: {title}")
    dims = "[188, 192]" if is_pro else "[117, 123]"
    margins = "[13, 6]" if is_pro else "[8, 4]"
    output.append(f"widget_dimensions: {dims}")
    output.append(f"widget_size: [{grid_params['def_w']}, {grid_params['def_h']}]")
    output.append(f"widget_margins: {margins}")
    output.append(f"columns: {ad_columns}")
    output.append(f"rows: {grid_params['rows_grid']}")
    output.append("global_parameters:")
    output.append("  use_comma: 0")
    output.append("  precision: 1")
    output.append("  use_hass_icon: 1")
    output.append("  namespace: default")
    output.append("  devices:")
    output.append("    media_player:")
    output.append("      step: 5")
    output.append("    climate:")
    output.append("      step: 1")
    output.append(f"  title_style: \"{style_title}\"")
    output.append(f"  title2_style: \"{style_title2}\"")
    output.append(f"  white_text_style: \"{style_text}\"")
    output.append(f"  state_text_style: \"{style_state_text}\"")
    output.append(f"  text_style: \"{style_text}\"")
    output.append(f"  level_style: \"{style_text}\"")
    output.append(f"  unit_style: \"{style_text}\"")
    output.append(f"  value_style: \"{style_text}\"")
    output.append(f"  icon_style_active: \"{style_icon}\"")
    output.append(f"  icon_style_inactive: \"{style_icon}; opacity: 0.5;\"")
    output.append(f"  artist_style: \"{style_text}\"")
    output.append(f"  album_style: \"{style_text}\"")
    output.append(f"  media_title_style: \"{style_text}\"")
    output.append("skin: simplyred")
    output.append("")

    try:
        processed_widgets = []

        if rows:
            output.append("layout:")
            # Removed automated navigation inject to prevent overriding user layout

            for row in rows:
                if not row:
                    continue
                row_parts = []
                max_h = 1
                for w in row:
                    h = grid_params['def_h']
                    size_str = w.get('size', '')
                    if size_str:
                        import re
                        m = re.search(r'x(\d+)', size_str)
                        if m:
                            h = int(m.group(1))
                    if h > max_h:
                        max_h = h

                    if w['type'] == 'spacer':
                        row_parts.append("spacer")
                        continue

                    widget_id = w['id']
                    is_default = False

                    if size_str == f"({grid_params['def_w']}x{grid_params['def_h']})":
                        is_default = True
                    elif size_str == "(2x1)" and grid_params['def_w'] == 2 and grid_params['def_h'] == 1:
                        is_default = True
                    elif size_str == "(1x1)" and grid_params['def_w'] == 1 and grid_params['def_h'] == 1:
                        is_default = True

                    if not is_default and size_str:
                        if not size_str.startswith('('):
                            size_str = f"({size_str})"
                        widget_id += size_str

                    if not widget_id: continue
                    row_parts.append(widget_id)
                    processed_widgets.append(w)
                if row_parts:
                    output.append(f"  - {', '.join(row_parts)}")
                    for _ in range(max_h - 1):
                        output.append("  -")

            output.append("")
            output.append("# -------------------")
            output.append("# WIDGET DEFINITIONS")
            output.append("# -------------------")
            output.append("")

            seen_ids = set()

            for w in processed_widgets:
                w_id = w.get('id', '')
                if not w_id or w_id in seen_ids:
                    continue
                seen_ids.add(w_id)
                real_entity_id = get_real_entity(w_id)

                if w_id in custom_defs and not w.get('was_edited', False):
                    output.append(f"{w_id}:")
                    for line in custom_defs[w_id].split('\n'):
                        line_stripped = line.strip()
                        if line_stripped:
                            if is_pro:
                                # Auto-upgrade standard 6-inch sizes to 13-inch sizes for imported legacy widgets
                                if 'font-size: 20px' in line: line = line.replace('font-size: 20px', 'font-size: 32px')
                                elif 'font-size: 16px' in line: line = line.replace('font-size: 16px', 'font-size: 24px')
                                elif 'font-size: 54px' in line: line = line.replace('font-size: 54px', 'font-size: 90px')
                                elif 'font-size: 34px' in line: line = line.replace('font-size: 34px', 'font-size: 60px')
                                # Ensure icons get scaled if missing font-size
                                if ('icon_style' in line or 'icon_active_style' in line or 'icon_inactive_style' in line):
                                    if 'font-size' not in line:
                                        line = line.replace('!important"', '!important; font-size: 90px;"')
                            output.append(f"  {line}")
                    output.append("")
                    continue

                w_type = w['type']
                w_name = w['name']

                # Common property extraction for all widgets
                is_small = (w.get('size') == '(1x1)' or w.get('size') == '(1x2)')
                t_size_custom = w.get('title_size_custom')
                v_size_custom = w.get('value_size_custom')

                w_icon = normalize_icon_format(w.get('icon'))
                i_on = normalize_icon_format(w.get('icon_on'))
                i_off = normalize_icon_format(w.get('icon_off'))
                value_size_hint = w.get('value_size_hint', 'auto')
                # Calculate real hint (auto -> medium/small/normal based on state)
                final_size_hint = pick_auto_size(value_size_hint, real_entity_id, entities_map)
                
                output.append(f"{w_id}:")

                w_title2 = w.get('title2', '')

                if w_type == 'navigate':
                    dash_name = w.get('dash', w_id.replace('navigate.', ''))
                    nav_icon = w_icon or 'mdi-arrow-right-circle'
                    output.append(f"  widget_type: navigate")
                    output.append(f"  title: \"{w_name}\"")
                    output.append(f"  dashboard: {dash_name}")
                    output.append(f"  icon_active: {nav_icon}")
                    output.append(f"  icon_inactive: {nav_icon}")
                    output.append(f"  title_style: \"{build_title_style_local(is_small, t_size_custom)}\"")
                    output.append(f"  widget_style: \"{style_widget}\"")
                    output.append(f"  icon_active_style: \"{style_icon}\"")
                    output.append(f"  icon_inactive_style: \"{style_icon}\"")

                elif w_type == 'switch':
                    output.append(f"  widget_type: switch")
                    output.append(f"  entity: {real_entity_id}")
                    output.append(f"  title: \"{w_name}\"")
                    if w_title2:
                        output.append(f"  title2: \"{w_title2}\"")
                        output.append(f"  title2_style: \"{style_title2}\"")
                    if i_on: output.append(f"  icon_on: {i_on}")
                    if i_off: output.append(f"  icon_off: {i_off}")
                    if w_icon and not i_on:
                        output.append(f"  icon: {w_icon}")
                        output.append(f"  icon_on: {w_icon}")
                        output.append(f"  icon_off: {w_icon}")
                    
                    st_enabled = w.get('state_text_enabled', True)
                    if str(st_enabled).lower() == 'false' or st_enabled is False:
                        output.append(f"  state_text_style: \"display: none !important;\"")
                        output.append(f"  value_style: \"display: none !important;\"")
                    else:
                        output.append(f"  state_text: 1")
                        v_size_custom = w.get('value_size_custom')
                        output.append(f"  value_style: \"{build_val_style_local(final_size_hint, is_small, v_size_custom)}\"")
                    
                    t_size_custom = w.get('title_size_custom')
                    output.append(f"  title_style: \"{build_title_style_local(is_small, t_size_custom)}\"")
                    output.append(f"  widget_style: \"{style_widget}\"")
                    output.append(f"  icon_style_active: \"{style_icon}\"")
                    output.append(f"  icon_style_inactive: \"{style_icon}; opacity: 0.5;\"")
                    output.append("  state_map:")
                    output.append(f"    \"on\": \"{dic['on']}\"")
                    output.append(f"    \"off\": \"{dic['off']}\"")

                elif w_type == 'sensor':
                    output.append(f"  widget_type: sensor")
                    output.append(f"  entity: {real_entity_id}")
                    output.append(f"  title: \"{w_name}\"")
                    if w_title2:
                        output.append(f"  title2: \"{w_title2}\"")
                        output.append(f"  title2_style: \"{style_title2}\"")
                    if w_icon:
                        output.append(f"  icon: {w_icon}")

                    output.append(f"  title_style: \"{build_title_style_local(is_small, t_size_custom)}\"")
                    output.append(f"  text_style: \"{style_text}\"")
                    output.append(f"  value_style: \"{build_val_style_local(final_size_hint, is_small, v_size_custom)}\"")
                    output.append(f"  unit_style: \"{style_unit}\"")
                    output.append(f"  widget_style: \"{style_widget}\"")
                    if any(k in w_id for k in ['battery', 'bateria', 'level']):
                        output.append("  precision: 0")
                    else:
                        output.append("  precision: 1")

                elif w_type == 'media_player':
                    output.append(f"  widget_type: media_player")
                    output.append(f"  entity: {real_entity_id}")
                    output.append(f"  title: \"{w_name}\"")

                    if w_icon:
                        output.append(f"  icon: {w_icon}")
                    output.append(f"  title_style: \"{build_title_style_local(is_small, t_size_custom)}\"")
                    output.append(f"  widget_style: \"{style_widget}\"")
                    output.append(f"  icon_style: \"{style_icon}\"")
                    output.append("  truncate_name: 20")
                    output.append("  step: 5")

                elif w_type == 'climate':
                    output.append(f"  widget_type: climate")
                    output.append(f"  entity: {real_entity_id}")
                    output.append(f"  title: \"{w_name}\"")

                    output.append(f"  step: 1")
                    output.append(f"  precision: 1")
                    output.append(f"  title_style: \"{build_title_style_local(is_small, t_size_custom)}\"")
                    output.append(f"  widget_style: \"{style_widget}\"")
                    output.append(f"  icon_style_active: \"{style_icon}\"")
                    output.append(f"  icon_style_inactive: \"{style_icon}; opacity: 0.5;\"")
                    output.append(f"  icon_style: \"{style_icon}\"")

                elif w_type == 'fan':
                    output.append(f"  widget_type: fan")
                    # Use percentage values for modern HA fan API
                    output.append("  low_speed: 33")
                    output.append("  medium_speed: 66")
                    output.append("  high_speed: 100")
                    output.append(f"  entity: {real_entity_id}")
                    output.append(f"  title: \"{w_name}\"")
                    # Configure service to use fan.set_percentage
                    output.append("  post_service_speed:")
                    output.append("    service: fan/set_percentage")
                    output.append(f"    entity_id: {real_entity_id}")
                    output.append("  post_service_active:")
                    output.append("    service: fan/turn_on")
                    output.append(f"    entity_id: {real_entity_id}")
                    output.append("  post_service_inactive:")
                    output.append("    service: fan/turn_off")
                    output.append(f"    entity_id: {real_entity_id}")

                    if i_on: output.append(f"  icon_on: {i_on}")
                    if i_off: output.append(f"  icon_off: {i_off}")
                    if w_icon and not i_on:
                        output.append(f"  icon: {w_icon}")
                        output.append(f"  icon_on: {w_icon}")
                        output.append(f"  icon_off: {w_icon}")

                    output.append(f"  title_style: \"{build_title_style_local(is_small, t_size_custom)}\"")
                    output.append(f"  widget_style: \"{style_widget}\"")
                    output.append(f"  container_style: \"{style_widget}\"")
                    output.append(f"  icon_style_active: \"{style_icon}\"")
                    output.append(f"  icon_style_inactive: \"{style_icon}; opacity: 0.5;\"")
                    # Speed button styles
                    output.append(f"  speed1_style_active: \"{style_icon}\"")
                    output.append(f"  speed1_style_inactive: \"{style_icon}; opacity: 0.3;\"")
                    output.append(f"  speed2_style_active: \"{style_icon}\"")
                    output.append(f"  speed2_style_inactive: \"{style_icon}; opacity: 0.3;\"")
                    output.append(f"  speed3_style_active: \"{style_icon}\"")
                    output.append(f"  speed3_style_inactive: \"{style_icon}; opacity: 0.3;\"")
                    # Speed button icons
                    output.append("  icon1_active: mdi-fan-speed-1")
                    output.append("  icon1_inactive: mdi-fan-speed-1")
                    output.append("  icon2_active: mdi-fan-speed-2")
                    output.append("  icon2_inactive: mdi-fan-speed-2")
                    output.append("  icon3_active: mdi-fan-speed-3")
                    output.append("  icon3_inactive: mdi-fan-speed-3")

                elif w_type == 'scene':
                    output.append(f"  widget_type: scene")
                    output.append(f"  entity: {real_entity_id}")
                    output.append(f"  title: \"{w_name}\"")

                    if w_icon: output.append(f"  icon: {w_icon}")
                    elif i_on: output.append(f"  icon: {i_on}")

                    output.append(f"  title_style: \"{build_title_style_local(is_small, t_size_custom)}\"")
                    output.append(f"  widget_style: \"{style_widget}\"")
                    output.append(f"  icon_style_active: \"{style_icon}\"")
                    output.append(f"  icon_style_inactive: \"{style_icon}\"")

                elif w_type == 'clock':
                    output.append(f"  widget_type: clock")
                    output.append(f"  time_format: 24hr")
                    output.append(f"  show_seconds: 0")
                    output.append(f"  date_style: \"{style_text}\"")
                    output.append(f"  time_style: \"{build_val_style_local('normal', False, 54)}\"")

                elif w_type == 'gauge':
                    output.append(f"  widget_type: gauge")
                    output.append(f"  entity: {real_entity_id}")
                    output.append(f"  title: \"{w_name}\"")

                    
                    g_min = w.get('min', '').strip()
                    g_max = w.get('max', '').strip()
                    if not g_min: g_min = "0"
                    if not g_max: g_max = "100"

                    output.append(f"  min: {g_min}")
                    output.append(f"  max: {g_max}")
                    output.append(f"  low_color: \"#000000\"")
                    output.append(f"  med_color: \"#000000\"")
                    output.append(f"  high_color: \"#000000\"")
                    output.append(f"  title_style: \"{build_title_style_local(is_small, t_size_custom)}\"")
                    output.append(f"  widget_style: \"{style_widget}\"")
                    output.append(f"  value_style: \"{style_gauge_val}\"")
                    
                    # Try to fetch unit from map
                    unit = ""
                    if w_id in entities_map:
                        unit = entities_map[w_id].get('attributes', {}).get('unit_of_measurement', '') or entities_map[w_id].get('unit', '')
                    
                    if unit:
                        output.append(f"  units: \"{unit}\"")
                        
                    output.append(f"  unit_style: \"{style_unit}\"")

                elif w_type == 'light':
                    output.append(f"  widget_type: light")
                    output.append(f"  entity: {real_entity_id}")
                    output.append(f"  title: \"{w_name}\"")
                    if w_title2:
                        output.append(f"  title2: \"{w_title2}\"")
                        output.append(f"  title2_style: \"{style_title2}\"")

                    if i_on: output.append(f"  icon_on: {i_on}")
                    if i_off: output.append(f"  icon_off: {i_off}")
                    if w_icon and not i_on:
                        output.append(f"  icon: {w_icon}")
                        output.append(f"  icon_on: {w_icon}")
                        output.append(f"  icon_off: {w_icon}")
                    output.append(f"  title_style: \"{style_title}\"")
                    output.append(f"  widget_style: \"{style_widget}\"")
                    output.append(f"  icon_style_inactive: \"{style_icon}; opacity: 0.5;\"")
                    
                    st_enabled = w.get('state_text_enabled', True)
                    if str(st_enabled).lower() == 'false' or st_enabled is False:
                        output.append(f"  state_text_style: \"display: none !important;\"")
                        output.append(f"  value_style: \"display: none !important;\"")
                    else:
                        output.append(f"  state_text: 1")
                        v_size_custom = w.get('value_size_custom')
                        output.append(f"  value_style: \"{build_val_style_local(final_size_hint, is_small, v_size_custom)}\"")
                    output.append("  state_map:")
                    output.append(f"    \"on\": \"{dic['on']}\"")
                    output.append(f"    \"off\": \"{dic['off']}\"")

                elif w_type == 'group':
                    output.append(f"  widget_type: group")
                    output.append(f"  entity: {real_entity_id}")
                    output.append(f"  title: \"{w_name}\"")

                    if i_on: output.append(f"  icon_on: {i_on}")
                    if i_off: output.append(f"  icon_off: {i_off}")
                    if w_icon and not i_on:
                        output.append(f"  icon: {w_icon}")
                        output.append(f"  icon_on: {w_icon}")
                        output.append(f"  icon_off: {w_icon}")
                    t_size_custom = w.get('title_size_custom')
                    output.append(f"  title_style: \"{build_title_style_local(is_small, t_size_custom)}\"")
                    if w_title2:
                        output.append(f"  title2: \"{w_title2}\"")
                        output.append(f"  title2_style: \"{style_title2}\"")
                    output.append(f"  widget_style: \"{style_widget}\"")
                    output.append(f"  icon_style_active: \"{style_icon}\"")
                    output.append(f"  icon_style_inactive: \"{style_icon}; opacity: 0.5;\"")
                    
                    st_enabled = w.get('state_text_enabled', True)
                    if str(st_enabled).lower() == 'false' or st_enabled is False:
                        output.append(f"  state_text_style: \"display: none !important;\"")
                        output.append(f"  value_style: \"display: none !important;\"")
                    else:
                        output.append(f"  state_text: 1")
                        v_size_custom = w.get('value_size_custom')
                        output.append(f"  value_style: \"{build_val_style_local(final_size_hint, is_small, v_size_custom)}\"")
                    output.append("  state_map:")
                    output.append(f"    \"on\": \"{dic['on']}\"")
                    output.append(f"    \"off\": \"{dic['off']}\"")

                elif w_type == 'input_boolean':
                    output.append(f"  widget_type: input_boolean")
                    output.append(f"  entity: {real_entity_id}")
                    output.append(f"  title: \"{w_name}\"")

                    if i_on: output.append(f"  icon_on: {i_on}")
                    if i_off: output.append(f"  icon_off: {i_off}")
                    if w_icon and not i_on:
                        output.append(f"  icon: {w_icon}")
                        output.append(f"  icon_on: {w_icon}")
                        output.append(f"  icon_off: {w_icon}")
                    
                    st_enabled = w.get('state_text_enabled', True)
                    if str(st_enabled).lower() == 'false' or st_enabled is False:
                        output.append(f"  state_text_style: \"display: none !important;\"")
                        output.append(f"  value_style: \"display: none !important;\"")
                    else:
                        output.append(f"  state_text: 1")
                        v_size_custom = w.get('value_size_custom')
                        output.append(f"  value_style: \"{build_val_style_local(final_size_hint, is_small, v_size_custom)}\"")
                    output.append(f"  title_style: \"{style_title}\"")
                    output.append(f"  widget_style: \"{style_widget}\"")
                    output.append(f"  icon_style_active: \"{style_icon}\"")
                    output.append(f"  icon_style_inactive: \"{style_icon}; opacity: 0.5;\"")
                    output.append("  state_map:")
                    output.append(f"    \"on\": \"{dic['on']}\"")
                    output.append(f"    \"off\": \"{dic['off']}\"")

                elif w_type == 'person':
                    output.append(f"  widget_type: person")
                    output.append(f"  entity: {real_entity_id}")
                    output.append(f"  title: \"{w_name}\"")

                    if i_on: output.append(f"  icon_on: {i_on}")
                    if i_off: output.append(f"  icon_off: {i_off}")
                    if w_icon and not i_on: output.append(f"  icon: {w_icon}")
                    
                    # Robust check for state_text_enabled
                    st_enabled = w.get('state_text_enabled', True)
                    if str(st_enabled).lower() == 'false' or st_enabled is False:
                        output.append(f"  state_text_style: \"display: none !important;\"")
                        output.append(f"  value_style: \"display: none !important;\"")
                    else:
                        output.append(f"  state_text: 1")
                        v_size_custom = w.get('value_size_custom')
                        output.append(f"  value_style: \"{build_val_style_local(final_size_hint, is_small, v_size_custom)}\"")
                    output.append(f"  title_style: \"{style_title}\"")
                    output.append(f"  widget_style: \"{style_widget}\"")
                    output.append(f"  icon_style_active: \"{style_icon}\"")
                    output.append(f"  icon_style_inactive: \"{style_icon}; opacity: 0.5;\"")
                    output.append("  state_map:")
                    output.append(f"    \"home\": \"{dic['home']}\"")
                    output.append(f"    \"not_home\": \"{dic['not_home']}\"")

                elif w_type == 'lock':
                    output.append(f"  widget_type: lock")
                    output.append(f"  entity: {real_entity_id}")
                    output.append(f"  title: \"{w_name}\"")

                    if i_on: output.append(f"  icon_on: {i_on}")
                    if i_off: output.append(f"  icon_off: {i_off}")
                    if w_icon and not i_on:
                        output.append(f"  icon: {w_icon}")
                        output.append(f"  icon_on: {w_icon}")
                        output.append(f"  icon_off: {w_icon}")
                    
                    # Robust check for state_text_enabled
                    st_enabled = w.get('state_text_enabled', True)
                    if str(st_enabled).lower() == 'false' or st_enabled is False:
                        output.append(f"  state_text_style: \"display: none !important;\"")
                        output.append(f"  value_style: \"display: none !important;\"")
                    else:
                        output.append(f"  state_text: 1")
                        v_size_custom = w.get('value_size_custom')
                        output.append(f"  value_style: \"{build_val_style_local(final_size_hint, is_small, v_size_custom)}\"")
                    output.append(f"  title_style: \"{style_title}\"")
                    output.append(f"  widget_style: \"{style_widget}\"")
                    output.append(f"  icon_style_active: \"{style_icon}\"")
                    output.append(f"  icon_style_inactive: \"{style_icon}; opacity: 0.5;\"")
                    output.append("  state_map:")
                    output.append(f"    \"locked\": \"{dic['locked']}\"")
                    output.append(f"    \"unlocked\": \"{dic['unlocked']}\"")

                elif w_type == 'cover':
                    output.append(f"  widget_type: cover")
                    output.append(f"  entity: {real_entity_id}")
                    output.append(f"  title: \"{w_name}\"")
                    if i_on: output.append(f"  icon_on: {i_on}")
                    if i_off: output.append(f"  icon_off: {i_off}")
                    if w_icon and not i_on:
                        output.append(f"  icon: {w_icon}")
                        output.append(f"  icon_on: {w_icon}")
                        output.append(f"  icon_off: {w_icon}")
                    output.append(f"  title_style: \"{build_title_style_local(is_small, t_size_custom)}\"")
                    output.append(f"  widget_style: \"{style_widget}\"")
                    output.append(f"  icon_style_active: \"{style_icon}\"")
                    output.append(f"  icon_style_inactive: \"{style_icon}; opacity: 0.5;\"")
                    
                    st_enabled = w.get('state_text_enabled', True)
                    if str(st_enabled).lower() == 'false' or st_enabled is False:
                        output.append(f"  state_text_style: \"display: none !important;\"")
                        output.append(f"  value_style: \"display: none !important;\"")
                    else:
                        output.append(f"  state_text: 1")

                        output.append(f"  value_style: \"{build_val_style_local(final_size_hint, is_small, v_size_custom)}\"")
                    output.append("  state_map:")
                    output.append(f"    \"open\": \"{dic.get('cover_open', dic['open'])}\"")
                    output.append(f"    \"closed\": \"{dic.get('cover_closed', dic['closed'])}\"")
                    output.append(f"    \"opening\": \"{dic['opening']}\"")
                    output.append(f"    \"closing\": \"{dic['closing']}\"")

                elif w_type == 'reload':
                    output.append(f"  widget_type: reload")
                    output.append(f"  title: \"{w_name}\"")
                    if w_icon: output.append(f"  icon_active: {w_icon}")
                    elif i_on: output.append(f"  icon_active: {i_on}")
                    else: output.append(f"  icon_active: mdi-refresh")
                    output.append(f"  title_style: \"{build_title_style_local(is_small, t_size_custom)}\"")
                    output.append(f"  widget_style: \"{style_widget}\"")
                    output.append(f"  icon_active_style: \"{style_icon}\"")
                    output.append(f"  icon_inactive_style: \"{style_icon}; opacity: 0.5;\"")

                elif w_type == 'input_number':
                    output.append(f"  widget_type: input_number")
                    output.append(f"  entity: {real_entity_id}")
                    output.append(f"  title: \"{w_name}\"")

                    
                    # Fetch units from entity if available
                    unit = ""
                    if real_entity_id in entities_map:
                        unit = entities_map[real_entity_id].get('attributes', {}).get('unit_of_measurement', '') or entities_map[real_entity_id].get('unit', '')
                    if unit:
                        output.append(f"  units: \"{unit}\"")
                    
                    output.append(f"  title_style: \"{build_title_style_local(is_small, t_size_custom)}\"")
                    output.append(f"  widget_style: \"{style_widget}\"")
                    output.append(f"  value_style: \"color: #000000 !important; font-size: 24px !important; font-weight: 700 !important;\"")
                    output.append(f"  slider_style: \"background-color: #cccccc !important;\"")
                    output.append(f"  slidercontainer_style: \"background-color: #ffffff !important;\"")

                elif w_type == 'input_slider':
                    output.append(f"  widget_type: input_slider")
                    output.append(f"  entity: {real_entity_id}")
                    output.append(f"  title: \"{w_name}\"")

                    # Fetch units from entity if available
                    unit = ""
                    if real_entity_id in entities_map:
                        unit = entities_map[real_entity_id].get('attributes', {}).get('unit_of_measurement', '') or entities_map[real_entity_id].get('unit', '')
                    if unit:
                        output.append(f"  units: \"{unit}\"")

                    output.append(f"  title_style: \"{build_title_style_local(is_small, t_size_custom)}\"")
                    output.append(f"  widget_style: \"{style_widget}\"")
                    output.append(f"  value_style: \"color: #000000 !important; font-size: 28px !important; font-weight: 700 !important; text-align: center !important;\"")
                    output.append(f"  minvalue_style: \"color: #000000 !important; font-size: 14px !important;\"")
                    output.append(f"  maxvalue_style: \"color: #000000 !important; font-size: 14px !important;\"")
                    output.append(f"  slider_style: \"color: #000000 !important; border: 2px solid #000000 !important;\"")
                    output.append(f"  slidercontainer_style: \"background-color: transparent !important;\"")

                elif w_type == 'input_select':
                    output.append(f"  widget_type: input_select")
                    output.append(f"  entity: {real_entity_id}")
                    output.append(f"  title: \"{w_name}\"")

                    output.append(f"  title_style: \"{build_title_style_local(is_small, t_size_custom)}\"")
                    output.append(f"  widget_style: \"{style_widget}\"")
                    output.append(f"  select_style: \"color: #000000 !important; font-size: 18px !important; background: #ffffff !important; border: 1px solid #999999 !important;\"")
                    output.append(f"  selectcontainer_style: \"background-color: #ffffff !important;\"")



                elif w_type == 'label':
                    output.append(f"  widget_type: label")
                    output.append(f"  text: \"{w_name}\"")
                    if w_title2:
                        output.append(f"  title2: \"{w_title2}\"")
                        output.append(f"  title2_style: \"{style_title2}\"")
                    if w_icon:
                        output.append(f"  icon: {w_icon}")
                    output.append(f"  text_style: \"{build_title_style_local(is_small, t_size_custom)}\"")

                else:
                    ad_type = w_type
                    if w_type == 'binary_sensor':
                        ad_type = 'binary_sensor'
                    if w_type == 'input_boolean':
                        ad_type = 'switch'
                    if w_type == 'person':
                        ad_type = 'device_tracker'
                    if w_type == 'light':
                        ad_type = 'switch'
                    if w_type == 'lock':
                        ad_type = 'lock'
                    if w_type == 'input_select':
                        ad_type = 'input_select'
                    if w_type == 'input_number':
                        ad_type = 'input_number'
                    if w_type == 'script':
                        ad_type = 'script'
                    if w_type == 'alarm':
                        ad_type = 'alarm'

                    output.append(f"  widget_type: {ad_type}")
                    output.append(f"  entity: {real_entity_id}")
                    output.append(f"  title: \"{w_name}\"")

                    if i_on: output.append(f"  icon_on: {i_on}")
                    if i_off: output.append(f"  icon_off: {i_off}")

                    if ad_type == 'lock':
                        if i_off: output.append(f"  icon_locked: {i_off}")
                        if i_on: output.append(f"  icon_unlocked: {i_on}")

                    if w_icon and not i_on:
                        output.append(f"  icon: {w_icon}")
                        # Fallback for all generic widgets (script, binary_sensor, etc)
                        output.append(f"  icon_on: {w_icon}")
                        output.append(f"  icon_off: {w_icon}")

                    # Robust check for state_text_enabled
                    st_enabled = w.get('state_text_enabled', True)
                    if str(st_enabled).lower() == 'false' or st_enabled is False:
                        output.append(f"  state_text_style: \"display: none !important;\"")
                        output.append(f"  value_style: \"display: none !important;\"")
                    else:
                        output.append(f"  state_text: 1")
                        v_size_custom = w.get('value_size_custom')
                        output.append(f"  value_style: \"{build_value_style(final_size_hint, is_small, v_size_custom)}\"")
                    
                    t_size_custom = w.get('title_size_custom')
                    output.append(f"  title_style: \"{build_title_style(is_small, t_size_custom)}\"")
                    output.append(f"  text_style: \"{STYLE_TEXT}\"")
                    output.append(f"  widget_style: \"{STYLE_WIDGET}\"")
                    output.append(f"  icon_style_active: \"{STYLE_ICON}\"")
                    output.append(f"  icon_style_inactive: \"{STYLE_ICON}\"")

                    if ad_type in ['cover', 'binary_sensor', 'switch', 'light', 'lock']:
                        output.append("  state_map:")
                        if ad_type == 'cover':
                            for s in ['open', 'closed', 'opening', 'closing']:
                                output.append(f"    \"{s}\": \"{dic.get(s, s)}\"")
                        elif ad_type == 'binary_sensor':
                            output.append(f"    \"on\": \"{dic['on']}\"")
                            output.append(f"    \"off\": \"{dic['off']}\"")
                        elif ad_type == 'lock':
                            output.append(f"    \"locked\": \"{dic['locked']}\"")
                            output.append(f"    \"unlocked\": \"{dic['unlocked']}\"")
                        else:
                            output.append(f"    \"on\": \"{dic['on']}\"")
                            output.append(f"    \"off\": \"{dic['off']}\"")

        if auto_nav_bar and available_dash_files:
            output.append("")
            output.append("# -------------------")
            output.append("# AUTO NAV BAR WIDGETS")
            output.append("# -------------------")
            output.append("")
            seen_navs = set(seen_ids)
            for dash_item in available_dash_files:
                dash_name = dash_item.get('name') if isinstance(dash_item, dict) else dash_item
                dash_slug = dash_name.replace('.dash', '')
                if dash_slug != title.lower().replace(' ', '_'):
                    nav_id = f"navigate.{dash_slug}"
                    if nav_id in seen_navs:
                        continue
                    seen_navs.add(nav_id)
                    nav_name = dash_slug.replace('_', ' ').title()
                    output.append(f"{nav_id}:")
                    output.append(f"  widget_type: navigate")
                    output.append(f"  title: \"{nav_name[:12]}\"")
                    output.append(f"  dashboard: {dash_slug}")
                    output.append(f"  icon_active: mdi-arrow-right-circle")
                    output.append(f"  icon_inactive: mdi-arrow-right-circle")
                    output.append(f"  title_style: \"{build_title_style_local(False, '')}\"")
                    output.append(f"  widget_style: \"{style_widget}\"")
                    output.append(f"  icon_active_style: \"{style_icon}\"")
                    output.append(f"  icon_inactive_style: \"{style_icon}\"")
                    output.append("")
    except Exception as e:
        print(f"❌ Error generating YAML: {e}")
        return f"# ERROR GENERATING YAML: {e}"

    return "\n".join(output)

# ROUTES
# -------------------------------------------------------------------------
@app.route('/', methods=['GET', 'POST'])
def index():
    generated_yaml = ""
    ha_data = get_ha_entities()
    ha_entities = ha_data.get('entities', [])
    ha_areas = ha_data.get('areas', [])
    entities_map = {e['id']: e for e in ha_entities}
    dashboard_filename = "joandashboard.dash"
    dashboard_slug = "joandashboard"
    has_token = bool(TOKEN)
    save_message = None


    bridge_active = check_appdaemon_bridge()
    has_dashboards = False
    available_dash_files = []
    if bridge_active:
        success, files = list_dashboards_via_api()
        if success and files:
            has_dashboards = True
            available_dash_files = files

    connection_info = {
        "token_source": TOKEN_SOURCE,
        "api_url": API_URL,
        "entity_count": len(ha_entities),
        "appdaemon_slug": APPDAEMON_SLUG,
        "bridge_active": bridge_active,
        "has_dashboards": has_dashboards
    }

    current_ui_lang = request.form.get('ui_language', 'pl') if request.method == 'POST' else request.args.get('lang', 'pl')

    if request.method == 'POST':
        action = request.form.get('action', 'generate')
        
        # Retrieving common data for most actions
        title = request.form.get('title', 'JoanDashboard')
        cols = safe_int(request.form.get('grid_columns'), 3)
        rows_grid = safe_int(request.form.get('grid_rows'), 8)
        def_size_str = request.form.get('default_widget_size', '2, 1')
        layout_json = request.form.get('layout_data_json', '[]')
        custom_defs_json = request.form.get('custom_definitions_json', '{}')
        lang = request.form.get('ui_language', 'pl')
        current_ui_lang = lang
        device_profile = request.form.get('device_profile', 'joan_6')
        auto_nav_bar = request.form.get('auto_nav_bar', 'false').lower() == 'true'
        dash_list_str = request.form.get('dashboards_list', '')
        available_dash_files = [d.strip() for d in dash_list_str.split(',') if d.strip()] if dash_list_str else []

        # Helper to preserve case sensitivity from existing files
        expected_slug = title.lower().replace(" ", "_").replace("ą", "a").replace("ć", "c").replace("ę", "e").replace("ł", "l").replace("ń", "n").replace("ó", "o").replace("ś", "s").replace("ź", "z").replace("ż", "z")
        expected_filename = expected_slug + ".dash"
        
        # Check against available files to preserve original camelCase/Capitalized filename
        dashboard_filename = expected_filename
        dashboard_slug = expected_slug
        for f in available_dash_files:
            fname = f.get('name', '') if isinstance(f, dict) else f
            if fname.lower() == expected_filename:
                dashboard_filename = fname
                dashboard_slug = fname.replace('.dash', '')
                break
        try:
            layout_data = json.loads(layout_json)
            custom_defs = json.loads(custom_defs_json)
            def_w, def_h = map(int, [x.strip() for x in def_size_str.split(',')])
            grid_params = {'cols': cols, 'rows_grid': rows_grid, 'def_w': def_w, 'def_h': def_h}
        except:
            layout_data = []
            custom_defs = {}
            grid_params = {'cols': 3, 'rows_grid': 8, 'def_w': 2, 'def_h': 1}

        if action == 'restart':
            success, msg = restart_appdaemon_addon()
            save_message = f"{'✅' if success else '❌'} {msg}"
            # Regenerate YAML so it doesn't disappear after page refresh on restart
            try:
                generated_yaml = generate_joan_dash_yaml(
                    layout_data, title, grid_params, lang, custom_defs, entities_map, device_profile, auto_nav_bar, available_dash_files
                )
            except Exception as e:
                generated_yaml = f"# ERROR REGENERATING: {e}"

        elif action == 'load_dashboard':
            filename = request.form.get('open_dashboard_name', '')
            if filename:
                success, content = read_dashboard_via_api(filename)
                if success:
                    generated_yaml = content
                    dashboard_filename = filename
                    save_message = f"✅ Dashboard wczytany: {filename}"
                else:
                    save_message = f"❌ Błąd odczytu pliku: {filename}"
            else:
                save_message = "❌ Nie podano nazwy pliku do odczytu."

        elif action == 'save_ad':
            try:
                generated_yaml = generate_joan_dash_yaml(
                    layout_data, title, grid_params, lang, custom_defs, entities_map, device_profile, auto_nav_bar, available_dash_files
                )
                success, msg = save_dash_file_via_api(dashboard_filename, generated_yaml)
                save_message = f"{'✅' if success else '❌'} {msg}"
            except Exception as e:
                save_message = f"❌ Save error: {e}"

        elif action == 'download_file':
            yaml_content = request.form.get('yaml_content', '')
            if yaml_content:
                file_obj = io.BytesIO(yaml_content.encode('utf-8'))
                return send_file(file_obj, mimetype='text/plain', as_attachment=True, download_name=dashboard_filename)
        
        else: # generate
            try:
                generated_yaml = generate_joan_dash_yaml(
                    layout_data, title, grid_params, lang, custom_defs, entities_map, device_profile, auto_nav_bar, available_dash_files
                )
            except Exception as e:
                print(f"❌ Error generating YAML: {e}")
                generated_yaml = f"# ERROR GENERATING YAML: {e}"

    return render_template(
        'index.html',
        generated_yaml=generated_yaml,
        entities=ha_entities,
        areas=ha_areas,
        filename=dashboard_filename,
        dash_name=dashboard_slug,
        has_token=has_token,
        save_message=save_message,
        connection_info=connection_info,
        current_lang=current_ui_lang,
        layout_data=layout_data if 'layout_data' in locals() else [],
        custom_defs=custom_defs if 'custom_defs' in locals() else {},
        title=title if 'title' in locals() else "JoanDashboard",
        cols=cols if 'cols' in locals() else 3,
        rows_grid=rows_grid if 'rows_grid' in locals() else 8,
        def_size=def_size_str if 'def_size_str' in locals() else "2, 1",
        dashboards_list=available_dash_files if 'available_dash_files' in locals() else [],
        device_profile=device_profile if 'device_profile' in locals() else 'joan_6',
        auto_nav_bar=auto_nav_bar if 'auto_nav_bar' in locals() else False
    )

# -------------------------------------------------------------------------
# API ENDPOINTS
# -------------------------------------------------------------------------
@app.route('/api/entity_frequency/<path:entity_id>')
def api_entity_frequency(entity_id):
    """Returns entity update frequency analysis (JSON)."""
    from flask import jsonify
    result = get_entity_frequency(entity_id, hours=24)
    return jsonify(result)

@app.route('/api/list_dashboards')
def api_list_dashboards():
    """Returns list of available dashboard files from AppDaemon (JSON)."""
    from flask import jsonify
    success, files = list_dashboards_via_api()
    if success:
        return jsonify({"status": "success", "files": files})
    else:
        return jsonify({"status": "error", "message": "Cannot list dashboards. Is dash_saver.py installed?", "files": []})

@app.route('/api/read_dashboard/<path:filename>')
def api_read_dashboard(filename):
    """Returns content of a dashboard file from AppDaemon (JSON)."""
    from flask import jsonify
    success, content = read_dashboard_via_api(filename)
    if success:
        return jsonify({"status": "success", "content": content, "filename": filename})
    else:
        return jsonify({"status": "error", "message": f"Cannot read dashboard: {filename}"})


if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000, debug=True)

