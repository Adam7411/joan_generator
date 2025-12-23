import os
import json
import requests
from flask import Flask, render_template, request

# Inicjalizacja aplikacji
print("📦 1. Inicjalizacja aplikacji Joan 6 Generator...")
app = Flask(__name__)
app.secret_key = 'joan_generator_secret_key'

# -------------------------------------------------------------------------
# 1. KONFIGURACJA API I TOKENU
# -------------------------------------------------------------------------
TOKEN = os.environ.get('SUPERVISOR_TOKEN')
API_URL = "http://supervisor/core/api"
SUPERVISOR_URL = "http://supervisor"
TOKEN_SOURCE = "System (Supervisor)"

# Domyślne wartości (zostaną nadpisane przez auto-detekcję)
APPDAEMON_ADDON_SLUG = "a0d7b954_appdaemon" 
OUTPUT_DIR = "/config/appdaemon/dashboards"

# Funkcja debugująca strukturę plików (Pomoże zrozumieć, dlaczego nie widzi katalogu)
def debug_directories():
    print("🔍 --- DEBUGOWANIE STRUKTURY KATALOGÓW ---")
    paths_to_check = ["/", "/config", "/addon_configs", "/data"]
    for p in paths_to_check:
        if os.path.exists(p):
            print(f"✅ Katalog istnieje: {p}")
            try:
                # Wypisz tylko katalogi, żeby nie śmiecić
                contents = [d for d in os.listdir(p) if os.path.isdir(os.path.join(p, d))]
                print(f"   Zawartość {p}: {contents[:10]}...") 
            except Exception as e:
                print(f"   Brak uprawnień do odczytu {p}: {e}")
        else:
            print(f"❌ Katalog NIE istnieje (brak montowania): {p}")
    print("--------------------------------------------")

# Odczyt opcji z pliku konfiguracyjnego Add-onu
try:
    options_path = '/data/options.json'
    if os.path.exists(options_path):
        with open(options_path, 'r') as f:
            options = json.load(f)
            
            # 1. Token manualny
            manual_token = options.get('manual_token')
            if manual_token and len(manual_token) > 10:
                TOKEN = manual_token
                API_URL = "http://homeassistant:8123/api"
                TOKEN_SOURCE = "Manual (Konfiguracja)"
                print(f"🔧 Wykryto manualny token. Przełączam API na: {API_URL}")
            
            # 2. Opcjonalne wymuszenie ścieżki przez użytkownika
            if options.get('output_path'):
                OUTPUT_DIR = options.get('output_path')
                print(f"🔧 Wymuszono ścieżkę zapisu z konfiguracji: {OUTPUT_DIR}")
            
            # 3. Opcjonalne wymuszenie sluga przez użytkownika
            if options.get('appdaemon_slug'):
                APPDAEMON_ADDON_SLUG = options.get('appdaemon_slug')
                print(f"🔧 Wymuszono slug AppDaemon z konfiguracji: {APPDAEMON_ADDON_SLUG}")

except Exception as e: 
    print(f"ℹ️ Info: Nie udało się odczytać pliku opcji: {e}")

if not TOKEN:
    print("❌ OSTRZEŻENIE: Brak tokena autoryzacji! Lista encji będzie pusta.")

# -------------------------------------------------------------------------
# 2. AUTOMATYCZNA DETEKCJA ŚRODOWISKA (AppDaemon)
# -------------------------------------------------------------------------
def detect_appdaemon_slug():
    """Próbuje znaleźć właściwy slug AppDaemona odpytując Supervisora"""
    if not os.environ.get('SUPERVISOR_TOKEN'):
        return APPDAEMON_ADDON_SLUG 

    headers = {"Authorization": f"Bearer {os.environ.get('SUPERVISOR_TOKEN')}"}
    try:
        resp = requests.get(f"{SUPERVISOR_URL}/addons", headers=headers, timeout=5)
        if resp.status_code == 200:
            addons = resp.json().get('data', {}).get('addons', [])
            for addon in addons:
                if 'appdaemon' in addon.get('slug', '') and addon.get('installed', False):
                    found_slug = addon.get('slug')
                    print(f"✅ Wykryto zainstalowany AppDaemon: {found_slug}")
                    return found_slug
    except Exception as e:
        print(f"⚠️ Błąd podczas detekcji AppDaemona: {e}")
    
    return APPDAEMON_ADDON_SLUG 

def detect_dashboard_path(detected_slug):
    """
    Próbuje ustalić, gdzie zapisać plik .dash.
    """
    
    # Lista potencjalnych ścieżek w kolejności priorytetu
    candidates = [
        # 1. Nowa struktura (jeśli jest zamontowana)
        f"/addon_configs/{detected_slug}/dashboards",
        f"/addon_configs/{detected_slug}/conf/dashboards",
        # 2. Klasyczna struktura w /config (najbardziej prawdopodobna dla Add-onów)
        "/config/appdaemon/dashboards",
        "/config/appdaemon/conf/dashboards"
    ]

    # Jeśli użytkownik wymusił ścieżkę w options, dodaj ją na początek
    if options.get('output_path'):
        candidates.insert(0, options.get('output_path'))

    for path in candidates:
        # Sprawdzamy czy katalog istnieje
        if os.path.exists(path):
            print(f"✅ Znaleziono istniejący katalog dashboardów: {path}")
            return path
        
        # Jeśli nie istnieje, sprawdzamy czy możemy go utworzyć (czy katalog nadrzędny istnieje)
        parent = os.path.dirname(path)
        if os.path.exists(parent):
            try:
                os.makedirs(path, exist_ok=True)
                print(f"✅ Utworzono katalog dashboardów: {path}")
                return path
            except:
                pass # Brak uprawnień, idziemy dalej
    
    print(f"⚠️ Nie znaleziono idealnego katalogu. Używam domyślnego: /config/appdaemon/dashboards")
    return "/config/appdaemon/dashboards"

# Uruchom detekcję przy starcie
debug_directories() # <--- NOWOŚĆ: Pokaż co widzi kontener
if not options.get('appdaemon_slug'):
    APPDAEMON_ADDON_SLUG = detect_appdaemon_slug()

# Zawsze próbuj wykryć ścieżkę na nowo, chyba że zablokowana w options
if not options.get('output_path'):
    OUTPUT_DIR = detect_dashboard_path(APPDAEMON_ADDON_SLUG)
else:
    OUTPUT_DIR = options.get('output_path')

print(f"📂 Docelowy katalog zapisu: {OUTPUT_DIR}")

# -------------------------------------------------------------------------
# 3. POBIERANIE DANYCH Z HA I RESTART
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

def restart_appdaemon():
    """Wysyła żądanie do HA, aby zrestartować wykryty dodatek AppDaemon"""
    if not TOKEN:
        return False, "Brak tokena API."
    
    if "supervisor" in API_URL:
        url = f"{SUPERVISOR_URL}/addons/{APPDAEMON_ADDON_SLUG}/restart"
        method = "POST"
    else:
        url = f"{API_URL}/services/hassio/addon_restart"
        method = "POST_SERVICE"

    headers = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
    
    try:
        print(f"🔄 Próba restartu dodatku: {APPDAEMON_ADDON_SLUG}...")
        
        if method == "POST_SERVICE":
            payload = {"addon": APPDAEMON_ADDON_SLUG}
            response = requests.post(url, json=payload, headers=headers, timeout=20)
        else:
            response = requests.post(url, headers=headers, timeout=20)
            
        if response.status_code in [200, 201]:
            print("✅ Wysłano polecenie restartu.")
            return True, f"Zapisano do {OUTPUT_DIR} i zrestartowano {APPDAEMON_ADDON_SLUG}."
        else:
            print(f"❌ Błąd restartu: {response.text}")
            return False, f"Błąd restartu (Code {response.status_code}): {response.text}"
    except Exception as e:
        print(f"❌ Wyjątek restartu: {e}")
        return False, f"Wyjątek podczas restartu: {str(e)}"

# -------------------------------------------------------------------------
# 4. STYLE I FORMATOWANIE
# -------------------------------------------------------------------------
STYLE_TITLE = "color: #000000; font-size: 20px; font-weight: 700; text-align: center; padding-top: 5px; width: 100%; font-family: 'Roboto', 'Arial Black', sans-serif;"
STYLE_WIDGET = "color: #000000 !important; background-color: #FFFFFF !important;"
STYLE_TEXT = "color: #000000 !important; font-weight: 700 !important;"
STYLE_VALUE = "color: #000000 !important; font-size: 54px !important; font-weight: 700 !important; padding-top: 60px !important; line-height: 1.1 !important; display: inline-block !important;"
STYLE_UNIT = "color: #000000 !important; padding-top: 60px !important; display: inline-block !important;"
STYLE_ICON = "color: #000000 !important;"
STYLE_STATE_TEXT = "color: #000000 !important; font-weight: 700 !important; font-size: 16px !important;"

def normalize_icon_format(icon_name):
    if not icon_name: return icon_name
    icon_name = icon_name.strip()
    if icon_name.startswith('mdi:'): return 'mdi-' + icon_name[4:]
    if icon_name.startswith('mdi-'): return icon_name
    return icon_name

@app.route('/', methods=['GET', 'POST'])
def index():
    generated_yaml = ""
    ha_entities = get_ha_entities()
    dashboard_filename = "joandashboard.dash"
    dashboard_slug = "joandashboard"
    has_token = bool(TOKEN)
    save_message = None
    
    if request.method == 'POST':
        try:
            title = request.form.get('title', 'JoanDashboard')
            action_type = request.form.get('action_type', 'generate')
            
            dashboard_slug = title.lower().replace(" ", "_")
            dashboard_filename = dashboard_slug + ".dash"
            
            cols = request.form.get('grid_columns', '4')
            rows = request.form.get('grid_rows', '8')
            lang = request.form.get('ui_language', 'pl')
            
            default_size_str = request.form.get('default_widget_size', '2, 1')
            def_size_parts = default_size_str.split(',')
            def_w = int(def_size_parts[0].strip())
            def_h = int(def_size_parts[1].strip()) if len(def_size_parts) > 1 else 1

            TRANS = {
                'pl': {'on': 'WŁĄCZONE', 'off': 'WYŁĄCZONE', 'open': 'OTWARTE', 'closed': 'ZAMKNIĘTE', 'opening': 'OTWIERANIE', 'closing': 'ZAMYKANIE', 'locked': 'ZAMKNIĘTE', 'unlocked': 'OTWARTE', 'home': 'W DOMU', 'not_home': 'POZA'},
                'en': {'on': 'ON', 'off': 'OFF', 'open': 'OPEN', 'closed': 'CLOSED', 'opening': 'OPENING', 'closing': 'CLOSING', 'locked': 'LOCKED', 'unlocked': 'UNLOCKED', 'home': 'HOME', 'not_home': 'AWAY'}
            }
            dic = TRANS.get(lang, TRANS['pl'])

            if def_w == 1: ad_columns = int(cols)
            else: ad_columns = int(cols) * 2

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
            generated_yaml += "    climate:\n"
            generated_yaml += "      step: 1\n"
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
                        size_str = w.get('size', '')
                        is_default = False
                        if size_str == f"({def_w}x{def_h})": is_default = True
                        elif size_str == "(2x1)" and def_w == 2 and def_h == 1: is_default = True
                        elif size_str == "(1x1)" and def_w == 1 and def_h == 1: is_default = True
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
                    w_icon = normalize_icon_format(w['icon'])
                    i_on = normalize_icon_format(w.get('icon_on'))
                    i_off = normalize_icon_format(w.get('icon_off'))
                    
                    generated_yaml += f"{w_id}:\n"
                    
                    if w_type == 'navigate':
                        dash_target = w_id.replace('navigate.', '')
                        nav_icon = w_icon or 'mdi-arrow-right-circle'
                        generated_yaml += f"  widget_type: navigate\n"
                        generated_yaml += f"  title: \"{w_name}\"\n"
                        generated_yaml += f"  dashboard: {dash_target}\n"
                        generated_yaml += f"  icon_active: {nav_icon}\n"
                        generated_yaml += f"  icon_inactive: {nav_icon}\n"
                        generated_yaml += f"  title_style: \"{STYLE_TITLE}\"\n"
                        generated_yaml += f"  widget_style: \"{STYLE_WIDGET}\"\n"
                        generated_yaml += f"  icon_active_style: \"{STYLE_ICON}\"\n"
                        generated_yaml += f"  icon_inactive_style: \"{STYLE_ICON}\"\n"
                    elif w_type == 'sensor':
                        generated_yaml += f"  widget_type: sensor\n"
                        generated_yaml += f"  entity: {w_id}\n"
                        generated_yaml += f"  title: \"{w_name}\"\n"
                        generated_yaml += f"  title_style: \"{STYLE_TITLE}\"\n"
                        generated_yaml += f"  text_style: \"{STYLE_TEXT}\"\n"
                        generated_yaml += f"  value_style: \"{STYLE_VALUE}\"\n"
                        generated_yaml += f"  unit_style: \"{STYLE_UNIT}\"\n"
                        generated_yaml += f"  widget_style: \"{STYLE_WIDGET}\"\n"
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
                    elif w_type == 'climate':
                        generated_yaml += f"  widget_type: climate\n"
                        generated_yaml += f"  entity: {w_id}\n"
                        generated_yaml += f"  title: \"{w_name}\"\n"
                        generated_yaml += f"  step: 1\n"
                        generated_yaml += f"  precision: 1\n"
                        generated_yaml += f"  title_style: \"{STYLE_TITLE}\"\n"
                        generated_yaml += f"  widget_style: \"{STYLE_WIDGET}\"\n"
                        generated_yaml += f"  icon_style: \"{STYLE_ICON}\"\n"
                    elif w_type == 'fan':
                        generated_yaml += f"  widget_type: fan\n"
                        generated_yaml += f"  entity: {w_id}\n"
                        generated_yaml += f"  title: \"{w_name}\"\n"
                        if i_on: generated_yaml += f"  icon_on: {i_on}\n"
                        if i_off: generated_yaml += f"  icon_off: {i_off}\n"
                        if w_icon and not i_on: generated_yaml += f"  icon: {w_icon}\n"
                        generated_yaml += "  low_speed: 33\n"
                        generated_yaml += "  medium_speed: 66\n"
                        generated_yaml += "  high_speed: 100\n"
                        generated_yaml += f"  title_style: \"{STYLE_TITLE}\"\n"
                        generated_yaml += f"  widget_style: \"{STYLE_WIDGET}\"\n"
                        generated_yaml += f"  icon_style_active: \"{STYLE_ICON}\"\n"
                        generated_yaml += f"  icon_style_inactive: \"{STYLE_ICON}; opacity: 0.5;\"\n"
                        generated_yaml += f"  speed1_icon_style_active: \"{STYLE_ICON}\"\n"
                        generated_yaml += f"  speed1_icon_style_inactive: \"{STYLE_ICON}; opacity: 0.3;\"\n"
                        generated_yaml += f"  speed2_icon_style_active: \"{STYLE_ICON}\"\n"
                        generated_yaml += f"  speed2_icon_style_inactive: \"{STYLE_ICON}; opacity: 0.3;\"\n"
                        generated_yaml += f"  speed3_icon_style_active: \"{STYLE_ICON}\"\n"
                        generated_yaml += f"  speed3_icon_style_inactive: \"{STYLE_ICON}; opacity: 0.3;\"\n"
                    elif w_type == 'scene':
                        generated_yaml += f"  widget_type: scene\n"
                        generated_yaml += f"  entity: {w_id}\n"
                        generated_yaml += f"  title: \"{w_name}\"\n"
                        if w_icon: generated_yaml += f"  icon: {w_icon}\n"
                        elif i_on: generated_yaml += f"  icon: {i_on}\n" 
                        generated_yaml += f"  title_style: \"{STYLE_TITLE}\"\n"
                        generated_yaml += f"  widget_style: \"{STYLE_WIDGET}\"\n"
                        generated_yaml += f"  icon_style_active: \"{STYLE_ICON}\"\n"
                        generated_yaml += f"  icon_style_inactive: \"{STYLE_ICON}\"\n"
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
                        if w_type == 'input_button': ad_type = 'script'
                        
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
                                for s in ['open', 'closed', 'opening', 'closing']: generated_yaml += f"    \"{s}\": \"{dic.get(s, s)}\"\n"
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
            
            # --- ZAPIS I RESTART ---
            if action_type == 'save_restart':
                try:
                    # Próba utworzenia katalogu jeśli nie istnieje
                    if not os.path.exists(OUTPUT_DIR):
                        try:
                            os.makedirs(OUTPUT_DIR, exist_ok=True)
                        except OSError as e:
                            print(f"❌ Nie można utworzyć katalogu {OUTPUT_DIR}: {e}")
                    
                    full_path = os.path.join(OUTPUT_DIR, dashboard_filename)
                    
                    with open(full_path, "w", encoding="utf-8") as f:
                        f.write(generated_yaml)
                    
                    success, msg = restart_appdaemon()
                    if success:
                        save_message = f"✅ Sukces: Zapisano do {full_path} i zrestartowano AppDaemon ({APPDAEMON_ADDON_SLUG})."
                    else:
                        save_message = f"⚠️ Zapisano plik, ale restart się nie udał: {msg}"
                        
                except Exception as e:
                    save_message = f"❌ Błąd zapisu pliku: {e}"

        except Exception as e: 
            print(f"❌ Error generating YAML: {e}")
            generated_yaml = f"# ERROR GENERATING YAML: {e}"

    return render_template('index.html', generated_yaml=generated_yaml, entities=ha_entities, filename=dashboard_filename, dash_name=dashboard_slug, has_token=has_token, save_message=save_message)

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000, debug=True)
