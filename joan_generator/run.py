import os
import json
import requests
from flask import Flask, render_template, request

print("📦 1. Inicjalizacja aplikacji Joan 6 Generator...")

app = Flask(__name__)

# -------------------------------------------------------------------------
# 1. KONFIGURACJA API I TOKENU
# -------------------------------------------------------------------------
# Domyślnie pobieramy token z Supervisora (Hass.io)
TOKEN = os.environ.get('SUPERVISOR_TOKEN')
API_URL = "http://supervisor/core/api" 
TOKEN_SOURCE = "System (Supervisor)"

# Sprawdzamy, czy użytkownik podał własny token w konfiguracji dodatku
try:
    options_path = '/data/options.json'
    if os.path.exists(options_path):
        with open(options_path, 'r') as f:
            options = json.load(f)
            manual_token = options.get('manual_token')
            # Jeśli token ma sensowną długość, używamy go
            if manual_token and len(manual_token) > 10:
                TOKEN = manual_token
                # W trybie manualnym zazwyczaj łączymy się bezpośrednio do HA
                API_URL = "http://homeassistant:8123/api"
                TOKEN_SOURCE = "Manual (Konfiguracja)"
                print(f"🔧 Wykryto manualny token. Przełączam API na: {API_URL}")
except Exception as e:
    print(f"ℹ️ Info: Nie udało się odczytać opcji (to normalne przy pierwszym uruchomieniu lokalnie): {e}")

if not TOKEN:
    print("❌ OSTRZEŻENIE: Brak tokena autoryzacji! Lista encji będzie pusta.")
    print("   Upewnij się, że dodatek ma odpowiednie uprawnienia lub wpisz token w konfiguracji.")
else:
    print(f"🔑 Źródło tokena: {TOKEN_SOURCE}")

# -------------------------------------------------------------------------
# 2. POBIERANIE DANYCH Z HOME ASSISTANT
# -------------------------------------------------------------------------
def get_ha_entities():
    """
    Pobiera listę wszystkich encji z Home Assistant wraz z ich stanami i atrybutami.
    Jest to kluczowe dla funkcji Smart (wykrywanie typu) oraz Podglądu (Real-time state).
    """
    if not TOKEN:
        return []
    
    headers = {
        "Authorization": f"Bearer {TOKEN}", 
        "Content-Type": "application/json"
    }
    
    try:
        # print(f"🌍 Pobieranie stanów z: {API_URL}/states")
        response = requests.get(f"{API_URL}/states", headers=headers, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            entities = []
            
            for state in data:
                # Pobieramy atrybuty, aby przekazać je do JavaScript
                attributes = state.get('attributes', {})
                
                # Budujemy obiekt encji
                entity_obj = {
                    'id': state['entity_id'],
                    'state': state['state'],
                    'attributes': {
                        'friendly_name': attributes.get('friendly_name', state['entity_id']),
                        'device_class': attributes.get('device_class', ''),
                        'unit_of_measurement': attributes.get('unit_of_measurement', '')
                    },
                    'unit': attributes.get('unit_of_measurement', '')
                }
                entities.append(entity_obj)
            
            # Sortujemy alfabetycznie po ID dla wygody użytkownika
            entities.sort(key=lambda x: x['id'])
            return entities
            
        elif response.status_code == 401:
            print("❌ Błąd 401: Nieautoryzowany dostęp. Sprawdź token.")
        else:
            print(f"⚠️ Błąd API Home Assistant: {response.status_code} - {response.text}")
            
    except Exception as e:
        print(f"❌ Wyjątek podczas pobierania encji: {e}")
    
    return []

# -------------------------------------------------------------------------
# 3. DEFINICJE STYLÓW (ZGODNE Z JOAN.TXT)
# -------------------------------------------------------------------------
# Te stałe są używane do generowania kodu YAML, aby zachować spójność stylu.
STYLE_TITLE = "color: #000000; font-size: 20px; font-weight: 700; text-align: center; padding-top: 3px; width: 100%; font-family: 'Roboto', 'Arial Black', sans-serif;"
STYLE_WIDGET = "color: #000000 !important; background-color: #FFFFFF !important;"
STYLE_TEXT = "color: #000000 !important; font-weight: 700 !important;"
STYLE_VALUE = "color: #000000 !important; font-size: 44px !important; font-weight: 700 !important;"
STYLE_UNIT = "color: #000000 !important;"
STYLE_ICON = "color: #000000 !important;"
STYLE_STATE_TEXT = "color: #000000 !important; font-weight: 700 !important; font-size: 16px !important;"

# -------------------------------------------------------------------------
# 4. GŁÓWNY ROUTE (ENDPOINT)
# -------------------------------------------------------------------------
@app.route('/', methods=['GET', 'POST'])
def index():
    generated_yaml = ""
    # Zawsze pobieramy świeże dane o encjach przy odświeżeniu strony
    ha_entities = get_ha_entities()
    
    dashboard_filename = "joandashboard.dash"
    dashboard_slug = "joandashboard"
    
    if request.method == 'POST':
        try:
            # Pobranie danych z formularza
            title = request.form.get('title', 'JoanDashboard')
            dashboard_slug = title.lower().replace(" ", "_")
            dashboard_filename = dashboard_slug + ".dash"
            
            # Parametry siatki
            cols = request.form.get('grid_columns', '6')
            rows = request.form.get('grid_rows', '8')
            
            # Język interfejsu (wpływa na state_map)
            lang = request.form.get('ui_language', 'pl')
            
            # Słownik tłumaczeń stanów dla YAML
            TRANS = {
                'pl': {
                    'on': 'WŁĄCZONE', 'off': 'WYŁĄCZONE', 
                    'open': 'OTWARTA', 'closed': 'ZAMKNIĘTA', 
                    'opening': 'OTWIERANIE', 'closing': 'ZAMYKANIE',
                    'locked': 'ZAMKNIĘTE', 'unlocked': 'OTWARTE', 
                    'home': 'W DOMU', 'not_home': 'POZA'
                },
                'en': {
                    'on': 'ON', 'off': 'OFF', 
                    'open': 'OPEN', 'closed': 'CLOSED', 
                    'opening': 'OPENING', 'closing': 'CLOSING',
                    'locked': 'LOCKED', 'unlocked': 'UNLOCKED', 
                    'home': 'HOME', 'not_home': 'AWAY'
                }
            }
            dic = TRANS.get(lang, TRANS['pl'])

            # -------------------------------------------------
            # GENEROWANIE NAGŁÓWKA DASHBOARDU
            # -------------------------------------------------
            generated_yaml += f"title: {title}\n"
            generated_yaml += "widget_dimensions: [117, 117]\n"
            generated_yaml += "widget_size: [2, 1]\n" # Domyślny rozmiar bazowy
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
            
            # -------------------------------------------------
            # GENEROWANIE SEKCJI LAYOUT
            # -------------------------------------------------
            layout_data_str = request.form.get('layout_data_json')
            processed_widgets = []
            
            if layout_data_str:
                layout_rows = json.loads(layout_data_str)
                generated_yaml += "layout:\n"
                
                for row in layout_rows:
                    if not row: continue # Pomiń puste wiersze
                    
                    row_parts = []
                    for w in row:
                        # Obsługa SPACER
                        if w['type'] == 'spacer':
                            row_parts.append("spacer")
                            continue
                            
                        widget_id = w['id']
                        size = w.get('size', '').strip()
                        
                        # Jeśli rozmiar różni się od domyślnego (2x1), dodaj go
                        # W joan.txt widget_size to [2, 1], więc 2x1 jest domyślne.
                        if size and size != "(2x1)":
                            if not size.startswith('('): size = f"({size})"
                            widget_id += size
                            
                        row_parts.append(widget_id)
                        processed_widgets.append(w) # Zapisz do późniejszego definiowania
                    
                    generated_yaml += f"  - {', '.join(row_parts)}\n"
                
                generated_yaml += "\n# -------------------\n# DEFINICJE WIDŻETÓW\n# -------------------\n\n"
                
                # -------------------------------------------------
                # GENEROWANIE SZCZEGÓŁOWYCH DEFINICJI
                # -------------------------------------------------
                seen_ids = set()
                for w in processed_widgets:
                    w_id = w['id']
                    if w_id in seen_ids: continue # Unikaj duplikatów definicji
                    seen_ids.add(w_id)
                    
                    w_type = w['type']
                    w_name = w['name']
                    w_icon = w['icon']
                    i_on = w.get('icon_on')
                    i_off = w.get('icon_off')
                    
                    generated_yaml += f"{w_id}:\n"
                    
                    # --- 1. NAWIGACJA ---
                    if w_type == 'navigate':
                        # Navigate nie ma 'entity', ma 'dashboard'
                        dash_target = w_id.replace('navigate.', '')
                        generated_yaml += f"  widget_type: navigate\n"
                        generated_yaml += f"  title: \"{w_name}\"\n"
                        generated_yaml += f"  dashboard: {dash_target}\n"
                        generated_yaml += f"  icon_inactive: {w_icon or 'mdi-arrow-right-circle'}\n"
                        generated_yaml += f"  title_style: \"{STYLE_TITLE}\"\n"
                        generated_yaml += f"  widget_style: \"background-color: #FFFFFF !important; border-radius: 8px !important; padding: 10px !important; color: #000000 !important;\"\n"

                    # --- 2. SENSOR ---
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
                        # Precyzja dla baterii
                        if 'bateria' in w_id or 'battery' in w_id:
                            generated_yaml += "  precision: 0\n"
                        else:
                            generated_yaml += "  precision: 1\n"

                    # --- 3. MEDIA PLAYER ---
                    elif w_type == 'media_player':
                        generated_yaml += f"  widget_type: media_player\n"
                        generated_yaml += f"  entity: {w_id}\n"
                        generated_yaml += f"  title: \"{w_name}\"\n"
                        if w_icon: generated_yaml += f"  icon: {w_icon}\n"
                        generated_yaml += f"  title_style: \"{STYLE_TITLE}\"\n"
                        generated_yaml += f"  widget_style: \"{STYLE_WIDGET}\"\n"
                        generated_yaml += f"  icon_style: \"{STYLE_ICON}\"\n"
                        generated_yaml += "  truncate_name: 20\n"

                    # --- 4. CLIMATE ---
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
                        generated_yaml += f"  icon_style_active: \"{STYLE_ICON}\"\n"
                        generated_yaml += f"  icon_style_inactive: \"{STYLE_ICON}\"\n"
                        # Mapowanie stanów klimatyzacji
                        generated_yaml += "  state_map:\n"
                        generated_yaml += "    \"off\": \"WYŁĄCZONA\"\n"
                        generated_yaml += "    \"auto\": \"AUTO\"\n"
                        generated_yaml += "    \"heat\": \"GRZANIE\"\n"
                        generated_yaml += "    \"cool\": \"CHŁODZENIE\"\n"
                        generated_yaml += "    \"dry\": \"OSUSZANIE\"\n"
                        generated_yaml += "    \"fan_only\": \"WENTYLATOR\"\n"

                    # --- 5. ZEGAR ---
                    elif w_type == 'clock':
                        generated_yaml += f"  widget_type: clock\n"
                        generated_yaml += f"  time_format: 24hr\n"
                        generated_yaml += f"  show_seconds: 0\n"
                        generated_yaml += f"  date_style: \"{STYLE_TEXT}\"\n"
                        generated_yaml += f"  time_style: \"{STYLE_VALUE}\"\n"

                    # --- 6. LABEL ---
                    elif w_type == 'label':
                         generated_yaml += f"  widget_type: label\n"
                         generated_yaml += f"  text: \"{w_name}\"\n"
                         if w_icon: generated_yaml += f"  icon: {w_icon}\n"
                    
                    # --- 7. POZOSTAŁE (SWITCH, LIGHT, COVER, LOCK...) ---
                    else:
                        # Mapowanie typu formularza na typ AppDaemon
                        real_type = 'switch' # Domyślny
                        if w_type == 'cover': real_type = 'cover'
                        elif w_type == 'binary_sensor': real_type = 'binary_sensor'
                        elif w_type == 'input_boolean': real_type = 'switch'
                        elif w_type == 'light': real_type = 'switch'
                        elif w_type == 'lock': real_type = 'lock'
                        elif w_type == 'script': real_type = 'script'
                        elif w_type == 'input_select': real_type = 'input_select'
                        elif w_type == 'input_number': real_type = 'input_number'
                        
                        generated_yaml += f"  widget_type: {real_type}\n"
                        generated_yaml += f"  entity: {w_id}\n"
                        generated_yaml += f"  title: \"{w_name}\"\n"
                        
                        # Obsługa ikon (on/off)
                        if i_on: generated_yaml += f"  icon_on: {i_on}\n"
                        if i_off: generated_yaml += f"  icon_off: {i_off}\n"
                        # Jeśli to zamek, używamy icon_locked/unlocked
                        if real_type == 'lock':
                            if i_off: generated_yaml += f"  icon_locked: {i_off}\n"
                            if i_on: generated_yaml += f"  icon_unlocked: {i_on}\n"
                        # Zwykła ikona jako fallback
                        if w_icon and not i_on: generated_yaml += f"  icon: {w_icon}\n"
                        
                        generated_yaml += f"  state_text: 1\n"
                        generated_yaml += f"  title_style: \"{STYLE_TITLE}\"\n"
                        generated_yaml += f"  text_style: \"{STYLE_TEXT}\"\n"
                        generated_yaml += f"  widget_style: \"{STYLE_WIDGET}\"\n"
                        generated_yaml += f"  icon_style_active: \"{STYLE_ICON}\"\n"
                        generated_yaml += f"  icon_style_inactive: \"{STYLE_ICON}\"\n"
                        
                        # Mapowanie stanów na PL/EN
                        if real_type == 'cover':
                            generated_yaml += "  state_map:\n"
                            generated_yaml += f"    \"open\": \"{dic['open']}\"\n"
                            generated_yaml += f"    \"closed\": \"{dic['closed']}\"\n"
                            generated_yaml += f"    \"opening\": \"{dic['opening']}\"\n"
                            generated_yaml += f"    \"closing\": \"{dic['closing']}\"\n"
                        elif real_type == 'binary_sensor':
                            generated_yaml += "  state_map:\n"
                            generated_yaml += f"    \"on\": \"{dic['open']}\"\n" # Zazwyczaj open dla drzwi
                            generated_yaml += f"    \"off\": \"{dic['closed']}\"\n"
                        elif real_type in ['switch', 'light']:
                            generated_yaml += "  state_map:\n"
                            generated_yaml += f"    \"on\": \"{dic['on']}\"\n"
                            generated_yaml += f"    \"off\": \"{dic['off']}\"\n"
                        elif real_type == 'lock':
                            generated_yaml += "  state_map:\n"
                            generated_yaml += f"    \"locked\": \"{dic['locked']}\"\n"
                            generated_yaml += f"    \"unlocked\": \"{dic['unlocked']}\"\n"

                    generated_yaml += "\n"
        except Exception as e:
            print(f"❌ Błąd generowania YAML: {e}")
            generated_yaml = f"# ERROR GENERATING YAML: {e}"

    return render_template('index.html', generated_yaml=generated_yaml, entities=ha_entities, filename=dashboard_filename, dash_name=dashboard_slug)

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000, debug=True)
