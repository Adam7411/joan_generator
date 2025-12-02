print("📦 1. Importing libraries...")
from flask import Flask, render_template, request
import os
import requests
import json
print("✅ 2. Libraries loaded.")

app = Flask(__name__)

# --- CONFIG ---
TOKEN = os.environ.get('SUPERVISOR_TOKEN')
API_URL = "http://supervisor/core/api" 

try:
    with open('/data/options.json', 'r') as f:
        options = json.load(f)
        manual_token = options.get('manual_token')
        if manual_token and len(manual_token) > 10:
            TOKEN = manual_token
            API_URL = "http://homeassistant:8123/api"
            print("🔧 Manual token found.")
except Exception as e:
    print(f"ℹ️ Info: {e}")

# STYLES FOR E-INK (High Contrast, B&W)
STYLES = {
    "title": "color: #000000; font-size: 30px; font-weight: 900; text-align: center; text-transform: uppercase; font-family: sans-serif;",
    "widget": "background-color: #FFFFFF; border: 3px solid #000000; color: #000000;",
    "value": "color: #000000; font-size: 40px; font-weight: 900;",
    "unit": "color: #000000; font-size: 16px; font-weight: 700;",
    "icon": "color: #000000;"
}

def get_ha_entities():
    if not TOKEN: return []
    headers = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
    try:
        response = requests.get(f"{API_URL}/states", headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            entities = []
            for state in data:
                attrs = state.get('attributes', {})
                entities.append({
                    'id': state['entity_id'],
                    'device_class': attrs.get('device_class', ''), # KLUCZOWE DLA SMART
                    'friendly_name': attrs.get('friendly_name', state['entity_id']),
                    'unit': attrs.get('unit_of_measurement', '')
                })
            entities.sort(key=lambda x: x['id'])
            return entities
    except Exception as e:
        print(f"❌ API Error: {e}")
    return []

@app.route('/', methods=['GET', 'POST'])
def index():
    generated_yaml = ""
    ha_entities = get_ha_entities()
    dashboard_filename = ""
    dashboard_slug = ""
    
    if request.method == 'POST':
        title = request.form.get('title', 'JoanDashboard')
        dashboard_slug = title.lower().replace(" ", "_")
        dashboard_filename = dashboard_slug + ".dash"
        
        # Generowanie YAML (fragmenty)
        generated_yaml += f"title: {title}\n"
        generated_yaml += "widget_dimensions: [115, 115]\n"
        generated_yaml += "widget_size: [1, 1]\n" # Default AppDaemon size
        generated_yaml += "widget_margins: [8, 8]\n"
        generated_yaml += "columns: 6\n"
        generated_yaml += "rows: 6\n"
        generated_yaml += "global_parameters:\n"
        generated_yaml += "  use_comma: 0\n"
        generated_yaml += "  precision: 1\n"
        generated_yaml += "  use_hass_icon: 0\n" # Ważne: 0, żeby nasze ikony działały
        generated_yaml += f"  widget_style: \"{STYLES['widget']}\"\n"
        generated_yaml += f"  icon_style_active: \"{STYLES['icon']}\"\n"
        generated_yaml += f"  icon_style_inactive: \"{STYLES['icon']}\"\n"
        generated_yaml += f"  title_style: \"{STYLES['title']}\"\n"
        generated_yaml += f"  value_style: \"{STYLES['value']}\"\n"
        generated_yaml += f"  unit_style: \"{STYLES['unit']}\"\n"
        generated_yaml += "layout:\n"
        
        layout_data_str = request.form.get('layout_data_json')
        processed_widgets = []
        
        if layout_data_str:
            layout_rows = json.loads(layout_data_str)
            for row in layout_rows:
                row_parts = []
                for w in row:
                    if w['type'] == 'spacer':
                        row_parts.append("spacer")
                    else:
                        # Format AppDaemon: widget_id(2x1)
                        w_str = w['id']
                        if w.get('size'):
                            w_str += w['size'] # np. (2x1)
                        row_parts.append(w_str)
                        processed_widgets.append(w)
                generated_yaml += f"  - {', '.join(row_parts)}\n"

            generated_yaml += "\n# --- DEFINICJE WIDGETÓW ---\n"
            seen = set()
            for w in processed_widgets:
                if w['id'] in seen: continue
                seen.add(w['id'])
                
                generated_yaml += f"{w['id']}:\n"
                generated_yaml += f"  widget_type: {w['type'] if w['type'] != 'input_boolean' else 'switch'}\n"
                if w['type'] not in ['label', 'clock']:
                    generated_yaml += f"  entity: {w['id']}\n"
                generated_yaml += f"  title: \"{w['name']}\"\n"
                
                # Obsługa ikon zgodnie z dokumentacją AppDaemon
                # Dla Switch/Light/Cover/InputBoolean -> icon_on / icon_off
                if w['type'] in ['switch', 'light', 'cover', 'binary_sensor', 'input_boolean', 'lock']:
                    if w.get('icon_on'): generated_yaml += f"  icon_on: {w['icon_on']}\n"
                    if w.get('icon_off'): generated_yaml += f"  icon_off: {w['icon_off']}\n"
                    # Dla Lock specyficzne
                    if w['type'] == 'lock':
                         generated_yaml += f"  icon_locked: {w.get('icon_off', 'mdi-lock')}\n"
                         generated_yaml += f"  icon_unlocked: {w.get('icon_on', 'mdi-lock-open')}\n"
                # Dla Sensor/Scene/Label -> icon
                else:
                    if w.get('icon'): generated_yaml += f"  icon: {w['icon']}\n"
                
                # Nawigacja
                if w['type'] == 'navigate':
                    generated_yaml += f"  dashboard: {w['id'].replace('navigate.', '')}\n"
                    generated_yaml += f"  icon_inactive: {w.get('icon', 'mdi-arrow-right')}\n"

                generated_yaml += "\n"

    return render_template('index.html', generated_yaml=generated_yaml, entities=ha_entities, filename=dashboard_filename, dash_name=dashboard_slug)

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000, debug=False)
