import os
import json
import requests
from flask import Flask, render_template, request, send_file, Response
from pathlib import Path
import io

# Application Initialization
print("📦 1. Initializing Joan 6 Generator app (v1.5.0-HOTFIX-3)...", flush=True)
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
            opt_slug = options.get('appdaemon_slug')
            if opt_slug:
                APPDAEMON_SLUG = opt_slug
except Exception as e:
    print(f"ℹ️ Info: Could not read options file: {e}")

# -------------------------------------------------------------------------
# VISIONECT JOAN 6 CONFIGURATION
# -------------------------------------------------------------------------
VISIONECT_HOST = None
VISIONECT_API_KEY = None
VISIONECT_API_SECRET = None
DASHBOARD_BASE_URL = None

try:
    options_path = '/data/options.json'
    if os.path.exists(options_path):
        with open(options_path, 'r') as f:
            options = json.load(f)
            VISIONECT_HOST = options.get('visionect_host', '').strip() or None
            VISIONECT_API_KEY = options.get('visionect_api_key', '').strip() or None
            VISIONECT_API_SECRET = options.get('visionect_api_secret', '').strip() or None
            DASHBOARD_BASE_URL = options.get('dashboard_base_url', '').strip() or None
            if VISIONECT_HOST:
                print(f"🖥️ Visionect Server: {VISIONECT_HOST}")
            if DASHBOARD_BASE_URL:
                print(f"🔗 Dashboard Base URL: {DASHBOARD_BASE_URL}")
except Exception as e:
    print(f"ℹ️ Info: Could not read Visionect config: {e}")

if not TOKEN:
    print("❌ WARNING: No authorization token! Entity list will be empty.")

# -------------------------------------------------------------------------
# FETCHING DATA FROM HOME ASSISTANT
# -------------------------------------------------------------------------
def get_ha_entities():
    if not TOKEN:
        return []
    headers = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
    try:
        response = requests.get(f"{API_URL}/states", headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            entities = []
            for state in data:
                attributes = state.get('attributes', {})
                unit = attributes.get('unit_of_measurement', '')
                entity_obj = {
                    'id': state['entity_id'],
                    'state': state['state'],
                    'attributes': {
                        'friendly_name': attributes.get('friendly_name', state['entity_id']),
                        'device_class': attributes.get('device_class', ''),
                        'unit_of_measurement': unit
                    },
                    'unit': unit
                }
                entities.append(entity_obj)
            entities.sort(key=lambda x: x['id'])
            return entities
    except Exception as e:
        print(f"❌ Exception while fetching entities: {e}")
    return []

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
      else    -> normal (54px)
    If number parsing fails, falls back to text length:
      len>9 -> small, len>6 -> medium, otherwise normal.
    """
    if value_size_hint != "auto":
        return value_size_hint

    ent = entities_map.get(entity_id)
    if ent:
        raw = str(ent.get("state", "")).replace(",", ".").strip()
        try:
            val = float(raw)
            if abs(val) > 10000:
                return "small"
            if abs(val) > 1000:
                return "medium"
            return "normal"
        except Exception:
            pass
        length = len(raw)
        if length > 9:
            return "small"
        if length > 6:
            return "medium"
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

def generate_joan_dash_yaml(rows, title, grid_params, lang_code, custom_defs, entities_map):
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

    output = []
    output.append(f"title: {title}")
    output.append("widget_dimensions: [117, 123]")
    output.append(f"widget_size: [{grid_params['def_w']}, {grid_params['def_h']}]")
    output.append("widget_margins: [8, 4]")
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
    output.append(f"  title_style: \"{STYLE_TITLE}\"")
    output.append(f"  title2_style: \"{STYLE_TITLE2}\"")
    output.append(f"  white_text_style: \"{STYLE_TEXT}\"")
    output.append(f"  state_text_style: \"{STYLE_STATE_TEXT}\"")
    output.append(f"  text_style: \"{STYLE_TEXT}\"")
    output.append(f"  level_style: \"{STYLE_TEXT}\"")
    output.append(f"  unit_style: \"{STYLE_TEXT}\"")
    output.append(f"  value_style: \"{STYLE_TEXT}\"")
    output.append(f"  icon_style_active: \"{STYLE_ICON}\"")
    output.append(f"  icon_style_inactive: \"{STYLE_ICON}; opacity: 0.5;\"")
    output.append(f"  artist_style: \"{STYLE_TEXT}\"")
    output.append(f"  album_style: \"{STYLE_TEXT}\"")
    output.append(f"  media_title_style: \"{STYLE_TEXT}\"")
    output.append("skin: simplyred")
    output.append("")

    try:
        processed_widgets = []

        if rows:
            output.append("layout:")
            for row in rows:
                if not row:
                    continue
                row_parts = []
                for w in row:
                    if w['type'] == 'spacer':
                        row_parts.append("spacer")
                        continue

                    widget_id = w['id']
                    size_str = w.get('size', '')
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
                        if line.strip():
                            output.append(f"  {line}")
                    output.append("")
                    continue

                w_type = w['type']
                w_name = w['name']
                w_icon = normalize_icon_format(w.get('icon'))
                i_on = normalize_icon_format(w.get('icon_on'))
                i_off = normalize_icon_format(w.get('icon_off'))
                value_size_hint = w.get('value_size_hint', 'auto')
                # Calculate real hint (auto -> medium/small/normal based on state)
                final_size_hint = pick_auto_size(value_size_hint, real_entity_id, entities_map)

                output.append(f"{w_id}:")

                if w_type == 'navigate':
                    dash_name = w.get('dash', w_id.replace('navigate.', ''))
                    nav_icon = w_icon or 'mdi-arrow-right-circle'
                    output.append(f"  widget_type: navigate")
                    output.append(f"  title: \"{w_name}\"")
                    output.append(f"  dashboard: {dash_name}")
                    output.append(f"  icon_active: {nav_icon}")
                    output.append(f"  icon_inactive: {nav_icon}")
                    output.append(f"  title_style: \"{STYLE_TITLE}\"")
                    output.append(f"  widget_style: \"{STYLE_WIDGET}\"")
                    output.append(f"  icon_active_style: \"{STYLE_ICON}\"")
                    output.append(f"  icon_inactive_style: \"{STYLE_ICON}\"")

                elif w_type == 'switch':
                    is_small = (w.get('size') == '(1x1)' or w.get('size') == '(1x2)')
                    output.append(f"  widget_type: switch")
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
                    
                    t_size_custom = w.get('title_size_custom')
                    output.append(f"  title_style: \"{build_title_style(is_small, t_size_custom)}\"")
                    output.append(f"  widget_style: \"{STYLE_WIDGET}\"")
                    output.append(f"  icon_style_active: \"{STYLE_ICON}\"")
                    output.append(f"  icon_style_inactive: \"{STYLE_ICON}; opacity: 0.5;\"")
                    output.append("  state_map:")
                    output.append(f"    \"on\": \"{dic['on']}\"")
                    output.append(f"    \"off\": \"{dic['off']}\"")

                elif w_type == 'sensor':
                    output.append(f"  widget_type: sensor")
                    output.append(f"  entity: {real_entity_id}")
                    output.append(f"  title: \"{w_name}\"")
                    if w_icon:
                        output.append(f"  icon: {w_icon}")

                    is_small = (w.get('size') == '(1x1)' or w.get('size') == '(1x2)')
                    t_size_custom = w.get('title_size_custom')
                    v_size_custom = w.get('value_size_custom')
                    
                    output.append(f"  title_style: \"{build_title_style(is_small, t_size_custom)}\"")
                    output.append(f"  text_style: \"{STYLE_TEXT}\"")
                    output.append(f"  value_style: \"{build_value_style(final_size_hint, is_small, v_size_custom)}\"")
                    output.append(f"  unit_style: \"{STYLE_UNIT}\"")
                    output.append(f"  widget_style: \"{STYLE_WIDGET}\"")
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
                    output.append(f"  title_style: \"{STYLE_TITLE}\"")
                    output.append(f"  title2_style: \"{STYLE_TITLE}; font-size: 16px;\"")
                    output.append(f"  widget_style: \"{STYLE_WIDGET}\"")
                    output.append(f"  icon_style: \"{STYLE_ICON}\"")
                    output.append(f"  icon_style_active: \"{STYLE_ICON}\"")
                    output.append(f"  icon_style_inactive: \"{STYLE_ICON}; opacity: 0.5;\"")
                    output.append(f"  text_style: \"{STYLE_TEXT}\"")
                    output.append(f"  level_style: \"{STYLE_TEXT}; font-size: 16px;\"")
                    output.append(f"  units_style: \"{STYLE_TEXT}; font-size: 16px;\"")
                    output.append(f"  artist_style: \"{STYLE_TEXT}\"")
                    output.append(f"  media_title_style: \"{STYLE_TEXT}; font-weight: bold;\"")
                    output.append(f"  album_style: \"{STYLE_TEXT}\"")
                    output.append(f"  state_text_style: \"{STYLE_TEXT}\"")
                    output.append(f"  icon_up_style: \"{STYLE_ICON}\"")
                    output.append(f"  icon_down_style: \"{STYLE_ICON}\"")
                    output.append(f"  level_up_style: \"{STYLE_ICON}\"")
                    output.append(f"  level_down_style: \"{STYLE_ICON}\"")
                    output.append("  truncate_name: 20")
                    output.append("  step: 5")

                elif w_type == 'climate':
                    output.append(f"  widget_type: climate")
                    output.append(f"  entity: {real_entity_id}")
                    output.append(f"  title: \"{w_name}\"")

                    output.append(f"  step: 1")
                    output.append(f"  precision: 1")
                    output.append(f"  title_style: \"{STYLE_TITLE}\"")
                    output.append(f"  title2_style: \"{STYLE_TITLE}; font-size: 16px;\"")
                    output.append(f"  text_style: \"{STYLE_TEXT}\"")
                    output.append(f"  widget_style: \"{STYLE_WIDGET}\"")
                    output.append(f"  icon_style_active: \"{STYLE_ICON}\"")
                    output.append(f"  icon_style_inactive: \"{STYLE_ICON}; opacity: 0.5;\"")
                    output.append(f"  icon_style: \"{STYLE_ICON}\"")
                    output.append(f"  level_style: \"{STYLE_TEXT}; color: #000000 !important;\"")
                    output.append(f"  level2_style: \"{STYLE_TEXT}; color: #000000 !important;\"")
                    output.append(f"  unit_style: \"{STYLE_TEXT}; color: #000000 !important;\"")
                    output.append(f"  unit2_style: \"{STYLE_TEXT}; color: #000000 !important;\"")
                    output.append(f"  level_up_style: \"{STYLE_ICON}\"")
                    output.append(f"  level_down_style: \"{STYLE_ICON}\"")

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

                    output.append(f"  title_style: \"{STYLE_TITLE}\"")
                    output.append(f"  widget_style: \"{STYLE_WIDGET}\"")
                    output.append(f"  container_style: \"{STYLE_WIDGET}\"")
                    output.append(f"  icon_style_active: \"{STYLE_ICON}\"")
                    output.append(f"  icon_style_inactive: \"{STYLE_ICON}; opacity: 0.5;\"")
                    # Speed button styles
                    output.append(f"  speed1_style_active: \"{STYLE_ICON}\"")
                    output.append(f"  speed1_style_inactive: \"{STYLE_ICON}; opacity: 0.3;\"")
                    output.append(f"  speed2_style_active: \"{STYLE_ICON}\"")
                    output.append(f"  speed2_style_inactive: \"{STYLE_ICON}; opacity: 0.3;\"")
                    output.append(f"  speed3_style_active: \"{STYLE_ICON}\"")
                    output.append(f"  speed3_style_inactive: \"{STYLE_ICON}; opacity: 0.3;\"")
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

                    output.append(f"  title_style: \"{STYLE_TITLE}\"")
                    output.append(f"  widget_style: \"{STYLE_WIDGET}\"")
                    output.append(f"  icon_style_active: \"{STYLE_ICON}\"")
                    output.append(f"  icon_style_inactive: \"{STYLE_ICON}\"")

                elif w_type == 'clock':
                    output.append(f"  widget_type: clock")
                    output.append(f"  time_format: 24hr")
                    output.append(f"  show_seconds: 0")
                    output.append(f"  date_style: \"{STYLE_TEXT}\"")
                    output.append(f"  time_style: \"{STYLE_VALUE_TEMPLATE.format(px=54)}\"")

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
                    output.append(f"  title_style: \"{STYLE_TITLE}\"")
                    output.append(f"  widget_style: \"{STYLE_WIDGET}\"")
                    output.append(f"  value_style: \"{STYLE_GAUGE_VALUE}\"")
                    
                    # Try to fetch unit from map
                    unit = ""
                    if w_id in entities_map:
                        unit = entities_map[w_id].get('attributes', {}).get('unit_of_measurement', '') or entities_map[w_id].get('unit', '')
                    
                    if unit:
                        output.append(f"  units: \"{unit}\"")
                        
                    output.append(f"  unit_style: \"{STYLE_UNIT}\"")

                elif w_type == 'light':
                    output.append(f"  widget_type: light")
                    output.append(f"  entity: {real_entity_id}")
                    output.append(f"  title: \"{w_name}\"")

                    if i_on: output.append(f"  icon_on: {i_on}")
                    if i_off: output.append(f"  icon_off: {i_off}")
                    if w_icon and not i_on:
                        output.append(f"  icon: {w_icon}")
                        output.append(f"  icon_on: {w_icon}")
                        output.append(f"  icon_off: {w_icon}")
                    output.append(f"  title_style: \"{STYLE_TITLE}\"")
                    output.append(f"  widget_style: \"{STYLE_WIDGET}\"")
                    output.append(f"  icon_style_inactive: \"{STYLE_ICON}; opacity: 0.5;\"")
                    
                    st_enabled = w.get('state_text_enabled', True)
                    if str(st_enabled).lower() == 'false' or st_enabled is False:
                        output.append(f"  state_text_style: \"display: none !important;\"")
                        output.append(f"  value_style: \"display: none !important;\"")
                    else:
                        output.append(f"  state_text: 1")
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
                    output.append(f"  title_style: \"{STYLE_TITLE}\"")
                    output.append(f"  widget_style: \"{STYLE_WIDGET}\"")
                    output.append(f"  icon_style_active: \"{STYLE_ICON}\"")
                    output.append(f"  icon_style_inactive: \"{STYLE_ICON}; opacity: 0.5;\"")
                    
                    st_enabled = w.get('state_text_enabled', True)
                    if str(st_enabled).lower() == 'false' or st_enabled is False:
                        output.append(f"  state_text_style: \"display: none !important;\"")
                        output.append(f"  value_style: \"display: none !important;\"")
                    else:
                        output.append(f"  state_text: 1")
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
                    output.append(f"  title_style: \"{STYLE_TITLE}\"")
                    output.append(f"  widget_style: \"{STYLE_WIDGET}\"")
                    output.append(f"  icon_style_active: \"{STYLE_ICON}\"")
                    output.append(f"  icon_style_inactive: \"{STYLE_ICON}; opacity: 0.5;\"")
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
                    output.append(f"  title_style: \"{STYLE_TITLE}\"")
                    output.append(f"  widget_style: \"{STYLE_WIDGET}\"")
                    output.append(f"  icon_style_active: \"{STYLE_ICON}\"")
                    output.append(f"  icon_style_inactive: \"{STYLE_ICON}; opacity: 0.5;\"")
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
                    output.append(f"  title_style: \"{STYLE_TITLE}\"")
                    output.append(f"  widget_style: \"{STYLE_WIDGET}\"")
                    output.append(f"  icon_style_active: \"{STYLE_ICON}\"")
                    output.append(f"  icon_style_inactive: \"{STYLE_ICON}; opacity: 0.5;\"")
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
                    output.append(f"  title_style: \"{STYLE_TITLE}\"")
                    output.append(f"  widget_style: \"{STYLE_WIDGET}\"")
                    output.append(f"  icon_style_active: \"{STYLE_ICON}\"")
                    output.append(f"  icon_style_inactive: \"{STYLE_ICON}; opacity: 0.5;\"")
                    
                    st_enabled = w.get('state_text_enabled', True)
                    if str(st_enabled).lower() == 'false' or st_enabled is False:
                        output.append(f"  state_text_style: \"display: none !important;\"")
                        output.append(f"  value_style: \"display: none !important;\"")
                    else:
                        output.append(f"  state_text: 1")
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
                    output.append(f"  title_style: \"{STYLE_TITLE}\"")
                    output.append(f"  widget_style: \"{STYLE_WIDGET}\"")
                    output.append(f"  icon_active_style: \"{STYLE_ICON}\"")
                    output.append(f"  icon_inactive_style: \"{STYLE_ICON}; opacity: 0.5;\"")

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
                    
                    output.append(f"  title_style: \"{STYLE_TITLE}\"")
                    output.append(f"  widget_style: \"{STYLE_WIDGET}\"")
                    output.append(f"  value_style: \"color: #000000 !important; font-size: 24px !important; font-weight: 700 !important;\"")
                    output.append(f"  slider_style: \"background-color: #cccccc !important;\"")
                    output.append(f"  slidercontainer_style: \"background-color: #ffffff !important;\"")

                elif w_type == 'input_select':
                    output.append(f"  widget_type: input_select")
                    output.append(f"  entity: {real_entity_id}")
                    output.append(f"  title: \"{w_name}\"")

                    output.append(f"  title_style: \"{STYLE_TITLE}\"")
                    output.append(f"  widget_style: \"{STYLE_WIDGET}\"")
                    output.append(f"  select_style: \"color: #000000 !important; font-size: 18px !important; background: #ffffff !important; border: 1px solid #999999 !important;\"")
                    output.append(f"  selectcontainer_style: \"background-color: #ffffff !important;\"")

                elif w_type == 'label':
                    output.append(f"  widget_type: label")
                    output.append(f"  text: \"{w_name}\"")
                    if w_icon:
                        output.append(f"  icon: {w_icon}")
                    output.append(f"  text_style: \"{STYLE_TITLE}\"")

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
                    output.append(f"  title_style: \"{STYLE_TITLE}\"")
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
    ha_entities = get_ha_entities()
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
        "has_dashboards": has_dashboards,
        "visionect_configured": bool(VISIONECT_HOST),
        "visionect_host": VISIONECT_HOST or ""
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

        # Update global view parameters
        dashboard_slug = title.lower().replace(" ", "_")
        dashboard_filename = dashboard_slug + ".dash"
        
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
                    layout_data, title, grid_params, lang, custom_defs, entities_map
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
                    layout_data, title, grid_params, lang, custom_defs, entities_map
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
                    layout_data, title, grid_params, lang, custom_defs, entities_map
                )
            except Exception as e:
                print(f"❌ Error generating YAML: {e}")
                generated_yaml = f"# ERROR GENERATING YAML: {e}"

    return render_template(
        'index.html',
        generated_yaml=generated_yaml,
        entities=ha_entities,
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
        dashboards_list=available_dash_files if 'available_dash_files' in locals() else []
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

# -------------------------------------------------------------------------
# VISIONECT JOAN 6 API FUNCTIONS
# -------------------------------------------------------------------------
import hmac
import hashlib
import base64
import wsgiref.handlers
import time

def _visionect_hmac_headers(api_key, api_secret, method, endpoint, body=None):
    """Build HMAC headers for Visionect API authentication."""
    if not api_key or not api_secret:
        return {}
    
    # Extract path from URL if full URL is provided
    sign_endpoint = endpoint
    if "://" in sign_endpoint:
        from urllib.parse import urlparse
        sign_endpoint = urlparse(sign_endpoint).path

    # Normalize endpoint logic to match visionect_joan
    if not sign_endpoint.endswith("/") and "/api" in sign_endpoint and "restart" not in sign_endpoint:
         sign_endpoint += "/"

    content_type = "application/json"
    date_hdr = wsgiref.handlers.format_date_time(time.time())
    
    # Visionect requires SHA256 of body if present
    content_md5 = ""
    if body:
        if isinstance(body, dict):
            body_str = json.dumps(body, separators=(',', ':'))
        else:
            body_str = body
        content_md5 = hashlib.sha256(body_str.encode('utf-8')).hexdigest()

    signature_base = f"{method.upper()}\n{content_md5}\n{content_type}\n{date_hdr}\n{sign_endpoint}"
    
    # Debug logout for troubleshooting
    # print(f"🔐 DEBUG AUTH: Base:\n{signature_base.replace('\n', '\\n')}")
    
    h = hmac.new(api_secret.encode("utf-8"), signature_base.encode("utf-8"), hashlib.sha256)
    auth = f"{api_key}:{base64.b64encode(h.digest()).decode('ascii').strip()}"
    
    return {
        "Date": date_hdr,
        "Content-Type": content_type,
        "Authorization": auth,
    }

def get_joan_devices():
    """Fetch all Joan 6 devices from Visionect Server."""
    # Use global configuration variables
    host = VISIONECT_HOST
    api_key = VISIONECT_API_KEY
    api_secret = VISIONECT_API_SECRET

    if not host:
        return {"status": "error", "message": "Visionect Host not configured"}

    # Basic URL construction logic
    if not host.startswith("http"):
        host = f"http://{host}"
    
    # Auto-append port 8081 if missing and no port specified
    if ":" not in host.split("://")[1]:
        host = f"{host}:8081"
        
    # Strip trailing slash from host to be safe
    host = host.rstrip("/")

    # Try paths. Standard is /api/device/ (trailing slash required by some servers)
    urls_to_try = [
        f"{host}/api/device/",
        f"{host}/api/device",
        f"{host}/api/v1/device"
    ]

    last_error = ""

    for api_url in urls_to_try:
        try:
            headers = _visionect_hmac_headers(api_key, api_secret, "GET", api_url) if api_key and api_secret else {}
            
            print(f"🔭 DEBUG: Connecting to Visionect: {api_url}", flush=True)
            
            response = requests.get(api_url, headers=headers, timeout=5)
            
            print(f"🔭 DEBUG: Response {response.status_code} from {api_url}", flush=True)
            
            if response.status_code == 200:
                devices_data = response.json()
                if isinstance(devices_data, dict) and 'data' in devices_data:
                    devices_data = devices_data['data']
                
                if not isinstance(devices_data, list):
                    print(f"⚠️ Unexpected format from Visionect: {type(devices_data)}")
                    return {"status": "error", "message": "Invalid response format from Visionect"}

                devices_list = []
                for d in devices_data:
                    # Robust battery detection
                    battery_level = d.get('Battery')
                    status_obj = d.get('Status', {})
                    last_status_obj = d.get('LastStatus', {})
                    
                    voltage = d.get('Voltage')
                    if voltage is None:
                        voltage = status_obj.get('Voltage') or last_status_obj.get('Voltage')

                    if battery_level is None:
                        battery_level = status_obj.get('Battery') or last_status_obj.get('Battery')

                    if battery_level is None and voltage:
                        try:
                            v = float(voltage)
                            if v > 10: v = v / 1000.0
                            pct = int((v - 3.6) / (4.2 - 3.6) * 100)
                            battery_level = max(0, min(100, pct))
                        except (ValueError, TypeError):
                            battery_level = None

                    # Robust IP detection
                    ip = d.get('IP') or status_obj.get('IP') or last_status_obj.get('IP') or "Unknown"

                    # WiFi Signal (RSSI)
                    rssi = status_obj.get('RSSI') or last_status_obj.get('RSSI') or d.get('RSSI')
                    
                    # State (online/offline)
                    state = d.get('State', 'unknown')

                    # Check online status - simplified
                    # Status 0 is usually OK/Online in Visionect
                    is_online = (state.lower() == 'online')
                    if not is_online:
                        current_status_code = status_obj.get('Status')
                        if current_status_code == 0:
                            is_online = True
                        elif current_status_code is None and last_status_obj.get('Status') == 0:
                            is_online = True
                    
                    devices_list.append({
                        "name": d.get('Name') or d.get('Uuid', 'Unknown'),
                        "uuid": d.get('Uuid'),
                        "status": status_obj,
                        "online": is_online,
                        "state": state,
                        "rssi": rssi if rssi is not None else "?",
                        "battery": battery_level if battery_level is not None else "?",
                        "battery_voltage": voltage if voltage is not None else "?",
                        "ip": ip
                    })
                
                print(f"✅ Found {len(devices_list)} Joan devices.")
                return {"status": "success", "devices": devices_list}
            
            elif response.status_code == 404:
                last_error = f"HTTP 404 (Not Found) at {api_url}"
                continue
            elif response.status_code == 401:
                print(f"❌ Visionect Auth Error: 401 Unauthorized")
                return {"status": "error", "message": "HTTP 401 Unauthorized - Check API Key & Secret"}
            else:
                last_error = f"HTTP {response.status_code}: {response.text}"
                break 

        except requests.exceptions.ConnectionError:
            last_error = f"Connection Failed to {host}"
            break 
        except Exception as e:
            last_error = str(e)
            print(f"❌ Unexpected error fetching Joan devices: {e}")
            break

    print(f"❌ Failed to fetch devices. Last error: {last_error}", flush=True)
    
    # Enhance error message for user
    final_message = last_error
    if "404" in last_error:
        final_message += f" (Checked: {host})"
    if "Connection Failed" in last_error:
        final_message += f" (Failed to reach: {host})"
        
    return {"status": "error", "message": final_message, "devices": []}

def send_to_joan_device(uuid, dashboard_url):
    """Send dashboard URL to a Joan 6 device."""
    print(f"🛰️ Sending to Joan: Device {uuid} -> {dashboard_url}")
    if not VISIONECT_HOST:
        return {"status": "error", "message": "Visionect host not configured"}
    
    try:
        host = VISIONECT_HOST
        if not host.startswith(('http://', 'https://')):
            host = f"http://{host}"
        if ':' not in host.split('://')[-1]:
            host = f"{host}:8081"
        
        # First, get current session data
        session_url = f"{host}/api/session/{uuid}/"
        headers = _visionect_hmac_headers(VISIONECT_API_KEY, VISIONECT_API_SECRET, "GET", f"/api/session/{uuid}/")
        
        print(f"📡 Fetching session for {uuid}")
        response = requests.get(session_url, headers=headers, timeout=10)
        
        if response.status_code != 200:
            return {"status": "error", "message": f"Cannot fetch session: {response.status_code}"}
        
        session_data = response.json()
        
        # Update session with new URL
        if "Backend" not in session_data:
            session_data["Backend"] = {}
        if "Fields" not in session_data["Backend"]:
            session_data["Backend"]["Fields"] = {}
        
        session_data["Backend"]["Name"] = "HTML"
        session_data["Backend"]["Fields"]["url"] = dashboard_url
        session_data["Backend"]["Fields"]["ReloadTimeout"] = "300"  # 5 minutes
        
        # Send updated session
        put_headers = _visionect_hmac_headers(VISIONECT_API_KEY, VISIONECT_API_SECRET, "PUT", f"/api/session/{uuid}/", body=session_data)
        put_headers["Content-Type"] = "application/json"
        
        print(f"📤 Setting URL for {uuid}: {dashboard_url}")
        put_response = requests.put(
            session_url, 
            headers=put_headers, 
            data=json.dumps(session_data, separators=(',', ':')), 
            timeout=10
        )
        
        if put_response.status_code in [200, 201, 204]:
            # Restart session to apply changes
            restart_url = f"{host}/api/session/{uuid}/restart"
            restart_headers = _visionect_hmac_headers(VISIONECT_API_KEY, VISIONECT_API_SECRET, "POST", f"/api/session/{uuid}/restart")
            requests.post(restart_url, headers=restart_headers, timeout=10)
            
            return {"status": "success", "message": f"Dashboard sent to device {uuid}"}
        else:
            return {"status": "error", "message": f"Failed to set URL: {put_response.status_code} - {put_response.text}"}
    except Exception as e:
        print(f"❌ Error sending to Joan device: {e}")
        return {"status": "error", "message": str(e)}

@app.route('/api/joan_devices')
def api_joan_devices():
    """Returns list of Joan 6 devices with status."""
    from flask import jsonify
    result = get_joan_devices()
    return jsonify(result)

@app.route('/api/send_to_joan', methods=['POST'])
def api_send_to_joan():
    """Send dashboard to a Joan 6 device."""
    from flask import jsonify
    
    data = request.get_json() or {}
    uuid = data.get('uuid')
    dashboard_url = data.get('url')
    print(f"🛰️ API Request: send_to_joan [UUID: {uuid}, URL: {dashboard_url}]")
    
    if not uuid:
        return jsonify({"status": "error", "message": "Missing device UUID"})
    if not dashboard_url:
        return jsonify({"status": "error", "message": "Missing dashboard URL"})
    
    result = send_to_joan_device(uuid, dashboard_url)
    return jsonify(result)

@app.route('/api/visionect_status')
def api_visionect_status():
    """Returns Visionect connection status."""
    from flask import jsonify
    return jsonify({
        "configured": bool(VISIONECT_HOST),
        "host": VISIONECT_HOST or "",
        "has_credentials": bool(VISIONECT_API_KEY and VISIONECT_API_SECRET),
        "dashboard_base_url": DASHBOARD_BASE_URL
    })


if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000, debug=True)

