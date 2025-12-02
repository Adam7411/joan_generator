print("📦 1. Importing libraries...")
from flask import Flask, render_template, request
import os
import requests
import json
print("✅ 2. Libraries loaded.")

app = Flask(__name__)

# -------------------------------------------------------------------------
# KONFIGURACJA API I TOKENU
# -------------------------------------------------------------------------
TOKEN = os.environ.get('SUPERVISOR_TOKEN')
API_URL = "http://supervisor/core/api" 
TOKEN_SOURCE = "System (Supervisor)"

# Próba odczytu tokenu z konfiguracji dodatku (dla trybu manualnego)
try:
    if os.path.exists('/data/options.json'):
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
    print("❌ WARNING: No token found. Entity list will be empty!")
else:
    print(f"🔑 Token Source: {TOKEN_SOURCE}")

# -------------------------------------------------------------------------
# POBIERANIE ENCJI Z HA (Z PEŁNYMI DANYMI O STANIE)
# -------------------------------------------------------------------------
def get_ha_entities():
    if not TOKEN:
        return []
    
    headers = {
        "Authorization": f"Bearer {TOKEN}", 
        "Content-Type": "application/json"
    }
    
    try:
        # Pobieramy wszystkie stany z Home Assistant
        # To zapytanie zwraca listę wszystkich encji wraz z ich aktualnym stanem
        response = requests.get(f"{API_URL}/states", headers=headers, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            entities = []
            for state in data:
                # Przekazujemy ID, STAN, ATRYBUTY (nazwa, klasa) i JEDNOSTKĘ
                # To jest kluczowe, żeby podgląd w HTML pokazywał prawdziwe dane
                attributes = state.get('attributes', {})
                unit = attributes.get('unit_of_measurement', '')
                
                entities.append({
                    'id': state['entity_id'],
                    'state': state['state'],
                    'attributes': attributes,
                    'unit': unit
                })
            
            # Sortowanie alfabetyczne po ID dla porządku
            entities.sort(key=lambda x: x['id'])
            return entities
        else:
            print(f"⚠️ API Error: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"❌ Exception while fetching entities: {e}")
    return []

# -------------------------------------------------------------------------
# STYLE E-INK (High Contrast - Joan 6)
# -------------------------------------------------------------------------
STYLES = {
    "title": "color: #000000; font-size: 20px; font-weight: 700; text-align: center; padding-top: 3px; width: 100%; font-family: 'Roboto', 'Arial Black', sans-serif;",
    "widget": "color: #000000 !important; background-color: #FFFFFF !important;",
    "text": "color: #000000 !important; font-weight: 700 !important;",
    "value": "color: #000000 !important; font-size: 44px !important; font-weight: 700 !important;",
    "unit": "color: #000000 !important;",
    "icon": "color: #000000 !important;",
    "state_text": "color: #000000 !important; font-weight: 700 !important; font-size: 16px !important;"
}

# Pomocnicza funkcja do ikon (fallback dla Pythona)
def get_icon_pair(base_icon, w_type):
    if not base_icon:
        if w_type == 'lock': return 'mdi-lock-open', 'mdi-lock'
        if w_type == 'cover': return 'mdi-window-shutter-open', 'mdi-window-shutter'
        if w_type == 'person' or w_type == 'device_tracker': return 'mdi-home', 'mdi-home-outline'
        return None, None
        
    i = base_icon.lower()
    if 'garage' in i: return 'mdi-garage-open', 'mdi-garage'
    if 'gate' in i: return 'mdi-gate-open', 'mdi-gate'
    if 'light' in i or 'bulb' in i: return 'mdi-lightbulb-on', 'mdi-lightbulb-outline'
    if 'lock' in i: return 'mdi-lock-open', 'mdi-lock'
    if 'door' in i: return 'mdi-door-open', 'mdi-door-closed'
    if 'window' in i or 'blind' in i or 'shutter' in i: return 'mdi-window-shutter-open', 'mdi-window-shutter'
    return i, i + '-outline'

@app.route('/', methods=['GET', 'POST'])
def index():
    generated_yaml = ""
    ha_entities = get_ha_entities()
    dashboard_filename = ""
    dashboard_slug = ""
    
    if request.method == 'POST':
        try:
            title = request.form.get('title', 'JoanDashboard')
            dashboard_slug = title.lower().replace(" ", "_")
            dashboard_filename = dashboard_slug + ".dash"
            lang = request.form.get('ui_language', 'pl')
            
            # Tłumaczenia stanów dla AppDaemon (state_map)
            T = {
                'pl': {'on': 'WŁĄCZONE', 'off': 'WYŁĄCZONE', 'open': 'OTWARTE', 'closed': 'ZAMKNIĘTE', 
                       'opening': 'OTWIERANIE', 'closing': 'ZAMYKANIE',
                       'locked': 'ZAMKNIĘTE', 'unlocked': 'OTWARTE', 'home': 'W DOMU', 'not_home': 'POZA'},
                'en': {'on': 'ON', 'off': 'OFF', 'open': 'OPEN', 'closed': 'CLOSED', 
                       'opening': 'OPENING', 'closing': 'CLOSING',
                       'locked': 'LOCKED', 'unlocked': 'UNLOCKED', 'home': 'HOME', 'not_home': 'AWAY'}
            }
            dic = T.get(lang, T['pl'])

            # --- NAGŁÓWEK PLIKU DASH ---
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
            generated_yaml += "  devices:\n"
            generated_yaml += "    media_player:\n"
            generated_yaml += "      step: 5\n"
            generated_yaml += f"  white_text_style: \"{STYLES['text']}\"\n"
            generated_yaml += f"  state_text_style: \"{STYLES['state_text']}\"\n"
            generated_yaml += "skin: simplyred\n\n"
            
            layout_data_str = request.form.get('layout_data_json')
            if layout_data_str:
                layout_rows = json.loads(layout_data_str)
                generated_yaml += "layout:\n"
                processed_widgets = []
                
                # --- GENEROWANIE SEKCJI LAYOUT ---
                for row in layout_rows:
                    if not row: continue
                    row_parts = []
                    for w in row:
                        if w['type'] == 'spacer':
                            row_parts.append("spacer")
                            continue
                            
                        widget_str = w['id']
                        size = w.get('size', '').strip()
                        # Jeśli rozmiar jest inny niż domyślny [2,1] z nagłówka, dodajemy go
                        if size and size != "(2x1)":
                            if not size.startswith('('): size = f"({size})"
                            widget_str += size
                        row_parts.append(widget_str)
                    
                    row_str = ", ".join(row_parts)
                    generated_yaml += f"  - {row_str}\n"
                    processed_widgets.extend(row)
                
                generated_yaml += "\n# --- WIDGET DEFINITIONS ---\n\n"
                
                # --- GENEROWANIE DEFINICJI WIDGETÓW ---
                seen_ids = set()
                for w in processed_widgets:
                    if w['type'] == 'spacer': continue
                    w_id = w['id']
                    if w_id in seen_ids: continue
                    seen_ids.add(w_id)
                    
                    w_type = w['type']
                    w_name = w['name']
                    w_icon = w['icon']
                    
                    generated_yaml += f"{w_id}:\n"
                    generated_yaml += f"  widget_type: {w_type}\n"
                    generated_yaml += f"  entity: {w_id}\n"
                    generated_yaml += f"  title: \"{w_name}\"\n"
                    
                    # 1. NAWIGACJA
                    if w_type == 'navigate':
                        dashboard_name = w_id.replace('navigate.', '')
                        # Nadpisz entity linię wyżej bo navigate nie ma entity
                        generated_yaml = generated_yaml.replace(f"  entity: {w_id}\n", "") 
                        generated_yaml += f"  dashboard: {dashboard_name}\n"
                        generated_yaml += f"  icon_inactive: {w_icon or 'mdi-arrow-right-circle'}\n"
                        generated_yaml += f"  title_style: \"{STYLES['title']}\"\n"
                        generated_yaml += f"  widget_style: \"background-color: #FFFFFF !important; border-radius: 8px !important; padding: 10px !important; color: #000000 !important;\"\n"
                    
                    # 2. SENSOR
                    elif w_type == 'sensor':
                        generated_yaml += f"  title_style: \"{STYLES['title']}\"\n"
                        generated_yaml += f"  text_style: \"{STYLES['text']}\"\n"
                        generated_yaml += f"  value_style: \"{STYLES['value']}\"\n"
                        generated_yaml += f"  unit_style: \"{STYLES['unit']}\"\n"
                        generated_yaml += f"  widget_style: \"{STYLES['widget']}\"\n"
                        if w_icon: generated_yaml += f"  icon: {w_icon}\n"

                    # 3. MEDIA PLAYER
                    elif w_type == 'media_player':
                        generated_yaml += f"  truncate_name: 20\n"
                        generated_yaml += f"  step: 5\n"
                        generated_yaml += f"  title_style: \"{STYLES['title']}\"\n"
                        generated_yaml += f"  widget_style: \"{STYLES['widget']}\"\n"
                        generated_yaml += f"  icon_style: \"{STYLES['icon']}\"\n"

                    # 4. CLIMATE
                    elif w_type == 'climate':
                        generated_yaml += f"  step: 1\n"
                        generated_yaml += f"  title_style: \"{STYLES['title']}\"\n"
                        generated_yaml += f"  widget_style: \"{STYLES['widget']}\"\n"
                        generated_yaml += f"  state_text: 1\n"
                        generated_yaml += f"  text_style: \"{STYLES['text']}\"\n"
                        generated_yaml += f"  icon_style_active: \"{STYLES['icon']}\"\n"
                        generated_yaml += f"  icon_style_inactive: \"{STYLES['icon']}\"\n"

                    # 5. ZEGAR
                    elif w_type == 'clock':
                        generated_yaml = generated_yaml.replace(f"  entity: {w_id}\n", "")
                        generated_yaml += f"  time_format: 24hr\n"
                        generated_yaml += f"  show_seconds: 0\n"
                        generated_yaml += f"  date_style: \"{STYLES['text']}\"\n"
                        generated_yaml += f"  time_style: \"{STYLES['value']} font-size: 50px !important;\"\n"

                    # 6. ETYKIETA
                    elif w_type == 'label':
                         generated_yaml = generated_yaml.replace(f"  entity: {w_id}\n", "")
                         generated_yaml += f"  text: \"{w_name}\"\n"
                         if w_icon: generated_yaml += f"  icon: {w_icon}\n"
                    
                    # 7. INNE (Actionable - Switch, Light, Binary Sensor, Lock)
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
                        
                        # Pobieramy dokładne ikony z obiektu widgetu (JSON z JS)
                        current_w_json = next((item for item in processed_widgets if item["id"] == w_id), None)
                        
                        if current_w_json:
                            i_on = current_w_json.get('icon_on')
                            i_off = current_w_json.get('icon_off')
                            
                            if ad_type == 'lock':
                                if i_off: generated_yaml += f"  icon_locked: {i_off}\n"
                                if i_on: generated_yaml += f"  icon_unlocked: {i_on}\n"
                            else:
                                if i_on: generated_yaml += f"  icon_on: {i_on}\n"
                                if i_off: generated_yaml += f"  icon_off: {i_off}\n"
                        
                        generated_yaml += f"  title_style: \"{STYLES['title']}\"\n"
                        generated_yaml += f"  widget_style: \"{STYLES['widget']}\"\n"
                        generated_yaml += f"  icon_style_active: \"{STYLES['icon']}\"\n"
                        generated_yaml += f"  icon_style_inactive: \"{STYLES['icon']}\"\n"
                        generated_yaml += f"  state_text: 1\n"
                        generated_yaml += f"  text_style: \"{STYLES['text']}\"\n"
                        
                        if ad_type in ['switch', 'binary_sensor', 'cover', 'lock', 'device_tracker']:
                            generated_yaml += "  state_map:\n"
                            generated_yaml += f"    \"on\": \"{dic['on']}\"\n"
                            generated_yaml += f"    \"off\": \"{dic['off']}\"\n"
                            generated_yaml += f"    \"open\": \"{dic['open']}\"\n"
                            generated_yaml += f"    \"closed\": \"{dic['closed']}\"\n"
                            generated_yaml += f"    \"opening\": \"{dic['opening']}\"\n"
                            generated_yaml += f"    \"closing\": \"{dic['closing']}\"\n"
                            generated_yaml += f"    \"locked\": \"{dic['locked']}\"\n"
                            generated_yaml += f"    \"unlocked\": \"{dic['unlocked']}\"\n"
                            generated_yaml += f"    \"home\": \"{dic['home']}\"\n"
                            generated_yaml += f"    \"not_home\": \"{dic['not_home']}\"\n"

                    generated_yaml += "\n"
        except Exception as e:
            print(f"❌ Error generating YAML: {e}")
            generated_yaml = f"# ERROR GENERATING YAML: {e}"

    return render_template('index.html', generated_yaml=generated_yaml, entities=ha_entities, filename=dashboard_filename, dash_name=dashboard_slug)

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000, debug=True)
