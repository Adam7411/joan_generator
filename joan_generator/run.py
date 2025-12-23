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
    if not os.environ.get('SUPERVISOR_TOKEN'):
        return False, "Brak tokena Supervisor (wymagane środowisko Add-on)"
    
    headers = {
        "Authorization": f"Bearer {os.environ.get('SUPERVISOR_TOKEN')}",
        "Content-Type": "application/json"
    }
    # Endpoint Supervisora do restartu (wewnętrzny docker network)
    url = f"{SUPERVISOR_URL}/addons/{APPDAEMON_SLUG}/restart"
    
    try:
        print(f"🔄 Restartowanie: {APPDAEMON_SLUG}...")
        response = requests.post(url, headers=headers, timeout=30)
        
        if response.status_code in [200, 201, 202, 204]:
            print("✅ Restart zainicjowany pomyślnie.")
            return True, "Zainicjowano restart AppDaemon."
        else:
            print(f"❌ Błąd restartu: {response.status_code} - {response.text}")
            return False, f"Błąd restartu: {response.status_code}"
    except Exception as e:
        print(f"❌ Wyjątek restartu: {e}")
        return False, str(e)

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

@app.route('/', methods=['GET', 'POST'])
def index():
    generated_yaml = ""
    ha_entities = get_ha_entities()
    dashboard_filename = "joandashboard.dash"
    dashboard_slug = "joandashboard"
    has_token = bool(TOKEN)
    save_message = None # <--- DODAJ ZMIENNĄ DLA KOMUNIKATU

    if request.method == 'POST':
        # Sprawdzamy czy to restart czy generowanie
        action = request.form.get('action', 'generate') # <--- ODCZYT AKCJI

        if action == 'restart':
            success, msg = restart_appdaemon_addon()
            if success:
                save_message = f"✅ Sukces: {msg}"
            else:
                save_message = f"❌ Błąd: {msg}"
        
        else:
            # ... TUTAJ ZACZYNA SIĘ STARY KOD (try: title = request.form...)
            # ... NIC TU NIE ZMIENIAJ AŻ DO DOŁU BLOKU try/except
            try:
                title = request.form.get('title', 'JoanDashboard')
                dashboard_slug = title.lower().replace(" ", "_")
                dashboard_filename = dashboard_slug + ".dash"
                
                cols = request.form.get('grid_columns', '4')
                rows_grid = request.form.get('grid_rows', '8')
                lang = request.form.get('ui_language', 'pl')
                
                default_size_str = request.form.get('default_widget_size', '2, 1')
                def_size_parts = default_size_str.split(',')
                def_w = int(def_size_parts[0].strip())
                def_h = int(def_size_parts[1].strip()) if len(def_size_parts) > 1 else 1

                # -------------------------------------------------
                # TŁUMACZENIA STANÓW (BILINGUAL SUPPORT)
                # -------------------------------------------------
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
                # Wybierz słownik na podstawie języka z formularza
                dic = TRANS.get(lang, TRANS['pl'])

                # AppDaemon liczy kolumny jednostkowe (np. 117px).
                if def_w == 1:
                    ad_columns = int(cols)
                else: 
                    ad_columns = int(cols) * 2

                # -------------------------------------------------
                # NAGŁÓWEK PLIKU YAML
                # -------------------------------------------------
                generated_yaml += f"title: {title}\n"
                generated_yaml += "widget_dimensions: [117, 117]\n"
                generated_yaml += f"widget_size: [{def_w}, {def_h}]\n"
                generated_yaml += "widget_margins: [8, 8]\n"
                generated_yaml += f"columns: {ad_columns}\n"
                generated_yaml += f"rows: {rows_grid}\n"
                generated_yaml += "global_parameters:\n"
                generated_yaml += "  use_comma: 0\n"
                generated_yaml += "  precision: 1\n"
                generated_yaml += "  use_hass_icon: 1\n"
                generated_yaml += "  namespace: default\n"
                generated_yaml += "  devices:\n"
                generated_yaml += "    media_player:\n"
                generated_yaml += "      step: 5\n" # Globalny krok głośności
                generated_yaml += "    climate:\n"
                generated_yaml += "      step: 1\n" # Globalny krok temperatury
                generated_yaml += f"  white_text_style: \"{STYLE_TEXT}\"\n"
                generated_yaml += f"  state_text_style: \"{STYLE_STATE_TEXT}\"\n"
                generated_yaml += "skin: simplyred\n\n"
                
                layout_data_str = request.form.get('layout_data_json')
                custom_defs_str = request.form.get('custom_definitions_json', '{}')
                custom_defs = json.loads(custom_defs_str)
                
                processed_widgets = []
                
                # -------------------------------------------------
                # GENEROWANIE SEKCJI LAYOUT
                # -------------------------------------------------
                if layout_data_str:
                    layout_rows = json.loads(layout_data_str)
                    generated_yaml += "layout:\n"
                    for row in layout_rows:
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
                            if size_str == f"({def_w}x{def_h})":
                                is_default = True
                            elif size_str == "(2x1)" and def_w == 2 and def_h == 1:
                                is_default = True
                            elif size_str == "(1x1)" and def_w == 1 and def_h == 1:
                                is_default = True
                                
                            if not is_default and size_str:
                                if not size_str.startswith('('):
                                    size_str = f"({size_str})"
                                widget_id += size_str
                                 
                            row_parts.append(widget_id)
                            processed_widgets.append(w)
                        generated_yaml += f"  - {', '.join(row_parts)}\n"
                    
                    generated_yaml += "\n# -------------------\n# DEFINICJE WIDŻETÓW\n# -------------------\n\n"
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
                            generated_yaml += f"{w_id}:\n"
                            for line in custom_defs[w_id].split('\n'):
                                if line.strip():
                                    generated_yaml += f"  {line}\n"
                            generated_yaml += "\n"
                            continue

                        w_type = w['type']
                        w_name = w['name']
                        w_icon = normalize_icon_format(w['icon'])
                        i_on = normalize_icon_format(w.get('icon_on'))
                        i_off = normalize_icon_format(w.get('icon_off'))
                        
                        generated_yaml += f"{w_id}:\n"
                        
                        # --- NAVIGATE ---
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

                        # --- SENSOR ---
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

                        # --- MEDIA PLAYER ---
                        elif w_type == 'media_player':
                            generated_yaml += f"  widget_type: media_player\n"
                            generated_yaml += f"  entity: {w_id}\n"
                            generated_yaml += f"  title: \"{w_name}\"\n"
                            if w_icon:
                                generated_yaml += f"  icon: {w_icon}\n"
                            generated_yaml += f"  title_style: \"{STYLE_TITLE}\"\n"
                            generated_yaml += f"  widget_style: \"{STYLE_WIDGET}\"\n"
                            generated_yaml += f"  icon_style: \"{STYLE_ICON}\"\n"
                            generated_yaml += "  truncate_name: 20\n"
                            generated_yaml += "  step: 5\n" # Krok głośności 5%

                        # --- CLIMATE (TERMOSTAT) ---
                        elif w_type == 'climate':
                            generated_yaml += f"  widget_type: climate\n"
                            generated_yaml += f"  entity: {w_id}\n"
                            generated_yaml += f"  title: \"{w_name}\"\n"
                            generated_yaml += f"  step: 1\n" # Ważne dla E-Ink: Krok zmiany temperatury
                            generated_yaml += f"  precision: 1\n"
                            generated_yaml += f"  title_style: \"{STYLE_TITLE}\"\n"
                            generated_yaml += f"  widget_style: \"{STYLE_WIDGET}\"\n"
                            generated_yaml += f"  icon_style: \"{STYLE_ICON}\"\n"

                        # --- FAN (WENTYLATOR) ---
                        elif w_type == 'fan':
                            generated_yaml += f"  widget_type: fan\n"
                            generated_yaml += f"  entity: {w_id}\n"
                            generated_yaml += f"  title: \"{w_name}\"\n"
                            if i_on: generated_yaml += f"  icon_on: {i_on}\n"
                            if i_off: generated_yaml += f"  icon_off: {i_off}\n"
                            if w_icon and not i_on: generated_yaml += f"  icon: {w_icon}\n"
                            
                            # NAPRAWA PRĘDKOŚCI (Mapowanie low/med/high na procenty dla nowego HA)
                            generated_yaml += "  low_speed: 33\n"
                            generated_yaml += "  medium_speed: 66\n"
                            generated_yaml += "  high_speed: 100\n"

                            generated_yaml += f"  title_style: \"{STYLE_TITLE}\"\n"
                            generated_yaml += f"  widget_style: \"{STYLE_WIDGET}\"\n"
                            generated_yaml += f"  icon_style_active: \"{STYLE_ICON}\"\n"
                            generated_yaml += f"  icon_style_inactive: \"{STYLE_ICON}; opacity: 0.5;\"\n"
                            
                            # Style dla ikonek prędkości (kontrast e-ink)
                            generated_yaml += f"  speed1_icon_style_active: \"{STYLE_ICON}\"\n"
                            generated_yaml += f"  speed1_icon_style_inactive: \"{STYLE_ICON}; opacity: 0.3;\"\n"
                            generated_yaml += f"  speed2_icon_style_active: \"{STYLE_ICON}\"\n"
                            generated_yaml += f"  speed2_icon_style_inactive: \"{STYLE_ICON}; opacity: 0.3;\"\n"
                            generated_yaml += f"  speed3_icon_style_active: \"{STYLE_ICON}\"\n"
                            generated_yaml += f"  speed3_icon_style_inactive: \"{STYLE_ICON}; opacity: 0.3;\"\n"

                        # --- SCENE (SCENA) ---
                        elif w_type == 'scene':
                            generated_yaml += f"  widget_type: scene\n"
                            generated_yaml += f"  entity: {w_id}\n"
                            generated_yaml += f"  title: \"{w_name}\"\n"
                            # Scena jest bezstanowa, używamy tylko jednej ikony
                            if w_icon: generated_yaml += f"  icon: {w_icon}\n"
                            elif i_on: generated_yaml += f"  icon: {i_on}\n" 
                            
                            generated_yaml += f"  title_style: \"{STYLE_TITLE}\"\n"
                            generated_yaml += f"  widget_style: \"{STYLE_WIDGET}\"\n"
                            generated_yaml += f"  icon_style_active: \"{STYLE_ICON}\"\n"
                            generated_yaml += f"  icon_style_inactive: \"{STYLE_ICON}\"\n"

                        # --- CLOCK ---
                        elif w_type == 'clock':
                            generated_yaml += f"  widget_type: clock\n"
                            generated_yaml += f"  time_format: 24hr\n"
                            generated_yaml += f"  show_seconds: 0\n"
                            generated_yaml += f"  date_style: \"{STYLE_TEXT}\"\n"
                            generated_yaml += f"  time_style: \"{STYLE_VALUE}\"\n"

                        # --- LABEL ---
                        elif w_type == 'label':
                            generated_yaml += f"  widget_type: label\n"
                            generated_yaml += f"  text: \"{w_name}\"\n"
                            if w_icon: 
                                generated_yaml += f"  icon: {w_icon}\n"
                            generated_yaml += f"  text_style: \"{STYLE_TITLE}\"\n"
                        
                        # --- GENERIC (Switch, Cover, Script, Light, Lock, Input Button etc.) ---
                        else:
                            ad_type = w_type
                            # Mapowanie typów generatora na typy AppDaemon
                            if w_type == 'binary_sensor': ad_type = 'binary_sensor'
                            if w_type == 'input_boolean': ad_type = 'switch'
                            if w_type == 'person': ad_type = 'device_tracker'
                            if w_type == 'light': ad_type = 'switch'
                            if w_type == 'lock': ad_type = 'lock'
                            if w_type == 'input_select': ad_type = 'input_select'
                            if w_type == 'input_number': ad_type = 'input_number'
                            if w_type == 'script': ad_type = 'script'
                            if w_type == 'input_button': ad_type = 'script' # Traktujemy input_button jak skrypt
                            
                            generated_yaml += f"  widget_type: {ad_type}\n"
                            generated_yaml += f"  entity: {w_id}\n"
                            generated_yaml += f"  title: \"{w_name}\"\n"
                            
                            if i_on: generated_yaml += f"  icon_on: {i_on}\n"
                            if i_off: generated_yaml += f"  icon_off: {i_off}\n"
                            
                            if ad_type == 'lock':
                                if i_off: generated_yaml += f"  icon_locked: {i_off}\n"
                                if i_on: generated_yaml += f"  icon_unlocked: {i_on}\n"
                            
                            if w_icon and not i_on: 
                                generated_yaml += f"  icon: {w_icon}\n"
                            
                            generated_yaml += f"  state_text: 1\n"
                            generated_yaml += f"  title_style: \"{STYLE_TITLE}\"\n"
                            generated_yaml += f"  text_style: \"{STYLE_TEXT}\"\n"
                            generated_yaml += f"  widget_style: \"{STYLE_WIDGET}\"\n"
                            generated_yaml += f"  icon_style_active: \"{STYLE_ICON}\"\n"
                            generated_yaml += f"  icon_style_inactive: \"{STYLE_ICON}\"\n"
                            
                            # Tłumaczenie stanów (State Map) zależnie od języka
                            if ad_type in ['cover', 'binary_sensor', 'switch', 'light', 'lock']: 
                                generated_yaml += "  state_map:\n"
                                if ad_type == 'cover':
                                    for s in ['open', 'closed', 'opening', 'closing']: 
                                        generated_yaml += f"    \"{s}\": \"{dic.get(s, s)}\"\n"
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

    return render_template('index.html', generated_yaml=generated_yaml, entities=ha_entities, filename=dashboard_filename, dash_name=dashboard_slug, has_token=has_token, save_message=save_message)

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000, debug=True)
