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
            return entities
    except Exception as e:
        print(f"!!! Blad API: {e}")
    return []

# Style - DEFINICJA
# Kluczowe dla E-Ink: Wymuszenie czarnego koloru i pogrubienia
CSS_BLACK = "color: #000000 !important; font-weight: 700 !important;"
CSS_BG_WHITE = "background-color: #FFFFFF !important;"

# --- INTELIGENTNE IKONY ---
def get_icon_pair(base_icon, w_type):
    if not base_icon:
        if w_type == 'cover': return 'mdi-window-shutter-open', 'mdi-window-shutter'
        if w_type == 'lock': return 'mdi-lock-open', 'mdi-lock'
        if w_type == 'binary_sensor': return 'mdi-checkbox-marked-circle', 'mdi-radiobox-blank'
        return 'mdi-toggle-switch', 'mdi-toggle-switch-off'

    i = base_icon.lower()
    # Logika parowania ikon
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
    
    if request.method == 'POST':
        title = request.form.get('title', 'JoanDashboard')
        lang = request.form.get('ui_language', 'pl')
        
        T = {
            'pl': {'on': 'WŁĄCZONE', 'off': 'WYŁĄCZONE', 'open': 'OTWARTE', 'closed': 'ZAMKNIĘTE', 
                   'opening': 'OTWIERANIE', 'closing': 'ZAMYKANIE', 'locked': 'ZAMKNIĘTE', 'unlocked': 'OTWARTE'},
            'en': {'on': 'ON', 'off': 'OFF', 'open': 'OPEN', 'closed': 'CLOSED', 
                   'opening': 'OPENING', 'closing': 'CLOSING', 'locked': 'LOCKED', 'unlocked': 'UNLOCKED'}
        }
        dic = T.get(lang, T['pl'])

        generated_yaml += f"title: {title}\n"
        generated_yaml += "widget_dimensions: [117, 117]\n"
        generated_yaml += "widget_size: [2, 1]\n"
        generated_yaml += "widget_margins: [8, 8]\n"
        generated_yaml += "columns: 6\n"
        generated_yaml += "rows: 9\n"
        
        # --- GLOBAL PARAMETERS (TU JEST KLUCZ DO SUKCESU) ---
        generated_yaml += "global_parameters:\n"
        generated_yaml += "  use_comma: 0\n"
        generated_yaml += "  precision: 1\n"
        generated_yaml += "  use_hass_icon: 1\n"
        generated_yaml += "  namespace: default\n"
        generated_yaml += "  state_text: 1\n" # Wymuszenie globalne tekstu stanu
        # Style globalne
        generated_yaml += f"  title_style: \"{CSS_BLACK} font-size: 20px; padding-top: 5px; font-family: 'Roboto', sans-serif;\"\n"
        generated_yaml += f"  text_style: \"{CSS_BLACK}\"\n"
        generated_yaml += f"  state_text_style: \"{CSS_BLACK} font-size: 14px; text-transform: uppercase; margin-top: 5px;\"\n"
        generated_yaml += f"  widget_style: \"{CSS_BLACK} {CSS_BG_WHITE}\"\n"
        generated_yaml += f"  icon_style_active: \"{CSS_BLACK}\"\n"
        generated_yaml += f"  icon_style_inactive: \"{CSS_BLACK}\"\n"
        
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
                    generated_yaml += f"  title: \"{w_name}\"\n"
                    
                    # 1. NAWIGACJA
                    if w_type == 'navigate':
                        dashboard_name = w_id.replace('navigate.', '')
                        generated_yaml += f"  widget_type: navigate\n"
                        generated_yaml += f"  dashboard: {dashboard_name}\n"
                        generated_yaml += f"  icon_inactive: {w_icon if w_icon else 'mdi-arrow-left-circle'}\n"
                        generated_yaml += f"  widget_style: \"{CSS_BG_WHITE} border-radius: 8px !important;\"\n"
                    
                    # 2. SENSOR
                    elif w_type == 'sensor':
                        generated_yaml += f"  widget_type: sensor\n"
                        generated_yaml += f"  entity: {w_id}\n"
                        generated_yaml += f"  value_style: \"{CSS_BLACK} font-size: 44px !important;\"\n"
                        generated_yaml += f"  unit_style: \"{CSS_BLACK}\"\n"
                        if w_icon:
                            generated_yaml += f"  icon: {w_icon}\n"
                    
                    # 3. MEDIA PLAYER
                    elif w_type == 'media_player':
                        generated_yaml += f"  widget_type: media_player\n"
                        generated_yaml += f"  entity: {w_id}\n"
                        generated_yaml += f"  truncate_name: 20\n"
                        generated_yaml += f"  step: 5\n"

                    # 4. PRZEŁĄCZNIKI I INNE (Tu najważniejszy jest STAN)
                    else:
                        ad_type = w_type
                        if w_type == 'binary_sensor': ad_type = 'binary_sensor'
                        if w_type == 'input_boolean': ad_type = 'switch'
                        
                        generated_yaml += f"  widget_type: {ad_type}\n"
                        generated_yaml += f"  entity: {w_id}\n"
                        
                        # Generowanie ikon
                        icon_on, icon_off = get_icon_pair(w_icon, ad_type)
                        generated_yaml += f"  icon_on: {icon_on}\n"
                        generated_yaml += f"  icon_off: {icon_off}\n"

                        # Wymuszenie stanu per widget (dla pewności)
                        generated_yaml += f"  state_text: 1\n"
                        
                        # Mapowanie stanów (PL/EN)
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
                print(f"Blad przetwarzania JSON: {e}")

    return render_template('index.html', generated_yaml=generated_yaml, entities=ha_entities)

print("--> 3. Uruchamiam serwer Flask na porcie 5000...")
app.run(host='0.0.0.0', port=5000, debug=False)
