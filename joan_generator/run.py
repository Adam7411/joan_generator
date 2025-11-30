
from flask import Flask, render_template, request, Response
import datetime

app = Flask(__name__)

# Domyślne style wyciągnięte z Twoich plików Joan
DEFAULT_STYLES = {
    "title_style": "color: #000000; font-size: 20px; font-weight: 700; text-align: center; padding-top: 5px; width: 100%; font-family: 'Roboto', 'Arial Black', sans-serif;",
    "widget_style": "color: #000000 !important; background-color: #FFFFFF !important;",
    "text_style": "color: #000000 !important; font-weight: 700 !important;",
    "value_style": "color: #000000 !important; font-size: 44px !important; font-weight: 700 !important;",
    "unit_style": "color: #000000 !important;",
    "icon_style": "color: #000000 !important;"
}

@app.route('/', methods=['GET', 'POST'])
def index():
    generated_yaml = ""
    if request.method == 'POST':
        # Pobranie danych globalnych
        title = request.form.get('title', 'JoanDashboard')
        cols = request.form.get('columns', '6')
        rows = request.form.get('rows', '9')
        
        # Generowanie nagłówka
        generated_yaml += f"title: {title}\n"
        generated_yaml += "widget_dimensions: [117, 117]\n"
        generated_yaml += "widget_size: [2, 1]\n" # Domyślny rozmiar, można nadpisać per widget
        generated_yaml += "widget_margins: [8, 8]\n"
        generated_yaml += f"columns: {cols}\n"
        generated_yaml += f"rows: {rows}\n"
        generated_yaml += "global_parameters:\n"
        generated_yaml += "  use_comma: 0\n  precision: 1\n  use_hass_icon: 1\n  namespace: default\n"
        generated_yaml += "skin: simplyred\n\n"
        
        # Layout section
        generated_yaml += "layout:\n"
        
        # Pobieranie widgetów z formularza (prosta pętla po rzędach)
        # Zakładamy, że frontend prześle listę stringów layoutu
        layout_rows = request.form.getlist('layout_row')
        for row in layout_rows:
            if row.strip():
                generated_yaml += f"  - {row}\n"
        
        generated_yaml += "\n# --- DEFINICJE WIDŻETÓW ---\n\n"
        
        # Definicje widgetów
        # Oczekujemy danych w formacie: widget_id_1, widget_type_1, widget_name_1, itp.
        widget_ids = request.form.getlist('widget_id')
        widget_types = request.form.getlist('widget_type')
        widget_names = request.form.getlist('widget_name')
        widget_icons = request.form.getlist('widget_icon')
        
        for i, entity_id in enumerate(widget_ids):
            if not entity_id: continue
            
            w_type = widget_types[i]
            w_name = widget_names[i]
            w_icon = widget_icons[i]
            
            # Nagłówek definicji (np. light.kurnik:)
            # Jeśli to navigate, używamy innej nazwy bloku
            block_name = entity_id
            if w_type == 'navigate':
                 # Dla navigate często ID to np. navigate.joan2
                 pass
            
            generated_yaml += f"{block_name}:\n"
            generated_yaml += f"  widget_type: {w_type}\n"
            
            # Logika per typ (bazując na Twoich plikach)
            if w_type == 'navigate':
                # Specyfika dla navigate
                dashboard_name = entity_id.replace('navigate.', '')
                generated_yaml += f"  dashboard: {dashboard_name}\n"
                generated_yaml += f"  title: \"{w_name}\"\n"
                generated_yaml += f"  icon_inactive: {w_icon if w_icon else 'mdi-arrow-left-circle'}\n"
                generated_yaml += f"  widget_style: \"background-color: #FFFFFF !important; border-radius: 8px !important; padding: 10px !important; color: #000000 !important;\"\n"
                generated_yaml += f"  title_style: \"{DEFAULT_STYLES['title_style']}\"\n"
            
            elif w_type == 'sensor':
                generated_yaml += f"  entity: {entity_id}\n"
                generated_yaml += f"  title: {w_name}\n"
                generated_yaml += f"  title_style: \"{DEFAULT_STYLES['title_style']}\"\n"
                generated_yaml += f"  text_style: \"{DEFAULT_STYLES['text_style']}\"\n"
                generated_yaml += f"  value_style: \"{DEFAULT_STYLES['value_style']}\"\n"
                generated_yaml += f"  unit_style: \"{DEFAULT_STYLES['unit_style']}\"\n"
                generated_yaml += f"  widget_style: \"{DEFAULT_STYLES['widget_style']}\"\n"
                if w_icon:
                    generated_yaml += f"  icon: {w_icon}\n"
                    generated_yaml += f"  icon_style: \"{DEFAULT_STYLES['icon_style']}\"\n"

            elif w_type in ['switch', 'light', 'input_boolean', 'cover', 'script', 'fan']:
                generated_yaml += f"  entity: {entity_id}\n"
                generated_yaml += f"  title: {w_name}\n"
                generated_yaml += f"  icon_on: {w_icon if w_icon else 'mdi-help-circle'}\n"
                generated_yaml += f"  icon_off: {w_icon if w_icon else 'mdi-help-circle-outline'}\n"
                generated_yaml += f"  state_text: 1\n"
                generated_yaml += f"  title_style: \"{DEFAULT_STYLES['title_style']}\"\n"
                generated_yaml += f"  widget_style: \"{DEFAULT_STYLES['widget_style']}\"\n"
                generated_yaml += f"  icon_style_active: \"{DEFAULT_STYLES['icon_style']}\"\n"
                generated_yaml += f"  icon_style_inactive: \"{DEFAULT_STYLES['icon_style']}\"\n"
                
                # Przykładowe mapowanie stanów (uproszczone)
                generated_yaml += "  state_map:\n"
                generated_yaml += "    \"on\": \"WŁĄCZONE\"\n    \"off\": \"WYŁĄCZONE\"\n"
                if w_type == 'cover':
                    generated_yaml += "    \"open\": \"OTWARTA\"\n    \"closed\": \"ZAMKNIĘTA\"\n"

            generated_yaml += "\n"

    return render_template('index.html', generated_yaml=generated_yaml)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
