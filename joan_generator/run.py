import os
import re
import json
import logging
import requests
from flask import Flask, render_template, request, send_file, Response, jsonify
from pathlib import Path
import io
from datetime import datetime, timedelta

# Configure logging **before** first use
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# Application Initialization
logger.info("Initializing Joan 6 Generator app...")
app = Flask(__name__)
app.config['JSON_AS_ASCII'] = False

def safe_int(val, default):
    if val is None:
        return default
    s = str(val).strip().lower()
    if not s or s == 'undefined' or s == 'none':
        return default
    try:
        # Handle cases like "12.0" or "undefined"
        return int(float(s))
    except (ValueError, TypeError):
        return default

# -------------------------------------------------------------------------
# API AND TOKEN CONFIGURATION
# -------------------------------------------------------------------------
SUPERVISOR_URL = "http://supervisor"
S6_ENV_DIR = Path('/run/s6/container_environment')
MANUAL_TOKEN = None
ACTIVE_HA_PROFILE = None
TOKEN = None
API_URL = "http://supervisor/core/api"
TOKEN_SOURCE = "Brak"


def _read_s6_env(name):
    """Read Supervisor-injected secrets (available when init:true / s6-overlay)."""
    path = S6_ENV_DIR / name
    if path.is_file():
        try:
            value = path.read_text(encoding='utf-8').strip()
            if value:
                return value
        except OSError as e:
            logger.debug("Cannot read %s: %s", path, e)
    return None


def resolve_supervisor_token():
    """Resolve HA/Supervisor API token from process env or s6 files."""
    for name in ('SUPERVISOR_TOKEN', 'HASSIO_TOKEN'):
        value = (os.environ.get(name) or '').strip()
        if not value:
            value = _read_s6_env(name) or ''
        if value:
            os.environ[name] = value
            return value
    return None


SUPERVISOR_TOKEN = resolve_supervisor_token()

# AppDaemon Slug (configurable: env APPDAEMON_SLUG or options.json)
APPDAEMON_SLUG = os.environ.get('APPDAEMON_SLUG', "a0d7b954_appdaemon")

# Tymczasowy plik podglądu w przeglądarce (nie nadpisuje docelowego .dash)
JOAN_LIVE_PREVIEW_FILENAME = "_joan_live_preview.dash"
JOAN_LIVE_PREVIEW_SLUG = "_joan_live_preview"


def _load_addon_options():
    global MANUAL_TOKEN, APPDAEMON_SLUG
    try:
        options_path = '/data/options.json'
        if not os.path.exists(options_path):
            return
        with open(options_path, 'r') as f:
            options = json.load(f)
        manual = (options.get('manual_token') or '').strip()
        if manual and len(manual) > 10:
            MANUAL_TOKEN = manual
        opt_slug = options.get('appdaemon_slug')
        if opt_slug:
            APPDAEMON_SLUG = str(opt_slug).strip()
    except Exception as e:
        logger.info(f"Could not read options file: {e}")


_load_addon_options()


def get_ha_auth_profiles():
    """
    Ordered auth profiles for Home Assistant REST API.
    Supervisor token + proxy URL must be first inside the add-on container.
    Manual LLAT is only a fallback (e.g. dev outside Supervisor).
    """
    global SUPERVISOR_TOKEN
    if not SUPERVISOR_TOKEN:
        SUPERVISOR_TOKEN = resolve_supervisor_token()

    profiles = []
    if SUPERVISOR_TOKEN:
        profiles.append({
            'token': SUPERVISOR_TOKEN,
            'base': 'http://supervisor/core/api',
            'source': 'Supervisor',
        })
    if MANUAL_TOKEN:
        profiles.append({
            'token': MANUAL_TOKEN,
            'base': 'http://homeassistant:8123/api',
            'source': 'Manual (Konfiguracja)',
        })
    return profiles


def _set_active_ha_profile(profile):
    global ACTIVE_HA_PROFILE, TOKEN, API_URL, TOKEN_SOURCE
    ACTIVE_HA_PROFILE = profile
    TOKEN = profile['token']
    API_URL = profile['base']
    TOKEN_SOURCE = profile['source']


def ha_api_request(method, endpoint, json_body=None, timeout=15):
    """
    Call Home Assistant API; try each auth profile until one succeeds.
    Returns (response, profile) or (last_response, None).
    """
    endpoint = endpoint.lstrip('/')
    profiles = get_ha_auth_profiles()
    if not profiles:
        return None, None

    headers_base = {"Content-Type": "application/json"}
    last_response = None

    for profile in profiles:
        url = f"{profile['base'].rstrip('/')}/{endpoint}"
        headers = {**headers_base, "Authorization": f"Bearer {profile['token']}"}
        try:
            if method.upper() == 'GET':
                response = requests.get(url, headers=headers, timeout=timeout)
            elif method.upper() == 'POST':
                response = requests.post(url, headers=headers, json=json_body, timeout=timeout)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")
            last_response = response
            if response.status_code == 200:
                _set_active_ha_profile(profile)
                return response, profile
            logger.debug(
                "HA API %s %s via %s -> %s",
                method, endpoint, profile['source'], response.status_code,
            )
        except Exception as e:
            logger.warning("HA API %s %s via %s failed: %s", method, endpoint, profile['source'], e)

    if profiles:
        _set_active_ha_profile(profiles[0])
    return last_response, None


# Defaults for UI / AppDaemon bridge (updated after first successful HA call)
_profiles = get_ha_auth_profiles()
if _profiles:
    _set_active_ha_profile(_profiles[0])
else:
    TOKEN = None
    API_URL = "http://supervisor/core/api"
    TOKEN_SOURCE = "Brak"
    logger.warning("No Home Assistant API token — entity list will be empty.")

if SUPERVISOR_TOKEN:
    logger.info("Supervisor token ready for Home Assistant API.")
    if MANUAL_TOKEN:
        logger.info("manual_token w konfiguracji jest ignorowany — używany jest token Supervisora.")
elif MANUAL_TOKEN:
    logger.warning(
        "Brak SUPERVISOR_TOKEN — używany manual_token (często 403 w add-onie; wyczyść pole w konfiguracji)."
    )
else:
    logger.warning("Brak tokena API — podgląd stanów encji nie zadziała.")

# -------------------------------------------------------------------------
# FETCHING DATA FROM HOME ASSISTANT
# -------------------------------------------------------------------------
def _fetch_areas_from_registry():
    """Load area names from HA area registry (UTF-8 safe). Returns None if unavailable."""
    response, profile = ha_api_request('GET', 'config/area_registry/list', timeout=15)
    if response is None or response.status_code != 200:
        return None
    try:
        areas = []
        for area in response.json():
            area_id = area.get('area_id')
            if area_id:
                areas.append({'id': area_id, 'name': area.get('name') or area_id})
        logger.info(
            "Loaded %s areas via area_registry API (%s)",
            len(areas),
            profile['source'] if profile else '?',
        )
        return areas
    except (ValueError, TypeError) as e:
        logger.warning("area_registry parse error: %s", e)
        return None


def _fetch_entity_area_map_from_registry():
    """Load entity -> area mapping from HA entity registry. Returns None if unavailable."""
    response, profile = ha_api_request('GET', 'config/entity_registry/list', timeout=20)
    if response is None or response.status_code != 200:
        return None
    try:
        entity_map = {}
        for ent in response.json():
            eid = ent.get('entity_id')
            if eid:
                entity_map[eid] = ent.get('area_id') or ''
        logger.info(
            "Loaded entity-area map for %s entities via entity_registry API (%s)",
            len(entity_map),
            profile['source'] if profile else '?',
        )
        return entity_map
    except (ValueError, TypeError) as e:
        logger.warning("entity_registry parse error: %s", e)
        return None


def _get_ha_areas_and_map_template():
    """HA Template API with | tojson — UTF-8 safe (Polish chars) and JSON escaping."""
    template_str = """
{
    "areas": [
        {%- for area_id in areas() %}
        {
            "id": {{ area_id | tojson }},
            "name": {{ area_name(area_id) | tojson }}
        },
        {%- endfor %}
        null
    ],
    "entity_map": {
        {%- for state in states %}
        {{ state.entity_id | tojson }}: {{ (area_id(state.entity_id) or '') | tojson }},
        {%- endfor %}
        "_end": null
    }
}
"""
    try:
        response, profile = ha_api_request(
            'POST', 'template', json_body={"template": template_str}, timeout=15
        )
        if response is not None and response.status_code == 200:
            result = response.json()
            if result:
                areas = [a for a in result.get('areas', []) if a]
                entity_map = {
                    k: v for k, v in result.get('entity_map', {}).items() if k != "_end"
                }
                logger.info(
                    "Loaded %s areas via template API (%s)",
                    len(areas),
                    profile['source'] if profile else '?',
                )
                return areas, entity_map
        if response is not None:
            logger.warning(
                "Template API failed (%s): %s",
                response.status_code,
                (response.text or "")[:300],
            )
    except Exception as e:
        logger.error("Exception while fetching areas via template: %s", e, exc_info=True)
    return [], {}


def get_ha_areas_and_map():
    """
    Fetches Area Registry and Entity Registry data from Home Assistant.
    Returns:
        areas (list): List of area objects {id, name}
        entity_map (dict): Mapping of entity_id -> area_id
    """
    if not get_ha_auth_profiles():
        return [], {}

    # REST registry endpoints are not available on all HA versions — template is primary.
    areas, entity_map = _get_ha_areas_and_map_template()
    if areas:
        return areas, entity_map

    # Optional fallback for newer HA builds with registry REST API
    reg_areas = _fetch_areas_from_registry()
    reg_map = _fetch_entity_area_map_from_registry()
    if reg_areas:
        return reg_areas, reg_map if reg_map is not None else {}
    return [], reg_map if reg_map is not None else {}

def get_ha_entities():
    if not get_ha_auth_profiles():
        return {'entities': [], 'areas': []}

    areas, entity_area_map = get_ha_areas_and_map()

    try:
        response, profile = ha_api_request('GET', 'states', timeout=20)
        if response is not None and response.status_code == 200:
            data = response.json()
            entities = []
            for state in data:
                attributes = state.get('attributes', {})
                unit = attributes.get('unit_of_measurement', '')
                e_id = state['entity_id']
                area_id_val = entity_area_map.get(e_id)

                entities.append({
                    'id': e_id,
                    'area_id': area_id_val,
                    'state': state['state'],
                    'attributes': {
                        'friendly_name': attributes.get('friendly_name', e_id),
                        'device_class': attributes.get('device_class', ''),
                        'unit_of_measurement': unit,
                    },
                    'unit': unit,
                })
            entities.sort(key=lambda x: x['id'])
            logger.info(
                "Loaded %s entity states via %s",
                len(entities),
                profile['source'] if profile else '?',
            )
            return {'entities': entities, 'areas': areas}
        if response is not None:
            logger.error(
                "Cannot load /states (%s): %s",
                response.status_code,
                (response.text or "")[:300],
            )
    except Exception as e:
        logger.error(f"Exception while fetching entities: {e}", exc_info=True)

    return {'entities': [], 'areas': areas}

# -------------------------------------------------------------------------
# .DASH FILE SAVE FUNCTION
# -------------------------------------------------------------------------
def save_dash_file(filename, content):
    """
    WARNING: In Home Assistant Supervisor, add-ons run in isolated Docker containers.
    Direct saving to another add-on's directory is not possible without specific configuration.
    
    This function informs the user they must save the file manually.
    """
    network_path = f"\\\\[HA_IP]\\addon_configs\\{APPDAEMON_SLUG}\\dashboards\\{filename}"
    unix_path = f"/addon_configs/{APPDAEMON_SLUG}/dashboards/{filename}"
    
    message = (
        f"⚠️ DIRECT SAVE NOT POSSIBLE\n\n"
        f"Home Assistant add-ons run in isolated Docker containers. "
        f"Saving files directly to another add-on's directory is not possible without specific configuration.\n\n"
        f"Save the file manually:\n"
        f"• Via Samba: {network_path}\n"
        f"• Via SSH: {unix_path}\n\n"
        f"Or copy the generated code and save it manually."
    )
    
    print(f"⚠️ {message}")
    return False, message

# -------------------------------------------------------------------------
# APPDAEMON RESTART FUNCTION
# -------------------------------------------------------------------------
def restart_appdaemon_addon():
    """Restarts AppDaemon via Supervisor API (preferred) or HA service call."""
    target_slug = APPDAEMON_SLUG

    if SUPERVISOR_TOKEN:
        url = f"{SUPERVISOR_URL}/addons/{target_slug}/restart"
        headers = {
            "Authorization": f"Bearer {SUPERVISOR_TOKEN}",
            "Content-Type": "application/json",
        }
        print(f"🔄 Restarting via Supervisor API: {url}")
        try:
            response = requests.post(url, headers=headers, timeout=30)
            if response.status_code in [200, 201, 202]:
                return True, "AppDaemon restarted."
            print(f"❌ Supervisor restart: {response.status_code} - {response.text}")
        except Exception as e:
            print(f"❌ Connection exception: {e}")
            return False, str(e)

    if MANUAL_TOKEN:
        url = "http://homeassistant:8123/api/services/hassio/addon_restart"
        headers = {
            "Authorization": f"Bearer {MANUAL_TOKEN}",
            "Content-Type": "application/json",
        }
        payload = {"addon": target_slug}
        print(f"🔄 Restarting via HA service (manual token): {url}")
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            if response.status_code in [200, 201, 202]:
                return True, "AppDaemon restarted."
            return False, f"API Error: {response.status_code} {response.text}"
        except Exception as e:
            return False, str(e)

    return False, "Błąd: Brak tokena API (Supervisor lub manual_token w konfiguracji)."

# -------------------------------------------------------------------------
# CHECK HISTORY COMPONENT
# -------------------------------------------------------------------------
def check_history_active():
    """Checks if the history component is active in Home Assistant config."""
    if not get_ha_auth_profiles():
        return False
    try:
        res, _ = ha_api_request('GET', 'config', timeout=10)
        if res is not None and res.status_code == 200:
            components = res.json().get("components", [])
            return "history" in components
    except Exception as e:
        logger.error(f"Error checking history active: {e}", exc_info=True)
    return False

# -------------------------------------------------------------------------
# APPDAEMON API BRIDGE FUNCTIONS (Direct Save)
# -------------------------------------------------------------------------
def check_appdaemon_bridge():
    """Checks if dash_saver.py script is installed and active in AppDaemon."""
    host = APPDAEMON_SLUG.replace('_', '-')
    paths = ["/api/save_dash", "/api/appdaemon/save_dash"]
    
    for path in paths:
        url = f"http://{host}:5050{path}"
        print(f"🔍 Checking path: {url}")
        try:
            response = requests.get(url, timeout=3)
            if response.status_code in [200, 405]:
                print(f"✅ AppDaemon bridge detected at: {url}")
                # Save working path in global variable for save function
                global ACTIVE_BRIDGE_PATH
                ACTIVE_BRIDGE_PATH = path
                return True
            else:
                print(f"ℹ️ Path {path} returned status: {response.status_code}")
        except Exception as e:
            print(f"❌ Error for path {path}: {e}")
    
    return False

ACTIVE_BRIDGE_PATH = "/api/save_dash" # Fallback

def _probe_appdaemon_endpoint(endpoint_key):
    """
    GET probe for dash_saver endpoints. New script answers with
    '{"status":"success","message":"<name> endpoint is active"}'.
    """
    host = APPDAEMON_SLUG.replace('_', '-')
    headers = {}
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"

    for path in (f"/api/appdaemon/{endpoint_key}", f"/api/{endpoint_key}"):
        url = f"http://{host}:5050{path}"
        try:
            response = requests.get(url, headers=headers or None, timeout=3)
            if response.status_code != 200:
                continue
            try:
                data = response.json()
            except ValueError:
                continue
            if data.get("status") != "success":
                continue
            msg = str(data.get("message", "")).lower()
            key = endpoint_key.lower().replace("_", "")
            if "active" in msg and key in msg.replace("_", ""):
                return True
            if endpoint_key == "save_dash" and "dashsaver" in msg.replace(" ", ""):
                return True
        except Exception as e:
            logger.debug("Probe %s failed: %s", path, e)
    return False

def get_dash_saver_capabilities():
    """Detect installed dash_saver features (delete/rename need script >= 1.6)."""
    bridge = check_appdaemon_bridge()
    caps = {
        "bridge": bridge,
        "delete_file": False,
        "rename_file": False,
        "file_ops_ready": False,
        "needs_dash_saver_update": False,
        "needs_install": not bridge,
    }
    if not bridge:
        return caps

    caps["delete_file"] = _probe_appdaemon_endpoint("delete_file")
    caps["rename_file"] = _probe_appdaemon_endpoint("rename_file")
    caps["file_ops_ready"] = caps["delete_file"] and caps["rename_file"]
    caps["needs_dash_saver_update"] = not caps["file_ops_ready"]
    return caps

def save_dash_file_via_api(filename, content):
    """Sends file to AppDaemon by trying various possible API paths."""
    # Napraw uszkodzone linie dashboard: (np. dashboard: icon_active: mdi-...) przed zapisem
    content = repair_dash_yaml(content, 'joan_13_pro' if '[188, 192]' in (content or '') else 'joan_6')
    host = APPDAEMON_SLUG.replace('_', '-')
    paths = ["/api/appdaemon/save_dash", "/api/save_dash"]
    
    last_error = "Nieznany błąd"
    for path in paths:
        url = f"http://{host}:5050{path}"
        payload = {"filename": filename, "content": content}
        
        print(f"🚀 Attempting to upload dashboard to: {url}")
        try:
            headers = {"Content-Type": "application/json"}
            if TOKEN:
                 headers["Authorization"] = f"Bearer {TOKEN}"

            response = requests.post(url, json=payload, headers=headers, timeout=10)
            
            if response.status_code == 200:
                return True, f"Success: File {filename} saved!"
            
            last_error = f"Status {response.status_code}: {response.text}"
            print(f"ℹ️ Path {path} did not work ({last_error})")
        except Exception as e:
            last_error = str(e)
            print(f"❌ Connection error with path {path}: {e}")

    return False, f"Save error (tried all paths). Last error: {last_error}"

def list_dashboards_via_api():
    """Lists available dashboard files from AppDaemon via dash_saver bridge."""
    host = APPDAEMON_SLUG.replace('_', '-')
    paths = ["/api/appdaemon/list_dir", "/api/list_dir"]
    
    for path in paths:
        url = f"http://{host}:5050{path}"
        payload = {"path": "dashboards"}
        
        print(f"📂 Attempting to list dashboards from: {url}")
        try:
            headers = {"Content-Type": "application/json"}
            if TOKEN:
                headers["Authorization"] = f"Bearer {TOKEN}"

            response = requests.post(url, json=payload, headers=headers, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                if data.get("status") == "success":
                    # Filter only .dash files
                    items = data.get("items", [])
                    dash_files = [item for item in items if item.get("name", "").endswith(".dash")]
                    return True, _filter_user_visible_dashboards(dash_files)
            
            print(f"ℹ️ Path {path} returned: {response.status_code}")
        except Exception as e:
            print(f"❌ Error listing dashboards from {path}: {e}")
    
    return False, []

def read_dashboard_via_api(filename):
    """Reads dashboard content from AppDaemon via dash_saver bridge."""
    host = APPDAEMON_SLUG.replace('_', '-')
    paths = ["/api/appdaemon/read_file", "/api/read_file"]
    
    for path in paths:
        url = f"http://{host}:5050{path}"
        payload = {"path": f"dashboards/{filename}"}
        
        print(f"📖 Attempting to read dashboard from: {url}")
        try:
            headers = {"Content-Type": "application/json"}
            if TOKEN:
                headers["Authorization"] = f"Bearer {TOKEN}"

            response = requests.post(url, json=payload, headers=headers, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                if data.get("status") == "success":
                    return True, data.get("content", "")
            
            print(f"ℹ️ Path {path} returned: {response.status_code}")
        except Exception as e:
            print(f"❌ Error reading dashboard from {path}: {e}")
    
    return False, ""

def _appdaemon_bridge_post(path_candidates, payload, timeout=10):
    """POST JSON to AppDaemon dash_saver endpoints; tries multiple URL paths."""
    host = APPDAEMON_SLUG.replace('_', '-')
    last_error = "Nieznany błąd"
    headers = {"Content-Type": "application/json"}
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"

    for path in path_candidates:
        url = f"http://{host}:5050{path}"
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=timeout)
            if response.status_code == 200:
                try:
                    data = response.json()
                except ValueError:
                    data = {"status": "success", "message": response.text}
                if data.get("status") == "success":
                    return True, data
                last_error = data.get("message", response.text)
            else:
                last_error = f"Status {response.status_code}: {response.text}"
        except Exception as e:
            last_error = str(e)
            logger.warning("AppDaemon bridge %s failed: %s", path, e)

    return False, {"status": "error", "message": last_error}

def _normalize_dash_filename(name):
    """Basename only, must end with .dash."""
    if not name:
        return None
    base = os.path.basename(str(name).strip().replace("\\", "/"))
    if not base or ".." in base or "/" in base:
        return None
    if not base.lower().endswith(".dash"):
        base = f"{base}.dash"
    return base

def _title_from_dash_filename(filename):
    """Dashboard title from .dash basename (e.g. salon.dash -> salon)."""
    fn = _normalize_dash_filename(filename)
    if not fn:
        return "JoanDashboard"
    stem = fn[:-5] if fn.lower().endswith(".dash") else fn
    return stem.strip() or "JoanDashboard"

def _is_internal_preview_dash(name):
    """True for the temporary browser-preview scratch file (hidden from UI lists)."""
    if not name:
        return False
    base = os.path.basename(str(name).strip().replace("\\", "/"))
    return base.lower() == JOAN_LIVE_PREVIEW_FILENAME.lower()

def _filter_user_visible_dashboards(files):
    if not files:
        return []
    out = []
    for item in files:
        fname = item.get("name", "") if isinstance(item, dict) else str(item)
        if _is_internal_preview_dash(fname):
            continue
        out.append(item)
    return out


def extract_dashboard_title(content, fallback=""):
    """Read top-level title: from a .dash file (preserves Polish characters)."""
    if not content:
        return fallback
    for line in content.splitlines():
        if line.startswith(" ") or line.startswith("\t"):
            continue
        stripped = line.strip()
        if stripped.startswith("title:"):
            title = stripped.split(":", 1)[1].strip()
            if len(title) >= 2 and title[0] == title[-1] and title[0] in ('"', "'"):
                title = title[1:-1]
            return title or fallback
        if stripped.startswith("layout:") or stripped == "-":
            break
    return fallback


def _dashboard_slug_display_name(slug):
    return slug.replace('.dash', '').replace('_', ' ')


def get_dashboard_display_title(dash_item):
    """Human title for a dashboard: from enriched metadata or .dash title: line."""
    if isinstance(dash_item, dict):
        title = (dash_item.get('title') or '').strip()
        if title:
            return title
        fname = dash_item.get('name', '')
    else:
        fname = str(dash_item)
    if not fname:
        return ''
    slug = fname.replace('.dash', '')
    fallback = _dashboard_slug_display_name(slug)
    read_ok, content = read_dashboard_via_api(fname)
    if read_ok:
        return extract_dashboard_title(content, fallback)
    return fallback


def enrich_dashboard_files_with_titles(files):
    """Attach display title from each .dash file (UTF-8, with Polish characters)."""
    enriched = []
    for item in files or []:
        if isinstance(item, dict):
            fname = item.get('name', '')
            entry = dict(item)
        else:
            fname = str(item)
            entry = {'name': fname}
        if not fname:
            continue
        slug = fname.replace('.dash', '')
        fallback = _dashboard_slug_display_name(slug)
        read_ok, content = read_dashboard_via_api(fname)
        entry['title'] = extract_dashboard_title(content, fallback) if read_ok else fallback
        enriched.append(entry)
    return enriched

def _resolve_dashboard_file(title, available_dash_files):
    """Map dashboard title to .dash filename and URL slug (preserve existing file casing)."""
    expected_slug = title.lower().replace(" ", "_").replace("ą", "a").replace("ć", "c").replace("ę", "e").replace("ł", "l").replace("ń", "n").replace("ó", "o").replace("ś", "s").replace("ź", "z").replace("ż", "z")
    expected_filename = expected_slug + ".dash"
    dashboard_filename = expected_filename
    dashboard_slug = expected_slug
    for f in available_dash_files or []:
        fname = f.get('name', '') if isinstance(f, dict) else str(f)
        if fname.lower() == expected_filename.lower():
            dashboard_filename = fname
            dashboard_slug = fname.replace('.dash', '')
            break
    return dashboard_filename, dashboard_slug

def _is_joan_dashboard_header_comment(line):
    """Generator header comment — removed when title/file is renamed (stale name)."""
    return line.strip().lower().startswith("# joan dashboard:")

def _update_yaml_dashboard_title(content, new_title):
    """Replace top-level title: line; drop outdated '# Joan Dashboard: …' header comments."""
    if not content or not new_title:
        return content
    lines = [ln for ln in content.split("\n") if not _is_joan_dashboard_header_comment(ln)]
    replaced = False
    for i, line in enumerate(lines):
        if line.startswith(" ") or line.startswith("\t"):
            continue
        stripped = line.strip()
        if stripped.startswith("title:"):
            lines[i] = f"title: {new_title}"
            replaced = True
            break
        if stripped.startswith("layout:") or stripped.startswith("-"):
            break
    if not replaced:
        lines.insert(0, f"title: {new_title}")
    return "\n".join(lines)

def _suggest_duplicate_filename(filename, existing_names):
    """Pick a free name: foo.dash -> foo_copy.dash, foo_copy2.dash, ..."""
    stem = filename[:-5] if filename.lower().endswith(".dash") else filename
    lower_set = {n.lower() for n in existing_names}
    candidate = f"{stem}_copy.dash"
    if candidate.lower() not in lower_set:
        return candidate
    n = 2
    while True:
        candidate = f"{stem}_copy{n}.dash"
        if candidate.lower() not in lower_set:
            return candidate
        n += 1
        if n > 999:
            return f"{stem}_copy_extra.dash"

def _ensure_unique_dash_filename(filename, existing_names):
    """Return filename if free, otherwise foo_copy.dash / foo_copy2.dash …"""
    filename = _normalize_dash_filename(filename)
    if not filename:
        return None
    lower_set = {n.lower() for n in (existing_names or [])}
    if filename.lower() not in lower_set:
        return filename
    return _suggest_duplicate_filename(filename, existing_names)

def delete_dashboard_via_api(filename):
    filename = _normalize_dash_filename(filename)
    if not filename:
        return False, "Nieprawidłowa nazwa pliku"
    ok, data = _appdaemon_bridge_post(
        ["/api/appdaemon/delete_file", "/api/delete_file"],
        {"path": f"dashboards/{filename}"},
    )
    if ok:
        return True, data.get("message", f"Usunięto {filename}")
    return False, data.get("message", "Usuwanie nie powiodło się")

def rename_dashboard_via_api(old_filename, new_filename):
    old_filename = _normalize_dash_filename(old_filename)
    new_filename = _normalize_dash_filename(new_filename)
    if not old_filename or not new_filename:
        return False, "Nieprawidłowa nazwa pliku", None
    if old_filename.lower() == new_filename.lower():
        return False, "Nowa nazwa jest taka sama jak stara", None

    new_title = _title_from_dash_filename(new_filename)
    read_ok, content = read_dashboard_via_api(old_filename)

    if read_ok and content:
        content = _update_yaml_dashboard_title(content, new_title)
        save_ok, msg = save_dash_file_via_api(new_filename, content)
        if not save_ok:
            return False, msg, None
        if old_filename.lower() != new_filename.lower():
            delete_dashboard_via_api(old_filename)
        return True, f"Zmieniono na {new_filename} (title: {new_title})", new_title

    ok, data = _appdaemon_bridge_post(
        ["/api/appdaemon/rename_file", "/api/rename_file"],
        {"path": f"dashboards/{old_filename}", "new_filename": new_filename},
    )
    if not ok:
        return False, data.get("message", "Zmiana nazwy nie powiodła się"), None

    read_ok, content = read_dashboard_via_api(new_filename)
    if read_ok and content:
        content = _update_yaml_dashboard_title(content, new_title)
        save_dash_file_via_api(new_filename, content)
    return True, data.get("message", f"Zmieniono nazwę na {new_filename}"), new_title

def duplicate_dashboard_via_api(filename, new_title=None):
    filename = _normalize_dash_filename(filename)
    if not filename:
        return False, "Nieprawidłowa nazwa pliku", None, None

    list_ok, files = list_dashboards_via_api()
    existing = []
    if list_ok:
        existing = [f.get("name", "") for f in files if f.get("name")]

    read_ok, content = read_dashboard_via_api(filename)
    if not read_ok:
        return False, f"Nie można odczytać pliku: {filename}", None, None

    title_clean = (str(new_title).strip() if new_title is not None else "")
    if title_clean:
        new_name, _ = _resolve_dashboard_file(title_clean, [{"name": n} for n in existing])
        new_name = _ensure_unique_dash_filename(new_name, existing)
        new_title = title_clean
    else:
        new_name = _suggest_duplicate_filename(filename, existing)
        new_title = _title_from_dash_filename(new_name)

    content = _update_yaml_dashboard_title(content, new_title)
    save_ok, msg = save_dash_file_via_api(new_name, content)
    if save_ok:
        return True, f"Skopiowano jako {new_name} (title: {new_title})", new_name, new_title
    return False, msg, None, None

# -------------------------------------------------------------------------
# ENTITY FREQUENCY ANALYZER
# -------------------------------------------------------------------------
def get_entity_frequency(entity_id, hours=24):
    """
    Fetches entity state history for the last X hours and calculates update frequency.
    Returns: {'changes_per_hour': float, 'total_changes': int, 'level': 'ok'|'warning'|'danger'}
    """
    if not get_ha_auth_profiles():
        return {'error': 'Brak tokena API', 'changes_per_hour': 0, 'total_changes': 0, 'level': 'unknown'}

    from datetime import datetime, timedelta

    end_time = datetime.utcnow()
    start_time = end_time - timedelta(hours=hours)
    start_iso = start_time.strftime('%Y-%m-%dT%H:%M:%SZ')

    try:
        endpoint = (
            f"history/period/{start_iso}"
            f"?filter_entity_id={entity_id}&minimal_response"
        )
        response, _ = ha_api_request('GET', endpoint, timeout=20)

        if response is not None and response.status_code == 200:
            data = response.json()
            if data and len(data) > 0 and len(data[0]) > 0:
                history = data[0]
                total_changes = len(history) - 1  # -1 because first entry is initial state
                if total_changes < 0:
                    total_changes = 0
                
                changes_per_hour = total_changes / hours if hours > 0 else 0
                
                # Warning levels (relaxed thresholds)
                # < 10/h = OK
                # 10-60/h = Warning (every 1-6 min)
                # > 60/h = Danger (more frequent than every minute)
                if changes_per_hour > 60:
                    level = 'danger'
                elif changes_per_hour > 10:
                    level = 'warning'
                else:
                    level = 'ok'
                
                return {
                    'entity_id': entity_id,
                    'changes_per_hour': round(changes_per_hour, 2),
                    'total_changes': total_changes,
                    'hours_analyzed': hours,
                    'level': level
                }
            else:
                # No history - new entity or no changes
                return {
                    'entity_id': entity_id,
                    'changes_per_hour': 0,
                    'total_changes': 0,
                    'hours_analyzed': hours,
                    'level': 'ok'
                }
        else:
            code = response.status_code if response is not None else 'no response'
            if code in (401, 403):
                logger.warning("History API auth error for %s: %s", entity_id, code)
                return {
                    'changes_per_hour': 0,
                    'total_changes': 0,
                    'level': 'unknown',
                    'history_unavailable': True,
                }
            logger.warning("History API error for %s: %s", entity_id, code)
            return {
                'changes_per_hour': 0,
                'total_changes': 0,
                'level': 'unknown',
                'history_unavailable': True,
            }
    except Exception as e:
        print(f"❌ Exception during frequency analysis: {e}")
        return {'error': str(e), 'changes_per_hour': 0, 'total_changes': 0, 'level': 'unknown'}



# 3. STYLES (E-INK OPTIMIZED & TWEAKED)
# -------------------------------------------------------------------------
STYLE_TITLE = "color: #000000 !important; font-size: 20px; font-weight: 700; text-align: center; padding-top: 5px; width: 100%; font-family: 'Roboto', 'Arial Black', sans-serif"
STYLE_WIDGET = "color: #000000 !important; background-color: #FFFFFF !important"
STYLE_TEXT = "color: #000000 !important; font-weight: 700 !important"
STYLE_VALUE_TEMPLATE = "color: #000000 !important; font-size: {px}px !important; font-weight: 700 !important; padding-top: 60px !important; line-height: 1.1 !important; display: inline-block !important"
STYLE_GAUGE_VALUE = "color: #000000 !important; font-size: 30px !important; font-weight: 700 !important; line-height: 1.1 !important; display: inline-block !important"
STYLE_UNIT = "color: #000000 !important; padding-top: 60px !important; display: inline-block !important"
STYLE_ICON = "color: #000000 !important"
STYLE_STATE_TEXT = "color: #000000 !important; font-weight: 700 !important; font-size: 16px !important"
STYLE_TITLE2 = "color: #000000 !important; font-size: 16px; font-weight: 700; text-align: center; width: 100%; font-family: 'Roboto', 'Arial Black', sans-serif"
STYLE_TITLE_SMALL = "color: #000000 !important; font-size: 16px; font-weight: 700; text-align: center; padding-top: 5px; width: 100%; font-family: 'Roboto', 'Arial Black', sans-serif"

def build_value_style(size_hint: str, is_small: bool = False, custom_px: str = None) -> str:
    """
    Returns style for value based on hint or custom px.
    """
    if custom_px and str(custom_px).strip():
        try:
            px = int(custom_px)
        except:
            px = 34 if is_small else 54
    elif is_small:
        px = 34
    else:
        px = {
            "normal": 54,
            "medium": 40,
            "small": 32
        }.get(size_hint, 54)
    return STYLE_VALUE_TEMPLATE.format(px=px)

def build_title_style(is_small: bool = False, custom_px: str = None) -> str:
    """
    Returns style for title with custom px if provided.
    """
    base_style = STYLE_TITLE_SMALL if is_small else STYLE_TITLE
    if custom_px and str(custom_px).strip():
        import re
        return re.sub(r'font-size: \d+px', f'font-size: {custom_px}px', base_style)
    return base_style

def pick_auto_size(value_size_hint: str, entity_id: str, entities_map: dict) -> str:
    """
    If hint == 'auto', selects size based on current entity state:
      >10000  -> small (40px)
      >1000   -> medium (48px)
      length <= 3 -> large (110px)
      else    -> normal (54px)
    If number parsing fails, falls back to text length:
      len>9 -> small, len>6 -> medium, len<=3 -> large, otherwise normal.
    """
    if value_size_hint != "auto":
        return value_size_hint

    ent = entities_map.get(entity_id)
    if ent:
        raw = str(ent.get("state", "")).replace(",", ".").strip()
        length = len(raw)
        try:
            val = float(raw)
            if abs(val) > 10000:
                return "small"
            if abs(val) > 1000:
                return "medium"
            if length <= 3:
                return "large"
            return "normal"
        except Exception:
            pass
        if length > 9:
            return "small"
        if length > 6:
            return "medium"
        if length <= 3:
            return "large"
    return "normal"

# ICON FORMAT NORMALIZATION
# -------------------------------------------------------------------------
def normalize_icon_format(icon_name):
    if icon_name is None:
        return None
    icon_name = str(icon_name).strip()
    if not icon_name or icon_name.lower() in ('0', 'false', 'null', 'none'):
        return None
    if icon_name.startswith('mdi:'):
        return 'mdi-' + icon_name[4:]
    if icon_name.startswith('mdi-'):
        return icon_name
    return icon_name


def _nav_dashboard_name(widget, w_id):
    """Navigate target dashboard — fallback gdy import zostawił puste dash."""
    dash = (widget.get('dash') or '').strip()
    if dash:
        return dash
    if w_id.startswith('navigate.'):
        return w_id.replace('navigate.', '', 1)
    return w_id


def _get_custom_def(custom_defs, w_id):
    if not custom_defs or not w_id:
        return None
    if w_id in custom_defs:
        return custom_defs[w_id]
    w_lower = w_id.lower()
    for key, body in custom_defs.items():
        if key.lower() == w_lower:
            return body
    return None


def _normalize_def_lines(lines):
    """Flatten imported widget lines to a single 2-space YAML indent."""
    out = []
    for line in lines:
        s = line.strip()
        if s:
            out.append(f"  {s}")
    return out


def _upsert_def_line(lines, key, value):
    """Replace or append a single key: value line in an imported widget definition."""
    if not value:
        return lines
    prefix = f"{key}:"
    out = []
    replaced = False
    for line in lines:
        if line.strip().startswith(prefix):
            out.append(f"  {key}: {value}")
            replaced = True
        else:
            out.append(line)
    if not replaced:
        out.append(f"  {key}: {value}")
    return out


def _patch_imported_widget_def(def_text, widget_meta):
    """
    Keep imported widget YAML in sync with layout metadata.
    Ensures custom icons work (use_hass_icon: 0) and UI/icon edits are reflected.
    """
    w_type = widget_meta.get('type', '')
    lines = [l for l in def_text.split('\n') if l.strip()]

    if w_type == 'navigate':
        nav_icon = normalize_icon_format(widget_meta.get('icon'))
        if nav_icon:
            lines = _upsert_def_line(lines, 'icon_active', nav_icon)
            lines = _upsert_def_line(lines, 'icon_inactive', nav_icon)
        drop_keys = ('use_hass_icon:', 'icon_on:', 'icon_off:', 'icon:', 'entity:')
        lines = [l for l in lines if not l.strip().startswith(drop_keys)]
        return _normalize_def_lines(lines)

    icon_on = normalize_icon_format(widget_meta.get('icon_on'))
    icon_off = normalize_icon_format(widget_meta.get('icon_off'))
    icon = normalize_icon_format(widget_meta.get('icon'))

    if icon_on:
        lines = _upsert_def_line(lines, 'icon_on', icon_on)
    if icon_off:
        lines = _upsert_def_line(lines, 'icon_off', icon_off)
    if icon and not icon_on:
        lines = _upsert_def_line(lines, 'icon', icon)

    has_custom_icon = bool(icon_on or icon_off or icon) or any(
        s.strip().startswith(('icon_on:', 'icon_off:', 'icon:', 'icon_active:', 'icon_inactive:'))
        for s in lines
    )
    if not has_custom_icon:
        return _normalize_def_lines(lines)

    lines = [l for l in lines if not l.strip().startswith('use_hass_icon:')]
    patched = []
    inserted = False
    for line in lines:
        s = line.strip()
        patched.append(f"  {s}")
        if not inserted and s.startswith('entity:'):
            patched.append("  use_hass_icon: 0")
            inserted = True
    if not inserted:
        patched.insert(1 if patched else 0, "  use_hass_icon: 0")
    return patched

# YAML GENERATION LOGIC
# -------------------------------------------------------------------------
def get_real_entity(w_id: str) -> str:
    """
    Removes _copyX suffix from widget ID to get real entity ID.
    E.g. sensor.temp_copy1 -> sensor.temp
    """
    import re
    return re.sub(r'_copy\d+$', '', w_id)

def repair_dash_yaml(content, device_profile='joan_13_pro'):
    """
    Normalize legacy .dash files for HADashboard:
    - use_hass_icon: 0
    - flat 2-space widget properties
    - icon font-size for Joan
    - naprawa uszkodzonych linii dashboard: w navigate
    """
    import re
    if not content:
        return content

    is_pro = device_profile == 'joan_13_pro'
    icon_px = '90' if is_pro else '54'
    content = re.sub(r'use_hass_icon:\s*1\b', 'use_hass_icon: 0', content)

    PROP = re.compile(
        r'^(widget_type|entity|title2?|dashboard|icon|icon_on|icon_off|icon_active|icon_inactive|'
        r'state_text|state_text_style|value_style|title_style|text_style|widget_style|'
        r'icon_style\w*|icon_active_style|icon_inactive_style|unit_style|precision|use_hass_icon|'
        r'low_speed|medium_speed|high_speed|step|truncate_name|speed[123]_|post_service|enabled|momentary|units|min|max|warn)\s*:'
    )
    WIDGET_KEY = re.compile(r'^[\w.-]+\.[\w.-]+:\s*$')
    STATE_MAP_LINE = re.compile(r'^["\']')

    out = []
    zone = 'head'
    current_entity = ''

    for line in content.split('\n'):
        s = line.strip()
        if '# WIDGET DEFINITIONS' in s:
            zone = 'widgets'
            out.append(s)
            continue
        if zone == 'widgets' and s.startswith('# AUTO NAV'):
            zone = 'tail'
            out.append(s)
            continue

        if not s:
            out.append('')
            continue
        if s.startswith('#'):
            out.append(s)
            continue

        if zone != 'widgets':
            out.append(line.rstrip())
            continue

        if WIDGET_KEY.match(s):
            current_entity = s[:-1]
            out.append(s)
            continue

        if STATE_MAP_LINE.match(s) or (s.startswith('"') and '":' in s):
            out.append(f'    {s}')
            continue

        if PROP.match(s):
            fixed = s
            # Napraw uszkodzone dashboard: icon_active: ... (doklejona następna linia)
            if fixed.startswith('dashboard:'):
                val = fixed[len('dashboard:'):].strip()
                if ':' in val:
                    # Uszkodzone — pobierz nazwę z current_entity
                    nav_name = current_entity.replace('navigate.', '').strip()
                    fixed = f'dashboard: {nav_name}' if nav_name else 'dashboard: main'
            if 'icon' in fixed and 'style' in fixed and 'font-size' not in fixed and 'display: none' not in fixed:
                if fixed.endswith('"'):
                    fixed = fixed[:-1].rstrip(';') + f'; font-size: {icon_px}px;"'
            if fixed.startswith('entity:'):
                current_entity = fixed.split(':', 1)[1].strip()
            out.append(f'  {fixed}')
            continue

        out.append(f'  {s}')

    return '\n'.join(out)


def generate_joan_dash_yaml(rows, title, grid_params, lang_code, custom_defs, entities_map, device_profile='joan_6', auto_nav_bar=False, available_dash_files=None):
    if available_dash_files is None:
        available_dash_files = []

    TRANS = {
        'pl': {
            'on': 'WŁĄCZONE', 'off': 'WYŁĄCZONE',
            'open': 'OTWARTE', 'closed': 'ZAMKNIĘTE',
            'opening': 'OTWIERANIE', 'closing': 'ZAMYKANIE',
            'locked': 'ZAMKNIĘTE', 'unlocked': 'OTWARTE',
            'home': 'W DOMU', 'not_home': 'POZA',
            'cover_open': 'OTWARTA', 'cover_closed': 'ZAMKNIĘTA'
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

    # device profile settings
    is_pro = (device_profile == 'joan_13_pro')

    if is_pro:
        style_title = "color: #000000 !important; font-size: 32px; font-weight: 700; text-align: center; padding-top: 5px; width: 100%; font-family: 'Roboto', 'Arial Black', sans-serif"
        style_title2 = "color: #000000 !important; font-size: 24px; font-weight: 700; text-align: center; width: 100%; font-family: 'Roboto', 'Arial Black', sans-serif"
        style_title_small = "color: #000000 !important; font-size: 24px; font-weight: 700; text-align: center; padding-top: 5px; width: 100%; font-family: 'Roboto', 'Arial Black', sans-serif"
        
        style_widget = "color: #000000 !important; background-color: #FFFFFF !important"
        style_text = "color: #000000 !important; font-weight: 700 !important; font-size: 28px !important"
        style_state_text = "color: #000000 !important; font-weight: 700 !important; font-size: 28px !important"
        
        style_gauge_val = "color: #000000 !important; font-size: 54px !important; font-weight: 700 !important; line-height: 1.1 !important; display: inline-block !important"
        style_unit = "color: #000000 !important; padding-top: 90px !important; display: inline-block !important; font-size: 30px;"
        style_icon = "color: #000000 !important; font-size: 90px;"
    else:
        style_title = "color: #000000 !important; font-size: 20px; font-weight: 700; text-align: center; padding-top: 5px; width: 100%; font-family: 'Roboto', 'Arial Black', sans-serif"
        style_title2 = "color: #000000 !important; font-size: 16px; font-weight: 700; text-align: center; width: 100%; font-family: 'Roboto', 'Arial Black', sans-serif"
        style_title_small = "color: #000000 !important; font-size: 16px; font-weight: 700; text-align: center; padding-top: 5px; width: 100%; font-family: 'Roboto', 'Arial Black', sans-serif"
        
        style_widget = "color: #000000 !important; background-color: #FFFFFF !important"
        style_text = "color: #000000 !important; font-weight: 700 !important"
        style_state_text = "color: #000000 !important; font-weight: 700 !important; font-size: 16px !important"
        
        style_gauge_val = "color: #000000 !important; font-size: 30px !important; font-weight: 700 !important; line-height: 1.1 !important; display: inline-block !important"
        style_unit = "color: #000000 !important; padding-top: 60px !important; display: inline-block !important"
        style_icon = "color: #000000 !important"

    # dynamic value/title helpers inside
    def build_val_style_local(size_hint, is_small_w, custom_px):
        if custom_px and str(custom_px).strip():
            try:
                px = int(custom_px)
                if not is_pro and px in [110, 90, 65, 60, 50]:
                    px = 34 if is_small_w else 54
            except:
                px = (60 if is_pro else 34) if is_small_w else (90 if is_pro else 54)
        else:
            if size_hint == 'small': px = 50 if is_pro else 34
            elif size_hint == 'large': px = 110 if is_pro else 64
            else: px = 90 if is_pro else 54
        tmpl = f"color: #000000 !important; font-size: {{px}}px !important; font-weight: 700 !important; padding-top: 60px !important; line-height: 1.1 !important; display: inline-block !important"
        return tmpl.format(px=px)

    def build_title_style_local(is_small_w, custom_px):
        base_style = style_title_small if is_small_w else style_title
        if custom_px and str(custom_px).strip():
            try:
                px = int(custom_px)
                if not is_pro and px in [40, 32, 24]:
                    return base_style
            except:
                pass
            import re
            return re.sub(r'font-size: \d+px', f'font-size: {custom_px}px', base_style)
        return base_style

    def _parse_int_or_none(value):
        try:
            text = str(value).strip()
            if text == "":
                return None
            return int(text)
        except Exception:
            return None

    def _icon_vertical_shift_px(offset_px, gap_px):
        """HADashboard reliably applies margin-top on icons; sum gap + offset like preview."""
        total = 0
        has_any = False
        if offset_px is not None:
            total += offset_px
            has_any = True
        if gap_px is not None:
            total += gap_px
            has_any = True
        return total if has_any else None

    def build_icon_style_local(custom_px, offset_px=None, gap_px=None, suffix=""):
        if custom_px and str(custom_px).strip():
            try:
                px = int(custom_px)
                base = f"color: #000000 !important; font-size: {px}px;"
            except:
                base = style_icon
        else:
            base = style_icon
        shift_px = _icon_vertical_shift_px(offset_px, gap_px)
        if shift_px is not None:
            base = base.rstrip(';') + f"; margin-top: {shift_px}px !important;"
        if suffix:
            return base.rstrip(';') + suffix
        return base

    output = []
    output.append(f"# Joan Dashboard: {title}")
    output.append(f"# Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    output.append(f"# Model: {'Joan 13 Pro' if is_pro else 'Joan 6'}")
    output.append("")
    output.append(f"title: {title}")
    dims = "[188, 192]" if is_pro else "[117, 123]"
    margins = "[13, 6]" if is_pro else "[8, 4]"
    output.append(f"widget_dimensions: {dims}")
    output.append(f"widget_size: [{grid_params['def_w']}, {grid_params['def_h']}]")
    output.append(f"widget_margins: {margins}")
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
    output.append(f"  title_style: \"{style_title}\"")
    output.append(f"  title2_style: \"{style_title2}\"")
    output.append(f"  white_text_style: \"{style_text}\"")
    output.append(f"  state_text_style: \"{style_state_text}\"")
    output.append(f"  text_style: \"{style_text}\"")
    output.append(f"  level_style: \"{style_text}\"")
    output.append(f"  unit_style: \"{style_text}\"")
    output.append(f"  value_style: \"{style_text}\"")
    output.append(f"  icon_style_active: \"{style_icon}\"")
    output.append(f"  icon_style_inactive: \"{style_icon}; opacity: 0.5;\"")
    output.append(f"  artist_style: \"{style_text}\"")
    output.append(f"  album_style: \"{style_text}\"")
    output.append(f"  media_title_style: \"{style_text}\"")
    output.append(f"  widget_style: \"{style_widget}\"")
    output.append("skin: simplyred")
    output.append("")

    try:
        processed_widgets = []

        if rows:
            output.append("layout:")
            # Removed automated navigation inject to prevent overriding user layout

            for row in rows:
                if not row:
                    continue
                row_parts = []
                max_h = 1
                for w in row:
                    h = grid_params['def_h']
                    size_str = w.get('size', '')
                    if size_str:
                        import re
                        m = re.search(r'x(\d+)', size_str)
                        if m:
                            h = int(m.group(1))
                    if h > max_h:
                        max_h = h

                    if w['type'] == 'spacer':
                        row_parts.append("spacer")
                        continue

                    widget_id = w['id']
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

                    if not widget_id: continue
                    row_parts.append(widget_id)
                    processed_widgets.append(w)
                if row_parts:
                    output.append(f"  - {', '.join(row_parts)}")
                    for _ in range(max_h - 1):
                        output.append("  -")

            output.append("")
            output.append("# -------------------")
            output.append("# WIDGET DEFINITIONS")
            output.append("# -------------------")
            output.append("")

            seen_ids = set()

            for w in processed_widgets:
                w_id = w.get('id', '')
                if not w_id or w_id in seen_ids:
                    continue
                seen_ids.add(w_id)
                real_entity_id = get_real_entity(w_id)

                # Zachowaj oryginalne definicje z importu (działają na Joan — nie nadpisuj)
                imported_body = _get_custom_def(custom_defs, w_id)
                if imported_body is not None and not w.get('was_edited', False):
                    output.append(f"{w_id}:")
                    dash_fixed = _nav_dashboard_name(w, w_id)
                    w_type_check = ''
                    skip_next_as_dashboard_cont = False
                    for line in imported_body.split('\n'):
                        stripped = line.strip()
                        if not stripped:
                            continue
                        if stripped.startswith('widget_type:'):
                            w_type_check = stripped.split(':', 1)[1].strip()
                        # Napraw uszkodzone lub puste dashboard: w navigate
                        if w_type_check == 'navigate' and stripped.startswith('dashboard:'):
                            val_after = stripped[len('dashboard:'):].strip()
                            # Puste lub uszkodzone (zawiera ':', czyli następna linia była doklejona)
                            if not val_after or ':' in val_after:
                                output.append(f"  dashboard: {dash_fixed}")
                            else:
                                output.append(f"  dashboard: {val_after}")
                        else:
                            output.append(line if line.startswith('  ') else f"  {stripped}")
                    if 'widget_style:' not in imported_body:
                        output.append(f"  widget_style: \"{style_widget}\"")
                    output.append("")
                    continue

                w_type = w['type']
                w_name = w['name']

                # Common property extraction for all widgets
                is_small = (w.get('size') == '(1x1)' or w.get('size') == '(1x2)')
                t_size_custom = w.get('title_size_custom')
                v_size_custom = w.get('value_size_custom')

                w_icon = normalize_icon_format(w.get('icon'))
                i_on = normalize_icon_format(w.get('icon_on'))
                i_off = normalize_icon_format(w.get('icon_off'))
                value_size_hint = w.get('value_size_hint', 'auto')
                # Calculate real hint (auto -> medium/small/normal based on state)
                final_size_hint = pick_auto_size(value_size_hint, real_entity_id, entities_map)

                i_size_custom = w.get('icon_size_custom')
                icon_offset_custom = _parse_int_or_none(w.get('icon_offset_custom'))
                icon_gap_custom = _parse_int_or_none(w.get('icon_gap_custom'))
                dim_inactive_icon = w.get('dim_inactive_icon', True)
                dim_inactive_icon = not (str(dim_inactive_icon).lower() == 'false' or dim_inactive_icon is False)
                _icon = build_icon_style_local(i_size_custom, icon_offset_custom, icon_gap_custom)
                _icon_off = build_icon_style_local(
                    i_size_custom,
                    icon_offset_custom,
                    icon_gap_custom,
                    "; opacity: 0.5 !important;" if dim_inactive_icon else "; opacity: 1 !important;"
                )
                _icon_off3 = build_icon_style_local(i_size_custom, icon_offset_custom, icon_gap_custom, "; opacity: 0.3;")
                
                output.append(f"{w_id}:")

                w_title2 = w.get('title2', '')

                if w_type == 'navigate':
                    dash_name = _nav_dashboard_name(w, w_id)
                    nav_icon = w_icon or 'mdi-arrow-right-circle'
                    output.append(f"  widget_type: navigate")
                    output.append(f"  title: \"{w_name}\"")
                    output.append(f"  dashboard: {dash_name}")
                    output.append(f"  icon_active: {nav_icon}")
                    output.append(f"  icon_inactive: {nav_icon}")
                    output.append(f"  title_style: \"{build_title_style_local(is_small, t_size_custom)}\"")
                    output.append(f"  widget_style: \"{style_widget}\"")
                    output.append(f"  icon_active_style: \"{_icon}\"")
                    output.append(f"  icon_inactive_style: \"{_icon}\"")

                elif w_type == 'switch':
                    output.append(f"  widget_type: switch")
                    output.append(f"  entity: {real_entity_id}")
                    output.append(f"  title: \"{w_name}\"")
                    if w_title2:
                        output.append(f"  title2: \"{w_title2}\"")
                        output.append(f"  title2_style: \"{style_title2}\"")
                    if i_on: output.append(f"  icon_on: {i_on}")
                    if i_off: output.append(f"  icon_off: {i_off}")
                    if w_icon and not i_on:
                        output.append(f"  icon: {w_icon}")
                        output.append(f"  icon_on: {w_icon}")
                        output.append(f"  icon_off: {w_icon}")
                    
                    st_enabled = w.get('state_text_enabled', True)
                    if str(st_enabled).lower() == 'false' or st_enabled is False:
                        output.append(f"  state_text_style: \"display: none !important;\"")
                    else:
                        output.append(f"  state_text: 1")
                    
                    t_size_custom = w.get('title_size_custom')
                    output.append(f"  title_style: \"{build_title_style_local(is_small, t_size_custom)}\"")
                    output.append(f"  widget_style: \"{style_widget}\"")
                    output.append(f"  icon_style_active: \"{_icon}\"")
                    output.append(f"  icon_style_inactive: \"{_icon_off}\"")
                    output.append("  state_map:")
                    output.append(f"    \"on\": \"{dic['on']}\"")
                    output.append(f"    \"off\": \"{dic['off']}\"")

                elif w_type == 'sensor':
                    output.append(f"  widget_type: sensor")
                    output.append(f"  entity: {real_entity_id}")
                    output.append(f"  title: \"{w_name}\"")
                    if w_title2:
                        output.append(f"  title2: \"{w_title2}\"")
                        output.append(f"  title2_style: \"{style_title2}\"")
                    if w_icon:
                        output.append(f"  icon: {w_icon}")

                    output.append(f"  title_style: \"{build_title_style_local(is_small, t_size_custom)}\"")
                    output.append(f"  text_style: \"{style_text}\"")
                    output.append(f"  value_style: \"{build_val_style_local(final_size_hint, is_small, v_size_custom)}\"")
                    output.append(f"  unit_style: \"{style_unit}\"")
                    output.append(f"  widget_style: \"{style_widget}\"")
                    if any(k in w_id for k in ['battery', 'bateria', 'level']):
                        output.append("  precision: 0")
                    else:
                        output.append("  precision: 1")

                elif w_type == 'media_player':
                    output.append(f"  widget_type: media_player")
                    output.append(f"  entity: {real_entity_id}")
                    output.append(f"  title: \"{w_name}\"")

                    if w_icon:
                        output.append(f"  icon: {w_icon}")
                    output.append(f"  title_style: \"{build_title_style_local(is_small, t_size_custom)}\"")
                    output.append(f"  widget_style: \"{style_widget}\"")
                    output.append(f"  icon_style: \"{_icon}\"")
                    output.append("  truncate_name: 20")
                    output.append("  step: 5")

                elif w_type == 'climate':
                    output.append(f"  widget_type: climate")
                    output.append(f"  entity: {real_entity_id}")
                    output.append(f"  title: \"{w_name}\"")

                    output.append(f"  step: 1")
                    output.append(f"  precision: 1")
                    output.append(f"  title_style: \"{build_title_style_local(is_small, t_size_custom)}\"")
                    output.append(f"  widget_style: \"{style_widget}\"")
                    output.append(f"  icon_style_active: \"{_icon}\"")
                    output.append(f"  icon_style_inactive: \"{_icon_off}\"")
                    output.append(f"  icon_style: \"{_icon}\"")

                elif w_type == 'fan':
                    output.append(f"  widget_type: fan")
                    output.append("  low_speed: 33")
                    output.append("  medium_speed: 66")
                    output.append("  high_speed: 100")
                    output.append(f"  entity: {real_entity_id}")
                    output.append(f"  title: \"{w_name}\"")

                    if i_on: output.append(f"  icon_on: {i_on}")
                    if i_off: output.append(f"  icon_off: {i_off}")
                    if w_icon and not i_on:
                        output.append(f"  icon: {w_icon}")
                        output.append(f"  icon_on: {w_icon}")
                        output.append(f"  icon_off: {w_icon}")

                    output.append(f"  title_style: \"{build_title_style_local(is_small, t_size_custom)}\"")
                    output.append(f"  widget_style: \"{style_widget}\"")
                    output.append(f"  container_style: \"{style_widget}\"")
                    output.append(f"  icon_style_active: \"{_icon}\"")
                    output.append(f"  icon_style_inactive: \"{_icon_off3}\"")
                    output.append(f"  speed1_icon_style_active: \"{_icon}\"")
                    output.append(f"  speed1_icon_style_inactive: \"{_icon_off3}\"")
                    output.append(f"  speed2_icon_style_active: \"{_icon}\"")
                    output.append(f"  speed2_icon_style_inactive: \"{_icon_off3}\"")
                    output.append(f"  speed3_icon_style_active: \"{_icon}\"")
                    output.append(f"  speed3_icon_style_inactive: \"{_icon_off3}\"")

                elif w_type == 'scene':
                    output.append(f"  widget_type: scene")
                    output.append(f"  entity: {real_entity_id}")
                    output.append(f"  title: \"{w_name}\"")

                    if w_icon: output.append(f"  icon: {w_icon}")
                    elif i_on: output.append(f"  icon: {i_on}")

                    output.append(f"  title_style: \"{build_title_style_local(is_small, t_size_custom)}\"")
                    output.append(f"  widget_style: \"{style_widget}\"")
                    output.append(f"  icon_style_active: \"{_icon}\"")
                    output.append(f"  icon_style_inactive: \"{_icon}\"")

                elif w_type == 'clock':
                    output.append(f"  widget_type: clock")
                    output.append(f"  time_format: 24hr")
                    output.append(f"  show_seconds: 0")
                    output.append(f"  date_style: \"{style_text}\"")
                    output.append(f"  time_style: \"{build_val_style_local('normal', False, 54)}\"")

                elif w_type == 'gauge':
                    output.append(f"  widget_type: gauge")
                    output.append(f"  entity: {real_entity_id}")
                    output.append(f"  title: \"{w_name}\"")

                    
                    g_min = w.get('min', '').strip()
                    g_max = w.get('max', '').strip()
                    if not g_min: g_min = "0"
                    if not g_max: g_max = "100"

                    output.append(f"  min: {g_min}")
                    output.append(f"  max: {g_max}")
                    output.append(f"  low_color: \"#000000\"")
                    output.append(f"  med_color: \"#000000\"")
                    output.append(f"  high_color: \"#000000\"")
                    output.append(f"  title_style: \"{build_title_style_local(is_small, t_size_custom)}\"")
                    output.append(f"  widget_style: \"{style_widget}\"")
                    output.append(f"  value_style: \"{style_gauge_val}\"")
                    
                    # Try to fetch unit from map
                    unit = ""
                    if w_id in entities_map:
                        unit = entities_map[w_id].get('attributes', {}).get('unit_of_measurement', '') or entities_map[w_id].get('unit', '')
                    
                    if unit:
                        output.append(f"  units: \"{unit}\"")
                        
                    output.append(f"  unit_style: \"{style_unit}\"")

                elif w_type == 'light':
                    output.append(f"  widget_type: light")
                    output.append(f"  entity: {real_entity_id}")
                    output.append(f"  title: \"{w_name}\"")
                    if w_title2:
                        output.append(f"  title2: \"{w_title2}\"")
                        output.append(f"  title2_style: \"{style_title2}\"")

                    if i_on: output.append(f"  icon_on: {i_on}")
                    if i_off: output.append(f"  icon_off: {i_off}")
                    if w_icon and not i_on:
                        output.append(f"  icon: {w_icon}")
                        output.append(f"  icon_on: {w_icon}")
                        output.append(f"  icon_off: {w_icon}")
                    output.append(f"  title_style: \"{style_title}\"")
                    output.append(f"  widget_style: \"{style_widget}\"")
                    output.append(f"  icon_style_inactive: \"{_icon_off}\"")
                    
                    st_enabled = w.get('state_text_enabled', True)
                    if str(st_enabled).lower() == 'false' or st_enabled is False:
                        output.append(f"  state_text_style: \"display: none !important;\"")
                        output.append(f"  value_style: \"display: none !important;\"")
                    else:
                        output.append(f"  state_text: 1")
                        v_size_custom = w.get('value_size_custom')
                        output.append(f"  value_style: \"{build_val_style_local(final_size_hint, is_small, v_size_custom)}\"")
                    output.append("  state_map:")
                    output.append(f"    \"on\": \"{dic['on']}\"")
                    output.append(f"    \"off\": \"{dic['off']}\"")

                elif w_type == 'group':
                    output.append(f"  widget_type: group")
                    output.append(f"  entity: {real_entity_id}")
                    output.append(f"  title: \"{w_name}\"")

                    if i_on: output.append(f"  icon_on: {i_on}")
                    if i_off: output.append(f"  icon_off: {i_off}")
                    if w_icon and not i_on:
                        output.append(f"  icon: {w_icon}")
                        output.append(f"  icon_on: {w_icon}")
                        output.append(f"  icon_off: {w_icon}")
                    t_size_custom = w.get('title_size_custom')
                    output.append(f"  title_style: \"{build_title_style_local(is_small, t_size_custom)}\"")
                    if w_title2:
                        output.append(f"  title2: \"{w_title2}\"")
                        output.append(f"  title2_style: \"{style_title2}\"")
                    output.append(f"  widget_style: \"{style_widget}\"")
                    output.append(f"  icon_style_active: \"{_icon}\"")
                    output.append(f"  icon_style_inactive: \"{_icon_off}\"")
                    
                    st_enabled = w.get('state_text_enabled', True)
                    if str(st_enabled).lower() == 'false' or st_enabled is False:
                        output.append(f"  state_text_style: \"display: none !important;\"")
                        output.append(f"  value_style: \"display: none !important;\"")
                    else:
                        output.append(f"  state_text: 1")
                        v_size_custom = w.get('value_size_custom')
                        output.append(f"  value_style: \"{build_val_style_local(final_size_hint, is_small, v_size_custom)}\"")
                    output.append("  state_map:")
                    output.append(f"    \"on\": \"{dic['on']}\"")
                    output.append(f"    \"off\": \"{dic['off']}\"")

                elif w_type == 'input_boolean':
                    output.append(f"  widget_type: input_boolean")
                    output.append(f"  entity: {real_entity_id}")
                    output.append(f"  title: \"{w_name}\"")

                    if i_on: output.append(f"  icon_on: {i_on}")
                    if i_off: output.append(f"  icon_off: {i_off}")
                    if w_icon and not i_on:
                        output.append(f"  icon: {w_icon}")
                        output.append(f"  icon_on: {w_icon}")
                        output.append(f"  icon_off: {w_icon}")
                    
                    st_enabled = w.get('state_text_enabled', True)
                    if str(st_enabled).lower() == 'false' or st_enabled is False:
                        output.append(f"  state_text_style: \"display: none !important;\"")
                        output.append(f"  value_style: \"display: none !important;\"")
                    else:
                        output.append(f"  state_text: 1")
                        v_size_custom = w.get('value_size_custom')
                        output.append(f"  value_style: \"{build_val_style_local(final_size_hint, is_small, v_size_custom)}\"")
                    output.append(f"  title_style: \"{style_title}\"")
                    output.append(f"  widget_style: \"{style_widget}\"")
                    output.append(f"  icon_style_active: \"{_icon}\"")
                    output.append(f"  icon_style_inactive: \"{_icon_off}\"")
                    output.append("  state_map:")
                    output.append(f"    \"on\": \"{dic['on']}\"")
                    output.append(f"    \"off\": \"{dic['off']}\"")

                elif w_type == 'person':
                    output.append(f"  widget_type: person")
                    output.append(f"  entity: {real_entity_id}")
                    output.append(f"  title: \"{w_name}\"")

                    if i_on: output.append(f"  icon_on: {i_on}")
                    if i_off: output.append(f"  icon_off: {i_off}")
                    if w_icon and not i_on: output.append(f"  icon: {w_icon}")
                    
                    # Robust check for state_text_enabled
                    st_enabled = w.get('state_text_enabled', True)
                    if str(st_enabled).lower() == 'false' or st_enabled is False:
                        output.append(f"  state_text_style: \"display: none !important;\"")
                        output.append(f"  value_style: \"display: none !important;\"")
                    else:
                        output.append(f"  state_text: 1")
                        v_size_custom = w.get('value_size_custom')
                        output.append(f"  value_style: \"{build_val_style_local(final_size_hint, is_small, v_size_custom)}\"")
                    output.append(f"  title_style: \"{style_title}\"")
                    output.append(f"  widget_style: \"{style_widget}\"")
                    output.append(f"  icon_style_active: \"{_icon}\"")
                    output.append(f"  icon_style_inactive: \"{_icon_off}\"")
                    output.append("  state_map:")
                    output.append(f"    \"home\": \"{dic['home']}\"")
                    output.append(f"    \"not_home\": \"{dic['not_home']}\"")

                elif w_type == 'lock':
                    output.append(f"  widget_type: lock")
                    output.append(f"  entity: {real_entity_id}")
                    output.append(f"  title: \"{w_name}\"")

                    if i_on: output.append(f"  icon_on: {i_on}")
                    if i_off: output.append(f"  icon_off: {i_off}")
                    if w_icon and not i_on:
                        output.append(f"  icon: {w_icon}")
                        output.append(f"  icon_on: {w_icon}")
                        output.append(f"  icon_off: {w_icon}")
                    
                    # Robust check for state_text_enabled
                    st_enabled = w.get('state_text_enabled', True)
                    if str(st_enabled).lower() == 'false' or st_enabled is False:
                        output.append(f"  state_text_style: \"display: none !important;\"")
                        output.append(f"  value_style: \"display: none !important;\"")
                    else:
                        output.append(f"  state_text: 1")
                        v_size_custom = w.get('value_size_custom')
                        output.append(f"  value_style: \"{build_val_style_local(final_size_hint, is_small, v_size_custom)}\"")
                    output.append(f"  title_style: \"{style_title}\"")
                    output.append(f"  widget_style: \"{style_widget}\"")
                    output.append(f"  icon_style_active: \"{_icon}\"")
                    output.append(f"  icon_style_inactive: \"{_icon_off}\"")
                    output.append("  state_map:")
                    output.append(f"    \"locked\": \"{dic['locked']}\"")
                    output.append(f"    \"unlocked\": \"{dic['unlocked']}\"")

                elif w_type == 'cover':
                    output.append(f"  widget_type: cover")
                    output.append(f"  entity: {real_entity_id}")
                    output.append(f"  title: \"{w_name}\"")
                    if i_on: output.append(f"  icon_on: {i_on}")
                    if i_off: output.append(f"  icon_off: {i_off}")
                    if w_icon and not i_on:
                        output.append(f"  icon: {w_icon}")
                        output.append(f"  icon_on: {w_icon}")
                        output.append(f"  icon_off: {w_icon}")
                    output.append(f"  title_style: \"{build_title_style_local(is_small, t_size_custom)}\"")
                    output.append(f"  widget_style: \"{style_widget}\"")
                    output.append(f"  icon_style_active: \"{_icon}\"")
                    output.append(f"  icon_style_inactive: \"{_icon_off}\"")
                    
                    st_enabled = w.get('state_text_enabled', True)
                    if str(st_enabled).lower() == 'false' or st_enabled is False:
                        output.append(f"  state_text_style: \"display: none !important;\"")
                        output.append(f"  value_style: \"display: none !important;\"")
                    else:
                        output.append(f"  state_text: 1")

                        output.append(f"  value_style: \"{build_val_style_local(final_size_hint, is_small, v_size_custom)}\"")
                    output.append("  state_map:")
                    output.append(f"    \"open\": \"{dic.get('cover_open', dic['open'])}\"")
                    output.append(f"    \"closed\": \"{dic.get('cover_closed', dic['closed'])}\"")
                    output.append(f"    \"opening\": \"{dic['opening']}\"")
                    output.append(f"    \"closing\": \"{dic['closing']}\"")

                elif w_type == 'reload':
                    output.append(f"  widget_type: reload")
                    output.append(f"  title: \"{w_name}\"")
                    if w_icon: output.append(f"  icon_active: {w_icon}")
                    elif i_on: output.append(f"  icon_active: {i_on}")
                    else: output.append(f"  icon_active: mdi-refresh")
                    output.append(f"  title_style: \"{build_title_style_local(is_small, t_size_custom)}\"")
                    output.append(f"  widget_style: \"{style_widget}\"")
                    output.append(f"  icon_active_style: \"{_icon}\"")
                    output.append(f"  icon_inactive_style: \"{_icon_off}\"")

                elif w_type == 'input_number':
                    output.append(f"  widget_type: input_number")
                    output.append(f"  entity: {real_entity_id}")
                    output.append(f"  title: \"{w_name}\"")

                    
                    # Fetch units from entity if available
                    unit = ""
                    if real_entity_id in entities_map:
                        unit = entities_map[real_entity_id].get('attributes', {}).get('unit_of_measurement', '') or entities_map[real_entity_id].get('unit', '')
                    if unit:
                        output.append(f"  units: \"{unit}\"")
                    
                    output.append(f"  title_style: \"{build_title_style_local(is_small, t_size_custom)}\"")
                    output.append(f"  widget_style: \"{style_widget}\"")
                    output.append(f"  value_style: \"color: #000000 !important; font-size: 24px !important; font-weight: 700 !important;\"")
                    output.append(f"  slider_style: \"background-color: #cccccc !important;\"")
                    output.append(f"  slidercontainer_style: \"background-color: #ffffff !important;\"")

                elif w_type == 'input_slider':
                    output.append(f"  widget_type: input_slider")
                    output.append(f"  entity: {real_entity_id}")
                    output.append(f"  title: \"{w_name}\"")

                    # Fetch units from entity if available
                    unit = ""
                    if real_entity_id in entities_map:
                        unit = entities_map[real_entity_id].get('attributes', {}).get('unit_of_measurement', '') or entities_map[real_entity_id].get('unit', '')
                    if unit:
                        output.append(f"  units: \"{unit}\"")

                    output.append(f"  title_style: \"{build_title_style_local(is_small, t_size_custom)}\"")
                    output.append(f"  widget_style: \"{style_widget}\"")
                    output.append(f"  value_style: \"color: #000000 !important; font-size: 28px !important; font-weight: 700 !important; text-align: center !important;\"")
                    output.append(f"  minvalue_style: \"color: #000000 !important; font-size: 14px !important;\"")
                    output.append(f"  maxvalue_style: \"color: #000000 !important; font-size: 14px !important;\"")
                    output.append(f"  slider_style: \"color: #000000 !important; border: 2px solid #000000 !important;\"")
                    output.append(f"  slidercontainer_style: \"background-color: transparent !important;\"")

                elif w_type == 'input_select':
                    output.append(f"  widget_type: input_select")
                    output.append(f"  entity: {real_entity_id}")
                    output.append(f"  title: \"{w_name}\"")

                    output.append(f"  title_style: \"{build_title_style_local(is_small, t_size_custom)}\"")
                    output.append(f"  widget_style: \"{style_widget}\"")
                    output.append(f"  select_style: \"color: #000000 !important; font-size: 18px !important; background: #ffffff !important; border: 1px solid #999999 !important;\"")
                    output.append(f"  selectcontainer_style: \"background-color: #ffffff !important;\"")



                elif w_type == 'script':
                    # AppDaemon: widget_type script — https://appdaemon.readthedocs.io/.../DASHBOARD_CREATION.html#script
                    output.append(f"  widget_type: script")
                    output.append(f"  entity: {real_entity_id}")
                    output.append(f"  title: \"{w_name}\"")
                    if w_title2:
                        output.append(f"  title2: \"{w_title2}\"")
                        output.append(f"  title2_style: \"{style_title2}\"")
                    if i_on: output.append(f"  icon_on: {i_on}")
                    if i_off: output.append(f"  icon_off: {i_off}")
                    if w_icon and not i_on:
                        output.append(f"  icon_on: {w_icon}")
                        output.append(f"  icon_off: {w_icon}")
                    st_enabled = w.get('state_text_enabled', True)
                    if str(st_enabled).lower() == 'false' or st_enabled is False:
                        output.append(f"  state_text_style: \"display: none !important;\"")
                    else:
                        output.append(f"  state_text: 1")
                        output.append("  state_map:")
                        output.append(f"    \"on\": \"{dic['on']}\"")
                        output.append(f"    \"off\": \"{dic['off']}\"")
                    output.append(f"  title_style: \"{build_title_style_local(is_small, t_size_custom)}\"")
                    output.append(f"  widget_style: \"{style_widget}\"")
                    output.append(f"  icon_style_active: \"{_icon}\"")
                    output.append(f"  icon_style_inactive: \"{_icon_off}\"")

                elif w_type == 'label':
                    output.append(f"  widget_type: label")
                    output.append(f"  text: \"{w_name}\"")
                    if w_title2:
                        output.append(f"  title2: \"{w_title2}\"")
                        output.append(f"  title2_style: \"{style_title2}\"")
                    if w_icon:
                        output.append(f"  icon: {w_icon}")
                    output.append(f"  text_style: \"{build_title_style_local(is_small, t_size_custom)}\"")

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
                    if w_type == 'alarm':
                        ad_type = 'alarm'

                    output.append(f"  widget_type: {ad_type}")
                    output.append(f"  entity: {real_entity_id}")
                    output.append(f"  title: \"{w_name}\"")

                    if i_on: output.append(f"  icon_on: {i_on}")
                    if i_off: output.append(f"  icon_off: {i_off}")

                    if ad_type == 'lock':
                        if i_off: output.append(f"  icon_locked: {i_off}")
                        if i_on: output.append(f"  icon_unlocked: {i_on}")

                    if w_icon and not i_on:
                        output.append(f"  icon: {w_icon}")
                        # Fallback for all generic widgets (script, binary_sensor, etc)
                        output.append(f"  icon_on: {w_icon}")
                        output.append(f"  icon_off: {w_icon}")

                    # Robust check for state_text_enabled
                    st_enabled = w.get('state_text_enabled', True)
                    if str(st_enabled).lower() == 'false' or st_enabled is False:
                        output.append(f"  state_text_style: \"display: none !important;\"")
                        output.append(f"  value_style: \"display: none !important;\"")
                    else:
                        output.append(f"  state_text: 1")
                        v_size_custom = w.get('value_size_custom')
                        output.append(f"  value_style: \"{build_val_style_local(final_size_hint, is_small, v_size_custom)}\"")
                    
                    t_size_custom = w.get('title_size_custom')
                    output.append(f"  title_style: \"{build_title_style_local(is_small, t_size_custom)}\"")
                    output.append(f"  text_style: \"{style_text}\"")
                    output.append(f"  widget_style: \"{style_widget}\"")

                    # On some wall panels, icon-only binary_sensor widgets render the icon too high
                    # and overlap large titles. Push icon down when state/value text is hidden.
                    icon_style_active = _icon
                    icon_style_inactive = _icon_off
                    if (
                        ad_type == 'binary_sensor'
                        and (str(st_enabled).lower() == 'false' or st_enabled is False)
                        and icon_offset_custom is None
                        and icon_gap_custom is None
                    ):
                        icon_style_active = build_icon_style_local(i_size_custom, 24, 24)
                        icon_style_inactive = build_icon_style_local(i_size_custom, 24, 24, "; opacity: 0.5;")

                    output.append(f"  icon_style_active: \"{icon_style_active}\"")
                    output.append(f"  icon_style_inactive: \"{icon_style_inactive}\"")

                    if ad_type in ['cover', 'binary_sensor', 'switch', 'light', 'lock']:
                        output.append("  state_map:")
                        if ad_type == 'cover':
                            for s in ['open', 'closed', 'opening', 'closing']:
                                output.append(f"    \"{s}\": \"{dic.get(s, s)}\"")
                        elif ad_type == 'binary_sensor':
                            output.append(f"    \"on\": \"{dic['on']}\"")
                            output.append(f"    \"off\": \"{dic['off']}\"")
                        elif ad_type == 'lock':
                            output.append(f"    \"locked\": \"{dic['locked']}\"")
                            output.append(f"    \"unlocked\": \"{dic['unlocked']}\"")
                        else:
                            output.append(f"    \"on\": \"{dic['on']}\"")
                            output.append(f"    \"off\": \"{dic['off']}\"")

        if auto_nav_bar and available_dash_files:
            output.append("")
            output.append("# -------------------")
            output.append("# AUTO NAV BAR WIDGETS")
            output.append("# -------------------")
            output.append("")
            seen_navs = set(seen_ids)
            for dash_item in available_dash_files:
                dash_name = dash_item.get('name') if isinstance(dash_item, dict) else dash_item
                dash_slug = dash_name.replace('.dash', '')
                if dash_slug != title.lower().replace(' ', '_'):
                    nav_id = f"navigate.{dash_slug}"
                    if nav_id in seen_navs:
                        continue
                    seen_navs.add(nav_id)
                    nav_name = get_dashboard_display_title(dash_item)
                    output.append(f"{nav_id}:")
                    output.append(f"  widget_type: navigate")
                    output.append(f"  title: \"{nav_name[:12]}\"")
                    output.append(f"  dashboard: {dash_slug}")
                    output.append(f"  icon_active: mdi-arrow-right-circle")
                    output.append(f"  icon_inactive: mdi-arrow-right-circle")
                    output.append(f"  title_style: \"{build_title_style_local(False, '')}\"")
                    output.append(f"  widget_style: \"{style_widget}\"")
                    output.append(f"  icon_active_style: \"{style_icon}\"")
                    output.append(f"  icon_inactive_style: \"{style_icon}\"")
                    output.append("")
    except Exception as e:
        print(f"❌ Error generating YAML: {e}")
        return f"# ERROR GENERATING YAML: {e}"

    return "\n".join(output)

# ROUTES
# -------------------------------------------------------------------------
@app.route('/', methods=['GET', 'POST'])
def index():
    generated_yaml = ""
    ha_data = get_ha_entities()
    ha_entities = ha_data.get('entities', [])
    ha_areas = ha_data.get('areas', [])
    entities_map = {e['id']: e for e in ha_entities}
    dashboard_filename = "joandashboard.dash"
    dashboard_slug = "joandashboard"
    has_token = bool(TOKEN)
    save_message = None


    bridge_active = check_appdaemon_bridge()
    has_dashboards = False
    available_dash_files = []
    if bridge_active:
        success, files = list_dashboards_via_api()
        if success and files:
            has_dashboards = True
            available_dash_files = enrich_dashboard_files_with_titles(files)

    dash_caps = get_dash_saver_capabilities()
    connection_info = {
        "token_source": TOKEN_SOURCE,
        "api_url": API_URL,
        "entity_count": len(ha_entities),
        "appdaemon_slug": APPDAEMON_SLUG,
        "bridge_active": bridge_active,
        "has_dashboards": has_dashboards,
        "dash_saver_file_ops": dash_caps.get("file_ops_ready", False),
        "needs_dash_saver_update": dash_caps.get("needs_dash_saver_update", False),
    }

    current_ui_lang = request.form.get('ui_language', 'pl') if request.method == 'POST' else request.args.get('lang', 'pl')

    if request.method == 'POST':
        action = request.form.get('action', 'generate')
        
        # Retrieving common data for most actions
        title = request.form.get('title', 'JoanDashboard')
        cols = safe_int(request.form.get('grid_columns'), 3)
        rows_grid = safe_int(request.form.get('grid_rows'), 8)
        def_size_str = request.form.get('default_widget_size', '2, 1')
        layout_json = request.form.get('layout_data_json', '[]')
        custom_defs_json = request.form.get('custom_definitions_json', '{}')
        lang = request.form.get('ui_language', 'pl')
        current_ui_lang = lang
        device_profile = request.form.get('device_profile', 'joan_6')
        auto_nav_bar = request.form.get('auto_nav_bar', 'false').lower() == 'true'
        dash_list_str = request.form.get('dashboards_list', '')
        available_dash_files = [
            {'name': d.strip()} for d in dash_list_str.split(',')
            if d.strip() and not _is_internal_preview_dash(d.strip())
        ] if dash_list_str else []
        if available_dash_files:
            available_dash_files = enrich_dashboard_files_with_titles(available_dash_files)

        dashboard_filename, dashboard_slug = _resolve_dashboard_file(title, available_dash_files)
        try:
            layout_data = json.loads(layout_json)
            custom_defs = json.loads(custom_defs_json)
            def_w, def_h = map(int, [x.strip() for x in def_size_str.split(',')])
            grid_params = {'cols': cols, 'rows_grid': rows_grid, 'def_w': def_w, 'def_h': def_h}
        except:
            layout_data = []
            custom_defs = {}
            grid_params = {'cols': 3, 'rows_grid': 8, 'def_w': 2, 'def_h': 1}

        print(f"📦 custom_defs keys ({len(custom_defs)}): {list(custom_defs.keys())[:10]}")

        if action == 'restart':
            success, msg = restart_appdaemon_addon()
            save_message = f"{'✅' if success else '❌'} {msg}"
            # Regenerate YAML so it doesn't disappear after page refresh on restart
            try:
                generated_yaml = generate_joan_dash_yaml(
                    layout_data, title, grid_params, lang, custom_defs, entities_map, device_profile, auto_nav_bar, available_dash_files
                )
            except Exception as e:
                generated_yaml = f"# ERROR REGENERATING: {e}"

        elif action == 'load_dashboard':
            filename = request.form.get('open_dashboard_name', '')
            if filename:
                success, content = read_dashboard_via_api(filename)
                if success:
                    generated_yaml = content
                    dashboard_filename = filename
                    save_message = f"✅ Dashboard wczytany: {filename}"
                else:
                    save_message = f"❌ Błąd odczytu pliku: {filename}"
            else:
                save_message = "❌ Nie podano nazwy pliku do odczytu."

        elif action == 'save_ad':
            try:
                generated_yaml = generate_joan_dash_yaml(
                    layout_data, title, grid_params, lang, custom_defs, entities_map, device_profile, auto_nav_bar, available_dash_files
                )
                success, msg = save_dash_file_via_api(dashboard_filename, generated_yaml)
                save_message = f"{'✅' if success else '❌'} {msg}"
            except Exception as e:
                save_message = f"❌ Save error: {e}"

        elif action == 'download_file':
            yaml_content = request.form.get('yaml_content', '')
            if yaml_content:
                file_obj = io.BytesIO(yaml_content.encode('utf-8'))
                return send_file(file_obj, mimetype='text/plain', as_attachment=True, download_name=dashboard_filename)
        
        else: # generate
            try:
                generated_yaml = generate_joan_dash_yaml(
                    layout_data, title, grid_params, lang, custom_defs, entities_map, device_profile, auto_nav_bar, available_dash_files
                )
            except Exception as e:
                print(f"❌ Error generating YAML: {e}")
                generated_yaml = f"# ERROR GENERATING YAML: {e}"

    return render_template(
        'index.html',
        generated_yaml=generated_yaml,
        entities=ha_entities,
        areas=ha_areas,
        filename=dashboard_filename,
        dash_name=dashboard_slug,
        has_token=has_token,
        save_message=save_message,
        connection_info=connection_info,
        current_lang=current_ui_lang,
        layout_data=layout_data if 'layout_data' in locals() else [],
        custom_defs=custom_defs if 'custom_defs' in locals() else {},
        title=title if 'title' in locals() else "JoanDashboard",
        cols=cols if 'cols' in locals() else 3,
        rows_grid=rows_grid if 'rows_grid' in locals() else 8,
        def_size=def_size_str if 'def_size_str' in locals() else "2, 1",
        dashboards_list=available_dash_files if 'available_dash_files' in locals() else [],
        device_profile=device_profile if 'device_profile' in locals() else 'joan_6',
        auto_nav_bar=auto_nav_bar if 'auto_nav_bar' in locals() else True
    )

# -------------------------------------------------------------------------
# API ENDPOINTS
# -------------------------------------------------------------------------
@app.route('/api/entities')
def api_entities():
    """Current Home Assistant entity states for UI refresh and dashboard preview."""
    ha_data = get_ha_entities()
    return jsonify({
        'status': 'success' if ha_data.get('entities') else 'error',
        'entities': ha_data.get('entities', []),
        'areas': ha_data.get('areas', []),
        'token_source': TOKEN_SOURCE,
        'entity_count': len(ha_data.get('entities', [])),
        'message': None if ha_data.get('entities') else (
            'Brak dostępu do API Home Assistant. Wyczyść manual_token w konfiguracji addona '
            'i zrestartuj add-on (wymagany token Supervisora).'
        ),
    })


@app.route('/api/entity_frequency/<path:entity_id>')
def api_entity_frequency(entity_id):
    """Returns entity update frequency analysis (JSON)."""
    result = get_entity_frequency(entity_id, hours=24)
    return jsonify(result)

@app.route('/api/dash_saver_capabilities')
def api_dash_saver_capabilities():
    """Whether dash_saver supports delete/rename (full script from generator 1.6+)."""
    caps = get_dash_saver_capabilities()
    return jsonify({"status": "success", "capabilities": caps})

@app.route('/api/list_dashboards')
def api_list_dashboards():
    """Returns list of available dashboard files from AppDaemon (JSON)."""
    from flask import jsonify
    success, files = list_dashboards_via_api()
    if success:
        return jsonify({"status": "success", "files": enrich_dashboard_files_with_titles(files)})
    else:
        return jsonify({"status": "error", "message": "Cannot list dashboards. Is dash_saver.py installed?", "files": []})

@app.route('/api/read_dashboard/<path:filename>')
def api_read_dashboard(filename):
    """Returns content of a dashboard file from AppDaemon (JSON)."""
    from flask import jsonify
    success, content = read_dashboard_via_api(filename)
    if success:
        return jsonify({"status": "success", "content": content, "filename": filename})
    else:
        return jsonify({"status": "error", "message": f"Cannot read dashboard: {filename}"})

@app.route('/api/delete_dashboard', methods=['POST'])
def api_delete_dashboard():
    """Delete a .dash file from AppDaemon dashboards folder."""
    from flask import jsonify, request
    data = request.get_json(silent=True) or {}
    filename = data.get('filename', '')
    success, message = delete_dashboard_via_api(filename)
    if success:
        return jsonify({"status": "success", "message": message, "filename": _normalize_dash_filename(filename)})
    return jsonify({"status": "error", "message": message}), 400

@app.route('/api/rename_dashboard', methods=['POST'])
def api_rename_dashboard():
    """Rename a .dash file in AppDaemon dashboards folder."""
    from flask import jsonify, request
    data = request.get_json(silent=True) or {}
    old_name = data.get('old_filename') or data.get('filename', '')
    new_name = data.get('new_filename', '')
    result = rename_dashboard_via_api(old_name, new_name)
    success = result[0]
    message = result[1]
    dashboard_title = result[2] if len(result) > 2 else None
    if success:
        return jsonify({
            "status": "success",
            "message": message,
            "old_filename": _normalize_dash_filename(old_name),
            "new_filename": _normalize_dash_filename(new_name),
            "dashboard_title": dashboard_title or _title_from_dash_filename(new_name),
        })
    return jsonify({"status": "error", "message": message}), 400

@app.route('/api/push_dashboard_preview', methods=['POST'])
def api_push_dashboard_preview():
    """Generate YAML from current editor layout and save to AppDaemon before browser preview."""
    from flask import jsonify, request

    if not check_appdaemon_bridge():
        return jsonify({
            "status": "error",
            "message": "Most AppDaemon nie jest aktywny — nie można zapisać podglądu.",
            "bridge_active": False,
        }), 503

    data = request.get_json(silent=True) or {}
    ha_data = get_ha_entities()
    entities_map = {e['id']: e for e in ha_data.get('entities', [])}

    title = (data.get('title') or 'JoanDashboard').strip() or 'JoanDashboard'
    cols = safe_int(data.get('grid_columns'), 3)
    rows_grid = safe_int(data.get('grid_rows'), 8)
    def_size_str = data.get('default_widget_size', '2, 1')
    lang = data.get('ui_language', 'pl')
    device_profile = data.get('device_profile', 'joan_6')
    auto_nav_bar = data.get('auto_nav_bar') in (True, 'true', 'True', '1', 1)

    layout_data = data.get('layout_data')
    if layout_data is None:
        raw_layout = data.get('layout_data_json', '[]')
        try:
            layout_data = json.loads(raw_layout) if isinstance(raw_layout, str) else raw_layout
        except Exception:
            layout_data = []
    if not isinstance(layout_data, list):
        layout_data = []

    custom_defs = data.get('custom_definitions')
    if custom_defs is None:
        raw_defs = data.get('custom_definitions_json', '{}')
        try:
            custom_defs = json.loads(raw_defs) if isinstance(raw_defs, str) else raw_defs
        except Exception:
            custom_defs = {}
    if not isinstance(custom_defs, dict):
        custom_defs = {}

    available_dash_files = []
    list_ok, files = list_dashboards_via_api()
    if list_ok and files:
        available_dash_files = enrich_dashboard_files_with_titles(files)
    else:
        raw_list = data.get('dashboards_list', '')
        if isinstance(raw_list, str) and raw_list.strip():
            for part in raw_list.split(','):
                part = part.strip()
                if part:
                    available_dash_files.append({'name': part})

    target_filename, _target_slug = _resolve_dashboard_file(title, available_dash_files)
    preview_filename = JOAN_LIVE_PREVIEW_FILENAME
    preview_slug = JOAN_LIVE_PREVIEW_SLUG

    try:
        def_w, def_h = map(int, [x.strip() for x in str(def_size_str).split(',')])
        grid_params = {'cols': cols, 'rows_grid': rows_grid, 'def_w': def_w, 'def_h': def_h}
    except Exception:
        grid_params = {'cols': 3, 'rows_grid': 8, 'def_w': 2, 'def_h': 1}

    try:
        generated_yaml = generate_joan_dash_yaml(
            layout_data, title, grid_params, lang, custom_defs, entities_map,
            device_profile, auto_nav_bar, available_dash_files,
        )
    except Exception as e:
        return jsonify({"status": "error", "message": f"Błąd generowania YAML: {e}"}), 500

    success, msg = save_dash_file_via_api(preview_filename, generated_yaml)
    if success:
        return jsonify({
            "status": "success",
            "message": msg,
            "filename": preview_filename,
            "slug": preview_slug,
            "temporary": True,
            "target_filename": target_filename,
            "bridge_active": True,
        })
    return jsonify({"status": "error", "message": msg, "bridge_active": True}), 500

@app.route('/api/duplicate_dashboard', methods=['POST'])
def api_duplicate_dashboard():
    """Duplicate a .dash file with an auto-generated name (_copy, _copy2, ...)."""
    from flask import jsonify, request
    data = request.get_json(silent=True) or {}
    filename = data.get('filename', '')
    new_title = (data.get('new_title') or data.get('dashboard_title') or '').strip() or None
    success, message, new_name, dashboard_title = duplicate_dashboard_via_api(filename, new_title)
    if success:
        return jsonify({
            "status": "success",
            "message": message,
            "filename": new_name,
            "dashboard_title": dashboard_title or _title_from_dash_filename(new_name),
        })
    return jsonify({"status": "error", "message": message}), 400


if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000, debug=True)

