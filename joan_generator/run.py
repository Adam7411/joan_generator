import os
import json
import requests
from flask import Flask, render_template, request

# Inicjalizacja aplikacji
print("📦 1. Inicjalizacja aplikacji Joan 6 Generator...")
app = Flask(__name__)

# -------------------------------------------------------------------------
# 1. KONFIGURACJA API I TOKENU (HOME ASSISTANT)
# -------------------------------------------------------------------------
# Domyślnie pobieramy token z Supervisora (środowisko Hass.io)
TOKEN = os.environ.get('SUPERVISOR_TOKEN')
API_URL = "http://supervisor/core/api" 
TOKEN_SOURCE = "System (Supervisor)"

# Sprawdzamy, czy użytkownik podał własny token w konfiguracji dodatku (dla trybu manualnego)
try:
    options_path = '/data/options.json'
    if os.path.exists(options_path):
        with open(options_path, 'r') as f:
            options = json.load(f)
            manual_token = options.get('manual_token')
            # Jeśli token ma sensowną długość, używamy go zamiast systemowego
            if manual_token and len(manual_token) > 10:
                TOKEN = manual_token
                # W trybie manualnym łączymy się zazwyczaj bezpośrednio do HA na porcie 8123
                API_URL = "http://homeassistant:8123/api"
                TOKEN_SOURCE = "Manual (Konfiguracja)"
                print(f"🔧 Wykryto manualny token. Przełączam API na: {API_URL}")
except Exception as e:
    print(f"ℹ️ Info: Nie udało się odczytać pliku opcji (to normalne przy pierwszym uruchomieniu lokalnie): {e}")

if not TOKEN:
    print("❌ OSTRZEŻENIE: Brak tokena autoryzacji! Lista encji będzie pusta.")
    print("   Upewnij się, że dodatek ma odpowiednie uprawnienia lub wpisz token w konfiguracji.")
else:
    print(f"🔑 Źródło tokena: {TOKEN_SOURCE}")

# -------------------------------------------------------------------------
# 2. POBIERANIE DANYCH Z HOME ASSISTANT (PEŁNE DANE)
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
        # Wykonujemy zapytanie do API Home Assistant
        # Endpoint /api/states zwraca stan wszystkich encji
        response = requests.get(f"{API_URL}/states", headers=headers, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            entities = []
            
            for state in data:
                # Pobieramy atrybuty, aby przekazać je do JavaScript
                # Atrybuty zawierają m.in. friendly_name, device_class, unit_of_measurement
                attributes = state.get('attributes', {})
                unit = attributes.get('unit_of_measurement', '')
                
                # Budujemy obiekt encji do przekazania do szablonu
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
            
            # Sortujemy alfabetycznie po ID dla wygody użytkownika na liście
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
# Zmieniono VALUE_STYLE, aby obniżyć tekst (padding-top: 15px)
STYLE_TITLE = "color: #000000; font-size: 20px; font-weight: 700; text-align: center; padding-top: 3px; width: 100%; font-family: 'Roboto', 'Arial Black', sans-serif;"
STYLE_WIDGET = "color: #000000 !important; background-color: #FFFFFF !important;"
STYLE_TEXT = "color: #000000 !important; font-weight: 700 !important;"
# padding-top: 15px przesuwa wartość w dół (ok. 3mm na ekranie e-ink)
STYLE_VALUE = "color: #000000 !important; font-size: 44px !important; font-weight: 700 !important; padding-top: 15px !important; line-height: 1.2 !important;"
STYLE_UNIT = "color: #000000 !important;"
STYLE_ICON = "color: #000000 !important;"
STYLE_STATE_TEXT = "color: #000000 !important; font-weight: 700 !important; font-size: 16px !important;"

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
    if 'window' in i or 'blind' in i or 'shutter' in i: return 'mdi-window-shutter-open', 'mdi-window-shutter'
    return i, i + '-outline'

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
            
            # Parametry siatki (Smart Grid)
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
            if layout_data_str:
                layout_rows = json.loads(layout_data_str)
                generated_yaml += "layout:\n"
                processed_widgets = []
                
                for row in layout_rows:
                    if not row: continue # Pomiń puste wiersze
                    
                    row_parts = []
                    for w in row:
                        # Obsługa SPACER
                        if w['type'] == 'spacer':
                            row_parts.append("spacer")
                            continue
                            
                        widget_str = w['id']
                        size = w.get('size', '').strip()
                        
                        # Jeśli rozmiar różni się od domyślnego (2x1), dodaj go
                        if size and size != "(2x1)":
                            if not size.startswith('('): size = f"({size})"
                            widget_str += size
                        row_parts.append(widget_str)
                    
                    generated_yaml += f"  - {', '.join(row_parts)}\n"
                    processed_widgets.extend(row)
                
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
                    
                    # 1. NAWIGACJA
                    if w_type == 'navigate':
                        dash_target = w_id.replace('navigate.', '')
                        generated_yaml += f"  widget_type: navigate\n"
                        generated_yaml += f"  title: \"{w_name}\"\n"
                        generated_yaml += f"  dashboard: {dash_target}\n"
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
                        else:
                            generated_yaml += "  precision: 1\n"

                    # 3. MEDIA PLAYER
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
                        generated_yaml += f"  icon_style_active: \"{STYLE_ICON}\"\n"
                        generated_yaml += f"  icon_style_inactive: \"{STYLE_ICON}\"\n"
                        generated_yaml += "  state_map:\n"
                        generated_yaml += "    \"off\": \"WYŁĄCZONA\"\n"
                        generated_yaml += "    \"auto\": \"AUTO\"\n"
                        generated_yaml += "    \"heat\": \"GRZANIE\"\n"
                        generated_yaml += "    \"cool\": \"CHŁODZENIE\"\n"
                        generated_yaml += "    \"dry\": \"OSUSZANIE\"\n"
                        generated_yaml += "    \"fan_only\": \"WENTYLATOR\"\n"

                    # 5. ZEGAR
                    elif w_type == 'clock':
                        generated_yaml = generated_yaml.replace(f"  entity: {w_id}\n", "")
                        generated_yaml += f"  time_format: 24hr\n"
                        generated_yaml += f"  show_seconds: 0\n"
                        generated_yaml += f"  date_style: \"{STYLE_TEXT}\"\n"
                        generated_yaml += f"  time_style: \"{STYLE_VALUE}\"\n"

                    # 6. ETYKIETA
                    elif w_type == 'label':
                         generated_yaml = generated_yaml.replace(f"  entity: {w_id}\n", "")
                         generated_yaml += f"  text: \"{w_name}\"\n"
                         if w_icon: generated_yaml += f"  icon: {w_icon}\n"
                    
                    # 7. INNE (Actionable)
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
                        if w_icon and not i_on: generated_yaml += f"  icon: {w_icon}\n"
                        
                        generated_yaml += f"  state_text: 1\n"
                        generated_yaml += f"  title_style: \"{STYLE_TITLE}\"\n"
                        generated_yaml += f"  text_style: \"{STYLE_TEXT}\"\n"
                        generated_yaml += f"  widget_style: \"{STYLE_WIDGET}\"\n"
                        generated_yaml += f"  icon_style_active: \"{STYLE_ICON}\"\n"
                        generated_yaml += f"  icon_style_inactive: \"{STYLE_ICON}\"\n"
                        
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

                    generated_yaml += "\n"
        except Exception as e:
            print(f"❌ Error generating YAML: {e}")
            generated_yaml = f"# ERROR GENERATING YAML: {e}"

    return render_template('index.html', generated_yaml=generated_yaml, entities=ha_entities, filename=dashboard_filename, dash_name=dashboard_slug)

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000, debug=True)
