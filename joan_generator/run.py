print("--> 1. Importuje biblioteki...")
from flask import Flask, render_template, request
import os
import requests
import json
print("--> 2. Biblioteki zaladowane.")

app = Flask(__name__)

# --- KONFIGURACJA TOKENA ---
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
            TOKEN_SOURCE = "Reczny (Konfiguracja)"
            print("--> Znaleziono ręczny token. Zmieniam adres API na http://homeassistant:8123/api")
except Exception as e:
    print(f"--> Info: Nie udalo sie odczytac opcji: {e}")

if not TOKEN:
    print("!!! UWAGA: Brak tokena (ani systemowego, ani ręcznego) !!!")
else:
    print(f"--> Uzywany Token: {TOKEN_SOURCE}")

def get_ha_entities():
    if not TOKEN:
        return []
    
    headers = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
    
    try:
        print(f"--> Pobieram encje z: {API_URL}/states")
        response = requests.get(f"{API_URL}/states", headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            entities = [state['entity_id'] for state in data]
            entities.sort()
            print(f"--> SUKCES! Pobrano {len(entities)} encji.")
            return entities
        else:
            print(f"!!! Blad API Home Assistant: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"!!! Wyjatek podczas pobierania encji: {e}")
    return []

# Style zgodne z E-Ink (Czarny tekst, biale tlo)
STYLES = {
    "title": "color: #000000; font-size: 20px; font-weight: 700; text-align: center; padding-top: 5px; width: 100%; font-family: 'Roboto', 'Arial Black', sans-serif;",
    "widget": "color: #000000 !important; background-color: #FFFFFF !important;",
    "text": "color: #000000 !important; font-weight: 700 !important;",
    "value": "color: #000000 !important; font-size: 44px !important; font-weight: 700 !important;",
    "unit": "color: #000000 !important;",
    "icon": "color: #000000 !important;"
}

@app.route('/', methods=['GET', 'POST'])
def index():
    generated_yaml = ""
    ha_entities = get_ha_entities()
    
    if request.method == 'POST':
        title = request.form.get('title', 'JoanDashboard')
        lang = request.form.get('language', 'pl') # Pobieramy język (pl lub en)
        
        # Słownik tłumaczeń dla YAML
        TEXTS = {
            'pl': {'on': 'WŁĄCZONE', 'off': 'WYŁĄCZONE', 'open': 'OTWARTE', 'closed': 'ZAMKNIĘTE', 'opening': 'OTWIERANIE', 'closing': 'ZAMYKANIE'},
            'en': {'on': 'ON', 'off': 'OFF', 'open': 'OPEN', 'closed': 'CLOSED', 'opening': 'OPENING', 'closing': 'CLOSING'}
        }
        T = TEXTS[lang]

        generated_yaml += f"title: {title}\n"
        generated_yaml += "widget_dimensions: [117, 117]\n"
        generated_yaml += "widget_size: [2, 1]\n"
        generated_yaml += "widget_margins: [8, 8]\n"
        generated_yaml += "columns: 6\n"
        generated_yaml += "rows: 9\n"
        generated_yaml += "global_parameters:\n"
        generated_yaml += "  use_comma: 0\n  precision: 1\n  use_hass_icon: 1\n  namespace: default\n"
        generated_yaml += "skin: simplyred\n\n"
        
        layout_data_str = request.form.get('layout_data_json')
        if layout_data_str:
            try:
                layout_rows = json.loads(layout_data_str)
                generated_yaml += "layout:\n"
                processed_widgets = []
                
                for row in layout_rows:
                    if not row: continue
                    row_str = ", ".join([w['id'] for w in row])
                    generated_yaml += f"  - {row_str}\n"
                    processed_widgets.extend(row)
                
                generated_yaml += "\n# --- DEFINICJE WIDZETOW ---\n\n"
                
                seen_ids = set()
                for w in processed_widgets:
                    w_id = w['id']
                    if w_id in seen_ids: continue
                    seen_ids.add(w_id)
                    
                    w_type = w['type']
                    w_name = w['name']
                    w_icon = w['icon']
                    
                    generated_yaml += f"{w_id}:\n"
                    
                    # 1. NAWIGACJA
                    if w_type == 'navigate':
                        dashboard_name = w_id.replace('navigate.', '')
                        generated_yaml += f"  widget_type: navigate\n"
                        generated_yaml += f"  dashboard: {dashboard_name}\n"
                        generated_yaml += f"  title: \"{w_name}\"\n"
                        generated_yaml += f"  icon_inactive: {w_icon if w_icon else 'mdi-arrow-left-circle'}\n"
                        generated_yaml += f"  widget_style: \"background-color: #FFFFFF !important; border-radius: 8px !important; padding: 10px !important; color: #000000 !important;\"\n"
                        generated_yaml += f"  title_style: \"{STYLES['title']}\"\n"
                    
                    # 2. SENSOR
                    elif w_type == 'sensor':
                        generated_yaml += f"  widget_type: sensor\n"
                        generated_yaml += f"  entity: {w_id}\n"
                        generated_yaml += f"  title: {w_name}\n"
                        generated_yaml += f"  title_style: \"{STYLES['title']}\"\n"
                        generated_yaml += f"  text_style: \"{STYLES['text']}\"\n"
                        generated_yaml += f"  value_style: \"{STYLES['value']}\"\n"
                        generated_yaml += f"  unit_style: \"{STYLES['unit']}\"\n"
                        generated_yaml += f"  widget_style: \"{STYLES['widget']}\"\n"
                        if w_icon:
                            generated_yaml += f"  icon: {w_icon}\n"
                            generated_yaml += f"  icon_style: \"{STYLES['icon']}\"\n"

                    # 3. MEDIA PLAYER
                    elif w_type == 'media_player':
                        generated_yaml += f"  widget_type: media_player\n"
                        generated_yaml += f"  entity: {w_id}\n"
                        generated_yaml += f"  title: {w_name}\n"
                        generated_yaml += f"  truncate_name: 20\n"
                        generated_yaml += f"  step: 5\n"
                        generated_yaml += f"  title_style: \"{STYLES['title']}\"\n"
                        generated_yaml += f"  text_style: \"{STYLES['text']}\"\n"
                        generated_yaml += f"  widget_style: \"{STYLES['widget']}\"\n"
                        generated_yaml += f"  icon_style: \"{STYLES['icon']}\"\n"

                    # 4. POZOSTAŁE
                    else:
                        ad_type = w_type
                        if w_type == 'binary_sensor': ad_type = 'binary_sensor'
                        if w_type == 'input_boolean': ad_type = 'switch'
                        
                        generated_yaml += f"  widget_type: {ad_type}\n"
                        generated_yaml += f"  entity: {w_id}\n"
                        generated_yaml += f"  title: {w_name}\n"
                        
                        if w_icon:
                            generated_yaml += f"  icon_on: {w_icon}\n"
                            generated_yaml += f"  icon_off: {w_icon}\n"
                            if w_type == 'script' or w_type == 'scene':
                                generated_yaml += f"  icon: {w_icon}\n"
                        else:
                             generated_yaml += f"  icon_on: mdi-toggle-switch\n"
                             generated_yaml += f"  icon_off: mdi-toggle-switch-off\n"

                        # KLUCZOWE DLA WYŚWIETLANIA STANU
                        generated_yaml += f"  state_text: 1\n"
                        generated_yaml += f"  title_style: \"{STYLES['title']}\"\n"
                        generated_yaml += f"  text_style: \"{STYLES['text']}\"\n" 
                        generated_yaml += f"  widget_style: \"{STYLES['widget']}\"\n"
                        generated_yaml += f"  icon_style_active: \"{STYLES['icon']}\"\n"
                        generated_yaml += f"  icon_style_inactive: \"{STYLES['icon']}\"\n"
                        
                        generated_yaml += "  state_map:\n"
                        generated_yaml += f"    \"on\": \"{T['on']}\"\n"
                        generated_yaml += f"    \"off\": \"{T['off']}\"\n"
                        
                        if w_type == 'cover' or w_type == 'binary_sensor':
                            generated_yaml += f"    \"open\": \"{T['open']}\"\n"
                            generated_yaml += f"    \"closed\": \"{T['closed']}\"\n"
                            generated_yaml += f"    \"opening\": \"{T['opening']}\"\n"
                            generated_yaml += f"    \"closing\": \"{T['closing']}\"\n"

                    generated_yaml += "\n"
            except Exception as e:
                print(f"Blad przetwarzania JSON: {e}")

    return render_template('index.html', generated_yaml=generated_yaml, entities=ha_entities)

print("--> 3. Uruchamiam serwer Flask na porcie 5000...")
app.run(host='0.0.0.0', port=5000, debug=False)
