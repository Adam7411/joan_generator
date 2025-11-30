# --- IMPORTS ---
print("--> 1. Importuje biblioteki...")
from flask import Flask, render_template, request
import os
import requests
import json
print("--> 2. Biblioteki zaladowane.")

app = Flask(__name__)

# --- KONFIGURACJA ---
SUPERVISOR_TOKEN = os.environ.get('SUPERVISOR_TOKEN')
HASSIO_URL = "http://supervisor/core/api"

# --- FUNKCJE POMOCNICZE ---
def get_ha_entities():
    if not SUPERVISOR_TOKEN:
        print("Brak tokena supervisora - tryb testowy?")
        return []
    
    headers = {
        "Authorization": f"Bearer {SUPERVISOR_TOKEN}",
        "Content-Type": "application/json",
    }
    
    try:
        response = requests.get(f"{HASSIO_URL}/states", headers=headers)
        if response.status_code == 200:
            data = response.json()
            entities = [state['entity_id'] for state in data]
            entities.sort()
            return entities
    except Exception as e:
        print(f"Blad pobierania encji: {e}")
    
    return []

STYLES = {
    "title": "color: #000000; font-size: 20px; font-weight: 700; text-align: center; padding-top: 5px; width: 100%; font-family: 'Roboto', 'Arial Black', sans-serif;",
    "widget": "color: #000000 !important; background-color: #FFFFFF !important;",
    "text": "color: #000000 !important; font-weight: 700 !important;",
    "value": "color: #000000 !important; font-size: 44px !important; font-weight: 700 !important;",
    "unit": "color: #000000 !important;",
    "icon": "color: #000000 !important;"
}

# --- TRASY FLASK ---
@app.route('/', methods=['GET', 'POST'])
def index():
    generated_yaml = ""
    # Pobieramy encje przy kazdym odswiezeniu strony
    ha_entities = get_ha_entities()
    
    if request.method == 'POST':
        title = request.form.get('title', 'JoanDashboard')
        
        # HEADER
        generated_yaml += f"title: {title}\n"
        generated_yaml += "widget_dimensions: [117, 117]\n"
        generated_yaml += "widget_size: [2, 1]\n"
        generated_yaml += "widget_margins: [8, 8]\n"
        generated_yaml += "columns: 6\n"
        generated_yaml += "rows: 9\n"
        generated_yaml += "global_parameters:\n"
        generated_yaml += "  use_comma: 0\n  precision: 1\n  use_hass_icon: 1\n  namespace: default\n"
        generated_yaml += "skin: simplyred\n\n"
        
        # LAYOUT & WIDGETS PROCESSING
        layout_data_str = request.form.get('layout_data_json')
        if layout_data_str:
            try:
                layout_rows = json.loads(layout_data_str)
                
                # LAYOUT SECTION
                generated_yaml += "layout:\n"
                processed_widgets = []
                
                for row in layout_rows:
                    if not row: continue
                    row_str = ", ".join([w['id'] for w in row])
                    generated_yaml += f"  - {row_str}\n"
                    processed_widgets.extend(row)
                
                generated_yaml += "\n# --- DEFINICJE WIDZETOW ---\n\n"
                
                # WIDGET DEFINITIONS
                seen_ids = set()
                for w in processed_widgets:
                    w_id = w['id']
                    if w_id in seen_ids: continue
                    seen_ids.add(w_id)
                    
                    w_type = w['type']
                    w_name = w['name']
                    w_icon = w['icon']
                    
                    generated_yaml += f"{w_id}:\n"
                    
                    if w_type == 'navigate':
                        dashboard_name = w_id.replace('navigate.', '')
                        generated_yaml += f"  widget_type: navigate\n"
                        generated_yaml += f"  dashboard: {dashboard_name}\n"
                        generated_yaml += f"  title: \"{w_name}\"\n"
                        generated_yaml += f"  icon_inactive: {w_icon if w_icon else 'mdi-arrow-left-circle'}\n"
                        generated_yaml += f"  widget_style: \"background-color: #FFFFFF !important; border-radius: 8px !important; padding: 10px !important; color: #000000 !important;\"\n"
                        generated_yaml += f"  title_style: \"{STYLES['title']}\"\n"
                    
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

                    else:
                        generated_yaml += f"  widget_type: {w_type}\n"
                        generated_yaml += f"  entity: {w_id}\n"
                        generated_yaml += f"  title: {w_name}\n"
                        generated_yaml += f"  icon_on: {w_icon if w_icon else 'mdi-toggle-switch'}\n"
                        generated_yaml += f"  icon_off: {w_icon if w_icon else 'mdi-toggle-switch-off'}\n"
                        generated_yaml += f"  state_text: 1\n"
                        generated_yaml += f"  title_style: \"{STYLES['title']}\"\n"
                        generated_yaml += f"  widget_style: \"{STYLES['widget']}\"\n"
                        generated_yaml += f"  icon_style_active: \"{STYLES['icon']}\"\n"
                        generated_yaml += f"  icon_style_inactive: \"{STYLES['icon']}\"\n"
                        generated_yaml += "  state_map:\n"
                        generated_yaml += "    \"on\": \"WL\"\n    \"off\": \"WYL\"\n"
                        if w_type == 'cover':
                            generated_yaml += "    \"open\": \"OTWARTA\"\n    \"closed\": \"ZAMKNIETA\"\n"
                    
                    generated_yaml += "\n"
            except Exception as e:
                print(f"Blad przetwarzania JSON: {e}")

    return render_template('index.html', generated_yaml=generated_yaml, entities=ha_entities)

# --- URUCHOMIENIE ---
print("--> 3. Uruchamiam serwer Flask na porcie 5000...")

# BEZWARUNKOWE URUCHOMIENIE (Bez if __name__ == main)
# To gwarantuje, ze serwer wystartuje
app.run(host='0.0.0.0', port=5000, debug=False)
