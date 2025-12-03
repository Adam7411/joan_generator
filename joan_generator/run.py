import os
import json
import requests
from flask import Flask, render_template, request

app = Flask(__name__)

# -------------------------------------------------------------------------
# 1. KONFIGURACJA I ZMIENNE ŚRODOWISKOWE
# -------------------------------------------------------------------------
SUPERVISOR_TOKEN = os.environ.get('SUPERVISOR_TOKEN')
HASSIO_URL = "http://supervisor/core/api"

# Ścieżka do pliku opcji (options.json) w Home Assistant
OPTIONS_PATH = "/data/options.json"

def get_options():
    """Wczytuje opcje z pliku konfiguracyjnego add-ona."""
    if os.path.exists(OPTIONS_PATH):
        try:
            with open(OPTIONS_PATH, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"Błąd odczytu options.json: {e}")
    return {}

# -------------------------------------------------------------------------
# 2. POBIERANIE ENCJI Z HOME ASSISTANT
# -------------------------------------------------------------------------
def get_ha_entities():
    """Pobiera listę encji z API Home Assistant."""
    token = SUPERVISOR_TOKEN
    
    # Sprawdzenie, czy użytkownik podał manualny token w konfiguracji
    options = get_options()
    manual_token = options.get('manual_token', '')
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    # Jeśli brak tokenu supervisora, próbujemy użyć manualnego (dla testów lokalnych/zewnętrznych)
    if not token and manual_token:
        token = manual_token
        headers["Authorization"] = f"Bearer {token}"
        # Jeśli używamy manualnego tokenu, adres może być inny (np. localhost:8123), 
        # ale w strukturze Add-ona zazwyczaj supervisor wystarcza. 
        # Tutaj zakładamy standardowe flow Supervisora.

    if not token:
        print("⚠️ Brak tokenu autoryzacji (SUPERVISOR_TOKEN ani manual_token).")
        return []

    try:
        url = f"{HASSIO_URL}/states"
        # Dla debugowania poza HA (np. bezpośrednio do IP HA):
        # url = "http://192.168.X.X:8123/api/states"
        
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        # Sortowanie alfabetyczne po entity_id
        data.sort(key=lambda x: x['entity_id'])
        return data
    except Exception as e:
        print(f"❌ Wyjątek podczas pobierania encji: {e}")
    return []

# -------------------------------------------------------------------------
# 3. STYLE (ZGODNE Z WYMOGAMI 33px i INLINE-BLOCK - E-INK OPTIMIZED)
# -------------------------------------------------------------------------
STYLE_TITLE = "color: #000000; font-size: 20px; font-weight: 700; text-align: center; padding-top: 3px; width: 100%; font-family: 'Roboto', 'Arial Black', sans-serif;"
STYLE_WIDGET = "color: #000000 !important; background-color: #FFFFFF !important;"
STYLE_TEXT = "color: #000000 !important; font-weight: 700 !important;"
STYLE_VALUE = "color: #000000 !important; font-size: 44px !important; font-weight: 700 !important; padding-top: 33px !important; line-height: 1.2 !important; display: inline-block !important;"
STYLE_UNIT = "color: #000000 !important; padding-top: 33px !important; display: inline-block !important;"
STYLE_ICON = "color: #000000 !important;"
STYLE_STATE_TEXT = "color: #000000 !important; font-weight: 700 !important; font-size: 16px !important;"

# -------------------------------------------------------------------------
# 4. ROUTE GŁÓWNY
# -------------------------------------------------------------------------
@app.route('/', methods=['GET', 'POST'])
def index():
    generated_yaml = ""
    ha_entities = get_ha_entities()
    dashboard_filename = "joandashboard.dash"
    dashboard_slug = "joandashboard"
    
    if request.method == 'POST':
        try:
            # Pobranie danych z formularza
            title = request.form.get('title', 'JoanDashboard')
            dashboard_slug = title.lower().replace(" ", "_")
            dashboard_filename = dashboard_slug + ".dash"
            
            # Konfiguracja siatki
            cols = request.form.get('grid_columns', '4')
            rows = request.form.get('grid_rows', '8')
            lang = request.form.get('ui_language', 'pl')
            
            # Słownik tłumaczeń dla stanów (mapowanie w AppDaemon)
            TRANS = {
                'pl': {'on': 'WŁĄCZONE', 'off': 'WYŁĄCZONE', 'open': 'OTWARTA', 'closed': 'ZAMKNIĘTA', 'opening': 'OTWIERANIE', 'closing': 'ZAMYKANIE', 'locked': 'ZAMKNIĘTE', 'unlocked': 'OTWARTE', 'home': 'W DOMU', 'not_home': 'POZA'},
                'en': {'on': 'ON', 'off': 'OFF', 'open': 'OPEN', 'closed': 'CLOSED', 'opening': 'OPENING', 'closing': 'CLOSING', 'locked': 'LOCKED', 'unlocked': 'UNLOCKED', 'home': 'HOME', 'not_home': 'AWAY'}
            }
            dic = TRANS.get(lang, TRANS['pl'])

            # --- NAGŁÓWEK YAML ---
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
            generated_yaml += "\n"

            # --- PRZETWARZANIE WIDGETÓW ---
            layout_json = request.form.get('layout_data_json', '[]')
            layout_data = json.loads(layout_json)  # Tablica wierszy, każdy wiersz to tablica widgetów

            layout_yaml_lines = [] # Tutaj będziemy zbierać definicje layoutu

            widget_definitions = ""
            
            row_idx = 0
            for row in layout_data:
                row_widgets_ids = []
                # Jeśli wiersz jest pusty, AppDaemon wymaga pustej linii w layout lub puste miejsce
                if not row:
                    # Dodajemy pusty wiersz (opcjonalne, zależnie od logiki)
                    # layout_yaml_lines.append(f"    - spacer") # ewentualnie
                    pass
                else:
                    for widget in row:
                        w_id = widget.get('id')
                        w_type = widget.get('type')
                        w_title = widget.get('title', '')
                        w_entity = widget.get('entity', '')
                        w_size = widget.get('size', '2x1')
                        
                        # Pobieranie niestandardowych ikon
                        w_icon_on = widget.get('icon_on', '').strip()
                        w_icon_off = widget.get('icon_off', '').strip()

                        # Generowanie definicji widgetu
                        widget_def = f"{w_id}:\n"
                        widget_def += f"    widget_type: {w_type}\n"
                        
                        # Jeśli to nie label/clock/weather, dodajemy entity
                        if w_type not in ['label', 'clock', 'weather', 'navigate']:
                            widget_def += f"    entity: {w_entity}\n"
                        
                        widget_def += f"    title: \"{w_title}\"\n"
                        
                        # Obsługa customowych ikon (NOWOŚĆ)
                        if w_icon_on:
                            widget_def += f"    icon_on: {w_icon_on}\n"
                            # Dla sensorów często używa się po prostu 'icon', ale AppDaemon mapuje icon_on
                            # w wielu widgetach jako główną ikonę.
                            widget_def += f"    icon: {w_icon_on}\n" 
                        
                        if w_icon_off:
                            widget_def += f"    icon_off: {w_icon_off}\n"

                        # Style E-Ink
                        widget_def += f"    widget_style: \"{STYLE_WIDGET}\"\n"

                        # Specyficzne dla typów
                        if w_type == 'switch' or w_type == 'light' or w_type == 'cover':
                            widget_def += f"    state_text: 1\n"
                            widget_def += f"    state_map:\n"
                            widget_def += f"      \"on\": \"{dic['on']}\"\n"
                            widget_def += f"      \"off\": \"{dic['off']}\"\n"
                            if w_type == 'cover':
                                widget_def += f"      \"open\": \"{dic['open']}\"\n"
                                widget_def += f"      \"closed\": \"{dic['closed']}\"\n"
                                widget_def += f"      \"opening\": \"{dic['opening']}\"\n"
                                widget_def += f"      \"closing\": \"{dic['closing']}\"\n"
                            widget_def += f"    state_text_style: \"{STYLE_STATE_TEXT}\"\n"
                            widget_def += f"    title_style: \"{STYLE_TITLE}\"\n"
                            widget_def += f"    icon_style: \"{STYLE_ICON}\"\n"

                        elif w_type == 'sensor':
                            widget_def += f"    text_style: \"{STYLE_TEXT}\"\n"
                            widget_def += f"    value_style: \"{STYLE_VALUE}\"\n"
                            widget_def += f"    unit_style: \"{STYLE_UNIT}\"\n"
                            widget_def += f"    title_style: \"{STYLE_TITLE}\"\n"
                            # Sensory binarne
                            if 'binary' in w_entity:
                                widget_def += f"    state_text: 1\n"
                                widget_def += f"    state_map:\n"
                                widget_def += f"      \"on\": \"{dic['open']}\"\n"
                                widget_def += f"      \"off\": \"{dic['closed']}\"\n"

                        elif w_type == 'navigate':
                            dash_target = w_entity  # Dla nawigacji używamy pola entity jako celu
                            widget_def += f"    dashboard: {dash_target}\n"
                            widget_def += f"    title_style: \"{STYLE_TITLE}\"\n"
                            widget_def += f"    icon_inactive_style: \"{STYLE_ICON}\"\n" 
                            widget_def += f"    icon_active_style: \"{STYLE_ICON}\"\n"

                        elif w_type == 'label':
                            widget_def += f"    text_style: \"{STYLE_TITLE}\"\n"

                        elif w_type == 'clock':
                            widget_def += f"    date_style: \"{STYLE_TITLE}\"\n"
                            widget_def += f"    time_style: \"{STYLE_VALUE}\"\n"

                        widget_def += "\n"
                        widget_definitions += widget_def
                        
                        # Dodanie ID do layoutu (z obsługą rozmiaru)
                        size_str = f"({w_size})"
                        row_widgets_ids.append(f"{w_id}{size_str}")

                # Formatowanie wiersza w sekcji layout:
                # np. - light_salon(2x1), sensor_temp(2x1)
                line = "    - " + ", ".join(row_widgets_ids)
                layout_yaml_lines.append(line)
                row_idx += 1

            # --- SKŁADANIE CAŁOŚCI ---
            generated_yaml += widget_definitions
            generated_yaml += "layout:\n"
            for line in layout_yaml_lines:
                generated_yaml += line + "\n"

        except Exception as e:
            print(f"Błąd generowania YAML: {e}")
            generated_yaml = f"# BŁĄD GENEROWANIA: {e}"

    return render_template('index.html', 
                           generated_yaml=generated_yaml, 
                           entities=ha_entities,
                           filename=dashboard_filename,
                           dash_name=dashboard_slug)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
