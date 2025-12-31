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
SUPERVISOR_URL = "http://supervisor"  # <--- DODAJ TO
TOKEN_SOURCE = "System (Supervisor)"

# Tutaj wpisz slug swojego AppDaemona (folderu z addon_configs)
APPDAEMON_SLUG = "a0d7b954_appdaemon" # <--- DODAJ TO

try:
    options_path = '/data/options.json'
    if os.path.exists(options_path):
        with open(options_path, 'r') as f:
            options = json.load(f)
            manual_token = options.get('manual_token')
            if manual_token and len(manual_token) > 10:
                TOKEN = manual_token
                # Adres lokalny HA
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
    if not TOKEN:
        return []
    headers = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
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
        print(f"❌ Wyjątek podczas pobierania encji: {e}")
    return []

# -------------------------------------------------------------------------
# FUNKCJA RESTARTU APPDAEMON
# -------------------------------------------------------------------------
def restart_appdaemon_addon():
    """Restartuje AppDaemon używając dostępnego tokena (Manual lub Supervisor)"""
    
    # 1. Sprawdź czy mamy JAKIKOLWIEK token (Manualny lub Systemowy)
    if not TOKEN:
        return False, "Błąd: Brak tokena API (uzupełnij manual_token w konfiguracji)."
    
    # Zdefiniuj slug Twojego AppDaemona
    target_slug = "a0d7b954_appdaemon"
    
    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json"
    }

    # 2. Wybierz metodę restartu w zależności od wykrytego API
    # Jeśli API_URL zawiera "homeassistant" lub port "8123", to używamy Manual Tokena
    if "homeassistant" in API_URL or "8123" in API_URL:
        # Metoda 1: Service Call (dla Manual Token)
        url = f"{API_URL}/services/hassio/addon_restart"
        payload = {"addon": target_slug}
        print(f"🔄 Restart przez Service Call (Manual Token): {url}")
        
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=30)
        except Exception as e:
            print(f"❌ Wyjątek połączenia: {e}")
            return False, str(e)

    else:
        # Metoda 2: Supervisor API (dla Tokena Systemowego)
        url = f"http://supervisor/addons/{target_slug}/restart"
        print(f"🔄 Restart przez Supervisor API: {url}")
        
        try:
            response = requests.post(url, headers=headers, timeout=30)
        except Exception as e:
            print(f"❌ Wyjątek połączenia: {e}")
            return False, str(e)

    # 3. Sprawdź wynik
    if response.status_code in [200, 201, 202]:
        print("✅ Restart udany.")
        return True, "Zrestartowano AppDaemon."
    else:
        print(f"❌ Błąd API: {response.status_code} - {response.text}")
        return False, f"Błąd API: {response.status_code} {response.text}"

# -------------------------------------------------------------------------
# 3. STYLE (E-INK OPTIMIZED & TWEAKED)
# -------------------------------------------------------------------------
# Style wymuszające wysoki kontrast (czarny na białym) dla ekranów E-Ink
STYLE_TITLE = "color: #000000; font-size: 20px; font-weight: 700; text-align: center; padding-top: 5px; width: 100%; font-family: 'Roboto', 'Arial Black', sans-serif;"
STYLE_WIDGET = "color: #000000 !important; background-color: #FFFFFF !important;"
STYLE_TEXT = "color: #000000 !important; font-weight: 700 !important;"
STYLE_VALUE = "color: #000000 !important; font-size: 54px !important; font-weight: 700 !important; padding-top: 60px !important; line-height: 1.1 !important; display: inline-block !important;"
STYLE_UNIT = "color: #000000 !important; padding-top: 60px !important; display: inline-block !important;"
STYLE_ICON = "color: #000000 !important;"
STYLE_STATE_TEXT = "color: #000000 !important; font-weight: 700 !important; font-size: 16px !important;"

# -------------------------------------------------------------------------
# 4. NORMALIZACJA FORMATU IKON DLA APPDAEMON
# -------------------------------------------------------------------------
def normalize_icon_format(icon_name):
    """
    Normalizuje format ikon do formatu 'mdi-nazwa'.
    """
    if not icon_name: 
        return icon_name
    
    icon_name = icon_name.strip()
    
    if icon_name.startswith('mdi:'):
        return 'mdi-' + icon_name[4:]
    
    if icon_name.startswith('mdi-'):
        return icon_name
    
    return icon_name

# -------------------------------------------------------------------------
# 5. LOGIKA GENEROWANIA YAML (Wydzielona funkcja)
# -------------------------------------------------------------------------
def generate_joan_dash_yaml(rows, title, grid_params, lang_code, custom_defs):
    """
    Generuje wynikowy plik .dash na podstawie parametrów.
    grid_params: słownik z kluczami 'cols', 'rows_grid', 'def_w', 'def_h'
    """
    
    # 1. Tłumaczenia (przeniesione do środka lub jako stała globalna)
    TRANS = {
        'pl': {
            'on': 'WŁĄCZONE', 'off': 'WYŁĄCZONE', 
            'open': 'OTWARTE', 'closed': 'ZAMKNIĘTE', 
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
    dic = TRANS.get(lang_code, TRANS['pl'])

    # 2. Obliczenia kolumn AppDaemon
    ad_columns = grid_params['cols'] if grid_params['def_w'] == 1 else grid_params['cols'] * 2

    # 3. Budowanie nagłówka
    output = []
    output.append(f"title: {title}")
    output.append("widget_dimensions: [117, 117]")
    output.append(f"widget_size: [{grid_params['def_w']}, {grid_params['def_h']}]")
    output.append("widget_margins: [8, 8]")
    output.append(f"columns: {ad_columns}")
    output.append(f"rows: {grid_params['rows_grid']}")
    output.append("global_parameters:")
    output.append("  use_comma: 0")
    output.append("  precision: 1")
    output.append("  use_hass_icon: 1")
    output.append("  namespace: default")
    output.append("  devices:")
    output.append("    media_player:")
    output.append("      step: 5")
    output.append("    climate:")
    output.append("      step: 1")
    output.append(f"  white_text_style: \"{STYLE_TEXT}\"")
    output.append(f"  state_text_style: \"{STYLE_STATE_TEXT}\"")
    output.append("skin: simplyred")
    output.append("")

    try:
        layout_data_str = json.dumps(rows)  # Zakładamy, że rows jest listą, ale używamy do generowania
        custom_defs_str = json.dumps(custom_defs)
        
        processed_widgets = []
        
        # -------------------------------------------------
        # GENEROWANIE SEKCJI LAYOUT
        # -------------------------------------------------
        if rows:
            output.append("layout:")
            for row in rows:
                if not row: 
                    continue
                row_parts = []
                for w in row:
                    if w['type'] == 'spacer':
                        row_parts.append("spacer")
                        continue
                    
                    widget_id = w['id']
                    size_str = w.get('size', '')
                    is_default = False
                    
                    # Sprawdzanie czy rozmiar jest domyślny
                    if size_str == f"({grid_params['def_w']}x{grid_params['def_h']})":
                        is_default = True
                    elif size_str == "(2x1)" and grid_params['def_w'] == 2 and grid_params['def_h'] == 1:
                        is_default = True
                    elif size_str == "(1x1)" and grid_params['def_w'] == 1 and grid_params['def_h'] == 1:
                        is_default = True
                        
                    if not is_default and size_str:
                        if not size_str.startswith('('):
                            size_str = f"({size_str})"
                        widget_id += size_str
                     
                    row_parts.append(widget_id)
                    processed_widgets.append(w)
                output.append(f"  - {', '.join(row_parts)}")
            
            output.append("")
            output.append("# -------------------")
            output.append("# DEFINICJE WIDŻETÓW")
            output.append("# -------------------")
            output.append("")

            seen_ids = set()
            
            # -------------------------------------------------
            # GENEROWANIE SZCZEGÓŁÓW KAŻDEGO WIDGETU
            # -------------------------------------------------
            for w in processed_widgets: 
                w_id = w['id']
                if w_id in seen_ids: 
                    continue
                seen_ids.add(w_id)
                
                # Importowane widgety bez edycji zachowują swój kod
                if w_id in custom_defs and not w.get('was_edited', False):
                    output.append(f"{w_id}:")
                    for line in custom_defs[w_id].split('\n'):
                        if line.strip():
                            output.append(f"  {line}")
                    output.append("")
                    continue

                w_type = w['type']
                w_name = w['name']
                w_icon = normalize_icon_format(w['icon'])
                i_on = normalize_icon_format(w.get('icon_on'))
                i_off = normalize_icon_format(w.get('icon_off'))
                
                output.append(f"{w_id}:")
                
                # --- NAVIGATE ---
                if w_type == 'navigate':
                    dash_target = w_id.replace('navigate.', '')
                    nav_icon = w_icon or 'mdi-arrow-right-circle'
                    output.append(f"  widget_type: navigate")
                    output.append(f"  title: \"{w_name}\"")
                    output.append(f"  dashboard: {dash_target}")
                    output.append(f"  icon_active: {nav_icon}")
                    output.append(f"  icon_inactive: {nav_icon}")
                    output.append(f"  title_style: \"{STYLE_TITLE}\"")
                    output.append(f"  widget_style: \"{STYLE_WIDGET}\"")
                    output.append(f"  icon_active_style: \"{STYLE_ICON}\"")
                    output.append(f"  icon_inactive_style: \"{STYLE_ICON}\"")

                # --- SENSOR ---
                elif w_type == 'sensor':
                    output.append(f"  widget_type: sensor")
                    output.append(f"  entity: {w_id}")
                    output.append(f"  title: \"{w_name}\"")
                    output.append(f"  title_style: \"{STYLE_TITLE}\"")
                    output.append(f"  text_style: \"{STYLE_TEXT}\"")
                    output.append(f"  value_style: \"{STYLE_VALUE}\"")
                    output.append(f"  unit_style: \"{STYLE_UNIT}\"")
                    output.append(f"  widget_style: \"{STYLE_WIDGET}\"")
                    if any(k in w_id for k in ['battery', 'bateria', 'level']):
                        output.append("  precision: 0")
                    else:
                        output.append("  precision: 1")

                # --- MEDIA PLAYER ---
                elif w_type == 'media_player':
                    output.append(f"  widget_type: media_player")
                    output.append(f"  entity: {w_id}")
                    output.append(f"  title: \"{w_name}\"")
                    if w_icon:
                        output.append(f"  icon: {w_icon}")
                    output.append(f"  title_style: \"{STYLE_TITLE}\"")
                    output.append(f"  widget_style: \"{STYLE_WIDGET}\"")
                    output.append(f"  icon_style: \"{STYLE_ICON}\"")
                    output.append("  truncate_name: 20")
                    output.append("  step: 5")

                # --- CLIMATE (TERMOSTAT) ---
                elif w_type == 'climate':
                    output.append(f"  widget_type: climate")
                    output.append(f"  entity: {w_id}")
                    output.append(f"  title: \"{w_name}\"")
                    output.append(f"  step: 1")
                    output.append(f"  precision: 1")
                    output.append(f"  title_style: \"{STYLE_TITLE}\"")
                    output.append(f"  widget_style: \"{STYLE_WIDGET}\"")
                    output.append(f"  icon_style: \"{STYLE_ICON}\"")

                # --- FAN (WENTYLATOR) ---
                elif w_type == 'fan':
                    output.append(f"  widget_type: fan")
                    output.append(f"  entity: {w_id}")
                    output.append(f"  title: \"{w_name}\"")
                    if i_on: output.append(f"  icon_on: {i_on}")
                    if i_off: output.append(f"  icon_off: {i_off}")
                    if w_icon and not i_on: output.append(f"  icon: {w_icon}")
                    
                    output.append("  low_speed: 33")
                    output.append("  medium_speed: 66")
                    output.append("  high_speed: 100")

                    output.append(f"  title_style: \"{STYLE_TITLE}\"")
                    output.append(f"  widget_style: \"{STYLE_WIDGET}\"")
                    output.append(f"  icon_style_active: \"{STYLE_ICON}\"")
                    output.append(f"  icon_style_inactive: \"{STYLE_ICON}; opacity: 0.5;\"")
                    
                    output.append(f"  speed1_icon_style_active: \"{STYLE_ICON}\"")
                    output.append(f"  speed1_icon_style_inactive: \"{STYLE_ICON}; opacity: 0.3;\"")
                    output.append(f"  speed2_icon_style_active: \"{STYLE_ICON}\"")
                    output.append(f"  speed2_icon_style_inactive: \"{STYLE_ICON}; opacity: 0.3;\"")
                    output.append(f"  speed3_icon_style_active: \"{STYLE_ICON}\"")
                    output.append(f"  speed3_icon_style_inactive: \"{STYLE_ICON}; opacity: 0.3;\"")

                # --- SCENE (SCENA) ---
                elif w_type == 'scene':
                    output.append(f"  widget_type: scene")
                    output.append(f"  entity: {w_id}")
                    output.append(f"  title: \"{w_name}\"")
                    if w_icon: output.append(f"  icon: {w_icon}")
                    elif i_on: output.append(f"  icon: {i_on}")
                    
                    output.append(f"  title_style: \"{STYLE_TITLE}\"")
                    output.append(f"  widget_style: \"{STYLE_WIDGET}\"")
                    output.append(f"  icon_style_active: \"{STYLE_ICON}\"")
                    output.append(f"  icon_style_inactive: \"{STYLE_ICON}\"")

                # --- CLOCK ---
                elif w_type == 'clock':
                    output.append(f"  widget_type: clock")
                    output.append(f"  time_format: 24hr")
                    output.append(f"  show_seconds: 0")
                    output.append(f"  date_style: \"{STYLE_TEXT}\"")
                    output.append(f"  time_style: \"{STYLE_VALUE}\"")

                # --- LABEL ---
                elif w_type == 'label':
                    output.append(f"  widget_type: label")
                    output.append(f"  text: \"{w_name}\"")
                    if w_icon: 
                        output.append(f"  icon: {w_icon}")
                    output.append(f"  text_style: \"{STYLE_TITLE}\"")
                
                # --- GENERIC (Switch, Cover, Script, Light, Lock, Input Button etc.) ---
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
                    if w_type == 'input_button': ad_type = 'script'
                    
                    output.append(f"  widget_type: {ad_type}")
                    output.append(f"  entity: {w_id}")
                    output.append(f"  title: \"{w_name}\"")
                    
                    if i_on: output.append(f"  icon_on: {i_on}")
                    if i_off: output.append(f"  icon_off: {i_off}")
                    
                    if ad_type == 'lock':
                        if i_off: output.append(f"  icon_locked: {i_off}")
                        if i_on: output.append(f"  icon_unlocked: {i_on}")
                    
                    if w_icon and not i_on: 
                        output.append(f"  icon: {w_icon}")
                    
                    output.append(f"  state_text: 1")
                    output.append(f"  title_style: \"{STYLE_TITLE}\"")
                    output.append(f"  text_style: \"{STYLE_TEXT}\"")
                    output.append(f"  widget_style: \"{STYLE_WIDGET}\"")
                    output.append(f"  icon_style_active: \"{STYLE_ICON}\"")
                    output.append(f"  icon_style_inactive: \"{STYLE_ICON}\"")
                    
                    if ad_type in ['cover', 'binary_sensor', 'switch', 'light', 'lock']: 
                        output.append("  state_map:")
                        if ad_type == 'cover':
                            for s in ['open', 'closed', 'opening', 'closing']: 
                                output.append(f"    \"{s}\": \"{dic.get(s, s)}\"")
                        elif ad_type == 'binary_sensor':
                            output.append(f"    \"on\": \"{dic['open']}\"")
                            output.append(f"    \"off\": \"{dic['closed']}\"")
                        elif ad_type == 'lock':
                            output.append(f"    \"locked\": \"{dic['locked']}\"")
                            output.append(f"    \"unlocked\": \"{dic['unlocked']}\"")
                        else:
                            output.append(f"    \"on\": \"{dic['on']}\"")
                            output.append(f"    \"off\": \"{dic['off']}\"")

                output.append("")
    except Exception as e: 
        print(f"❌ Error generating YAML: {e}")
        return f"# ERROR GENERATING YAML: {e}"

    return "\n".join(output)

@app.route('/', methods=['GET', 'POST'])
def index():
    generated_yaml = ""
    ha_entities = get_ha_entities()
    dashboard_filename = "joandashboard.dash"
    dashboard_slug = "joandashboard"
    has_token = bool(TOKEN)
    save_message = None

    if request.method == 'POST':
        action = request.form.get('action', 'generate')

        if action == 'restart':
            success, msg = restart_appdaemon_addon()
            if success:
                save_message = f"✅ Sukces: {msg}"
            else:
                save_message = f"❌ Błąd: {msg}"
        
        else:
            try:
                title = request.form.get('title', 'JoanDashboard')
                dashboard_slug = title.lower().replace(" ", "_")
                dashboard_filename = dashboard_slug + ".dash"
                
                cols = int(request.form.get('grid_columns', '4'))
                rows_grid = int(request.form.get('grid_rows', '8'))
                lang = request.form.get('ui_language', 'pl')
                
                default_size_str = request.form.get('default_widget_size', '2, 1')
                def_size_parts = default_size_str.split(',')
                def_w = int(def_size_parts[0].strip())
                def_h = int(def_size_parts[1].strip()) if len(def_size_parts) > 1 else 1

                # PRZYGOTOWANIE DANYCH
                layout_data = json.loads(request.form.get('layout_data_json', '[]'))
                custom_defs = json.loads(request.form.get('custom_definitions_json', '{}'))
                
                grid_params = {
                    'cols': cols,
                    'rows_grid': rows_grid,
                    'def_w': def_w,
                    'def_h': def_h
                }
                
                # WYWOŁANIE FUNKCJI
                generated_yaml = generate_joan_dash_yaml(
                    layout_data, 
                    title,
                    grid_params,
                    lang,
                    custom_defs
                )
            except Exception as e: 
                print(f"❌ Error generating YAML: {e}")
                generated_yaml = f"# ERROR GENERATING YAML: {e}"

    return render_template('index.html', generated_yaml=generated_yaml, entities=ha_entities, filename=dashboard_filename, dash_name=dashboard_slug, has_token=has_token, save_message=save_message)

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000, debug=True)
