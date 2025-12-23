import os
import json
import requests
import sys
from flask import Flask, render_template, request

# =========================================================================
# INITIALIZATION & SETUP
# =========================================================================
print("📦 [INIT] Initializing Joan 6 Generator application...")
print("-------------------------------------------------------------------")

app = Flask(__name__)
# Secret key for session/flash messages security
app.secret_key = 'joan_generator_secret_key_full_production'

# =========================================================================
# 1. API & TOKEN CONFIGURATION
# =========================================================================
# Default to Supervisor environment variables provided by HA OS
TOKEN = os.environ.get('SUPERVISOR_TOKEN')
API_URL = "http://supervisor/core/api"
SUPERVISOR_URL = "http://supervisor"
TOKEN_SOURCE = "System (Supervisor)"

# Default settings (will be overwritten by auto-detection logic)
APPDAEMON_ADDON_SLUG = "a0d7b954_appdaemon" 
OUTPUT_DIR = None  # None to force detection logic on startup

# -------------------------------------------------------------------------
# HELPER: DEBUGGING DIRECTORY STRUCTURE
# -------------------------------------------------------------------------
def debug_directories():
    """
    Helper function to list directories visible to the container.
    This helps diagnose 'Permission denied' or 'No such file' errors
    which are common in HA Add-on environment.
    """
    print("\n🔍 --- DIRECTORY STRUCTURE DEBUG START ---")
    
    # List of critical paths to check for existence and read permissions
    paths_to_check = [
        "/", 
        "/config", 
        "/addon_configs", 
        "/share", 
        "/data",
        "/config/appdaemon",
        "/config/appdaemon/dashboards"
    ]
    
    available_mounts = []
    
    for p in paths_to_check:
        if os.path.exists(p):
            print(f"✅ Directory exists: {p}")
            available_mounts.append(p)
            try:
                # Attempt to list contents to verify read access
                contents = [d for d in os.listdir(p)]
                # Filter to show only directories/files, limited count to avoid log spam
                preview = contents[:10]
                count = len(contents)
                print(f"   └── Contents ({count} items): {preview}...") 
            except Exception as e:
                print(f"   ⚠️ Directory exists but ACCESS DENIED to {p}: {e}")
        else:
            print(f"❌ Directory does NOT exist (not mounted or wrong path): {p}")
            
    print("🔍 --- DIRECTORY STRUCTURE DEBUG END ---\n")
    return available_mounts

# -------------------------------------------------------------------------
# LOAD ADD-ON OPTIONS (options.json)
# -------------------------------------------------------------------------
# This section reads configuration provided by the user in HA Add-on configuration tab
try:
    options_path = '/data/options.json'
    if os.path.exists(options_path):
        print(f"ℹ️ [OPTIONS] Reading user configuration from: {options_path}")
        with open(options_path, 'r') as f:
            options = json.load(f)
            
            # 1. Manual Token Override (Useful for local testing or non-supervisor env)
            manual_token = options.get('manual_token')
            if manual_token and len(manual_token) > 10:
                TOKEN = manual_token
                # If manual token is used, we usually talk to HA Core directly on port 8123
                API_URL = "http://homeassistant:8123/api"
                TOKEN_SOURCE = "Manual (Configuration)"
                print(f"🔧 [CONFIG] Manual token detected. Switching API URL to: {API_URL}")
            
            # 2. Path Override (User explicitly sets where to save)
            if options.get('output_path'):
                OUTPUT_DIR = options.get('output_path')
                print(f"🔧 [CONFIG] Output path enforced by configuration: {OUTPUT_DIR}")
            
            # 3. Slug Override (User explicitly sets AppDaemon slug)
            if options.get('appdaemon_slug'):
                APPDAEMON_ADDON_SLUG = options.get('appdaemon_slug')
                print(f"🔧 [CONFIG] AppDaemon slug enforced by configuration: {APPDAEMON_ADDON_SLUG}")

    else:
        print(f"ℹ️ [OPTIONS] No options.json found at {options_path}. Using defaults.")

except Exception as e: 
    print(f"⚠️ [OPTIONS] Error reading options.json: {e}")

# Critical check for Token
if not TOKEN:
    print("❌ [CRITICAL] WARNING: No Authorization Token found! Entity list will be empty and restart will fail.")

# =========================================================================
# 2. ENVIRONMENT AUTO-DETECTION (AppDaemon & Paths)
# =========================================================================
def detect_appdaemon_slug():
    """
    Queries Supervisor API to find the actual slug of the installed AppDaemon add-on.
    This handles variations like 'a0d7b954_appdaemon' vs local builds.
    """
    if not os.environ.get('SUPERVISOR_TOKEN'):
        print("ℹ️ [DETECT] No Supervisor token available for slug detection. Keeping default.")
        return APPDAEMON_ADDON_SLUG 

    headers = {"Authorization": f"Bearer {os.environ.get('SUPERVISOR_TOKEN')}"}
    try:
        print(f"🔍 [DETECT] Querying Supervisor for installed addons...")
        resp = requests.get(f"{SUPERVISOR_URL}/addons", headers=headers, timeout=5)
        
        if resp.status_code == 200:
            data = resp.json().get('data', {})
            addons = data.get('addons', [])
            
            for addon in addons:
                slug = addon.get('slug', '')
                # Look for 'appdaemon' in the slug string and ensure it's installed
                if 'appdaemon' in slug and addon.get('installed', False):
                    print(f"✅ [DETECT] Found installed AppDaemon Add-on: {slug}")
                    return slug
            print("⚠️ [DETECT] AppDaemon not found in installed addons list.")
        else:
            print(f"⚠️ [DETECT] Supervisor API returned status: {resp.status_code}")
            
    except Exception as e:
        print(f"⚠️ [DETECT] Exception during AppDaemon slug detection: {e}")
    
    return APPDAEMON_ADDON_SLUG # Fallback

def detect_dashboard_path(detected_slug):
    """
    Attempts to find a valid writable directory for .dash files.
    Prioritizes specific AppDaemon config folders, falls back to generic /config.
    """
    print(f"🔍 [PATH] Attempting to detect best save path for slug: {detected_slug}")
    
    # Priority list of paths to check
    candidates = [
        # 1. New HA OS structure in /addon_configs (Best practice if mounted)
        f"/addon_configs/{detected_slug}/dashboards",
        f"/addon_configs/{detected_slug}/conf/dashboards",
        # 2. Legacy structure in /config (Most common for file sharing)
        "/config/appdaemon/dashboards",
        "/config/appdaemon/conf/dashboards",
        # 3. Share folder (Alternative if config is locked)
        "/share/dashboards",
        "/share/appdaemon/dashboards"
    ]

    # If user enforced a path in options, try that first
    if 'options' in globals() and options.get('output_path'):
        user_path = options.get('output_path')
        print(f"ℹ️ [PATH] Checking user-defined path first: {user_path}")
        candidates.insert(0, user_path)

    # Preliminary check for mount points visibility
    has_config = os.path.exists("/config")
    has_addon_configs = os.path.exists("/addon_configs")
    has_share = os.path.exists("/share")
    
    if not has_config and not has_addon_configs and not has_share:
        print("❌ [CRITICAL] No major directories (/config, /addon_configs, /share) are mounted!")
        print("   Please check your 'config.json' -> 'map' section.")
        # We return None, logic later will show error to user
        return None

    for path in candidates:
        # Check if directory exists
        if os.path.exists(path):
            print(f"✅ [PATH] Found existing valid directory: {path}")
            # Verify write access
            if os.access(path, os.W_OK):
                return path
            else:
                print(f"   ⚠️ Read-only access to {path}, skipping...")
        
        # If not, check if parent exists and we can create it
        parent = os.path.dirname(path)
        if os.path.exists(parent):
            if os.access(parent, os.W_OK):
                try:
                    # Attempt to create directory
                    os.makedirs(path, exist_ok=True)
                    print(f"✅ [PATH] Successfully created directory: {path}")
                    return path
                except Exception as e:
                    print(f"   ⚠️ Failed to create {path}: {e}")
            else:
                pass # Parent exists but not writable
    
    # Fallback logic if nothing specific found
    if has_config:
        fallback = "/config/appdaemon/dashboards"
        print(f"⚠️ [PATH] Specific path not found. Defaulting to fallback in /config: {fallback}")
        # Try to create it just in case
        try:
            os.makedirs(fallback, exist_ok=True)
        except: pass
        return fallback
        
    return None

# =========================================================================
# RUN STARTUP ROUTINES
# =========================================================================
debug_directories()

# 1. Detect Slug
if 'options' in globals() and not options.get('appdaemon_slug'):
    APPDAEMON_ADDON_SLUG = detect_appdaemon_slug()

# 2. Detect Path
if 'options' in globals() and not options.get('output_path'):
    OUTPUT_DIR = detect_dashboard_path(APPDAEMON_ADDON_SLUG)
elif 'options' in globals() and options.get('output_path'):
    OUTPUT_DIR = options.get('output_path')

print(f"📂 [FINAL] Configured Target Save Directory: {OUTPUT_DIR}")
print("-------------------------------------------------------------------")

# =========================================================================
# 3. HOME ASSISTANT API FUNCTIONS
# =========================================================================
def get_ha_entities():
    """
    Fetches all states from Home Assistant Core API to populate the list.
    """
    if not TOKEN:
        return []
        
    headers = {
        "Authorization": f"Bearer {TOKEN}", 
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.get(f"{API_URL}/states", headers=headers, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            entities = []
            
            for state in data:
                attributes = state.get('attributes', {})
                unit = attributes.get('unit_of_measurement', '')
                
                # Create a simplified object for the frontend
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
            
            # Sort alphabetically by entity_id
            entities.sort(key=lambda x: x['id'])
            return entities
            
    except Exception as e: 
        print(f"❌ [API] Exception fetching entities: {e}")
        
    return []

def restart_appdaemon():
    """
    Sends a request to Home Assistant to restart the AppDaemon add-on.
    Handles both Internal Supervisor API and External Service Calls.
    """
    if not TOKEN:
        return False, "No API Token available."
    
    # Determine which API endpoint to use based on configuration
    if "supervisor" in API_URL:
        # Internal Supervisor API (Direct container to supervisor communication)
        url = f"{SUPERVISOR_URL}/addons/{APPDAEMON_ADDON_SLUG}/restart"
        method = "POST"
    else:
        # External/Core API Service Call (Standard HA Service)
        url = f"{API_URL}/services/hassio/addon_restart"
        method = "POST_SERVICE"

    headers = {
        "Authorization": f"Bearer {TOKEN}", 
        "Content-Type": "application/json"
    }
    
    try:
        print(f"🔄 [RESTART] Attempting restart of addon: {APPDAEMON_ADDON_SLUG}")
        print(f"   Using URL: {url}")
        
        response = None
        if method == "POST_SERVICE":
            payload = {"addon": APPDAEMON_ADDON_SLUG}
            response = requests.post(url, json=payload, headers=headers, timeout=20)
        else:
            # Supervisor API direct call (no body needed for restart)
            response = requests.post(url, headers=headers, timeout=20)
            
        if response.status_code in [200, 201]:
            print("✅ [RESTART] Command sent successfully.")
            return True, f"Saved to {OUTPUT_DIR} and restart command sent to {APPDAEMON_ADDON_SLUG}."
        else:
            print(f"❌ [RESTART] Failed. Status: {response.status_code}. Body: {response.text}")
            return False, f"Restart failed (Code {response.status_code}): {response.text}"
            
    except Exception as e:
        print(f"❌ [RESTART] Exception during restart: {e}")
        return False, f"Exception during restart: {str(e)}"

# =========================================================================
# 4. E-INK STYLES AND FORMATTERS
# =========================================================================
# High contrast styles for E-Ink displays (Black on White)
STYLE_TITLE = "color: #000000; font-size: 20px; font-weight: 700; text-align: center; padding-top: 5px; width: 100%; font-family: 'Roboto', 'Arial Black', sans-serif;"
STYLE_WIDGET = "color: #000000 !important; background-color: #FFFFFF !important;"
STYLE_TEXT = "color: #000000 !important; font-weight: 700 !important;"
STYLE_VALUE = "color: #000000 !important; font-size: 54px !important; font-weight: 700 !important; padding-top: 60px !important; line-height: 1.1 !important; display: inline-block !important;"
STYLE_UNIT = "color: #000000 !important; padding-top: 60px !important; display: inline-block !important;"
STYLE_ICON = "color: #000000 !important;"
STYLE_STATE_TEXT = "color: #000000 !important; font-weight: 700 !important; font-size: 16px !important;"

def normalize_icon_format(icon_name):
    """Ensures icons have mdi- prefix for AppDaemon."""
    if not icon_name: return icon_name
    icon_name = icon_name.strip()
    if icon_name.startswith('mdi:'): return 'mdi-' + icon_name[4:]
    if icon_name.startswith('mdi-'): return icon_name
    return icon_name

# =========================================================================
# 5. FLASK ROUTE HANDLER
# =========================================================================
@app.route('/', methods=['GET', 'POST'])
def index():
    generated_yaml = ""
    ha_entities = get_ha_entities()
    dashboard_filename = "joandashboard.dash"
    dashboard_slug = "joandashboard"
    has_token = bool(TOKEN)
    save_message = None
    
    # Re-detect output directory on every request if it was null (retry logic)
    global OUTPUT_DIR
    if OUTPUT_DIR is None:
        print("⚠️ [RUNTIME] Output Directory is None, retrying detection...")
        OUTPUT_DIR = detect_dashboard_path(APPDAEMON_ADDON_SLUG)

    if request.method == 'POST':
        try:
            # Form Data Retrieval
            title = request.form.get('title', 'JoanDashboard')
            action_type = request.form.get('action_type', 'generate')
            
            dashboard_slug = title.lower().replace(" ", "_")
            dashboard_filename = dashboard_slug + ".dash"
            
            cols = request.form.get('grid_columns', '4')
            rows = request.form.get('grid_rows', '8')
            lang = request.form.get('ui_language', 'pl')
            
            default_size_str = request.form.get('default_widget_size', '2, 1')
            def_size_parts = default_size_str.split(',')
            def_w = int(def_size_parts[0].strip())
            def_h = int(def_size_parts[1].strip()) if len(def_size_parts) > 1 else 1

            # Translation Dictionary for State Maps
            TRANS = {
                'pl': {
                    'on': 'WŁĄCZONE', 'off': 'WYŁĄCZONE', 
                    'open': 'OTWARTE', 'closed': 'ZAMKNIĘTE', 
                    'opening': 'OTWIERANIE', 'closing': 'ZAMYKANIE', 
                    'locked': 'ZAMKNIĘTE', 'unlocked': 'OTWARTE', 
                    'home': 'W DOMU', 'not_home': 'POZA'
                },
                'en': {
                    'on': 'ON', 'off': 'OFF', 
                    'open': 'OPEN', 'closed': 'CLOSED', 
                    'opening': 'OPENING', 'closing': 'CLOSING', 
                    'locked': 'LOCKED', 'unlocked': 'UNLOCKED', 
                    'home': 'HOME', 'not_home': 'AWAY'
                }
            }
            dic = TRANS.get(lang, TRANS['pl'])

            # Calculate AppDaemon Columns (base unit 117px)
            if def_w == 1: 
                ad_columns = int(cols)
            else: 
                ad_columns = int(cols) * 2

            # ----------------------------------------
            # YAML HEADER GENERATION
            # ----------------------------------------
            generated_yaml += f"title: {title}\n"
            generated_yaml += "widget_dimensions: [117, 117]\n"
            generated_yaml += f"widget_size: [{def_w}, {def_h}]\n"
            generated_yaml += "widget_margins: [8, 8]\n"
            generated_yaml += f"columns: {ad_columns}\n"
            generated_yaml += f"rows: {rows}\n"
            generated_yaml += "global_parameters:\n"
            generated_yaml += "  use_comma: 0\n"
            generated_yaml += "  precision: 1\n"
            generated_yaml += "  use_hass_icon: 1\n"
            generated_yaml += "  namespace: default\n"
            generated_yaml += "  devices:\n"
            generated_yaml += "    media_player:\n"
            generated_yaml += "      step: 5\n"
            generated_yaml += "    climate:\n"
            generated_yaml += "      step: 1\n"
            generated_yaml += f"  white_text_style: \"{STYLE_TEXT}\"\n"
            generated_yaml += f"  state_text_style: \"{STYLE_STATE_TEXT}\"\n"
            generated_yaml += "skin: simplyred\n\n"
            
            layout_data_str = request.form.get('layout_data_json')
            custom_defs_str = request.form.get('custom_definitions_json', '{}')
            custom_defs = json.loads(custom_defs_str)
            
            processed_widgets = []
            
            # ----------------------------------------
            # LAYOUT SECTION GENERATION
            # ----------------------------------------
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
                        
                        # Size detection
                        if size_str == f"({def_w}x{def_h})": is_default = True
                        elif size_str == "(2x1)" and def_w == 2 and def_h == 1: is_default = True
                        elif size_str == "(1x1)" and def_w == 1 and def_h == 1: is_default = True
                        
                        if not is_default and size_str:
                            if not size_str.startswith('('): size_str = f"({size_str})"
                            widget_id += size_str
                            
                        row_parts.append(widget_id)
                        processed_widgets.append(w)
                        
                    generated_yaml += f"  - {', '.join(row_parts)}\n"
                
                generated_yaml += "\n# -------------------\n# WIDGET DEFINITIONS\n# -------------------\n\n"
                seen_ids = set()
                
                # ----------------------------------------
                # WIDGET DETAILS GENERATION
                # ----------------------------------------
                for w in processed_widgets: 
                    w_id = w['id']
                    if w_id in seen_ids: continue
                    seen_ids.add(w_id)
                    
                    # If imported and not edited, preserve original code
                    if w_id in custom_defs and not w.get('was_edited', False):
                        generated_yaml += f"{w_id}:\n"
                        for line in custom_defs[w_id].split('\n'):
                            if line.strip(): generated_yaml += f"  {line}\n"
                        generated_yaml += "\n"
                        continue

                    w_type = w['type']
                    w_name = w['name']
                    w_icon = normalize_icon_format(w['icon'])
                    i_on = normalize_icon_format(w.get('icon_on'))
                    i_off = normalize_icon_format(w.get('icon_off'))
                    
                    generated_yaml += f"{w_id}:\n"
                    
                    # === NAVIGATE ===
                    if w_type == 'navigate':
                        dash_target = w_id.replace('navigate.', '')
                        nav_icon = w_icon or 'mdi-arrow-right-circle'
                        generated_yaml += f"  widget_type: navigate\n"
                        generated_yaml += f"  title: \"{w_name}\"\n"
                        generated_yaml += f"  dashboard: {dash_target}\n"
                        generated_yaml += f"  icon_active: {nav_icon}\n"
                        generated_yaml += f"  icon_inactive: {nav_icon}\n"
                        generated_yaml += f"  title_style: \"{STYLE_TITLE}\"\n"
                        generated_yaml += f"  widget_style: \"{STYLE_WIDGET}\"\n"
                        generated_yaml += f"  icon_active_style: \"{STYLE_ICON}\"\n"
                        generated_yaml += f"  icon_inactive_style: \"{STYLE_ICON}\"\n"

                    # === SENSOR ===
                    elif w_type == 'sensor':
                        generated_yaml += f"  widget_type: sensor\n"
                        generated_yaml += f"  entity: {w_id}\n"
                        generated_yaml += f"  title: \"{w_name}\"\n"
                        generated_yaml += f"  title_style: \"{STYLE_TITLE}\"\n"
                        generated_yaml += f"  text_style: \"{STYLE_TEXT}\"\n"
                        generated_yaml += f"  value_style: \"{STYLE_VALUE}\"\n"
                        generated_yaml += f"  unit_style: \"{STYLE_UNIT}\"\n"
                        generated_yaml += f"  widget_style: \"{STYLE_WIDGET}\"\n"
                        if any(k in w_id for k in ['battery', 'bateria', 'level']):
                            generated_yaml += "  precision: 0\n"
                        else:
                            generated_yaml += "  precision: 1\n"

                    # === MEDIA PLAYER ===
                    elif w_type == 'media_player':
                        generated_yaml += f"  widget_type: media_player\n"
                        generated_yaml += f"  entity: {w_id}\n"
                        generated_yaml += f"  title: \"{w_name}\"\n"
                        if w_icon: generated_yaml += f"  icon: {w_icon}\n"
                        generated_yaml += f"  title_style: \"{STYLE_TITLE}\"\n"
                        generated_yaml += f"  widget_style: \"{STYLE_WIDGET}\"\n"
                        generated_yaml += f"  icon_style: \"{STYLE_ICON}\"\n"
                        generated_yaml += "  truncate_name: 20\n"
                        generated_yaml += "  step: 5\n"

                    # === CLIMATE ===
                    elif w_type == 'climate':
                        generated_yaml += f"  widget_type: climate\n"
                        generated_yaml += f"  entity: {w_id}\n"
                        generated_yaml += f"  title: \"{w_name}\"\n"
                        generated_yaml += f"  step: 1\n"
                        generated_yaml += f"  precision: 1\n"
                        generated_yaml += f"  title_style: \"{STYLE_TITLE}\"\n"
                        generated_yaml += f"  widget_style: \"{STYLE_WIDGET}\"\n"
                        generated_yaml += f"  icon_style: \"{STYLE_ICON}\"\n"

                    # === FAN ===
                    elif w_type == 'fan':
                        generated_yaml += f"  widget_type: fan\n"
                        generated_yaml += f"  entity: {w_id}\n"
                        generated_yaml += f"  title: \"{w_name}\"\n"
                        if i_on: generated_yaml += f"  icon_on: {i_on}\n"
                        if i_off: generated_yaml += f"  icon_off: {i_off}\n"
                        if w_icon and not i_on: generated_yaml += f"  icon: {w_icon}\n"
                        generated_yaml += "  low_speed: 33\n"
                        generated_yaml += "  medium_speed: 66\n"
                        generated_yaml += "  high_speed: 100\n"
                        generated_yaml += f"  title_style: \"{STYLE_TITLE}\"\n"
                        generated_yaml += f"  widget_style: \"{STYLE_WIDGET}\"\n"
                        generated_yaml += f"  icon_style_active: \"{STYLE_ICON}\"\n"
                        generated_yaml += f"  icon_style_inactive: \"{STYLE_ICON}; opacity: 0.5;\"\n"
                        # Speed Icons
                        generated_yaml += f"  speed1_icon_style_active: \"{STYLE_ICON}\"\n"
                        generated_yaml += f"  speed1_icon_style_inactive: \"{STYLE_ICON}; opacity: 0.3;\"\n"
                        generated_yaml += f"  speed2_icon_style_active: \"{STYLE_ICON}\"\n"
                        generated_yaml += f"  speed2_icon_style_inactive: \"{STYLE_ICON}; opacity: 0.3;\"\n"
                        generated_yaml += f"  speed3_icon_style_active: \"{STYLE_ICON}\"\n"
                        generated_yaml += f"  speed3_icon_style_inactive: \"{STYLE_ICON}; opacity: 0.3;\"\n"

                    # === SCENE ===
                    elif w_type == 'scene':
                        generated_yaml += f"  widget_type: scene\n"
                        generated_yaml += f"  entity: {w_id}\n"
                        generated_yaml += f"  title: \"{w_name}\"\n"
                        if w_icon: generated_yaml += f"  icon: {w_icon}\n"
                        elif i_on: generated_yaml += f"  icon: {i_on}\n" 
                        generated_yaml += f"  title_style: \"{STYLE_TITLE}\"\n"
                        generated_yaml += f"  widget_style: \"{STYLE_WIDGET}\"\n"
                        generated_yaml += f"  icon_style_active: \"{STYLE_ICON}\"\n"
                        generated_yaml += f"  icon_style_inactive: \"{STYLE_ICON}\"\n"

                    # === CLOCK ===
                    elif w_type == 'clock':
                        generated_yaml += f"  widget_type: clock\n"
                        generated_yaml += f"  time_format: 24hr\n"
                        generated_yaml += f"  show_seconds: 0\n"
                        generated_yaml += f"  date_style: \"{STYLE_TEXT}\"\n"
                        generated_yaml += f"  time_style: \"{STYLE_VALUE}\"\n"

                    # === LABEL ===
                    elif w_type == 'label':
                        generated_yaml += f"  widget_type: label\n"
                        generated_yaml += f"  text: \"{w_name}\"\n"
                        if w_icon: 
                            generated_yaml += f"  icon: {w_icon}\n"
                        generated_yaml += f"  text_style: \"{STYLE_TITLE}\"\n"
                    
                    # === GENERIC WIDGETS ===
                    else:
                        ad_type = w_type
                        if w_type == 'binary_sensor': ad_type = 'binary_sensor'
                        if w_type == 'input_boolean': ad_type = 'switch'
                        if w_type == 'person': ad_type = 'device_tracker'
                        if w_type == 'light': ad_type = 'switch'
                        if w_type == 'lock': ad_type = 'lock'
                        if w_type == 'input_select': ad_type = 'input_select'
                        if w_type == 'input_number': ad_type = 'input_number'
                        if w_type == 'script': ad_type = 'script'
                        if w_type == 'input_button': ad_type = 'script'
                        
                        generated_yaml += f"  widget_type: {ad_type}\n"
                        generated_yaml += f"  entity: {w_id}\n"
                        generated_yaml += f"  title: \"{w_name}\"\n"
                        
                        if i_on: generated_yaml += f"  icon_on: {i_on}\n"
                        if i_off: generated_yaml += f"  icon_off: {i_off}\n"
                        
                        if ad_type == 'lock':
                            if i_off: generated_yaml += f"  icon_locked: {i_off}\n"
                            if i_on: generated_yaml += f"  icon_unlocked: {i_on}\n"
                        
                        if w_icon and not i_on: 
                            generated_yaml += f"  icon: {w_icon}\n"
                        
                        generated_yaml += f"  state_text: 1\n"
                        generated_yaml += f"  title_style: \"{STYLE_TITLE}\"\n"
                        generated_yaml += f"  text_style: \"{STYLE_TEXT}\"\n"
                        generated_yaml += f"  widget_style: \"{STYLE_WIDGET}\"\n"
                        generated_yaml += f"  icon_style_active: \"{STYLE_ICON}\"\n"
                        generated_yaml += f"  icon_style_inactive: \"{STYLE_ICON}\"\n"
                        
                        if ad_type in ['cover', 'binary_sensor', 'switch', 'light', 'lock']: 
                            generated_yaml += "  state_map:\n"
                            if ad_type == 'cover':
                                for s in ['open', 'closed', 'opening', 'closing']: 
                                    generated_yaml += f"    \"{s}\": \"{dic.get(s, s)}\"\n"
                            elif ad_type == 'binary_sensor':
                                generated_yaml += f"    \"on\": \"{dic['open']}\"\n"
                                generated_yaml += f"    \"off\": \"{dic['closed']}\"\n"
                            elif ad_type == 'lock':
                                generated_yaml += f"    \"locked\": \"{dic['locked']}\"\n"
                                generated_yaml += f"    \"unlocked\": \"{dic['unlocked']}\"\n"
                            else:
                                generated_yaml += f"    \"on\": \"{dic['on']}\"\n"
                                generated_yaml += f"    \"off\": \"{dic['off']}\"\n"

                    generated_yaml += "\n"
            
            # ----------------------------------------
            # ACTION: SAVE FILE & RESTART APPDAEMON
            # ----------------------------------------
            if action_type == 'save_restart':
                # Check write permissions implicitly by output directory presence
                if OUTPUT_DIR is None:
                    save_message = "❌ CONFIG ERROR: Container cannot write to /config or /addon_configs. Please verify 'map' in config.json."
                else:
                    try:
                        # Ensure directory exists
                        if not os.path.exists(OUTPUT_DIR):
                            try:
                                print(f"ℹ️ [SAVE] Creating missing directory: {OUTPUT_DIR}")
                                os.makedirs(OUTPUT_DIR, exist_ok=True)
                            except OSError as e:
                                save_message = f"❌ Error creating directory {OUTPUT_DIR}: {e}"
                        
                        if not save_message: # Proceed if no errors
                            full_path = os.path.join(OUTPUT_DIR, dashboard_filename)
                            print(f"ℹ️ [SAVE] Writing file to: {full_path}")
                            
                            # Write file
                            with open(full_path, "w", encoding="utf-8") as f:
                                f.write(generated_yaml)
                            
                            # --- CRITICAL PERMISSION FIX ---
                            # This ensures that AppDaemon (running as a different user)
                            # can actually read the file created by this generator.
                            try:
                                os.chmod(full_path, 0o666) # Read/Write for everyone
                                print(f"✅ [PERM] Permissions set to 666 for {full_path}")
                            except Exception as e:
                                print(f"⚠️ [PERM] Could not set permissions: {e}")
                            # -------------------------------

                            # --- FILE VERIFICATION ---
                            if os.path.exists(full_path):
                                size = os.path.getsize(full_path)
                                print(f"✅ [VERIFY] File confirmed on disk. Size: {size} bytes.")
                            else:
                                print("❌ [VERIFY] File NOT found after write operation!")
                            # -------------------------

                            # Restart Add-on
                            success, msg = restart_appdaemon()
                            if success:
                                save_message = f"✅ Success: Saved to {full_path} and restarted AppDaemon."
                            else:
                                save_message = f"⚠️ File saved, but restart failed: {msg}"
                            
                    except Exception as e:
                        print(f"❌ [SAVE] Exception: {e}")
                        save_message = f"❌ Exception during file save: {e}"

        except Exception as e: 
            print(f"❌ Error generating YAML: {e}")
            generated_yaml = f"# ERROR GENERATING YAML: {e}"

    return render_template('index.html', generated_yaml=generated_yaml, entities=ha_entities, filename=dashboard_filename, dash_name=dashboard_slug, has_token=has_token, save_message=save_message)

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000, debug=True)
