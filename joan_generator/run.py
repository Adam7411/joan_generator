import os
import json
import requests
from flask import Flask, render_template, request, jsonify

# Inicjalizacja aplikacji
print("📦 1. Inicjalizacja aplikacji Joan 6 Generator...")
app = Flask(__name__)

# -------------------------------------------------------------------------
# 1.  KONFIGURACJA API I TOKENU
# -------------------------------------------------------------------------
TOKEN = os.environ.get('SUPERVISOR_TOKEN')
API_URL = "http://supervisor/core/api"
TOKEN_SOURCE = "System (Supervisor)"

try:
    options_path = '/data/options.json'
    if os. path.exists(options_path):
        with open(options_path, 'r') as f:
            options = json. load(f)
            manual_token = options.get('manual_token')
            if manual_token and len(manual_token) > 10:
                TOKEN = manual_token
                API_URL = "http://homeassistant:8123/api"
                TOKEN_SOURCE = "Manual (Konfiguracja)"
                print(f"🔧 Wykryto manualny token.  Przełączam API na:  {API_URL}")
except Exception as e: 
    print(f"ℹ️ Info:  Nie udało się odczytać pliku opcji: {e}")

if not TOKEN:
    print("❌ OSTRZEŻENIE:  Brak tokena autoryzacji!  Lista encji będzie pusta.")

# -------------------------------------------------------------------------
# 2. POBIERANIE DANYCH Z HOME ASSISTANT
# -------------------------------------------------------------------------
def get_ha_entities():
    if not TOKEN:
        return []
    headers = {"Authorization": f"Bearer {TOKEN}", "Content-Type":  "application/json"}
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
                        'friendly_name': attributes. get('friendly_name', state['entity_id']),
                        'device_class': attributes. get('device_class', ''),
                        'unit_of_measurement':  unit
                    },
                    'unit': unit
                }
                entities.append(entity_obj)
            entities.sort(key=lambda x: x['id'])
            return entities
    except Exception as e: 
        print(f"❌ Wyjątek:  {e}")
    return []

# -------------------------------------------------------------------------
# 3. STYLE (E-INK OPTIMIZED & TWEAKED)
# -------------------------------------------------------------------------
STYLE_TITLE = "color: #000000; font-size: 20px; font-weight: 700; text-align: center; padding-top: 5px; width: 100%; font-family: 'Roboto', 'Arial Black', sans-serif;"
STYLE_WIDGET = "color: #000000 !important; background-color: #FFFFFF !important;"
STYLE_TEXT = "color: #000000 !important; font-weight: 700 !important;"
STYLE_VALUE = "color: #000000 !important; font-size: 54px !important; font-weight: 700 !important; padding-top: 60px !important; line-height: 1.1 !important; display: inline-block !important;"
STYLE_UNIT = "color: #000000 !important; padding-top: 60px !important; display: inline-block ! important;"
STYLE_ICON = "color: #000000 !important;"
STYLE_STATE_TEXT = "color: #000000 !important; font-weight:  700 !important; font-size: 16px !important;"

# -------------------------------------------------------------------------
# 4. NORMALIZACJA FORMATU IKON DLA APPDAEMON
# -------------------------------------------------------------------------
def normalize_icon_format(icon_name):
    """
    Normalizuje format ikon do formatu 'mdi-nazwa' wymaganego przez AppDaemon Dashboard. 
    
    AppDaemon Dashboard wymaga: 
    - Material Design Icons:  mdi-nazwa (np. mdi-home, mdi-power)
    - Font Awesome: fas-nazwa, far-nazwa, fab-nazwa (np. fas-bell)
    
    Konwersje:
        'mdi: home' -> 'mdi-home' (format HA -> format AppDaemon)
        'mdi-home' -> 'mdi-home' (już poprawny)
        '' -> '' (puste pozostaje puste)
    """
    if not icon_name:
        return icon_name
    
    icon_name = icon_name.strip()
    
    # Konwertuj format Home Assistant (mdi: nazwa) na format AppDaemon (mdi-nazwa)
    if icon_name.startswith('mdi:'):
        return 'mdi-' + icon_name[4:]
    
    # Format mdi-nazwa jest już poprawny dla AppDaemon
    if icon_name.startswith('mdi-'):
        return icon_name
    
    # Font Awesome i inne formaty - pozostaw bez zmian
    return icon_name

# -------------------------------------------------------------------------
# 5. AUTOMATYCZNE WYKRYWANIE ŚCIEŻKI APPDAEMON
# -------------------------------------------------------------------------
def get_appdaemon_path():
    """
    Automatycznie wykrywa ścieżkę do folderu dashboards AppDaemon. 
    
    Obsługuje różne instalacje:
    - /addon_configs/a0d7b954_appdaemon/dashboards
    - /addon_configs/g1a7c135_appdaemon/dashboards
    - /addon_configs/xxxx_appdaemon/dashboards
    - Własna ścieżka z konfiguracji
    """
    
    # 1. Sprawdź czy użytkownik podał własną ścieżkę w opcjach
    try:
        options_path = '/data/options.json'
        if os.path.exists(options_path):
            with open(options_path, 'r') as f:
                options = json.load(f)
                custom_path = options. get('appdaemon_path', '').strip()
                if custom_path and os.path.exists(custom_path):
                    print(f"✅ Używam ścieżki z konfiguracji: {custom_path}")
                    return custom_path
    except Exception as e:
        print(f"⚠️ Nie można odczytać opcji: {e}")
    
    # 2. Spróbuj znaleźć przez Supervisor API
    if TOKEN:
        try: 
            headers = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
            response = requests.get("http://supervisor/addons", headers=headers, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                addons = data.get('data', {}).get('addons', [])
                
                for addon in addons:
                    name = addon.get('name', '').lower()
                    slug = addon.get('slug', '')
                    
                    if 'appdaemon' in name or 'appdaemon' in slug:
                        dashboards_path = f"/addon_configs/{slug}/dashboards"
                        
                        # Utwórz folder jeśli nie istnieje
                        if not os.path. exists(dashboards_path):
                            parent = f"/addon_configs/{slug}"
                            if os.path. exists(parent):
                                os.makedirs(dashboards_path, exist_ok=True)
                                print(f"📁 Utworzono: {dashboards_path}")
                        
                        if os.path.exists(dashboards_path):
                            print(f"✅ Znaleziono przez API: {dashboards_path}")
                            return dashboards_path
                            
        except Exception as e: 
            print(f"⚠️ Błąd Supervisor API: {e}")
    
    # 3. Skanuj folder /addon_configs/ ręcznie
    base_paths = ["/addon_configs", "/config/addon_configs", "/homeassistant/addon_configs"]
    
    for base in base_paths: 
        if not os. path.exists(base):
            continue
        
        try: 
            for folder in os.listdir(base):
                if 'appdaemon' in folder. lower():
                    dashboards_path = os.path.join(base, folder, 'dashboards')
                    
                    # Utwórz folder dashboards jeśli nie istnieje
                    if not os. path.exists(dashboards_path):
                        parent = os.path.join(base, folder)
                        if os. path.exists(parent):
                            os.makedirs(dashboards_path, exist_ok=True)
                            print(f"📁 Utworzono:  {dashboards_path}")
                    
                    if os. path.exists(dashboards_path):
                        print(f"✅ Znaleziono przez skanowanie: {dashboards_path}")
                        return dashboards_path
                        
        except Exception as e:
            print(f"⚠️ Błąd skanowania {base}: {e}")
    
    # 4. Nie znaleziono
    print("❌ Nie znaleziono folderu AppDaemon dashboards")
    return None


def get_appdaemon_slug():
    """Pobiera slug dodatku AppDaemon dla operacji restart"""
    if not TOKEN:
        return None
    
    try:
        headers = {"Authorization": f"Bearer {TOKEN}", "Content-Type":  "application/json"}
        response = requests.get("http://supervisor/addons", headers=headers, timeout=10)
        
        if response. status_code == 200:
            data = response.json()
            addons = data.get('data', {}).get('addons', [])
            
            for addon in addons: 
                name = addon.get('name', '').lower()
                slug = addon. get('slug', '')
                
                if 'appdaemon' in name or 'appdaemon' in slug: 
                    return slug
                    
    except Exception as e:
        print(f"⚠️ Błąd pobierania slug: {e}")
    
    return None


def get_existing_dashboards():
    """Pobiera listę istniejących plików . dash"""
    path = get_appdaemon_path()
    if not path:
        return []
    
    try:
        files = [f for f in os.listdir(path) if f.endswith('.dash')]
        return sorted(files)
    except Exception as e: 
        print(f"❌ Błąd listowania plików: {e}")
        return []


def restart_appdaemon():
    """Restartuje dodatek AppDaemon przez Supervisor API"""
    if not TOKEN: 
        return False, "Brak tokena autoryzacji"
    
    try:
        # Sprawdź opcje - czy auto-restart jest włączony
        options_path = '/data/options.json'
        if os.path.exists(options_path):
            with open(options_path, 'r') as f:
                options = json.load(f)
                if not options.get('auto_restart_appdaemon', False):
                    return True, "Auto-restart wyłączony (włącz w konfiguracji)"
        
        headers = {"Authorization": f"Bearer {TOKEN}", "Content-Type":  "application/json"}
        
        # Znajdź slug AppDaemon
        slug = get_appdaemon_slug()
        
        if slug: 
            response = requests. post(
                f"http://supervisor/addons/{slug}/restart",
                headers=headers,
                timeout=30
            )
            if response.status_code == 200:
                return True, f"AppDaemon ({slug}) zrestartowany ✅"
            else:
                return False, f"Błąd restartu:  HTTP {response.status_code}"
        
        return False, "Nie znaleziono dodatku AppDaemon"
        
    except Exception as e: 
        return False, f"Błąd restartu: {e}"

# -------------------------------------------------------------------------
# 6. API ENDPOINTS - INTEGRACJA Z HOME ASSISTANT
# -------------------------------------------------------------------------

@app.route('/api/status', methods=['GET'])
def api_status():
    """Status integracji z Home Assistant i AppDaemon"""
    path = get_appdaemon_path()
    dashboards = get_existing_dashboards() if path else []
    slug = get_appdaemon_slug()
    
    return jsonify({
        'success': True,
        'appdaemon_path': path,
        'appdaemon_slug': slug,
        'appdaemon_found': path is not None,
        'dashboards_count': len(dashboards),
        'dashboards': dashboards,
        'ha_connected': TOKEN is not None,
        'token_source': TOKEN_SOURCE if TOKEN else None
    })


@app.route('/api/dashboards', methods=['GET'])
def api_list_dashboards():
    """Lista istniejących dashboardów"""
    dashboards = get_existing_dashboards()
    path = get_appdaemon_path()
    return jsonify({
        'success': True,
        'path': path,
        'dashboards': dashboards
    })


@app.route('/api/dashboard/<filename>', methods=['GET'])
def api_load_dashboard(filename):
    """Wczytaj zawartość pliku . dash"""
    path = get_appdaemon_path()
    if not path:
        return jsonify({'success': False, 'error': 'Nie znaleziono folderu dashboards AppDaemon'})
    
    # Walidacja nazwy pliku
    if not filename.endswith('.dash'):
        filename += '.dash'
    
    filepath = os.path. join(path, filename)
    
    # Bezpieczeństwo - sprawdź czy plik jest w dozwolonym folderze
    if not os.path.abspath(filepath).startswith(os.path.abspath(path)):
        return jsonify({'success': False, 'error':  'Niedozwolona ścieżka'})
    
    if not os.path. exists(filepath):
        return jsonify({'success': False, 'error': f'Plik {filename} nie istnieje'})
    
    try: 
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f. read()
        return jsonify({
            'success': True,
            'content':  content,
            'filename': filename,
            'path': filepath
        })
    except Exception as e: 
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/dashboard/save', methods=['POST'])
def api_save_dashboard():
    """Zapisz dashboard do pliku .dash"""
    path = get_appdaemon_path()
    if not path:
        return jsonify({
            'success':  False,
            'error': 'Nie znaleziono folderu dashboards AppDaemon.  Sprawdź czy AppDaemon jest zainstalowany i uruchomiony.'
        })
    
    data = request.json
    if not data: 
        return jsonify({'success': False, 'error': 'Brak danych'})
    
    filename = data.get('filename', 'joandashboard.dash')
    content = data.get('content', '')
    
    if not content. strip():
        return jsonify({'success':  False, 'error': 'Pusta zawartość pliku'})
    
    # Walidacja i czyszczenie nazwy pliku
    if not filename.endswith('.dash'):
        filename += '.dash'
    
    # Usuń niebezpieczne znaki (zostaw tylko alfanumeryczne, _, -, .)
    safe_filename = "".join(c for c in filename if c.isalnum() or c in ('_', '-', '.')).strip()
    
    if not safe_filename or safe_filename == '. dash':
        return jsonify({'success': False, 'error':  'Nieprawidłowa nazwa pliku'})
    
    filepath = os.path.join(path, safe_filename)
    
    # Bezpieczeństwo - sprawdź czy ścieżka jest w dozwolonym folderze
    if not os.path.abspath(filepath).startswith(os.path.abspath(path)):
        return jsonify({'success': False, 'error': 'Niedozwolona ścieżka'})
    
    try:
        # Zapisz plik
        with open(filepath, 'w', encoding='utf-8') as f:
            f. write(content)
        
        print(f"✅ Zapisano dashboard: {filepath}")
        
        # Opcjonalny restart AppDaemon
        restart_success, restart_msg = restart_appdaemon()
        
        return jsonify({
            'success': True,
            'message':  f'Zapisano:  {safe_filename}',
            'filename': safe_filename,
            'path': filepath,
            'restart_success': restart_success,
            'restart_message': restart_msg
        })
    except PermissionError: 
        return jsonify({'success': False, 'error': 'Brak uprawnień do zapisu.  Sprawdź konfigurację dodatku.'})
    except Exception as e: 
        return jsonify({'success': False, 'error': f'Błąd zapisu: {str(e)}'})


@app.route('/api/dashboard/delete/<filename>', methods=['DELETE'])
def api_delete_dashboard(filename):
    """Usuń plik .dash"""
    path = get_appdaemon_path()
    if not path:
        return jsonify({'success': False, 'error': 'Nie znaleziono folderu dashboards'})
    
    # Walidacja nazwy pliku
    if not filename. endswith('.dash'):
        filename += '. dash'
    
    filepath = os. path.join(path, filename)
    
    # Bezpieczeństwo
    if not os. path.abspath(filepath).startswith(os.path.abspath(path)):
        return jsonify({'success': False, 'error':  'Niedozwolona ścieżka'})
    
    if not os.path. exists(filepath):
        return jsonify({'success': False, 'error': f'Plik {filename} nie istnieje'})
    
    try:
        os.remove(filepath)
        print(f"🗑️ Usunięto dashboard:  {filepath}")
        return jsonify({
            'success':  True,
            'message': f'Usunięto:  {filename}'
        })
    except PermissionError: 
        return jsonify({'success': False, 'error': 'Brak uprawnień do usunięcia pliku'})
    except Exception as e: 
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/dashboard/rename', methods=['POST'])
def api_rename_dashboard():
    """Zmień nazwę pliku .dash"""
    path = get_appdaemon_path()
    if not path:
        return jsonify({'success':  False, 'error': 'Nie znaleziono folderu dashboards'})
    
    data = request.json
    if not data:
        return jsonify({'success': False, 'error':  'Brak danych'})
    
    old_name = data.get('old_name', '')
    new_name = data.get('new_name', '')
    
    if not old_name or not new_name: 
        return jsonify({'success': False, 'error': 'Podaj starą i nową nazwę'})
    
    # Dodaj rozszerzenie jeśli brak
    if not old_name.endswith('.dash'):
        old_name += '. dash'
    if not new_name. endswith('.dash'):
        new_name += '.dash'
    
    # Wyczyść nową nazwę
    safe_new_name = "". join(c for c in new_name if c.isalnum() or c in ('_', '-', '.')).strip()
    
    old_path = os. path.join(path, old_name)
    new_path = os.path. join(path, safe_new_name)
    
    # Bezpieczeństwo
    if not os.path. abspath(old_path).startswith(os.path.abspath(path)):
        return jsonify({'success': False, 'error': 'Niedozwolona ścieżka'})
    if not os.path. abspath(new_path).startswith(os.path.abspath(path)):
        return jsonify({'success': False, 'error': 'Niedozwolona ścieżka'})
    
    if not os.path. exists(old_path):
        return jsonify({'success': False, 'error':  f'Plik {old_name} nie istnieje'})
    
    if os.path.exists(new_path):
        return jsonify({'success': False, 'error': f'Plik {safe_new_name} już istnieje'})
    
    try:
        os.rename(old_path, new_path)
        print(f"📝 Zmieniono nazwę:  {old_name} -> {safe_new_name}")
        return jsonify({
            'success': True,
            'message':  f'Zmieniono nazwę: {old_name} -> {safe_new_name}',
            'old_name': old_name,
            'new_name': safe_new_name
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/appdaemon/restart', methods=['POST'])
def api_restart_appdaemon():
    """Ręczny restart AppDaemon"""
    # Tymczasowo wymuś restart (ignoruj ustawienie auto_restart)
    if not TOKEN:
        return jsonify({'success':  False, 'error': 'Brak tokena autoryzacji'})
    
    try:
        headers = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
        slug = get_appdaemon_slug()
        
        if slug:
            response = requests.post(
                f"http://supervisor/addons/{slug}/restart",
                headers=headers,
                timeout=30
            )
            if response.status_code == 200:
                return jsonify({
                    'success': True,
                    'message': f'AppDaemon ({slug}) zrestartowany ✅'
                })
            else:
                return jsonify({
                    'success':  False,
                    'error': f'Błąd restartu: HTTP {response.status_code}'
                })
        
        return jsonify({'success':  False, 'error': 'Nie znaleziono dodatku AppDaemon'})
        
    except Exception as e:
        return jsonify({'success': False, 'error':  f'Błąd restartu: {e}'})

# -------------------------------------------------------------------------
# 7. GŁÓWNA STRONA - GENEROWANIE YAML
# -------------------------------------------------------------------------

@app.route('/', methods=['GET', 'POST'])
def index():
    generated_yaml = ""
    ha_entities = get_ha_entities()
    dashboard_filename = "joandashboard.dash"
    dashboard_slug = "joandashboard"
    
    if request.method == 'POST':
        try:
            title = request.form. get('title', 'JoanDashboard')
            dashboard_slug = title.lower().replace(" ", "_")
            dashboard_filename = dashboard_slug + ".dash"
            
            cols = request.form. get('grid_columns', '4')
            rows = request.form.get('grid_rows', '8')
            lang = request.form. get('ui_language', 'pl')
            
            default_size_str = request.form. get('default_widget_size', '2, 1')
            def_size_parts = default_size_str.split(',')
            def_w = int(def_size_parts[0]. strip())
            def_h = int(def_size_parts[1].strip()) if len(def_size_parts) > 1 else 1

            TRANS = {
                'pl': {'on': 'WŁĄCZONE', 'off': 'WYŁĄCZONE', 'open': 'OTWARTA', 'closed': 'ZAMKNIĘTA', 'opening': 'OTWIERANIE', 'closing':  'ZAMYKANIE', 'locked': 'ZAMKNIĘTE', 'unlocked': 'OTWARTE', 'home': 'W DOMU', 'not_home': 'POZA'},
                'en':  {'on': 'ON', 'off':  'OFF', 'open': 'OPEN', 'closed': 'CLOSED', 'opening': 'OPENING', 'closing':  'CLOSING', 'locked': 'LOCKED', 'unlocked': 'UNLOCKED', 'home': 'HOME', 'not_home': 'AWAY'}
            }
            dic = TRANS.get(lang, TRANS['pl'])

            if def_w == 1: 
                ad_columns = int(cols)
            else:
                ad_columns = int(cols) * 2

            generated_yaml += f"title: {title}\n"
            generated_yaml += "widget_dimensions:  [117, 117]\n"
            generated_yaml += f"widget_size: [{def_w}, {def_h}]\n"
            generated_yaml += "widget_margins: [8, 8]\n"
            generated_yaml += f"columns: {ad_columns}\n"
            generated_yaml += f"rows: {rows}\n"
            generated_yaml += "global_parameters:\n"
            generated_yaml += "  use_comma:  0\n"
            generated_yaml += "  precision: 1\n"
            generated_yaml += "  use_hass_icon: 1\n"
            generated_yaml += "  namespace: default\n"
            generated_yaml += "  devices:\n"
            generated_yaml += "    media_player:\n"
            generated_yaml += "      step: 5\n"
            generated_yaml += f"  white_text_style:  \"{STYLE_TEXT}\"\n"
            generated_yaml += f"  state_text_style: \"{STYLE_STATE_TEXT}\"\n"
            generated_yaml += "skin: simplyred\n\n"
            
            layout_data_str = request.form.get('layout_data_json')
            custom_defs_str = request. form.get('custom_definitions_json', '{}')
            custom_defs = json.loads(custom_defs_str)
            
            processed_widgets = []
            
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
                        size_str = w. get('size', '')
                        is_default = False
                        
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
                
                for w in processed_widgets: 
                    w_id = w['id']
                    if w_id in seen_ids: 
                        continue
                    seen_ids. add(w_id)
                    
                    if w_id in custom_defs and not w. get('was_edited', False):
                        generated_yaml += f"{w_id}:\n"
                        for line in custom_defs[w_id]. split('\n'):
                            if line. strip():
                                generated_yaml += f"  {line}\n"
                        generated_yaml += "\n"
                        continue

                    w_type = w['type']
                    w_name = w['name']
                    w_icon = normalize_icon_format(w['icon'])
                    i_on = normalize_icon_format(w. get('icon_on'))
                    i_off = normalize_icon_format(w. get('icon_off'))
                    
                    generated_yaml += f"{w_id}:\n"
                    
                    if w_type == 'navigate':
                        # POPRAWKA: Wyciągnij samą nazwę dashboardu (bez "navigate.")
                        dash_target = w_id.replace('navigate.', '')
                        # POPRAWKA: Użyj icon_active i icon_inactive (oba wymagane dla navigate)
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
                        generated_yaml += f"  widget_type:  sensor\n"
                        generated_yaml += f"  entity: {w_id}\n"
                        generated_yaml += f"  title:  \"{w_name}\"\n"
                        generated_yaml += f"  title_style: \"{STYLE_TITLE}\"\n"
                        generated_yaml += f"  text_style: \"{STYLE_TEXT}\"\n"
                        generated_yaml += f"  value_style: \"{STYLE_VALUE}\"\n"
                        generated_yaml += f"  unit_style: \"{STYLE_UNIT}\"\n"
                        generated_yaml += f"  widget_style: \"{STYLE_WIDGET}\"\n"
                        if any(k in w_id for k in ['battery', 'bateria', 'level']):
                            generated_yaml += "  precision: 0\n"
                        else:
                            generated_yaml += "  precision: 1\n"

                    elif w_type == 'media_player':
                        generated_yaml += f"  widget_type: media_player\n"
                        generated_yaml += f"  entity:  {w_id}\n"
                        generated_yaml += f"  title: \"{w_name}\"\n"
                        if w_icon:
                            generated_yaml += f"  icon: {w_icon}\n"
                        generated_yaml += f"  title_style: \"{STYLE_TITLE}\"\n"
                        generated_yaml += f"  widget_style: \"{STYLE_WIDGET}\"\n"
                        generated_yaml += f"  icon_style: \"{STYLE_ICON}\"\n"
                        generated_yaml += "  truncate_name: 20\n"
                        generated_yaml += "  step: 5\n"

                    elif w_type == 'clock':
                        generated_yaml += f"  widget_type:  clock\n"
                        generated_yaml += f"  time_format: 24hr\n"
                        generated_yaml += f"  show_seconds: 0\n"
                        generated_yaml += f"  date_style: \"{STYLE_TEXT}\"\n"
                        generated_yaml += f"  time_style: \"{STYLE_VALUE}\"\n"

                    elif w_type == 'label':
                        generated_yaml += f"  widget_type:  label\n"
                        generated_yaml += f"  text: \"{w_name}\"\n"
                        if w_icon: 
                            generated_yaml += f"  icon: {w_icon}\n"
                        generated_yaml += f"  text_style: \"{STYLE_TITLE}\"\n"
                    
                    else:
                        ad_type = w_type
                        if w_type == 'binary_sensor':
                            ad_type = 'binary_sensor'
                        if w_type == 'input_boolean':
                            ad_type = 'switch'
                        if w_type == 'person':
                            ad_type = 'device_tracker'
                        if w_type == 'light':
                            ad_type = 'switch'
                        if w_type == 'lock':
                            ad_type = 'lock'
                        if w_type == 'input_select':
                            ad_type = 'input_select'
                        if w_type == 'input_number':
                            ad_type = 'input_number'
                        if w_type == 'script':
                            ad_type = 'script'
                        
                        generated_yaml += f"  widget_type: {ad_type}\n"
                        generated_yaml += f"  entity: {w_id}\n"
                        generated_yaml += f"  title: \"{w_name}\"\n"
                        
                        if i_on:
                            generated_yaml += f"  icon_on: {i_on}\n"
                        if i_off:
                            generated_yaml += f"  icon_off:  {i_off}\n"
                        if ad_type == 'lock':
                            if i_off:
                                generated_yaml += f"  icon_locked: {i_off}\n"
                            if i_on:
                                generated_yaml += f"  icon_unlocked: {i_on}\n"
                        if w_icon and not i_on: 
                            generated_yaml += f"  icon: {w_icon}\n"
                        
                        generated_yaml += f"  state_text:  1\n"
                        generated_yaml += f"  title_style: \"{STYLE_TITLE}\"\n"
                        generated_yaml += f"  text_style: \"{STYLE_TEXT}\"\n"
                        generated_yaml += f"  widget_style: \"{STYLE_WIDGET}\"\n"
                        generated_yaml += f"  icon_style_active: \"{STYLE_ICON}\"\n"
                        generated_yaml += f"  icon_style_inactive: \"{STYLE_ICON}\"\n"
                        
                        if ad_type in ['cover', 'binary_sensor', 'switch', 'light', 'lock']: 
                            generated_yaml += "  state_map:\n"
                            if ad_type == 'cover':
                                for s in ['open', 'closed', 'opening', 'closing']: 
                                    generated_yaml += f"    \"{s}\": \"{dic. get(s, s)}\"\n"
                            elif ad_type == 'binary_sensor': 
                                generated_yaml += f"    \"on\": \"{dic['open']}\"\n"
                                generated_yaml += f"    \"off\": \"{dic['closed']}\"\n"
                            elif ad_type == 'lock':
                                generated_yaml += f"    \"locked\":  \"{dic['locked']}\"\n"
                                generated_yaml += f"    \"unlocked\":  \"{dic['unlocked']}\"\n"
                            else:
                                generated_yaml += f"    \"on\": \"{dic['on']}\"\n"
                                generated_yaml += f"    \"off\": \"{dic['off']}\"\n"

                    generated_yaml += "\n"
        except Exception as e: 
            print(f"❌ Error generating YAML:  {e}")
            generated_yaml = f"# ERROR GENERATING YAML:  {e}"

    return render_template('index.html', generated_yaml=generated_yaml, entities=ha_entities, filename=dashboard_filename, dash_name=dashboard_slug)

# -------------------------------------------------------------------------
# 8. URUCHOMIENIE APLIKACJI
# -------------------------------------------------------------------------

if __name__ == "__main__":
    print("🚀 Uruchamianie Joan 6 Generator...")
    print(f"🔑 Token: {'Znaleziony (' + TOKEN_SOURCE + ')' if TOKEN else 'BRAK'}")
    print(f"🌐 API URL: {API_URL}")
    
    # Sprawdź ścieżkę AppDaemon przy starcie
    appdaemon_path = get_appdaemon_path()
    if appdaemon_path:
        print(f"📁 AppDaemon dashboards:  {appdaemon_path}")
        dashboards = get_existing_dashboards()
        print(f"📊 Znalezione dashboardy: {len(dashboards)}")
    else:
        print("⚠️ AppDaemon nie znaleziony - funkcja zapisu do HA będzie niedostępna")
    
    app. run(host='0.0.0.0', port=5000, debug=True)
