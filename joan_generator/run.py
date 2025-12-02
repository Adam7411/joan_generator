print("📦 1. Importing libraries...")
from flask import Flask, render_template, request
import os
import requests
import json
print("✅ 2. Libraries loaded.")

app = Flask(__name__)

# -------------------------------------------------------------------------
# 1. KONFIGURACJA API I TOKENU
# -------------------------------------------------------------------------
TOKEN = os.environ.get('SUPERVISOR_TOKEN')
API_URL = "http://supervisor/core/api" 
TOKEN_SOURCE = "System (Supervisor)"

try:
    if os.path.exists('/data/options.json'):
        with open('/data/options.json', 'r') as f:
            options = json.load(f)
            manual_token = options.get('manual_token')
            if manual_token and len(manual_token) > 10:
                TOKEN = manual_token
                API_URL = "http://homeassistant:8123/api"
                TOKEN_SOURCE = "Manual (Konfiguracja)"
                print("🔧 Manual token found. API: " + API_URL)
except Exception as e:
    print(f"ℹ️ Info: {e}")

if not TOKEN:
    print("❌ WARNING: No token found. Entity list will be empty!")
else:
    print(f"🔑 Token Source: {TOKEN_SOURCE}")

# -------------------------------------------------------------------------
# 2. POBIERANIE ENCJI Z HA
# -------------------------------------------------------------------------
def get_ha_entities():
    if not TOKEN: return []
    
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
                # Przekazujemy pełne dane: ID, Stan, Atrybuty (Friendly Name), Jednostka
                attr = state.get('attributes', {})
                entities.append({
                    'id': state['entity_id'],
                    'state': state['state'],
                    'attributes': attr,
                    'unit': attr.get('unit_of_measurement', ''),
                    'friendly_name': attr.get('friendly_name', state['entity_id'])
                })
            entities.sort(key=lambda x: x['id'])
            return entities
        else:
            print(f"⚠️ API Error: {response.status_code}")
    except Exception as e:
        print(f"❌ Exception: {e}")
    return []

# -------------------------------------------------------------------------
# 3. STYLE (JOAN 6) - POPRAWIONE POZYCJONOWANIE
# -------------------------------------------------------------------------
# STYLE_VALUE ma dodany padding-top, aby obniżyć liczby o ~3mm
STYLE_TITLE = "color: #000000; font-size: 20px; font-weight: 700; text-align: center; padding-top: 3px; width: 100%; font-family: 'Roboto', 'Arial Black', sans-serif;"
STYLE_WIDGET = "color: #000000 !important; background-color: #FFFFFF !important;"
STYLE_TEXT = "color: #000000 !important; font-weight: 700 !important;"
# Zmiana tutaj: padding-top: 15px przesuwa wartość w dół
STYLE_VALUE = "color: #000000 !important; font-size: 44px !important; font-weight: 700 !important; padding-top: 15px !important; line-height: 1.2 !important;"
STYLE_UNIT = "color: #000000 !important;"
STYLE_ICON = "color: #000000 !important;"
STYLE_STATE_TEXT = "color: #000000 !important; font-weight: 700 !important; font-size: 16px !important;"

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
    if 'window' in i or 'blind' in i: return 'mdi-window-shutter-open', 'mdi-window-shutter'
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
            
            # Pobieranie siatki (Smart Grid)
            cols = request.form.get('grid_columns', '6')
            rows = request.form.get('grid_rows', '8')
            
            lang = request.form.get('ui_language', 'pl')
            
            # Tłumaczenia stanów
            T = {
                'pl': {'on': 'WŁĄCZONE', 'off': 'WYŁĄCZONE', 'open': 'OTWARTE', 'closed': 'ZAMKNIĘTE', 
                       'opening': 'OTWIERANIE', 'closing': 'ZAMYKANIE',
                       'locked': 'ZAMKNIĘTE', 'unlocked': 'OTWARTE', 'home': 'W DOMU', 'not_home': 'POZA'},
                'en': {'on': 'ON', 'off': 'OFF', 'open': 'OPEN', 'closed': 'CLOSED', 
                       'opening': 'OPENING', 'closing': 'CLOSING',
                       'locked': 'LOCKED', 'unlocked': 'UNLOCKED', 'home': 'HOME', 'not_home': 'AWAY'}
            }
            dic = T.get(lang, T['pl'])

            # --- NAGŁÓWEK PLIKU ---
            generated_yaml += f"title: {title}\n"
            generated_yaml += "widget_dimensions: [117, 117]\n"
            generated_yaml += "widget_size: [2, 1]\n"
            generated_yaml += "widget_margins: [8, 8]\n"
            generated_yaml += f"columns: {cols}\n"
            generated_yaml += f"rows: {rows}\n"
            
            generated_yaml += "global_parameters:\n"
            generated_yaml += "  use_comma: 0\n"
            generated_yaml += "  precision: 1\n"
            generated_yaml += "  use_hass_icon: 1\n"
            generated_yaml += "  namespace: default\n"
            generated_yaml += "  devices:\n"
            generated_yaml += "    media_player:\n"
            generated_yaml += "      step: 5\n"
            generated_yaml += f"  white_text_style: \"{STYLE_TEXT}\"\n"
            generated_yaml += f"  state_text_style: \"{STYLE_STATE_TEXT}\"\n"
            generated_yaml += "skin: simplyred\n\n"
            
            layout_data_str = request.form.get('layout_data_json')
            if layout_data_str:
                layout_rows = json.loads(layout_data_str)
                generated_yaml += "layout:\n"
                processed_widgets = []
                
                # --- LAYOUT ---
                for row in layout_rows:
                    if not row: continue
                    row_parts = []
                    for w in row:
                        if w['type'] == 'spacer':
                            row_parts.append("spacer")
                            continue
                        
                        widget_str = w['id']
                        size = w.get('size', '').strip()
                        # Domyślny rozmiar [2,1], jeśli inny - dodajemy
                        if size and size != "(2x1)":
                            if not size.startswith('('): size = f"({size})"
                            widget_str += size
                        row_parts.append(widget_str)
                    
                    generated_yaml += f"  - {', '.join(row_parts)}\n"
                    processed_widgets.extend(row)
                
                generated_yaml += "\n# -------------------\n# DEFINICJE WIDŻETÓW\n# -------------------\n\n"
                
                # --- DEFINICJE ---
                seen_ids = set()
                for w in processed_widgets:
                    if w['type'] == 'spacer': continue
                    w_id = w['id']
                    if w_id in seen_ids: continue
                    seen_ids.add(w_id)
                    
                    w_type = w['type']
                    w_name = w['name']
                    w_icon = w['icon']
                    i_on = w.get('icon_on')
                    i_off = w.get('icon_off')
                    
                    generated_yaml += f"{w_id}:\n"
                    
                    # 1. NAWIGACJA
                    if w_type == 'navigate':
                        dash_name = w_id.replace('navigate.', '')
                        generated_yaml += f"  widget_type: navigate\n"
                        generated_yaml += f"  title: \"{w_name}\"\n"
                        generated_yaml += f"  dashboard: {dash_name}\n"
                        generated_yaml += f"  icon_inactive: {w_icon or 'mdi-arrow-right-circle'}\n"
                        generated_yaml += f"  title_style: \"color: #000000; font-size: 24px; font-weight: 700; text-align: center; padding-top: 5px; width: 100%; font-family: 'Roboto', 'Arial Black', sans-serif;\"\n"
                        generated_yaml += f"  widget_style: \"background-color: #FFFFFF !important; border-radius: 8px !important; padding: 10px !important; color: #000000 !important;\"\n"
                    
                    # 2. SENSOR (UŻYWA OBNIŻONEGO VALUE_STYLE)
                    elif w_type == 'sensor':
                        generated_yaml += f"  widget_type: sensor\n"
                        generated_yaml += f"  entity: {w_id}\n"
                        generated_yaml += f"  title: \"{w_name}\"\n"
                        if w_icon: generated_yaml += f"  icon: {w_icon}\n"
                        generated_yaml += f"  title_style: \"{STYLE_TITLE}\"\n"
                        generated_yaml += f"  text_style: \"{STYLE_TEXT}\"\n"
                        generated_yaml += f"  value_style: \"{STYLE_VALUE}\"\n"
                        generated_yaml += f"  unit_style: \"{STYLE_UNIT}\"\n"
                        generated_yaml += f"  widget_style: \"{STYLE_WIDGET}\"\n"
                        if 'bateria' in w_id or 'battery' in w_id:
                            generated_yaml += "  precision: 0\n"

                    # 3. MEDIA PLAYER
                    elif w_type == 'media_player':
                        generated_yaml += f"  widget_type: media_player\n"
                        generated_yaml += f"  entity: {w_id}\n"
                        generated_yaml += f"  title: \"{w_name}\"\n"
                        if w_icon: generated_yaml += f"  icon: {w_icon}\n"
                        generated_yaml += f"  title_style: \"{STYLE_TITLE}\"\n"
                        generated_yaml += f"  widget_style: \"{STYLE_WIDGET}\"\n"
                        generated_yaml += f"  icon_style: \"{STYLE_ICON}\"\n"
                        generated_yaml += f"  truncate_name: 20\n"

                    # 4. CLIMATE
                    elif w_type == 'climate':
                        generated_yaml += f"  widget_type: climate\n"
                        generated_yaml += f"  entity: {w_id}\n"
                        generated_yaml += f"  title: \"{w_name}\"\n"
                        generated_yaml += f"  title_style: \"{STYLE_TITLE}\"\n"
                        generated_yaml += "  units: \"°C\"\n"
                        generated_yaml += "  step: 1\n"
                        generated_yaml += "  state_text: 1\n"
                        generated_yaml += f"  text_style: \"{STYLE_TEXT}\"\n"
                        generated_yaml += f"  widget_style: \"{STYLE_WIDGET}\"\n"
                        generated_yaml += "  state_map:\n"
                        generated_yaml += "    \"off\": \"WYŁĄCZONA\"\n"
                        generated_yaml += "    \"auto\": \"AUTO\"\n"
                        generated_yaml += "    \"heat\": \"GRZANIE\"\n"
                        generated_yaml += "    \"cool\": \"CHŁODZENIE\"\n"
                        generated_yaml += "    \"dry\": \"OSUSZANIE\"\n"
                        generated_yaml += "    \"fan_only\": \"WENTYLATOR\"\n"
                        generated_yaml += f"  icon_style_active: \"{STYLE_ICON}\"\n"
                        generated_yaml += f"  icon_style_inactive: \"{STYLE_ICON}\"\n"

                    # 5. ZEGAR
                    elif w_type == 'clock':
                        generated_yaml = generated_yaml.replace(f"  entity: {w_id}\n", "")
                        generated_yaml += f"  time_format: 24hr\n"
                        generated_yaml += f"  show_seconds: 0\n"
                        generated_yaml += f"  date_style: \"{STYLE_TEXT}\"\n"
                        generated_yaml += f"  time_style: \"{STYLE_VALUE}\"\n"

                    # 6. LABEL
                    elif w_type == 'label':
                         generated_yaml = generated_yaml.replace(f"  entity: {w_id}\n", "")
                         generated_yaml += f"  text: \"{w_name}\"\n"
                         if w_icon: generated_yaml += f"  icon: {w_icon}\n"
                    
                    # 7. INNE
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
                        
                        # Pobieranie ikon z JSON
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
                                if w_icon and not i_on: generated_yaml += f"  icon: {w_icon}\n"
                        
                        generated_yaml += f"  state_text: 1\n"
                        generated_yaml += f"  title_style: \"{STYLE_TITLE}\"\n"
                        generated_yaml += f"  text_style: \"{STYLE_TEXT}\"\n"
                        generated_yaml += f"  widget_style: \"{STYLE_WIDGET}\"\n"
                        
                        if ad_type == 'cover':
                            generated_yaml += "  state_map:\n"
                            generated_yaml += f"    \"open\": \"{dic['open']}\"\n"
                            generated_yaml += f"    \"closed\": \"{dic['closed']}\"\n"
                            generated_yaml += f"    \"opening\": \"{dic['opening']}\"\n"
                            generated_yaml += f"    \"closing\": \"{dic['closing']}\"\n"
                        elif ad_type == 'binary_sensor':
                            generated_yaml += "  state_map:\n"
                            generated_yaml += f"    \"on\": \"{dic['open']}\"\n"
                            generated_yaml += f"    \"off\": \"{dic['closed']}\"\n"
                        elif ad_type in ['switch', 'light', 'input_boolean']:
                            generated_yaml += "  state_map:\n"
                            generated_yaml += f"    \"on\": \"{dic['on']}\"\n"
                            generated_yaml += f"    \"off\": \"{dic['off']}\"\n"
                        elif ad_type == 'lock':
                            generated_yaml += "  state_map:\n"
                            generated_yaml += f"    \"locked\": \"{dic['locked']}\"\n"
                            generated_yaml += f"    \"unlocked\": \"{dic['unlocked']}\"\n"
                            
                        generated_yaml += f"  icon_style_active: \"{STYLE_ICON}\"\n"
                        generated_yaml += f"  icon_style_inactive: \"{STYLE_ICON}\"\n"

                    generated_yaml += "\n"
        except Exception as e:
            print(f"❌ Error: {e}")
            generated_yaml = f"# ERROR: {e}"

    return render_template('index.html', generated_yaml=generated_yaml, entities=ha_entities, filename=dashboard_filename, dash_name=dashboard_slug)

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000, debug=True)
