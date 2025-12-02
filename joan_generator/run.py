"""
Joan Generator / run.py
Kompletny backend Flask dla dodatku generującego pliki .dash AppDaemon/HADashboard.

FUNKCJE:
- Wykrywanie tokenu (Supervisor lub manualny w /data/options.json)
- Pobieranie stanów /api/states
- Wstrzykiwanie encji do index.html
- Generowanie YAML z layout_data_json
- Endpoint diagnostyczny /api/entities
"""

import os
import json
from typing import List, Dict, Any, Optional
from flask import Flask, render_template, request, jsonify
import requests
from datetime import datetime

app = Flask(__name__)

# =========================================================
# KONFIGURACJA TOKENU I API
# =========================================================
SUPERVISOR_TOKEN = os.environ.get("SUPERVISOR_TOKEN")
TOKEN_SOURCE = None
API_URL = None

def detect_token() -> Optional[str]:
    """
    Zwraca token oraz ustawia globalne API_URL i TOKEN_SOURCE.
    Priorytety:
    1. SUPERVISOR_TOKEN -> http://supervisor/core/api
    2. manual_token w /data/options.json -> http://homeassistant:8123/api
    """
    global TOKEN_SOURCE, API_URL

    # 1. Supervisor
    if SUPERVISOR_TOKEN and len(SUPERVISOR_TOKEN) > 10:
        TOKEN_SOURCE = "Supervisor (env SUPERVISOR_TOKEN)"
        API_URL = "http://supervisor/core/api"
        return SUPERVISOR_TOKEN

    # 2. Manualny token
    try:
        if os.path.exists("/data/options.json"):
            with open("/data/options.json", "r", encoding="utf-8") as f:
                options = json.load(f)
            manual_token = options.get("manual_token")
            if manual_token and len(manual_token) > 10:
                TOKEN_SOURCE = "Manual (options.json)"
                API_URL = "http://homeassistant:8123/api"
                return manual_token
    except Exception as e:
        print(f"ℹ️ Info: Nie udało się odczytać /data/options.json: {e}")

    TOKEN_SOURCE = "Brak (no token)"
    API_URL = None
    return None

TOKEN = detect_token()
if TOKEN:
    print(f"🔑 Token wykryty: {TOKEN_SOURCE}")
    print(f"🌐 API_URL ustawione na: {API_URL}")
else:
    print("❌ UWAGA: Brak tokenu – lista encji będzie pusta!")

# =========================================================
# POBIERANIE STANÓW Z HOME ASSISTANT
# =========================================================
def fetch_entities() -> List[Dict[str, Any]]:
    """
    Pobiera wszystkie stany z Home Assistant (API /states).
    Format zwracany: {id, state, attributes, unit}
    """
    if not TOKEN or not API_URL:
        return []
    try:
        headers = {
            "Authorization": f"Bearer {TOKEN}",
            "Content-Type": "application/json"
        }
        url = f"{API_URL}/states"
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code != 200:
            print(f"⚠️ Błąd API ({resp.status_code}): {resp.text}")
            return []
        raw = resp.json()
        entities: List[Dict[str, Any]] = []
        for st in raw:
            attrs = st.get("attributes", {}) or {}
            unit = attrs.get("unit_of_measurement", "")
            entities.append({
                "id": st.get("entity_id"),
                "state": str(st.get("state", "")),
                "attributes": attrs,
                "unit": unit
            })
        # Sortuj dla przewidywalności
        entities.sort(key=lambda x: x["id"])
        return entities
    except Exception as e:
        print(f"❌ Wyjątek przy pobieraniu encji: {e}")
        return []

# =========================================================
# STYLE / MAPY
# =========================================================
STYLES = {
    "title": "color: #000000; font-size: 20px; font-weight: 700; text-align: center; padding-top: 3px; width: 100%; font-family: 'Roboto', 'Arial Black', sans-serif;",
    "widget": "color: #000000 !important; background-color: #FFFFFF !important;",
    "text": "color: #000000 !important; font-weight: 700 !important;",
    "value": "color: #000000 !important; font-size: 44px !important; font-weight: 700 !important;",
    "unit": "color: #000000 !important;",
    "icon": "color: #000000 !important;",
    "state_text": "color: #000000 !important; font-weight: 700 !important; font-size: 16px !important;"
}

STATE_MAP = {
    "pl": {
        "on": "WŁĄCZONE", "off": "WYŁĄCZONE", "open": "OTWARTE", "closed": "ZAMKNIĘTE",
        "opening": "OTWIERANIE", "closing": "ZAMYKANIE",
        "locked": "ZAMKNIĘTE", "unlocked": "OTWARTE",
        "home": "W DOMU", "not_home": "POZA"
    },
    "en": {
        "on": "ON", "off": "OFF", "open": "OPEN", "closed": "CLOSED",
        "opening": "OPENING", "closing": "CLOSING",
        "locked": "LOCKED", "unlocked": "UNLOCKED",
        "home": "HOME", "not_home": "AWAY"
    }
}

# =========================================================
# POMOCNICZE
# =========================================================
def normalize_filename(title: str) -> str:
    """
    Generuje nazwę pliku .dash z tytułu.
    """
    base = title.strip() or "JoanDashboard"
    slug = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in base).lower()
    if not slug.endswith(".dash"):
        slug += ".dash"
    return slug

def icon_pair_guess(w_type: str, base_icon: Optional[str]) -> (Optional[str], Optional[str]):
    """
    Zwraca parę ikon (on/off) gdy użytkownik ich nie podał.
    """
    if base_icon:
        i = base_icon.lower()
        # heurystyka
        if "garage" in i: return "mdi-garage-open", "mdi-garage"
        if "gate" in i: return "mdi-gate-open", "mdi-gate"
        if "lock" in i: return "mdi-lock-open", "mdi-lock"
        if "door" in i: return "mdi-door-open", "mdi-door-closed"
        if "window" in i or "blind" in i or "shutter" in i: return "mdi-window-shutter-open", "mdi-window-shutter"
        if "light" in i or "bulb" in i: return "mdi-lightbulb-on", "mdi-lightbulb-outline"
        return base_icon, base_icon + "-outline"

    # Fallback bez bazowej ikony
    if w_type == "lock": return "mdi-lock-open", "mdi-lock"
    if w_type == "cover": return "mdi-window-shutter-open", "mdi-window-shutter"
    if w_type in ("person", "device_tracker"): return "mdi-home", "mdi-home-outline"
    return None, None

def build_yaml(title: str, lang: str, layout_rows: List[List[Dict[str, Any]]]) -> str:
    """
    Generuje treść pliku .dash na podstawie layout_rows (lista wierszy z widgetami).
    """
    dic = STATE_MAP.get(lang, STATE_MAP["pl"])
    out = []
    out.append(f"title: {title}")
    out.append("widget_dimensions: [117, 117]")
    out.append("widget_size: [2, 1]")
    out.append("widget_margins: [8, 8]")
    out.append("columns: 6")
    out.append("rows: 9")
    out.append("global_parameters:")
    out.append("  use_comma: 0")
    out.append("  precision: 1")
    out.append("  use_hass_icon: 1")
    out.append("  namespace: default")
    out.append("  devices:")
    out.append("    media_player:")
    out.append("      step: 5")
    out.append(f"  white_text_style: \"{STYLES['text']}\"")
    out.append(f"  state_text_style: \"{STYLES['state_text']}\"")
    out.append("skin: simplyred")
    out.append("")  # blank

    # Layout sekcja
    out.append("layout:")
    processed_widgets: List[Dict[str, Any]] = []
    for row in layout_rows:
        if not row:
            continue
        parts = []
        for w in row:
            if w.get("type") == "spacer":
                parts.append("spacer")
                continue
            w_id = w.get("id")
            size = (w.get("size") or "").strip()
            item = w_id
            if size and size != "(2x1)":
                if not size.startswith("("):
                    size = f"({size})"
                item += size
            parts.append(item)
        out.append(f"  - {', '.join(parts)}")
        processed_widgets.extend(row)

    out.append("")
    out.append("# --- WIDGET DEFINITIONS ---")
    out.append("")

    seen = set()
    for w in processed_widgets:
        w_type = w.get("type")
        if w_type == "spacer":
            continue
        w_id = w.get("id")
        if not w_id or w_id in seen:
            continue
        seen.add(w_id)

        name = w.get("name") or w_id
        icon = w.get("icon")
        icon_on = w.get("icon_on")
        icon_off = w.get("icon_off")

        out.append(f"{w_id}:")
        out.append(f"  widget_type: {w_type}")

        # NAWIGACJA
        if w_type == "navigate":
            dashboard_name = w_id.replace("navigate.", "")
            out.append(f"  dashboard: {dashboard_name}")
            out.append(f"  title: \"{name}\"")
            out.append(f"  icon_inactive: {icon or 'mdi-arrow-right-circle'}")
            out.append(f"  title_style: \"{STYLES['title']}\"")
            out.append("  widget_style: \"background-color: #FFFFFF !important; border-radius: 8px !important; padding: 10px !important; color: #000000 !important;\"")
            out.append("")
            continue

        # CLOCK / LABEL nie mają entity
        if w_type not in ("clock", "label"):
            out.append(f"  entity: {w_id}")

        out.append(f"  title: \"{name}\"")

        if w_type == "sensor":
            out.append(f"  title_style: \"{STYLES['title']}\"")
            out.append(f"  text_style: \"{STYLES['text']}\"")
            out.append(f"  value_style: \"{STYLES['value']}\"")
            out.append(f"  unit_style: \"{STYLES['unit']}\"")
            out.append(f"  widget_style: \"{STYLES['widget']}\"")
            if icon:
                out.append(f"  icon: {icon}")

        elif w_type == "media_player":
            out.append("  truncate_name: 20")
            out.append("  step: 5")
            out.append(f"  title_style: \"{STYLES['title']}\"")
            out.append(f"  widget_style: \"{STYLES['widget']}\"")
            out.append(f"  icon_style: \"{STYLES['icon']}\"")

        elif w_type == "climate":
            out.append("  step: 1")
            out.append(f"  title_style: \"{STYLES['title']}\"")
            out.append(f"  widget_style: \"{STYLES['widget']}\"")
            out.append("  state_text: 1")
            out.append(f"  text_style: \"{STYLES['text']}\"")
            out.append(f"  icon_style_active: \"{STYLES['icon']}\"")
            out.append(f"  icon_style_inactive: \"{STYLES['icon']}\"")

        elif w_type == "clock":
            out[-1] = out[-1].replace(f"  title: \"{name}\"", f"  time_format: 24hr")  # usuń title
            out.append("  show_seconds: 0")
            out.append(f"  date_style: \"{STYLES['text']}\"")
            out.append(f"  time_style: \"{STYLES['value']} font-size: 50px !important;\"")

        elif w_type == "label":
            out[-1] = out[-1].replace(f"  title: \"{name}\"", f"  text: \"{name}\"")
            if icon:
                out.append(f"  icon: {icon}")

        else:
            # Actionable / przełączalne
            ad_type = w_type
            if w_type == "binary_sensor":
                ad_type = "binary_sensor"
            if w_type == "input_boolean":
                ad_type = "switch"
            if w_type == "person":
                ad_type = "device_tracker"
            if w_type == "light":
                ad_type = "switch"

            # Ikony
            if w_type == "lock":
                if icon_on or icon_off:
                    if icon_off:
                        out.append(f"  icon_locked: {icon_off}")
                    if icon_on:
                        out.append(f"  icon_unlocked: {icon_on}")
                else:
                    auto_on, auto_off = icon_pair_guess("lock", icon)
                    if auto_off:
                        out.append(f"  icon_locked: {auto_off}")
                    if auto_on:
                        out.append(f"  icon_unlocked: {auto_on}")
            else:
                if icon_on or icon_off:
                    if icon_on:
                        out.append(f"  icon_on: {icon_on}")
                    if icon_off:
                        out.append(f"  icon_off: {icon_off}")
                else:
                    auto_on, auto_off = icon_pair_guess(ad_type, icon)
                    if auto_on:
                        out.append(f"  icon_on: {auto_on}")
                    if auto_off:
                        out.append(f"  icon_off: {auto_off}")

            out.append(f"  title_style: \"{STYLES['title']}\"")
            out.append(f"  widget_style: \"{STYLES['widget']}\"")
            out.append(f"  icon_style_active: \"{STYLES['icon']}\"")
            out.append(f"  icon_style_inactive: \"{STYLES['icon']}\"")
            out.append("  state_text: 1")
            out.append(f"  text_style: \"{STYLES['text']}\"")
            out.append("  state_map:")
            for key, val in dic.items():
                out.append(f"    \"{key}\": \"{val}\"")

        out.append("")  # blank after widget
    return "\n".join(out)

# =========================================================
# ROUTES
# =========================================================
@app.route("/", methods=["GET", "POST"])
def index():
    entities = fetch_entities()
    generated_yaml = ""
    filename = ""
    dash_slug = ""

    if request.method == "POST":
        try:
            title = request.form.get("title", "JoanDashboard")
            dash_slug = title.lower().replace(" ", "_")
            filename = normalize_filename(title)
            lang = request.form.get("ui_language", "pl")
            layout_raw = request.form.get("layout_data_json", "[]")

            try:
                layout_rows = json.loads(layout_raw)
            except Exception:
                layout_rows = []
                print("⚠️ Nie udało się zdekodować layout_data_json – użyto pustej listy.")

            generated_yaml = build_yaml(title, lang, layout_rows)

        except Exception as e:
            generated_yaml = f"# ERROR GENERATING YAML: {e}"
            print(f"❌ Błąd generowania YAML: {e}")

    return render_template(
        "index.html",
        generated_yaml=generated_yaml,
        entities=entities,
        filename=filename,
        dash_name=dash_slug
    )

@app.route("/api/entities")
def api_entities():
    """
    Endpoint diagnostyczny – pozwala podejrzeć co backend pobiera z HA.
    """
    entities = fetch_entities()
    return jsonify({
        "count": len(entities),
        "source": TOKEN_SOURCE,
        "api_url": API_URL,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "entities": entities[:200]  # limit dla przejrzystości
    })

@app.route("/health")
def health():
    return jsonify({"status": "ok", "token_source": TOKEN_SOURCE, "api_url": API_URL})

# =========================================================
# MAIN
# =========================================================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    debug = os.environ.get("FLASK_DEBUG", "false").lower() == "true"
    print(f"🚀 Start Flask na porcie {port} (debug={debug})")
    app.run(host="0.0.0.0", port=port, debug=debug)
