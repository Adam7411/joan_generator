print("📦 1. Importing libraries...")
from flask import Flask, render_template, request
import os
import requests
import json
print("✅ 2. Libraries loaded.")

app = Flask(__name__)

# --- TOKEN CONFIGURATION ---
TOKEN = os.environ.get('SUPERVISOR_TOKEN')
API_URL = "http://supervisor/core/api" 
TOKEN_SOURCE = "System (Supervisor)"

try:
    with open('/data/options.json', 'r') as f:
        options = json.load(f)
        manual_token = options.get('manual_token')
        if manual_token and len(manual_token) > 10:
            TOKEN = manual_token
            API_URL = "http://homeassistant:8123/api"
            TOKEN_SOURCE = "Manual (Configuration)"
            print("🔧 Manual token found. Switching API URL to http://homeassistant:8123/api")
except Exception as e:
    print(f"ℹ️ Info: Could not read options (first run?): {e}")

if not TOKEN:
    print("❌ WARNING: No token found (neither System nor Manual) !!!")
else:
    print(f"🔑 Token Source: {TOKEN_SOURCE}")

def get_ha_entities():
    if not TOKEN:
        return []
    headers = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
    try:
        print(f"🌍 Fetching entities from: {API_URL}/states")
        response = requests.get(f"{API_URL}/states", headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            entities = [state['entity_id'] for state in data]
            entities.sort()
            print(f"✅ SUCCESS! Fetched {len(entities)} entities.")
            return entities
        else:
            print(f"⚠️ Home Assistant API Error: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"❌ Exception while fetching entities: {e}")
    return []

# E-Ink Styles
STYLES = {
    "title": "color: #000000; font-size: 20px; font-weight: 700; text-align: center; padding-top: 5px; width: 100%; font-family: 'Roboto', 'Arial Black', sans-serif;",
    "widget": "color: #000000 !important; background-color: #FFFFFF !important; border: 2px solid #000000 !important;",
    "text": "color: #000000 !important; font-weight: 700 !important;",
    "value": "color: #000000 !important; font-size: 44px !important; font-weight: 700 !important;",
    "unit": "color: #000000 !important;",
    "icon": "color: #000000 !important;"
}

# --- SMART ICONS ---
def get_icon_pair(base_icon, w_type):
    """Zwraca parę ikon lub None, jeśli brak ikony bazowej."""
    if not base_icon:
        return None, None

    i = base_icon.lower()
    if 'garage' in i: return 'mdi-garage-open', 'mdi-garage'
    if 'gate' in i: return 'mdi-gate-open', 'mdi-gate'
    if 'light' in i or 'bulb' in i: return 'mdi-lightbulb-on', 'mdi-lightbulb-outline'
    if 'lock' in i: return 'mdi-lock-open', 'mdi-lock'
    if 'door' in i: return 'mdi-door-open', 'mdi-door-closed'
    if 'window' in i or 'blind' in i or 'shutter' in i: return 'mdi-window-shutter-open', 'mdi-window-shutter'
    
    if 'off' in i or 'outline' in i:
        return i.replace('-off', '').replace('-outline', ''), i
    return i, i + '-outline'

@app.route('/', methods=['GET', 'POST'])
def index():
    generated_yaml = ""
    ha_entities = get_ha_entities()
    dashboard_filename = ""
    
    if request.method == 'POST':
        title = request.form.get('title', 'JoanDashboard')
        dashboard_filename = title.lower().replace(" ", "_") + ".dash"
        lang = request.form.get('ui_language', 'pl')
        
        T = {
            'pl': {'on': 'WŁĄCZONE', 'off': 'WYŁĄCZONE', 'open': 'OTWARTE', 'closed': 'ZAMKNIĘTE', 
                   'opening': 'OTWIERANIE', 'closing': 'ZAMYKANIE', 'locked': 'ZAMKNIĘTE', 'unlocked': 'OTWARTE'},
            'en': {'on': 'ON', 'off': 'OFF', 'open': 'OPEN', 'closed': 'CLOSED', 
                   'opening': 'OPENING', 'closing': 'CLOSING', 'locked': 'LOCKED', 'unlocked': 'UNLOCKED'}
        }
        dic = T.get(lang, T['pl'])

        generated_yaml += f"# --- JOAN 6 E-INK DASHBOARD ---\n"
        generated_yaml += f"# File: {dashboard_filename}\n"
        generated_yaml += f"# Location: \\\\IP_HA\\addon_configs\\appdaemon\\dashboards\\\n"
        generated_yaml += f"# --------------------------------\n\n"

        generated_yaml += f"title: {title}\n"
        generated_yaml += "widget_dimensions: [117, 117]\n"
        generated_yaml += "widget_size: [2, 1]\n"
        generated_yaml += "widget_margins: [8, 8]\n"
        generated_yaml += "columns: 6\n"
        generated_yaml += "rows: 9\n"
        
        generated_yaml += "global_parameters:\n"
        generated_yaml += "  use_comma: 0\n"
        generated_yaml += "  precision: 1\n"
        generated_yaml += "  use_hass_icon: 1\n"
        generated_yaml += "  namespace: default\n"
        generated_yaml += "  state_text: 1\n"
        generated_yaml += f"  title_style: \"{STYLES['title']}\"\n"
        generated_yaml += f"  text_style: \"{STYLES['text']}\"\n"
        generated_yaml += f"  state_text_style: \"color: #000000 !important; font-weight: 700 !important; font-size: 14px; text-transform: uppercase; margin-top: 5px;\"\n"
        generated_yaml += f"  widget_style: \"{STYLES['widget']}\"\n"
        generated_yaml += f"  icon_style_active: \"{STYLES['icon']}\"\n"
        generated_yaml += f"  icon_style_inactive: \"{STYLES['icon']}\"\n"
        
        generated_yaml += "skin: simplyred\n\n"
        
        layout_data_str = request.form.get('layout_data_json')
        if layout_data_str:
            try:
                layout_rows = json.loads(layout_data_str)
                generated_yaml += "layout:\n"
                processed_widgets = []
                
                for row in layout_rows:
                    if not row: continue
                    row_parts = []
                    for w in row:
                        widget_str = w['id']
                        size = w.get('size', '').strip()
                        if size:
                            if not size.startswith('('): size = f"({size})"
                            widget_str += size
                        row_parts.append(widget_str)
                    
                    row_str = ", ".join(row_parts)
                    generated_yaml += f"  - {row_str}\n"
                    processed_widgets.extend(row)
                
                generated_yaml += "\n# --- WIDGET DEFINITIONS ---\n\n"
                
                seen_ids = set()
                for w in processed_widgets:
                    w_id = w['id']
                    if w_id in seen_ids: continue
                    seen_ids.add(w_id)
                    
                    w_type = w['type']
                    w_name = w['name']
                    w_icon = w['icon']
                    
                    generated_yaml += f"{w_id}:\n"
                    generated_yaml += f"  title: \"{w_name}\"\n"
                    
                    # 1. NAVIGATE
                    if w_type == 'navigate':
                        dashboard_name = w_id.replace('navigate.', '')
                        generated_yaml += f"  widget_type: navigate\n"
                        generated_yaml += f"  dashboard: {dashboard_name}\n"
                        # Dla navigate ikona jest wymagana lub domyślna
                        nav_icon = w_icon if w_icon else 'mdi-arrow-right-circle'
                        generated_yaml += f"  icon_inactive: {nav_icon}\n"
                        generated_yaml += f"  widget_style: \"background-color: #FFFFFF !important; border-radius: 8px !important; padding: 10px !important; color: #000000 !important;\"\n"
                        generated_yaml += f"  icon_style_inactive: \"color: #000000 !important;\"\n"
                    
                    # 2. SENSOR
                    elif w_type == 'sensor':
                        generated_yaml += f"  widget_type: sensor\n"
                        generated_yaml += f"  entity: {w_id}\n"
                        generated_yaml += f"  value_style: \"{STYLES['value']}\"\n"
                        generated_yaml += f"  unit_style: \"{STYLES['unit']}\"\n"
                        if w_icon:
                            generated_yaml += f"  icon: {w_icon}\n"
                    
                    # 3. MEDIA PLAYER
                    elif w_type == 'media_player':
                        generated_yaml += f"  widget_type: media_player\n"
                        generated_yaml += f"  entity: {w_id}\n"
                        generated_yaml += f"  truncate_name: 20\n"
                        generated_yaml += f"  step: 5\n"

                    # 4. LABEL / SCENE
                    elif w_type == 'label':
                         generated_yaml += f"  widget_type: label\n"
                         generated_yaml += f"  text: \"{w_name}\"\n" # Name is text
                         if w_icon:
                             generated_yaml += f"  icon: {w_icon}\n"

                    # 5. OTHERS (Switch, Cover, etc.)
                    else:
                        ad_type = w_type
                        if w_type == 'binary_sensor': ad_type = 'binary_sensor'
                        if w_type == 'input_boolean': ad_type = 'switch'
                        
                        generated_yaml += f"  widget_type: {ad_type}\n"
                        generated_yaml += f"  entity: {w_id}\n"
                        
                        # --- IKONY ---
                        # Generujemy tylko jeśli użytkownik podał ikonę
                        if w_icon:
                            icon_on, icon_off = get_icon_pair(w_icon, ad_type)
                            # Jeśli get_icon_pair zwróciło coś sensownego
                            if icon_on: generated_yaml += f"  icon_on: {icon_on}\n"
                            if icon_off: generated_yaml += f"  icon_off: {icon_off}\n"
                        
                        generated_yaml += f"  state_text: 1\n"
                        
                        generated_yaml += "  state_map:\n"
                        generated_yaml += f"    \"on\": \"{dic['on']}\"\n"
                        generated_yaml += f"    \"off\": \"{dic['off']}\"\n"
                        
                        if w_type == 'cover' or w_type == 'binary_sensor':
                            generated_yaml += f"    \"open\": \"{dic['open']}\"\n"
                            generated_yaml += f"    \"closed\": \"{dic['closed']}\"\n"
                            generated_yaml += f"    \"opening\": \"{dic['opening']}\"\n"
                            generated_yaml += f"    \"closing\": \"{dic['closing']}\"\n"
                        
                        if w_type == 'lock':
                             generated_yaml += f"    \"locked\": \"{dic['locked']}\"\n"
                             generated_yaml += f"    \"unlocked\": \"{dic['unlocked']}\"\n"

                    generated_yaml += "\n"
            except Exception as e:
                print(f"❌ Error processing JSON: {e}")

    return render_template('index.html', generated_yaml=generated_yaml, entities=ha_entities, filename=dashboard_filename)

if __name__ == "__main__":
    print("🚀 3. Starting Dev Server...")
    app.run(host='0.0.0.0', port=5000, debug=False)
