import os
import json
import requests
import sys
from flask import Flask, render_template, request

# =========================================================================
# INITIALIZATION
# =========================================================================
print("📦 [INIT] Initializing Joan 6 Generator application...")
app = Flask(__name__)
# Secret key for session/flash messages security
app.secret_key = 'joan_generator_secret_key_v3'

# =========================================================================
# 1. API & TOKEN CONFIGURATION
# =========================================================================
TOKEN = os.environ.get('SUPERVISOR_TOKEN')
API_URL = "http://supervisor/core/api"
SUPERVISOR_URL = "http://supervisor"
TOKEN_SOURCE = "System (Supervisor)"

# Default settings
APPDAEMON_ADDON_SLUG = "a0d7b954_appdaemon"
# Default output directory (fallback)
OUTPUT_DIR = "/share/dashboards" 

# -------------------------------------------------------------------------
# DIRECTORY DEBUGGING
# -------------------------------------------------------------------------
def debug_directories():
    print("\n🔍 --- DIRECTORY STRUCTURE DEBUG START ---")
    paths_to_check = ["/", "/config", "/addon_configs", "/share", "/data", "/config/appdaemon/dashboards"]
    
    for p in paths_to_check:
        if os.path.exists(p):
            print(f"✅ Directory exists: {p}")
            try:
                contents = [d for d in os.listdir(p)]
                # Show first 5 items to avoid log spam
                print(f"   └── Contents: {contents[:5]}...") 
            except Exception as e:
                print(f"   ⚠️ Directory exists but ACCESS DENIED: {e}")
        else:
            print(f"❌ Directory does NOT exist: {p}")
    print("--------------------------------------------\n")

# -------------------------------------------------------------------------
# LOAD ADD-ON OPTIONS
# -------------------------------------------------------------------------
try:
    options_path = '/data/options.json'
    if os.path.exists(options_path):
        print(f"ℹ️ [OPTIONS] Reading user configuration from: {options_path}")
        with open(options_path, 'r') as f:
            options = json.load(f)
            
            manual_token = options.get('manual_token')
            if manual_token and len(manual_token) > 10:
                TOKEN = manual_token
                API_URL = "http://homeassistant:8123/api"
                print(f"🔧 [CONFIG] Manual token detected. API URL set to: {API_URL}")
            
            if options.get('output_path'):
                OUTPUT_DIR = options.get('output_path')
                print(f"🔧 [CONFIG] Output path enforced: {OUTPUT_DIR}")
            
            if options.get('appdaemon_slug'):
                APPDAEMON_ADDON_SLUG = options.get('appdaemon_slug')
                print(f"🔧 [CONFIG] AppDaemon slug enforced: {APPDAEMON_ADDON_SLUG}")

except Exception as e: 
    print(f"⚠️ [OPTIONS] Error reading options: {e}")

if not TOKEN:
    print("❌ [CRITICAL] WARNING: No Authorization Token found!")

# =========================================================================
# 2. AUTO-DETECTION FUNCTIONS
# =========================================================================
def detect_appdaemon_slug():
    if not os.environ.get('SUPERVISOR_TOKEN'): 
        return APPDAEMON_ADDON_SLUG 

    headers = {"Authorization": f"Bearer {os.environ.get('SUPERVISOR_TOKEN')}"}
    try:
        resp = requests.get(f"{SUPERVISOR_URL}/addons", headers=headers, timeout=5)
        if resp.status_code == 200:
            data = resp.json().get('data', {})
            for addon in data.get('addons', []):
                slug = addon.get('slug', '')
                if 'appdaemon' in slug and addon.get('installed', False):
                    print(f"✅ [DETECT] Found AppDaemon Add-on: {slug}")
                    return slug
    except Exception as e:
        print(f"⚠️ [DETECT] Error detecting AppDaemon slug: {e}")
    return APPDAEMON_ADDON_SLUG 

def detect_dashboard_path(detected_slug):
    """Attempts to find a writable dashboard directory."""
    candidates = [
        f"/addon_configs/{detected_slug}/dashboards",
        "/config/appdaemon/dashboards",
        "/share/dashboards"
    ]
    
    # Check general access
    if not os.path.exists("/config") and not os.path.exists("/addon_configs") and not os.path.exists("/share"):
        print("❌ [CRITICAL] No access to /config, /addon_configs or /share!")
        return None

    for path in candidates:
        if os.path.exists(path):
            print(f"✅ [PATH] Found existing directory: {path}")
            if os.access(path, os.W_OK): return path
            else: print(f"   ⚠️ Read-only access to: {path}")
        
        # Try to create if parent exists
        parent = os.path.dirname(path)
        if os.path.exists(parent) and os.access(parent, os.W_OK):
            try:
                os.makedirs(path, exist_ok=True)
                print(f"✅ [PATH] Created directory: {path}")
                return path
            except: pass
    
    # Fallback to config if available
    if os.path.exists("/config"):
        fallback = "/config/appdaemon/dashboards"
        print(f"⚠️ [PATH] Defaulting to fallback: {fallback}")
        try: os.makedirs(fallback, exist_ok=True)
        except: pass
        return fallback
        
    return None

# Run startup detection
debug_directories()
if 'options' in globals() and not options.get('appdaemon_slug'):
    APPDAEMON_ADDON_SLUG = detect_appdaemon_slug()

if 'options' in globals() and not options.get('output_path'):
    detected_path = detect_dashboard_path(APPDAEMON_ADDON_SLUG)
    if detected_path:
        OUTPUT_DIR = detected_path

print(f"📂 [FINAL] Target Save Directory: {OUTPUT_DIR}")

# =========================================================================
# 3. HOME ASSISTANT API INTERACTION
# =========================================================================
def get_ha_entities():
    """Fetch entities from HA API."""
    if not TOKEN: return []
    headers = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
    try:
        response = requests.get(f"{API_URL}/states", headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            entities = []
            for state in data:
                attr = state.get('attributes', {})
                entities.append({
                    'id': state['entity_id'],
                    'state': state['state'],
                    'attributes': {
                        'friendly_name': attr.get('friendly_name', state['entity_id']),
                        'device_class': attr.get('device_class', ''),
                        'unit_of_measurement': attr.get('unit_of_measurement', '')
                    },
                    'unit': attr.get('unit_of_measurement', '')
                })
            entities.sort(key=lambda x: x['id'])
            return entities
    except Exception as e: print(f"❌ [API] Error fetching entities: {e}")
    return []

def restart_appdaemon_addon():
    """Restarts AppDaemon using available method (Service Call or Supervisor)."""
    if not TOKEN: return False, "No API Token."
    
    headers = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
    
    # Determine method based on API URL
    if "homeassistant" in API_URL or "8123" in API_URL:
        # Manual Token -> Use Service Call
        url = f"{API_URL}/services/hassio/addon_restart"
        payload = {"addon": APPDAEMON_ADDON_SLUG}
        print(f"🔄 [RESTART] Using Service Call: {url}")
        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=30)
        except Exception as e: return False, str(e)
    else:
        # Supervisor Token -> Use Supervisor API
        url = f"{SUPERVISOR_URL}/addons/{APPDAEMON_ADDON_SLUG}/restart"
        print(f"🔄 [RESTART] Using Supervisor API: {url}")
        try:
            resp = requests.post(url, headers=headers, timeout=30)
        except Exception as e: return False, str(e)

    if resp.status_code in [200, 201, 202]:
        return True, "AppDaemon restart initiated."
    return False, f"Restart failed (Code {resp.status_code}): {resp.text}"

def deploy_url_to_device(device_entity_id, dashboard_name):
    """Sends the new dashboard URL to a Visionect device."""
    if not TOKEN: return False, "No API Token."
    
    # Determine Host IP
    try:
        host_ip = API_URL.split('//')[1].split(':')[0]
    except:
        host_ip = "homeassistant.local"
        
    target_url = f"http://{host_ip}:5050/{dashboard_name}"
    
    headers = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
    service_url = f"{API_URL}/services/visionect_joan/set_url"
    
    payload = {
        "entity_id": device_entity_id, 
        "url": target_url
    }
    
    try:
        print(f"🚀 [DEPLOY] Sending {target_url} to {device_entity_id}")
        resp = requests.post(service_url, json=payload, headers=headers, timeout=10)
        if resp.status_code in [200, 201]:
            return True, f"URL sent to {device_entity_id}"
        return False, f"Integration Error ({resp.status_code}): {resp.text}"
    except Exception as e:
        return False, str(e)

# -------------------------------------------------------------------------
# PROXY ROUTE FOR CAMERA IMAGES
# -------------------------------------------------------------------------
@app.route('/camera_proxy/<entity_id>')
def camera_proxy(entity_id):
    """Proxies HA camera images to the frontend."""
    if not TOKEN: return "No Token", 403
    
    headers = {"Authorization": f"Bearer {TOKEN}"}
    url = f"{API_URL}/camera_proxy/{entity_id}"
    
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code == 200:
            from flask import Response
            return Response(resp.content, mimetype=resp.headers.get('Content-Type', 'image/jpeg'))
        return f"Error from HA: {resp.status_code}", 404
    except Exception as e:
        return str(e), 500

# =========================================================================
# 4. GENERATOR LOGIC
# =========================================================================
STYLE_TITLE = "color: #000000; font-size: 20px; font-weight: 700; text-align: center; padding-top: 5px; width: 100%; font-family: 'Roboto', 'Arial Black', sans-serif;"
STYLE_WIDGET = "color: #000000 !important; background-color: #FFFFFF !important;"
STYLE_TEXT = "color: #000000 !important; font-weight: 700 !important;"
STYLE_VALUE = "color: #000000 !important; font-size: 54px !important; font-weight: 700 !important; padding-top: 60px !important; line-height: 1.1 !important; display: inline-block !important;"
STYLE_UNIT = "color: #000000 !important; padding-top: 60px !important; display: inline-block !important;"
STYLE_ICON = "color: #000000 !important;"
STYLE_STATE_TEXT = "color: #000000 !important; font-weight: 700 !important; font-size: 16px !important;"

def normalize_icon_format(icon_name):
    if not icon_name: return icon_name
    icon_name = icon_name.strip()
    if icon_name.startswith('mdi:'): return 'mdi-' + icon_name[4:]
    if icon_name.startswith('mdi-'): return icon_name
    return icon_name

def safe_yaml_string(s):
    if not s: return s
    return s.replace('"', '\\"').replace("'", "\\'")

@app.route('/', methods=['GET', 'POST'])
def index():
    generated_yaml = ""
    ha_entities = get_ha_entities()
    
    # 1. Filter Joan devices (look for cameras with specific names)
    joan_devices = []
    for e in ha_entities:
        eid = e['id'].lower()
        name = e['attributes'].get('friendly_name', '').lower()
        if eid.startswith('camera.'):
            if 'joan' in eid or 'joan' in name or 'visionect' in eid or 'live_view' in eid:
                joan_devices.append(e)
            else:
                pass 
    # Fallback: show all cameras if none matched
    if not joan_devices:
        joan_devices = [e for e in ha_entities if e['id'].startswith('camera.')]

    dashboard_filename = "joandashboard.dash"
    dashboard_slug = "joandashboard"
    has_token = bool(TOKEN)
    save_message = None
    
    global OUTPUT_DIR
    if OUTPUT_DIR is None:
        OUTPUT_DIR = detect_dashboard_path(APPDAEMON_ADDON_SLUG)

    if request.method == 'POST':
        try:
            title = request.form.get('title', 'JoanDashboard')
            # Action type from hidden input
            action_type = request.form.get('action_type', 'generate')
            
            dashboard_slug = title.lower().replace(" ", "_").replace("ą","a").replace("ć","c").replace("ę","e").replace("ł","l").replace("ń","n").replace("ó","o").replace("ś","s").replace("ź","z").replace("ż","z")
            dashboard_filename = dashboard_slug + ".dash"
            
            # --- YAML GENERATION (ALWAYS EXECUTE TO SHOW PREVIEW) ---
            cols = request.form.get('grid_columns', '4')
            rows = request.form.get('grid_rows', '8')
            lang = request.form.get('ui_language', 'pl')
            default_size_str = request.form.get('default_widget_size', '2, 1')
            def_size_parts = default_size_str.split(',')
            def_w = int(def_size_parts[0].strip())
            def_h = int(def_size_parts[1].strip()) if len(def_size_parts) > 1 else 1

            # Translation Maps
            TRANS = {
                'pl': {'on': 'WŁ', 'off': 'WYŁ', 'open': 'OTW', 'closed': 'ZAM', 'locked': 'ZAM', 'unlocked': 'OTW', 'home': 'DOM', 'not_home': 'POZA'},
                'en': {'on': 'ON', 'off': 'OFF', 'open': 'OPEN', 'closed': 'CLOSED', 'locked': 'LOCKED', 'unlocked': 'UNLOCKED', 'home': 'HOME', 'not_home': 'AWAY'}
            }
            dic = TRANS.get(lang, TRANS['pl'])
            ad_columns = int(cols) if def_w == 1 else int(cols) * 2

            # Header
            generated_yaml += f"title: {title}\nwidget_dimensions: [117, 117]\nwidget_size: [{def_w}, {def_h}]\nwidget_margins: [8, 8]\ncolumns: {ad_columns}\nrows: {rows}\n"
            generated_yaml += "global_parameters:\n  use_comma: 0\n  precision: 1\n  use_hass_icon: 1\n  namespace: default\n  devices:\n    media_player:\n      step: 5\n    climate:\n      step: 1\n"
            generated_yaml += f"  white_text_style: \"{STYLE_TEXT}\"\n  state_text_style: \"{STYLE_STATE_TEXT}\"\nskin: default\n\n"
            
            layout_data_str = request.form.get('layout_data_json')
            custom_defs_str = request.form.get('custom_definitions_json', '{}')
            custom_defs = json.loads(custom_defs_str)
            
            processed_widgets = []
            
            if layout_data_str:
                layout_rows = json.loads(layout_data_str)
                generated_yaml += "layout:\n"
                for row in layout_rows:
                    if not row: continue
                    row_parts = []
                    for w in row:
                        if w['type'] == 'spacer': 
                            row_parts.append("spacer")
                            continue
                        widget_id = w['id']
                        size_str = w.get('size', '')
                        is_default = False
                        if size_str == f"({def_w}x{def_h})": is_default = True
                        elif size_str == "(2x1)" and def_w == 2 and def_h == 1: is_default = True
                        elif size_str == "(1x1)" and def_w == 1 and def_h == 1: is_default = True
                        if not is_default and size_str:
                             if not size_str.startswith('('): size_str = f"({size_str})"
                             widget_id += size_str
                        row_parts.append(widget_id)
                        processed_widgets.append(w)
                    generated_yaml += f"  - {', '.join(row_parts)}\n"
                
                generated_yaml += "\n"
                seen_ids = set()
                
                # --- WIDGET GENERATION LOOP ---
                for w in processed_widgets: 
                    w_id = w['id']
                    if w_id in seen_ids: continue
                    seen_ids.add(w_id)
                    
                    if w_id in custom_defs and not w.get('was_edited', False):
                        generated_yaml += f"{w_id}:\n"
                        for line in custom_defs[w_id].split('\n'):
                            if line.strip(): generated_yaml += f"  {line}\n"
                        generated_yaml += "\n"
                        continue

                    w_type = w['type']
                    w_name = safe_yaml_string(w['name'])
                    w_icon = normalize_icon_format(w['icon'])
                    i_on = normalize_icon_format(w.get('icon_on'))
                    i_off = normalize_icon_format(w.get('icon_off'))
                    
                    generated_yaml += f"{w_id}:\n"
                    
                    if w_type == 'navigate':
                        dash_target = w_id.replace('navigate.', '')
                        nav_icon = w_icon or 'mdi-arrow-right-circle'
                        generated_yaml += f"  widget_type: navigate\n  title: \"{w_name}\"\n  dashboard: {dash_target}\n  icon_active: {nav_icon}\n  icon_inactive: {nav_icon}\n  title_style: \"{STYLE_TITLE}\"\n  widget_style: \"{STYLE_WIDGET}\"\n  icon_active_style: \"{STYLE_ICON}\"\n  icon_inactive_style: \"{STYLE_ICON}\"\n"
                    
                    elif w_type == 'sensor':
                        generated_yaml += f"  widget_type: sensor\n  entity: {w_id}\n  title: \"{w_name}\"\n  title_style: \"{STYLE_TITLE}\"\n  text_style: \"{STYLE_TEXT}\"\n  value_style: \"{STYLE_VALUE}\"\n  unit_style: \"{STYLE_UNIT}\"\n  widget_style: \"{STYLE_WIDGET}\"\n  precision: 1\n"
                    
                    elif w_type == 'media_player':
                        generated_yaml += f"  widget_type: media_player\n  entity: {w_id}\n  title: \"{w_name}\"\n"
                        if w_icon: generated_yaml += f"  icon: {w_icon}\n"
                        generated_yaml += f"  title_style: \"{STYLE_TITLE}\"\n  widget_style: \"{STYLE_WIDGET}\"\n  icon_style: \"{STYLE_ICON}\"\n  truncate_name: 20\n  step: 5\n"
                    
                    elif w_type == 'climate':
                        generated_yaml += f"  widget_type: climate\n  entity: {w_id}\n
