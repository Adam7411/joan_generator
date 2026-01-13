import os
import json
import requests
from flask import Flask, render_template, request, send_file, Response
from pathlib import Path
import io

# Inicjalizacja aplikacji
print("📦 1. Inicjalizacja aplikacji Joan 6 Generator...")
app = Flask(__name__)

# -------------------------------------------------------------------------
# 1. KONFIGURACJA API I TOKENU
# -------------------------------------------------------------------------
TOKEN = os.environ.get('SUPERVISOR_TOKEN')
API_URL = "http://supervisor/core/api"
SUPERVISOR_URL = "http://supervisor"
TOKEN_SOURCE = "System (Supervisor)"

# Slug AppDaemona (konfigurowalny: env APPDAEMON_SLUG lub options.json)
APPDAEMON_SLUG = os.environ.get('APPDAEMON_SLUG', "a0d7b954_appdaemon")

try:
    options_path = '/data/options.json'
    if os.path.exists(options_path):
        with open(options_path, 'r') as f:
            options = json.load(f)
            manual_token = options.get('manual_token')
            if manual_token and len(manual_token) > 10:
                TOKEN = manual_token
                API_URL = "http://homeassistant:8123/api"
                TOKEN_SOURCE = "Manual (Konfiguracja)"
                print(f"🔧 Wykryto manualny token. Przełączam API na: {API_URL}")
            opt_slug = options.get('appdaemon_slug')
            if opt_slug:
                APPDAEMON_SLUG = opt_slug
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
# FUNKCJA ZAPISU PLIKU .DASH
# -------------------------------------------------------------------------
def save_dash_file(filename, content):
    """
    UWAGA: W Home Assistant Supervisor addony działają w izolowanych kontenerach Docker.
    Bezpośredni zapis do katalogu innego addona nie jest możliwy bez specjalnej konfiguracji.
    
    Funkcja informuje użytkownika, że musi zapisać plik ręcznie.
    """
    network_path = f"\\\\[HA_IP]\\addon_configs\\{APPDAEMON_SLUG}\\dashboards\\{filename}"
    unix_path = f"/addon_configs/{APPDAEMON_SLUG}/dashboards/{filename}"
    
    message = (
        f"⚠️ BEZPOŚREDNI ZAPIS NIEMOŻLIWY\n\n"
        f"Addony w Home Assistant działają w izolowanych kontenerach Docker. "
        f"Nie można bezpośrednio zapisać pliku do katalogu innego addona.\n\n"
        f"Zapisz plik ręcznie:\n"
        f"• Przez Samba: {network_path}\n"
        f"• Przez SSH: {unix_path}\n\n"
        f"Lub skopiuj wygenerowany kod i zapisz go ręcznie."
    )
    
    print(f"⚠️ {message}")
    return False, message

# -------------------------------------------------------------------------
# FUNKCJA RESTARTU APPDAEMON
# -------------------------------------------------------------------------
def restart_appdaemon_addon():
    """Restartuje AppDaemon używając dostępnego tokena (Manual lub System)."""
    if not TOKEN:
        return False, "Błąd: Brak tokena API (uzupełnij manual_token w konfiguracji)."

    target_slug = APPDAEMON_SLUG
    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json"
    }

    if "homeassistant" in API_URL or "8123" in API_URL:
        url = f"{API_URL}/services/hassio/addon_restart"
        payload = {"addon": target_slug}
        print(f"🔄 Restart przez Service Call (Manual Token): {url}")
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=30)
        except Exception as e:
            print(f"❌ Wyjątek połączenia: {e}")
            return False, str(e)
    else:
        url = f"http://supervisor/addons/{target_slug}/restart"
        print(f"🔄 Restart przez Supervisor API: {url}")
        try:
            response = requests.post(url, headers=headers, timeout=30)
        except Exception as e:
            print(f"❌ Wyjątek połączenia: {e}")
            return False, str(e)

    if response.status_code in [200, 201, 202]:
        print("✅ Restart udany.")
        return True, "Zrestartowano AppDaemon."
    else:
        print(f"❌ Błąd API: {response.status_code} - {response.text}")
        return False, f"Błąd API: {response.status_code} {response.text}"

# -------------------------------------------------------------------------
# 3. STYLE (E-INK OPTIMIZED & TWEAKED)
# -------------------------------------------------------------------------
STYLE_TITLE = "color: #000000; font-size: 20px; font-weight: 700; text-align: center; padding-top: 5px; width: 100%; font-family: 'Roboto', 'Arial Black', sans-serif;"
STYLE_WIDGET = "color: #000000 !important; background-color: #FFFFFF !important;"
STYLE_TEXT = "color: #000000 !important; font-weight: 700 !important;"
STYLE_VALUE_TEMPLATE = "color: #000000 !important; font-size: {px}px !important; font-weight: 700 !important; padding-top: 60px !important; line-height: 1.1 !important; display: inline-block !important;"
STYLE_UNIT = "color: #000000 !important; padding-top: 60px !important; display: inline-block !important;"
STYLE_ICON = "color: #000000 !important;"
STYLE_STATE_TEXT = "color: #000000 !important; font-weight: 700 !important; font-size: 16px !important;"

def build_value_style(size_hint: str) -> str:
    """
    Zwraca styl dla wartości na podstawie wskazówki:
    - normal -> 54px
    - medium -> 48px
    - small  -> 40px
    - auto   -> 54px (zostanie dobrane wcześniej)
    """
    px = {
        "normal": 54,
        "medium": 48,
        "small": 40
    }.get(size_hint, 54)
    return STYLE_VALUE_TEMPLATE.format(px=px)

def pick_auto_size(value_size_hint: str, entity_id: str, entities_map: dict) -> str:
    """
    Jeśli hint == 'auto', na podstawie bieżącej wartości encji dobiera rozmiar:
      >10000  -> small (40px)
      >1000   -> medium (48px)
      else    -> normal (54px)
    Jeśli nie uda się sparsować liczby, fallback na długość tekstu:
      len>9 -> small, len>6 -> medium, inaczej normal.
    """
    if value_size_hint != "auto":
        return value_size_hint

    ent = entities_map.get(entity_id)
    if ent:
        raw = str(ent.get("state", "")).replace(",", ".").strip()
        try:
            val = float(raw)
            if abs(val) > 10000:
                return "small"
            if abs(val) > 1000:
                return "medium"
            return "normal"
        except Exception:
            pass
        length = len(raw)
        if length > 9:
            return "small"
        if length > 6:
            return "medium"
    return "normal"

# -------------------------------------------------------------------------
# 4. NORMALIZACJA FORMATU IKON
# -------------------------------------------------------------------------
def normalize_icon_format(icon_name):
    if not icon_name:
        return icon_name
    icon_name = icon_name.strip()
    if icon_name.startswith('mdi:'):
        return 'mdi-' + icon_name[4:]
    if icon_name.startswith('mdi-'):
        return icon_name
    return icon_name

# -------------------------------------------------------------------------
# 5. LOGIKA GENEROWANIA YAML
# -------------------------------------------------------------------------
def generate_joan_dash_yaml(rows, title, grid_params, lang_code, custom_defs, entities_map):
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

    ad_columns = grid_params['cols'] * grid_params['def_w']

    output = []
    output.append(f"title: {title}")
    output.append("widget_dimensions: [117, 123]")
    output.append(f"widget_size: [{grid_params['def_w']}, {grid_params['def_h']}]")
    output.append("widget_margins: [8, 4]")
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
        processed_widgets = []

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

            for w in processed_widgets:
                w_id = w['id']
                if w_id in seen_ids:
                    continue
                seen_ids.add(w_id)

                if w_id in custom_defs and not w.get('was_edited', False):
                    output.append(f"{w_id}:")
                    for line in custom_defs[w_id].split('\n'):
                        if line.strip():
                            output.append(f"  {line}")
                    output.append("")
                    continue

                w_type = w['type']
                w_name = w['name']
                w_icon = normalize_icon_format(w.get('icon'))
                i_on = normalize_icon_format(w.get('icon_on'))
                i_off = normalize_icon_format(w.get('icon_off'))
                value_size_hint = w.get('value_size_hint', 'auto')
                # Obliczamy realny hint (auto -> medium/small/normal wg stanu)
                final_size_hint = pick_auto_size(value_size_hint, w_id, entities_map)

                output.append(f"{w_id}:")

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

                elif w_type == 'sensor':
                    output.append(f"  widget_type: sensor")
                    output.append(f"  entity: {w_id}")
                    output.append(f"  title: \"{w_name}\"")
                    output.append(f"  title_style: \"{STYLE_TITLE}\"")
                    output.append(f"  text_style: \"{STYLE_TEXT}\"")
                    output.append(f"  value_style: \"{build_value_style(final_size_hint)}\"")
                    output.append(f"  unit_style: \"{STYLE_UNIT}\"")
                    output.append(f"  widget_style: \"{STYLE_WIDGET}\"")
                    if any(k in w_id for k in ['battery', 'bateria', 'level']):
                        output.append("  precision: 0")
                    else:
                        output.append("  precision: 1")

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

                elif w_type == 'climate':
                    output.append(f"  widget_type: climate")
                    output.append(f"  entity: {w_id}")
                    output.append(f"  title: \"{w_name}\"")
                    output.append(f"  step: 1")
                    output.append(f"  precision: 1")
                    output.append(f"  title_style: \"{STYLE_TITLE}\"")
                    output.append(f"  widget_style: \"{STYLE_WIDGET}\"")
                    output.append(f"  icon_style: \"{STYLE_ICON}\"")

                elif w_type == 'fan':
                    output.append(f"  widget_type: fan")
                    output.append("  fan_type: percentage")
                    output.append("  low_speed: 33")
                    output.append("  medium_speed: 66")
                    output.append("  high_speed: 100")
                    output.append(f"  entity: {w_id}")
                    output.append(f"  title: \"{w_name}\"")
                    if i_on: output.append(f"  icon_on: {i_on}")
                    if i_off: output.append(f"  icon_off: {i_off}")
                    if w_icon and not i_on: output.append(f"  icon: {w_icon}")



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

                elif w_type == 'clock':
                    output.append(f"  widget_type: clock")
                    output.append(f"  time_format: 24hr")
                    output.append(f"  show_seconds: 0")
                    output.append(f"  date_style: \"{STYLE_TEXT}\"")
                    output.append(f"  time_style: \"{STYLE_VALUE_TEMPLATE.format(px=54)}\"")

                elif w_type == 'label':
                    output.append(f"  widget_type: label")
                    output.append(f"  text: \"{w_name}\"")
                    if w_icon:
                        output.append(f"  icon: {w_icon}")
                    output.append(f"  text_style: \"{STYLE_TITLE}\"")

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
                    if w_type == 'input_button':
                        ad_type = 'script'

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

# -------------------------------------------------------------------------
# ROUTY
# -------------------------------------------------------------------------
@app.route('/', methods=['GET', 'POST'])
def index():
    generated_yaml = ""
    ha_entities = get_ha_entities()
    entities_map = {e['id']: e for e in ha_entities}
    dashboard_filename = "joandashboard.dash"
    dashboard_slug = "joandashboard"
    has_token = bool(TOKEN)
    save_message = None

    connection_info = {
        "token_source": TOKEN_SOURCE,
        "api_url": API_URL,
        "entity_count": len(ha_entities),
        "appdaemon_slug": APPDAEMON_SLUG
    }

    current_ui_lang = request.form.get('ui_language', 'pl') if request.method == 'POST' else request.args.get('lang', 'pl')

    if request.method == 'POST':
        action = request.form.get('action', 'generate')

        if action == 'restart':
            success, msg = restart_appdaemon_addon()
            if success:
                save_message = f"✅ Sukces: {msg}"
            else:
                save_message = f"❌ Błąd: {msg}"
        elif action == 'download_file':
            yaml_content = request.form.get('yaml_content', '')
            filename = request.form.get('filename', 'joandashboard.dash')
            if yaml_content and filename:
                file_obj = io.BytesIO(yaml_content.encode('utf-8'))
                return send_file(
                    file_obj,
                    mimetype='text/plain',
                    as_attachment=True,
                    download_name=filename
                )
            else:
                save_message = "❌ Błąd: Brak danych do pobrania"
        else:
            try:
                title = request.form.get('title', 'JoanDashboard')
                dashboard_slug = title.lower().replace(" ", "_")
                dashboard_filename = dashboard_slug + ".dash"

                cols = int(request.form.get('grid_columns', '4'))
                rows_grid = int(request.form.get('grid_rows', '8'))
                lang = request.form.get('ui_language', 'pl')
                current_ui_lang = lang

                default_size_str = request.form.get('default_widget_size', '2, 1')
                def_size_parts = default_size_str.split(',')
                def_w = int(def_size_parts[0].strip())
                def_h = int(def_size_parts[1].strip()) if len(def_size_parts) > 1 else 1

                layout_data = json.loads(request.form.get('layout_data_json', '[]'))
                custom_defs = json.loads(request.form.get('custom_definitions_json', '{}'))

                grid_params = {
                    'cols': cols,
                    'rows_grid': rows_grid,
                    'def_w': def_w,
                    'def_h': def_h
                }

                generated_yaml = generate_joan_dash_yaml(
                    layout_data,
                    title,
                    grid_params,
                    lang,
                    custom_defs,
                    entities_map
                )
            except Exception as e:
                print(f"❌ Error generating YAML: {e}")
                generated_yaml = f"# ERROR GENERATING YAML: {e}"

    return render_template(
        'index.html',
        generated_yaml=generated_yaml,
        entities=ha_entities,
        filename=dashboard_filename,
        dash_name=dashboard_slug,
        has_token=has_token,
        save_message=save_message,
        connection_info=connection_info,
        current_lang=current_ui_lang
    )

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000, debug=True)
