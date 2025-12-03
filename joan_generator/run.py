import os
import json
import requests
from flask import Flask, render_template, request

# Inicjalizacja aplikacji
print("📦 1. Inicjalizacja aplikacji Joan 6 Generator...")
app = Flask(__name__)

# -------------------------------------------------------------------------
# 1. KONFIGURACJA API I TOKENU
# -------------------------------------------------------------------------
TOKEN = os.environ.get('SUPERVISOR_TOKEN')
API_URL = "http://supervisor/core/api" 
TOKEN_SOURCE = "System (Supervisor)"

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
                print(f"🔧 Wykryto manualny token. Przełączam API na: {API_URL}")
except Exception as e:
    print(f"ℹ️ Info: Nie udało się odczytać pliku opcji: {e}")

if not TOKEN:
    print("❌ OSTRZEŻENIE: Brak tokena autoryzacji! Lista encji będzie pusta.")

# -------------------------------------------------------------------------
# 2. POBIERANIE DANYCH Z HOME ASSISTANT
# -------------------------------------------------------------------------
def get_ha_entities():
    if not TOKEN: return []
    headers = { "Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json" }
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
        print(f"❌ Wyjątek: {e}")
    return []

# -------------------------------------------------------------------------
# 3. STYLE (E-INK OPTIMIZED)
# -------------------------------------------------------------------------
STYLE_TITLE = "color: #000000; font-size: 20px; font-weight: 700; text-align: center; padding-top: 5px; width: 100%; font-family: 'Roboto', 'Arial Black', sans-serif;"
STYLE_WIDGET = "color: #000000 !important; background-color: #FFFFFF !important;"
STYLE_TEXT = "color: #000000 !important; font-weight: 700 !important;"
STYLE_VALUE = "color: #000000 !important; font-size: 44px !important; font-weight: 700 !important; padding-top: 45px !important; line-height: 1.2 !important; display: inline-block !important;"
STYLE_UNIT = "color: #000000 !important; padding-top: 45px !important; display: inline-block !important;"
STYLE_ICON = "color: #000000 !important;"
STYLE_STATE_TEXT = "color: #000000 !important; font-weight: 700 !important; font-size: 16px !important;"

@app.route('/', methods=['GET', 'POST'])
def index():
    generated_yaml = ""
    ha_entities = get_ha_entities()
    dashboard_filename = "joandashboard.dash"
    dashboard_slug = "joandashboard"
    
    if request.method == 'POST':
        try:
            title = request.form.get('title', 'JoanDashboard')
            dashboard_slug = title.lower().replace(" ", "_")
            dashboard_filename = dashboard_slug + ".dash"
            
            cols = request.form.get('grid_columns', '4')
            rows = request.form.get('grid_rows', '8')
            lang = request.form.get('ui_language', 'pl')
            
            # Odczyt domyślnego rozmiaru z formularza (przekazanego przez JS)
            default_size_str = request.form.get('default_widget_size', '2, 1')
            def_size_parts = default_size_str.split(',')
            def_w = int(def_size_parts[0].strip())
            def_h = int(def_size_parts[1].strip()) if len(def_size_parts) > 1 else 1

            TRANS = {
                'pl': {'on': 'WŁĄCZONE', 'off': 'WYŁĄCZONE', 'open': 'OTWARTA', 'closed': 'ZAMKNIĘTA', 'opening': 'OTWIERANIE', 'closing': 'ZAMYKANIE', 'locked': 'ZAMKNIĘTE', 'unlocked': 'OTWARTE', 'home': 'W DOMU', 'not_home': 'POZA'},
                'en': {'on': 'ON', 'off': 'OFF', 'open': 'OPEN', 'closed': 'CLOSED', 'opening': 'OPENING', 'closing': 'CLOSING', 'locked': 'LOCKED', 'unlocked': 'UNLOCKED', 'home': 'HOME', 'not_home': 'AWAY'}
            }
            dic = TRANS.get(lang, TRANS['pl'])

            ad_columns = int(cols) * 2

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
            generated_yaml += f"  white_text_style: \"{STYLE_TEXT}\"\n"
            generated_yaml += f"  state_text_style: \"{STYLE_STATE_TEXT}\"\n"
            generated_yaml += "skin: simplyred\n\n"
            
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
                        
                        # Logika rozmiaru w YAML
                        size_str = w.get('size', '')
                        is_default = False
                        
                        # Jeśli rozmiar widgetu jest taki sam jak globalny, nie piszemy go
                        if size_str == f"({def_w}x{def_h})":
                            is_default = True
                        elif size_str == "(2x1)" and def_w == 2 and def_h == 1:
                            is_default = True
                        elif size_str == "(1x1)" and def_w == 1 and def_h == 1:
                            is_default = True
                            
                        if not is_default and size_str:
                             if not size_str.startswith('('): size_str = f"({size_str})"
                             widget_id += size_str
                             
                        row_parts.append(widget_id)
                        processed_widgets.append(w)
                    generated_yaml += f"  - {', '.join(row_parts)}\n"
                
                generated_yaml += "\n# -------------------\n# DEFINICJE WIDŻETÓW\n# -------------------\n\n"
                seen_ids = set()
                
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
                    w_name = w['name']
                    w_icon = w['icon']
                    i_on = w.get('icon_on')
                    i_off = w.get('icon_off')
                    
                    generated_yaml += f"{w_id}:\n"
                    
                    if w_type == 'navigate':
                        dash_target = w_id.replace('navigate.', '')
                        generated_yaml += f"  widget_type: navigate\n"
                        generated_yaml += f"  title: \"{w_name}\"\n"
                        generated_yaml += f"  dashboard: {dash_target}\n"
                        generated_yaml += f"  icon_inactive: {w_icon or 'mdi-arrow-right-circle'}\n"
                        generated_yaml += f"  title_style: \"{STYLE_TITLE}\"\n"
                        generated_yaml += f"  widget_style: \"{STYLE_WIDGET}\"\n"

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

                    elif w_type == 'clock':
                        generated_yaml += f"  widget_type: clock\n"
                        generated_yaml += f"  time_format: 24hr\n"
                        generated_yaml += f"  show_seconds: 0\n"
                        generated_yaml += f"  date_style: \"{STYLE_TEXT}\"\n"
                        generated_yaml += f"  time_style: \"{STYLE_VALUE}\"\n"

                    elif w_type == 'label':
                         generated_yaml += f"  widget_type: label\n"
                         generated_yaml += f"  text: \"{w_name}\"\n"
                         if w_icon: generated_yaml += f"  icon: {w_icon}\n"
                         generated_yaml += f"  text_style: \"{STYLE_TITLE}\"\n"
                    
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
                        
                        generated_yaml += f"  widget_type: {ad_type}\n"
                        generated_yaml += f"  entity: {w_id}\n"
                        generated_yaml += f"  title: \"{w_name}\"\n"
                        
                        if i_on: generated_yaml += f"  icon_on: {i_on}\n"
                        if i_off: generated_yaml += f"  icon_off: {i_off}\n"
                        if ad_type == 'lock':
                            if i_off: generated_yaml += f"  icon_locked: {i_off}\n"
                            if i_on: generated_yaml += f"  icon_unlocked: {i_on}\n"
                        if w_icon and not i_on: generated_yaml += f"  icon: {w_icon}\n"
                        
                        generated_yaml += f"  state_text: 1\n"
                        generated_yaml += f"  title_style: \"{STYLE_TITLE}\"\n"
                        generated_yaml += f"  text_style: \"{STYLE_TEXT}\"\n"
                        generated_yaml += f"  widget_style: \"{STYLE_WIDGET}\"\n"
                        generated_yaml += f"  icon_style_active: \"{STYLE_ICON}\"\n"
                        generated_yaml += f"  icon_style_inactive: \"{STYLE_ICON}\"\n"
                        
                        if ad_type in ['cover', 'binary_sensor', 'switch', 'light', 'lock']:
                            generated_yaml += "  state_map:\n"
                            if ad_type == 'cover':
                                for s in ['open','closed','opening','closing']: generated_yaml += f"    \"{s}\": \"{dic.get(s,s)}\"\n"
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
        except Exception as e:
            print(f"❌ Error generating YAML: {e}")
            generated_yaml = f"# ERROR GENERATING YAML: {e}"

    return render_template('index.html', generated_yaml=generated_yaml, entities=ha_entities, filename=dashboard_filename, dash_name=dashboard_slug)

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000, debug=True)
