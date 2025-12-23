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
# NOWE FUNKCJE: INTEGRACJA Z VISIONECT JOAN
# -------------------------------------------------------------------------
def get_joan_devices():
    """Filtruje encje, aby znaleźć urządzenia Joan (szukamy kamer Visionect)."""
    all_entities = get_ha_entities()
    joan_devices = []
    for ent in all_entities:
        # Szukamy kamer z integracji visionect (zazwyczaj mają unikalne ID lub nazwę)
        # Zakładamy, że encja to np. camera.joan_6_live_view
        if ent['id'].startswith('camera.') and 'visionect' in str(ent).lower():
            joan_devices.append(ent)
        # Alternatywnie szukamy po friendly_name
        elif ent['id'].startswith('camera.') and 'joan' in ent['attributes'].get('friendly_name', '').lower():
            joan_devices.append(ent)
    return joan_devices

def deploy_url_to_device(device_entity_id, dashboard_name):
    """Wysyła URL dashboardu do urządzenia Joan za pomocą usługi set_url."""
    if not TOKEN: return False, "Brak tokena API."
    
    # Adres Twojego AppDaemona (można by go pobierać dynamicznie, ale tu wpiszemy standard)
    # UWAGA: Użyj adresu IP HA, który jest widoczny dla urządzenia Joan!
    # Pobieramy IP z API_URL (wycinamy http:// i :8123)
    try:
        host_ip = API_URL.split('//')[1].split(':')[0]
    except:
        host_ip = "homeassistant.local" # Fallback
        
    target_url = f"http://{host_ip}:5050/{dashboard_name}"
    
    headers = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
    service_url = f"{API_URL}/services/visionect_joan/set_url"
    
    # Konwersja entity_id kamery na device_id jest trudna bez rejestru, 
    # ale integracja visionect_joan często przyjmuje entity_id w service call (sprawdź to).
    # Jeśli wymaga device_id, musielibyśmy odpytać rejestr. 
    # Spróbujmy najpierw przekazać encję, wiele integracji to obsługuje.
    
    payload = {
        "entity_id": device_entity_id, 
        "url": target_url
    }
    
    try:
        print(f"🚀 [DEPLOY] Wysyłanie {target_url} do {device_entity_id}")
        resp = requests.post(service_url, json=payload, headers=headers, timeout=10)
        if resp.status_code in [200, 201]:
            return True, f"Wysłano URL do {device_entity_id}"
        return False, f"Błąd integracji ({resp.status_code}): {resp.text}"
    except Exception as e:
        return False, str(e)

# -------------------------------------------------------------------------
# PROXY DO KAMERY (Podgląd Live)
# -------------------------------------------------------------------------
@app.route('/camera_proxy/<entity_id>')
def camera_proxy(entity_id):
    """Pobiera obraz z kamery HA używając tokena Supervisora i oddaje go do przeglądarki."""
    if not TOKEN: return "No Token", 403
    
    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json"
    }
    # Używamy API HA do pobrania obrazka
    url = f"{API_URL}/camera_proxy/{entity_id}"
    
    try:
        # Pobieramy obrazek z HA
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code == 200:
            # Zwracamy go do przeglądarki
            from flask import Response
            return Response(resp.content, mimetype=resp.headers.get('Content-Type', 'image/jpeg'))
        else:
            return f"Error from HA: {resp.status_code}", 404
    except Exception as e:
        return str(e), 500

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

def safe_yaml_string(s):
    """Bezpieczna konwersja stringu do YAML."""
    if not s: return s
    return s.replace('"', '\\"').replace("'", "\\'")

@app.route('/', methods=['GET', 'POST'])
def index():
    generated_yaml = ""
    ha_entities = get_ha_entities()
    
    # POPRAWKA 1: Inteligentniejsze filtrowanie urządzeń Joan
    # Szukamy kamer, które mają "joan" lub "visionect" w nazwie lub ID, albo "live_view" (standard integracji)
    joan_devices = []
    for e in ha_entities:
        eid = e['id'].lower()
        name = e['attributes'].get('friendly_name', '').lower()
        if eid.startswith('camera.'):
            if 'joan' in eid or 'joan' in name or 'visionect' in eid or 'live_view' in eid:
                joan_devices.append(e)
            else:
                # Jeśli nie jesteśmy pewni, dodajemy wszystkie kamery, ale użytkownik musi wybrać
                pass 
    # Jeśli filtr był zbyt agresywny i nic nie znalazł, pokaż wszystkie kamery jako fallback
    if not joan_devices:
        joan_devices = [e for e in ha_entities if e['id'].startswith('camera.')]

    dashboard_filename = "joandashboard.dash"
    dashboard_slug = "joandashboard"
    has_token = bool(TOKEN)
    save_message = None
    
    global OUTPUT_DIR
    if OUTPUT_DIR is None:
        OUTPUT_DIR = detect_dashboard_path(APPDAEMON_ADDON_SLUG)

    if request.method == 'POST':
        try:
            # Pobieranie danych
            title = request.form.get('title', 'JoanDashboard')
            # Ważne: pobieramy 'action' z formularza (musi pasować do name="action" w HTML)
            action_type = request.form.get('action', 'generate')
            
            dashboard_slug = title.lower().replace(" ", "_").replace("ą","a").replace("ć","c").replace("ę","e").replace("ł","l").replace("ń","n").replace("ó","o").replace("ś","s").replace("ź","z").replace("ż","z")
            dashboard_filename = dashboard_slug + ".dash"
            
            # --- SEKCJA GENEROWANIA KODU (TO MUSI BYĆ WYKONANE ZAWSZE DLA PODGLĄDU) ---
            cols = request.form.get('grid_columns', '4')
            rows = request.form.get('grid_rows', '8')
            lang = request.form.get('ui_language', 'pl')
            default_size_str = request.form.get('default_widget_size', '2, 1')
            def_size_parts = default_size_str.split(',')
            def_w = int(def_size_parts[0].strip())
            def_h = int(def_size_parts[1].strip()) if len(def_size_parts) > 1 else 1

            TRANS = {
                'pl': {'on': 'WŁ', 'off': 'WYŁ', 'open': 'OTW', 'closed': 'ZAM', 'locked': 'ZAM', 'unlocked': 'OTW', 'home': 'DOM', 'not_home': 'POZA'},
                'en': {'on': 'ON', 'off': 'OFF', 'open': 'OPEN', 'closed': 'CLOSED', 'locked': 'LOCKED', 'unlocked': 'UNLOCKED', 'home': 'HOME', 'not_home': 'AWAY'}
            }
            dic = TRANS.get(lang, TRANS['pl'])
            ad_columns = int(cols) if def_w == 1 else int(cols) * 2

            # Generowanie nagłówka
            generated_yaml += f"title: {title}\nwidget_dimensions: [117, 117]\nwidget_size: [{def_w}, {def_h}]\nwidget_margins: [8, 8]\ncolumns: {ad_columns}\nrows: {rows}\n"
            generated_yaml += "global_parameters:\n  use_comma: 0\n  precision: 1\n  use_hass_icon: 1\n  namespace: default\n  devices:\n    media_player:\n      step: 5\n    climate:\n      step: 1\n"
            generated_yaml += f"  white_text_style: \"{STYLE_TEXT}\"\n  state_text_style: \"{STYLE_STATE_TEXT}\"\nskin: default\n\n"
            
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
                
                generated_yaml += "\n"
                seen_ids = set()
                
                # POPRAWKA 2: PEŁNA PĘTLA GENEROWANIA WIDGETÓW (Brakowało jej w poprzedniej wersji)
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
                    w_name = safe_yaml_string(w['name'])
                    w_icon = normalize_icon_format(w['icon'])
                    i_on = normalize_icon_format(w.get('icon_on'))
                    i_off = normalize_icon_format(w.get('icon_off'))
                    
                    generated_yaml += f"{w_id}:\n"
                    if w_type == 'navigate':
                        dash_target = w_id.replace('navigate.', '')
                        nav_icon = w_icon or 'mdi-arrow-right-circle'
                        generated_yaml += f"  widget_type: navigate\n  title: \"{w_name}\"\n  dashboard: {dash_target}\n  icon_active: {nav_icon}\n  icon_inactive: {nav_icon}\n  title_style: \"{STYLE_TITLE}\"\n  widget_style: \"{STYLE_WIDGET}\"\n  icon_active_style: \"{STYLE_ICON}\"\n  icon_inactive_style: \"{STYLE_ICON}\"\n"
                    elif w_type == 'sensor':
                        generated_yaml += f"  widget_type: sensor\n  entity: {w_id}\n  title: \"{w_name}\"\n  title_style: \"{STYLE_TITLE}\"\n  text_style: \"{STYLE_TEXT}\"\n  value_style: \"{STYLE_VALUE}\"\n  unit_style: \"{STYLE_UNIT}\"\n  widget_style: \"{STYLE_WIDGET}\"\n  precision: 1\n"
                    elif w_type == 'media_player':
                        generated_yaml += f"  widget_type: media_player\n  entity: {w_id}\n  title: \"{w_name}\"\n"
                        if w_icon: generated_yaml += f"  icon: {w_icon}\n"
                        generated_yaml += f"  title_style: \"{STYLE_TITLE}\"\n  widget_style: \"{STYLE_WIDGET}\"\n  icon_style: \"{STYLE_ICON}\"\n  truncate_name: 20\n  step: 5\n"
                    elif w_type == 'climate':
                        generated_yaml += f"  widget_type: climate\n  entity: {w_id}\n  title: \"{w_name}\"\n  step: 1\n  precision: 1\n  title_style: \"{STYLE_TITLE}\"\n  widget_style: \"{STYLE_WIDGET}\"\n  icon_style: \"{STYLE_ICON}\"\n"
                    elif w_type == 'fan':
                        generated_yaml += f"  widget_type: fan\n  entity: {w_id}\n  title: \"{w_name}\"\n"
                        if i_on: generated_yaml += f"  icon_on: {i_on}\n"
                        if i_off: generated_yaml += f"  icon_off: {i_off}\n"
                        if w_icon and not i_on: generated_yaml += f"  icon: {w_icon}\n"
                        generated_yaml += f"  low_speed: 33\n  medium_speed: 66\n  high_speed: 100\n  title_style: \"{STYLE_TITLE}\"\n  widget_style: \"{STYLE_WIDGET}\"\n  icon_style_active: \"{STYLE_ICON}\"\n  icon_style_inactive: \"{STYLE_ICON}; opacity: 0.5;\"\n"
                        generated_yaml += f"  speed1_icon_style_active: \"{STYLE_ICON}\"\n  speed1_icon_style_inactive: \"{STYLE_ICON}; opacity: 0.3;\"\n  speed2_icon_style_active: \"{STYLE_ICON}\"\n  speed2_icon_style_inactive: \"{STYLE_ICON}; opacity: 0.3;\"\n  speed3_icon_style_active: \"{STYLE_ICON}\"\n  speed3_icon_style_inactive: \"{STYLE_ICON}; opacity: 0.3;\"\n"
                    elif w_type == 'scene':
                        generated_yaml += f"  widget_type: scene\n  entity: {w_id}\n  title: \"{w_name}\"\n"
                        if w_icon: generated_yaml += f"  icon: {w_icon}\n"
                        elif i_on: generated_yaml += f"  icon: {i_on}\n" 
                        generated_yaml += f"  title_style: \"{STYLE_TITLE}\"\n  widget_style: \"{STYLE_WIDGET}\"\n  icon_style_active: \"{STYLE_ICON}\"\n  icon_style_inactive: \"{STYLE_ICON}\"\n"
                    elif w_type == 'clock':
                        generated_yaml += f"  widget_type: clock\n  time_format: 24hr\n  show_seconds: 0\n  date_style: \"{STYLE_TEXT}\"\n  time_style: \"{STYLE_VALUE}\"\n"
                    elif w_type == 'label':
                        generated_yaml += f"  widget_type: label\n  text: \"{w_name}\"\n"
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
                        generated_yaml += f"  widget_type: {ad_type}\n  entity: {w_id}\n  title: \"{w_name}\"\n"
                        if i_on: generated_yaml += f"  icon_on: {i_on}\n"
                        if i_off: generated_yaml += f"  icon_off: {i_off}\n"
                        if ad_type == 'lock':
                            if i_off: generated_yaml += f"  icon_locked: {i_off}\n"
                            if i_on: generated_yaml += f"  icon_unlocked: {i_on}\n"
                        if w_icon and not i_on: generated_yaml += f"  icon: {w_icon}\n"
                        generated_yaml += f"  state_text: 1\n  title_style: \"{STYLE_TITLE}\"\n  text_style: \"{STYLE_TEXT}\"\n  widget_style: \"{STYLE_WIDGET}\"\n  icon_style_active: \"{STYLE_ICON}\"\n  icon_style_inactive: \"{STYLE_ICON}\"\n"
                        if ad_type in ['cover', 'binary_sensor', 'switch', 'light', 'lock']: 
                            generated_yaml += "  state_map:\n"
                            if ad_type == 'cover':
                                for s in ['open', 'closed', 'opening', 'closing']: generated_yaml += f"    \"{s}\": \"{dic.get(s, s)}\"\n"
                            elif ad_type == 'binary_sensor':
                                generated_yaml += f"    \"on\": \"{dic['open']}\"\n    \"off\": \"{dic['closed']}\"\n"
                            elif ad_type == 'lock':
                                generated_yaml += f"    \"locked\": \"{dic['locked']}\"\n    \"unlocked\": \"{dic['unlocked']}\"\n"
                            else:
                                generated_yaml += f"    \"on\": \"{dic['on']}\"\n    \"off\": \"{dic['off']}\"\n"
                    generated_yaml += "\n"

            # --- OBSŁUGA AKCJI SPECJALNYCH (ZAPIS/DEPLOY) ---
            
            # Jeśli akcja to 'restart' - nie musimy zapisywać pliku, tylko wywołać restart
            if action_type == 'restart':
                success, msg = restart_appdaemon_addon()
                save_message = f"✅ Sukces: {msg}" if success else f"⚠️ Błąd restartu: {msg}"
            
            # Jeśli akcja to 'save_restart' (stary przycisk, jeśli gdzieś został)
            elif action_type == 'save_restart':
                # ... (stara logika, opcjonalna) ...
                pass 

            # Jeśli akcja to 'deploy' (wysłanie na tablet)
            elif action_type == 'deploy':
                target_device = request.form.get('deploy_device_id')
                if not target_device:
                    save_message = "❌ Błąd: Nie wybrano urządzenia z listy!"
                else:
                    success, msg = deploy_url_to_device(target_device, dashboard_slug)
                    save_message = f"🚀 Wysłano: {msg}" if success else f"⚠️ Błąd wysyłania: {msg}"
            
            # Jeśli akcja to 'generate' - po prostu przechodzimy dalej, generated_yaml jest już gotowy

        except Exception as e:
            print(f"ERROR: {e}")
            generated_yaml = f"# ERROR: {e}"

    return render_template('index.html', 
                           generated_yaml=generated_yaml, 
                           entities=ha_entities, 
                           joan_devices=joan_devices, # Lista tabletów
                           filename=dashboard_filename, 
                           dash_name=dashboard_slug, 
                           has_token=has_token, 
                           save_message=save_message)

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000, debug=True)
