print("📦 1. Importing libraries...")
from flask import Flask, render_template, request
import os
import requests
import json
print("✅ 2. Libraries loaded.")

app = Flask(__name__)

# --- KONFIGURACJA ---
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
                TOKEN_SOURCE = "Manual"
                print("🔧 Manual token found.")
except Exception as e:
    print(f"ℹ️ Info: {e}")

if not TOKEN:
    print("❌ WARNING: No token found.")

# --- POBIERANIE ENCJI ---
def get_ha_entities():
    if not TOKEN: return []
    headers = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
    try:
        response = requests.get(f"{API_URL}/states", headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            entities = []
            for state in data:
                entities.append({
                    'id': state['entity_id'],
                    'state': state['state'],
                    'attributes': state.get('attributes', {}),
                    'unit': state.get('attributes', {}).get('unit_of_measurement', '')
                })
            entities.sort(key=lambda x: x['id'])
            return entities
    except Exception as e:
        print(f"❌ Exception: {e}")
    return []

# --- STYLE Z TWOJEGO PLIKU JOAN.TXT ---
TITLE_STYLE = "color: #000000; font-size: 20px; font-weight: 700; text-align: center; padding-top: 3px; width: 100%; font-family: 'Roboto', 'Arial Black', sans-serif;"
TEXT_STYLE = "color: #000000 !important; font-weight: 700 !important;"
WIDGET_STYLE = "color: #000000 !important; background-color: #FFFFFF !important;"
ICON_STYLE = "color: #000000 !important;"
VALUE_STYLE = "color: #000000 !important; font-size: 44px !important; font-weight: 700 !important;"

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
            generated_yaml += f"  white_text_style: \"{TEXT_STYLE}\"\n"
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
                        
                        # Jeśli rozmiar jest inny niż domyślny [2,1], dodaj go w nawiasie
                        widget_str = w['id']
                        size = w.get('size', '').strip()
                        if size and size != "(2x1)": # Domyślny w Twoim pliku to [2,1]
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
                    
                    # Pobranie ikon ON/OFF z JSON
                    i_on = w.get('icon_on')
                    i_off = w.get('icon_off')
                    
                    generated_yaml += f"{w_id}:\n"
                    
                    # 1. NAWIGACJA (STYL JOAN)
                    if w_type == 'navigate':
                        dash_name = w_id.replace('navigate.', '')
                        generated_yaml += f"  widget_type: navigate\n"
                        generated_yaml += f"  title: \"{w_name}\"\n"
                        generated_yaml += f"  dashboard: {dash_name}\n"
                        generated_yaml += f"  icon_inactive: {w_icon or 'mdi-arrow-right-circle'}\n"
                        generated_yaml += f"  title_style: \"color: #000000; font-size: 24px; font-weight: 700; text-align: center; padding-top: 5px; width: 100%; font-family: 'Roboto', 'Arial Black', sans-serif;\"\n"
                        generated_yaml += f"  widget_style: \"background-color: #FFFFFF !important; border-radius: 8px !important; padding: 10px !important; color: #000000 !important;\"\n"

                    # 2. SENSOR
                    elif w_type == 'sensor':
                        generated_yaml += f"  widget_type: sensor\n"
                        generated_yaml += f"  entity: {w_id}\n"
                        generated_yaml += f"  title: \"{w_name}\"\n"
                        if w_icon: generated_yaml += f"  icon: {w_icon}\n"
                        generated_yaml += f"  title_style: \"{TITLE_STYLE}\"\n"
                        generated_yaml += f"  text_style: \"{TEXT_STYLE}\"\n"
                        generated_yaml += f"  value_style: \"{VALUE_STYLE}\"\n"
                        generated_yaml += f"  unit_style: \"color: #000000 !important;\"\n"
                        generated_yaml += f"  widget_style: \"{WIDGET_STYLE}\"\n"
                        if 'bateria' in w_id or 'battery' in w_id:
                            generated_yaml += "  precision: 0\n"

                    # 3. PRZEŁĄCZNIKI / ŚWIATŁA (SWITCH)
                    elif w_type in ['switch', 'light', 'input_boolean', 'fan']:
                        # Wszystkie traktujemy jako switch dla spójności, chyba że to cover
                        generated_yaml += f"  widget_type: switch\n"
                        generated_yaml += f"  entity: {w_id}\n"
                        generated_yaml += f"  title: \"{w_name}\"\n"
                        if i_on: generated_yaml += f"  icon_on: {i_on}\n"
                        if i_off: generated_yaml += f"  icon_off: {i_off}\n"
                        generated_yaml += f"  title_style: \"{TITLE_STYLE}\"\n"
                        generated_yaml += f"  state_text: 1\n"
                        generated_yaml += f"  text_style: \"{TEXT_STYLE}\"\n"
                        generated_yaml += f"  widget_style: \"{WIDGET_STYLE}\"\n"
                        generated_yaml += "  state_map:\n"
                        generated_yaml += "    \"on\": \"WŁĄCZONE\"\n"
                        generated_yaml += "    \"off\": \"WYŁĄCZONE\"\n"
                        generated_yaml += f"  icon_style_active: \"{ICON_STYLE}\"\n"
                        generated_yaml += f"  icon_style_inactive: \"{ICON_STYLE}\"\n"

                    # 4. ROLETY / BRAMY (COVER)
                    elif w_type == 'cover':
                        generated_yaml += f"  widget_type: cover\n"
                        generated_yaml += f"  entity: {w_id}\n"
                        generated_yaml += f"  title: \"{w_name}\"\n"
                        if i_on: generated_yaml += f"  icon_on: {i_on}\n"
                        if i_off: generated_yaml += f"  icon_off: {i_off}\n"
                        generated_yaml += f"  state_text: 1\n"
                        generated_yaml += f"  title_style: \"{TITLE_STYLE}\"\n"
                        generated_yaml += f"  text_style: \"{TEXT_STYLE}\"\n"
                        generated_yaml += f"  widget_style: \"{WIDGET_STYLE}\"\n"
                        generated_yaml += "  state_map:\n"
                        generated_yaml += "    \"open\": \"OTWARTA\"\n"
                        generated_yaml += "    \"closed\": \"ZAMKNIĘTA\"\n"
                        generated_yaml += "    \"opening\": \"OTWIERANIE\"\n"
                        generated_yaml += "    \"closing\": \"ZAMYKANIE\"\n"
                        generated_yaml += f"  icon_style_active: \"{ICON_STYLE}\"\n"
                        generated_yaml += f"  icon_style_inactive: \"{ICON_STYLE}\"\n"

                    # 5. BINARY SENSOR (DRZWI/OKNA)
                    elif w_type == 'binary_sensor':
                        generated_yaml += f"  widget_type: binary_sensor\n"
                        generated_yaml += f"  entity: {w_id}\n"
                        generated_yaml += f"  title: \"{w_name}\"\n"
                        if i_on: generated_yaml += f"  icon_on: {i_on}\n"
                        if i_off: generated_yaml += f"  icon_off: {i_off}\n"
                        generated_yaml += f"  title_style: \"{TITLE_STYLE}\"\n"
                        generated_yaml += f"  state_text: 1\n"
                        generated_yaml += f"  text_style: \"{TEXT_STYLE}\"\n"
                        generated_yaml += f"  widget_style: \"{WIDGET_STYLE}\"\n"
                        generated_yaml += f"  icon_style_active: \"{ICON_STYLE}\"\n"
                        generated_yaml += f"  icon_style_inactive: \"{ICON_STYLE}\"\n"
                        generated_yaml += "  state_map:\n"
                        generated_yaml += "    \"on\": \"OTWARTE\"\n"
                        generated_yaml += "    \"off\": \"ZAMKNIĘTE\"\n"

                    # 6. KLIMATYZACJA
                    elif w_type == 'climate':
                        generated_yaml += f"  widget_type: climate\n"
                        generated_yaml += f"  entity: {w_id}\n"
                        generated_yaml += f"  title: \"{w_name}\"\n"
                        generated_yaml += f"  title_style: \"{TITLE_STYLE}\"\n"
                        generated_yaml += "  units: \"°C\"\n"
                        generated_yaml += "  step: 1\n"
                        generated_yaml += "  state_text: 1\n"
                        generated_yaml += f"  text_style: \"{TEXT_STYLE}\"\n"
                        generated_yaml += f"  widget_style: \"{WIDGET_STYLE}\"\n"
                        generated_yaml += "  state_map:\n"
                        generated_yaml += "    \"off\": \"WYŁĄCZONA\"\n"
                        generated_yaml += "    \"auto\": \"AUTO\"\n"
                        generated_yaml += "    \"heat\": \"GRZANIE\"\n"
                        generated_yaml += "    \"cool\": \"CHŁODZENIE\"\n"
                        generated_yaml += f"  icon_style_active: \"{ICON_STYLE}\"\n"
                        generated_yaml += f"  icon_style_inactive: \"{ICON_STYLE}\"\n"

                    # 7. MEDIA PLAYER
                    elif w_type == 'media_player':
                        generated_yaml += f"  widget_type: media_player\n"
                        generated_yaml += f"  entity: {w_id}\n"
                        generated_yaml += f"  title: \"{w_name}\"\n"
                        if w_icon: generated_yaml += f"  icon: {w_icon}\n"
                        generated_yaml += f"  title_style: \"{TITLE_STYLE}\"\n"
                        generated_yaml += f"  widget_style: \"{WIDGET_STYLE}\"\n"
                        generated_yaml += f"  icon_style: \"{ICON_STYLE}\"\n"

                    # 8. SKRYPT
                    elif w_type == 'script':
                        generated_yaml += f"  widget_type: script\n"
                        generated_yaml += f"  entity: {w_id}\n"
                        generated_yaml += f"  title: \"{w_name}\"\n"
                        if w_icon: generated_yaml += f"  icon: {w_icon}\n"
                        generated_yaml += f"  title_style: \"{TITLE_STYLE}\"\n"
                        generated_yaml += f"  widget_style: \"{WIDGET_STYLE}\"\n"
                        generated_yaml += f"  icon_style: \"{ICON_STYLE}\"\n"

                    generated_yaml += "\n"
        except Exception as e:
            print(f"❌ Error: {e}")
            generated_yaml = f"# ERROR: {e}"

    return render_template('index.html', generated_yaml=generated_yaml, entities=ha_entities, filename=dashboard_filename, dash_name=dashboard_slug)

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000, debug=True)
