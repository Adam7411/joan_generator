print("📦 1. Importing libraries...")
from flask import Flask, render_template, request
import os
import requests
import json
print("✅ 2. Libraries loaded.")

app = Flask(__name__)

# --- KONFIGURACJA API I TOKENU ---
TOKEN = os.environ.get('SUPERVISOR_TOKEN')
API_URL = "http://supervisor/core/api" 
TOKEN_SOURCE = "System (Supervisor)"

# Próba odczytu tokenu z konfiguracji dodatku
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

# --- POBIERANIE ENCJI Z HA (PEŁNE DANE) ---
def get_ha_entities():
    if not TOKEN:
        return []
    headers = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
    try:
        # Pobieramy wszystkie stany
        response = requests.get(f"{API_URL}/states", headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            entities = []
            for state in data:
                # Przekazujemy pełne dane potrzebne do podglądu
                attr = state.get('attributes', {})
                entities.append({
                    'id': state['entity_id'],
                    'state': state['state'],
                    'attributes': attr,
                    'unit': attr.get('unit_of_measurement', ''),
                    'friendly_name': attr.get('friendly_name', state['entity_id'])
                })
            # Sortowanie alfabetyczne
            entities.sort(key=lambda x: x['id'])
            return entities
        else:
            print(f"⚠️ API Error: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"❌ Exception while fetching entities: {e}")
    return []

# --- STYLE Z PLIKU JOAN.TXT (DOKŁADNA KOPIA) ---
STYLES = {
    "title": "color: #000000; font-size: 20px; font-weight: 700; text-align: center; padding-top: 3px; width: 100%; font-family: 'Roboto', 'Arial Black', sans-serif;",
    "text": "color: #000000 !important; font-weight: 700 !important;",
    "value": "color: #000000 !important; font-size: 44px !important; font-weight: 700 !important;",
    "unit": "color: #000000 !important;",
    "widget": "color: #000000 !important; background-color: #FFFFFF !important;",
    "icon": "color: #000000 !important;"
}

# Pomocnicza funkcja do ikon (fallback)
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
            
            # --- GENEROWANIE NAGŁÓWKA (STYL JOAN) ---
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
            generated_yaml += "  state_text_style: \"color: #000000 !important; font-weight: 700 !important; font-size: 16px !important;\"\n"
            generated_yaml += "skin: simplyred\n\n"
            
            layout_data_str = request.form.get('layout_data_json')
            if layout_data_str:
                layout_rows = json.loads(layout_data_str)
                generated_yaml += "layout:\n"
                processed_widgets = []
                
                # --- SEKCJA LAYOUT ---
                for row in layout_rows:
                    if not row: continue
                    row_parts = []
                    for w in row:
                        if w['type'] == 'spacer':
                            row_parts.append("spacer")
                            continue
                        
                        widget_str = w['id']
                        size = w.get('size', '').strip()
                        # Domyślny to 2x1 w Twoim pliku. Jeśli inny, dodajemy.
                        if size and size != "(2x1)":
                            if not size.startswith('('): size = f"({size})"
                            widget_str += size
                        row_parts.append(widget_str)
                    
                    generated_yaml += f"  - {', '.join(row_parts)}\n"
                    processed_widgets.extend(row)
                
                generated_yaml += "\n# -------------------\n# DEFINICJE WIDŻETÓW\n# -------------------\n\n"
                
                # --- SEKCJA DEFINICJI ---
                seen_ids = set()
                for w in processed_widgets:
                    if w['type'] == 'spacer': continue
                    w_id = w['id']
                    if w_id in seen_ids: continue
                    seen_ids.add(w_id)
                    
                    w_type = w['type']
                    w_name = w['name']
                    w_icon = w['icon']
                    
                    # Pobierz ikony z JSON (smart lub manual)
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
                        # Styl Navigate z Twojego pliku
                        generated_yaml += f"  title_style: \"color: #000000; font-size: 24px; font-weight: 700; text-align: center; padding-top: 5px; width: 100%; font-family: 'Roboto', 'Arial Black', sans-serif;\"\n"
                        generated_yaml += f"  widget_style: \"background-color: #FFFFFF !important; border-radius: 8px !important; padding: 10px !important; color: #000000 !important;\"\n"

                    # 2. SENSOR
                    elif w_type == 'sensor':
                        generated_yaml += f"  widget_type: sensor\n"
                        generated_yaml += f"  entity: {w_id}\n"
                        generated_yaml += f"  title: \"{w_name}\"\n"
                        if w_icon: generated_yaml += f"  icon: {w_icon}\n"
                        generated_yaml += f"  title_style: \"{STYLES['title']}\"\n"
                        generated_yaml += f"  text_style: \"{STYLES['text']}\"\n"
                        generated_yaml += f"  value_style: \"{STYLES['value']}\"\n"
                        generated_yaml += f"  unit_style: \"{STYLES['unit']}\"\n"
                        generated_yaml += f"  widget_style: \"{STYLES['widget']}\"\n"
                        if 'bateria' in w_id or 'battery' in w_id or 'wymiana' in w_id:
                            generated_yaml += "  precision: 0\n"

                    # 3. MEDIA PLAYER
                    elif w_type == 'media_player':
                        generated_yaml += f"  widget_type: media_player\n"
                        generated_yaml += f"  entity: {w_id}\n"
                        generated_yaml += f"  title: \"{w_name}\"\n"
                        if w_icon: generated_yaml += f"  icon: {w_icon}\n"
                        generated_yaml += f"  title_style: \"{STYLES['title']}\"\n"
                        generated_yaml += f"  widget_style: \"{STYLES['widget']}\"\n"
                        generated_yaml += f"  icon_style: \"{STYLES['icon']}\"\n"

                    # 4. CLIMATE
                    elif w_type == 'climate':
                        generated_yaml += f"  widget_type: climate\n"
                        generated_yaml += f"  entity: {w_id}\n"
                        generated_yaml += f"  title: \"{w_name}\"\n"
                        generated_yaml += f"  title_style: \"{STYLES['title']}\"\n"
                        generated_yaml += "  units: \"°C\"\n"
                        generated_yaml += "  step: 1\n"
                        generated_yaml += "  state_text: 1\n"
                        generated_yaml += f"  text_style: \"{STYLES['text']}\"\n"
                        generated_yaml += f"  widget_style: \"{STYLES['widget']}\"\n"
                        generated_yaml += "  state_map:\n"
                        generated_yaml += "    \"off\": \"WYŁĄCZONA\"\n"
                        generated_yaml += "    \"auto\": \"AUTO\"\n"
                        generated_yaml += "    \"heat\": \"GRZANIE\"\n"
                        generated_yaml += "    \"cool\": \"CHŁODZENIE\"\n"
                        generated_yaml += "    \"dry\": \"OSUSZANIE\"\n"
                        generated_yaml += "    \"fan_only\": \"WENTYLATOR\"\n"
                        generated_yaml += f"  icon_style_active: \"{STYLES['icon']}\"\n"
                        generated_yaml += f"  icon_style_inactive: \"{STYLES['icon']}\"\n"

                    # 5. PRZEŁĄCZNIKI / ŚWIATŁA / INPUT_BOOLEAN / SKRYPTY
                    else:
                        # Mapowanie typów
                        real_type = 'switch' # Domyślnie switch dla light/input_boolean
                        if w_type == 'cover': real_type = 'cover'
                        elif w_type == 'binary_sensor': real_type = 'binary_sensor'
                        elif w_type == 'script': real_type = 'script'
                        elif w_type == 'lock': real_type = 'lock'
                        
                        generated_yaml += f"  widget_type: {real_type}\n"
                        generated_yaml += f"  entity: {w_id}\n"
                        generated_yaml += f"  title: \"{w_name}\"\n"
                        
                        if i_on: generated_yaml += f"  icon_on: {i_on}\n"
                        if i_off: generated_yaml += f"  icon_off: {i_off}\n"
                        if w_icon and not i_on: generated_yaml += f"  icon: {w_icon}\n"
                        
                        generated_yaml += f"  state_text: 1\n"
                        generated_yaml += f"  title_style: \"{STYLES['title']}\"\n"
                        generated_yaml += f"  text_style: \"{STYLES['text']}\"\n"
                        generated_yaml += f"  widget_style: \"{STYLES['widget']}\"\n"
                        
                        # Mapowanie stanów PL
                        if real_type == 'cover':
                            generated_yaml += "  state_map:\n"
                            generated_yaml += "    \"open\": \"OTWARTA\"\n"
                            generated_yaml += "    \"closed\": \"ZAMKNIĘTA\"\n"
                            generated_yaml += "    \"opening\": \"OTWIERANIE\"\n"
                            generated_yaml += "    \"closing\": \"ZAMYKANIE\"\n"
                        elif real_type == 'binary_sensor':
                            generated_yaml += "  state_map:\n"
                            generated_yaml += "    \"on\": \"OTWARTE\"\n"
                            generated_yaml += "    \"off\": \"ZAMKNIĘTE\"\n"
                        elif real_type in ['switch', 'light']:
                            generated_yaml += "  state_map:\n"
                            generated_yaml += "    \"on\": \"WŁĄCZONE\"\n"
                            generated_yaml += "    \"off\": \"WYŁĄCZONE\"\n"
                            
                        generated_yaml += f"  icon_style_active: \"{STYLES['icon']}\"\n"
                        generated_yaml += f"  icon_style_inactive: \"{STYLES['icon']}\"\n"

                    generated_yaml += "\n"
        except Exception as e:
            print(f"❌ Error: {e}")
            generated_yaml = f"# ERROR GENERATING YAML: {e}"

    return render_template('index.html', generated_yaml=generated_yaml, entities=ha_entities, filename=dashboard_filename, dash_name=dashboard_slug)

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000, debug=True)
