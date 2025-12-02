// static/script.js

// Config
const widgetTypesConfig = [
    { value: 'switch', pl: 'Przełącznik / Światło', en: 'Switch / Light' },
    { value: 'sensor', pl: 'Sensor (Liczba/Tekst)', en: 'Sensor' },
    { value: 'binary_sensor', pl: 'Sensor Binarny', en: 'Binary Sensor' },
    { value: 'cover', pl: 'Roleta / Brama', en: 'Cover / Gate' },
    { value: 'lock', pl: 'Zamek', en: 'Lock' },
    { value: 'person', pl: 'Osoba / Tracker', en: 'Person / Tracker' },
    { value: 'media_player', pl: 'Odtwarzacz', en: 'Media Player' },
    { value: 'climate', pl: 'Klimatyzacja', en: 'Climate' },
    { value: 'script', pl: 'Skrypt', en: 'Script' },
    { value: 'navigate', pl: 'Nawigacja (Button)', en: 'Navigate (Button)' },
    { value: 'weather', pl: 'Pogoda', en: 'Weather' },
    { value: 'alarm_control_panel', pl: 'Alarm', en: 'Alarm' },
    { value: 'input_number', pl: 'Suwak (Input Number)', en: 'Input Number' },
    { value: 'input_select', pl: 'Lista (Input Select)', en: 'Input Select' },
    { value: 'scene', pl: 'Scena', en: 'Scene' },
    { value: 'fan', pl: 'Wentylator', en: 'Fan' },
    { value: 'clock', pl: 'Zegar', en: 'Clock' },
    { value: 'label', pl: 'Etykieta', en: 'Label' },
    { value: 'reload', pl: 'Odśwież', en: 'Reload' }
];

const i18n = {
    pl: {
        status_ok:"✓ Połączono z Home Assistant", status_error:"⚠ Brak połączenia z API. Sprawdź token.",
        sec_settings:"1. Ustawienia", sec_add:"2. Dodaj / Edytuj Widget", sec_preview:"3. Podgląd Dashboardu (Kliknij, aby edytować)", sec_code:"Twój kod YAML:",
        dash_title:"Tytuł Dashboardu (Nazwa pliku)", label_entity:"Wybierz Encję (Home Assistant)", label_dashboard:"Nazwa pliku dashboardu (np. joan3)",
        label_type:"Typ Widgetu", label_name:"Tytuł na ekranie", label_icon:"Ikona", label_preview:"Podgląd", label_size:"Rozmiar",
        btn_add:"+ DODAJ DO WIERSZA", btn_update:"ZAPISZ ZMIANY", btn_cancel:"Anuluj", btn_new_row:"+ Dodaj Nowy Wiersz", btn_generate:"GENERUJ KOD .DASH",
        btn_import_toggle:"📂 Importuj / Edytuj Kod", header_paste_code:"Wklej kod pliku .dash tutaj:", btn_load_dash:"Wczytaj Dashboard",
        info_step1:"1. Zapisz kod w pliku:", info_step2:"2. Podgląd dashboardu:",
        state_on:"WŁĄCZONE", state_off:"WYŁĄCZONE", state_open:"OTWARTA", state_closed:"ZAMKNIĘTA",
        state_locked:"ZAMKNIĘTE", state_unlocked:"OTWARTE", state_home:"W DOMU", state_not_home:"POZA DOMEM"
    },
    en: {
        status_ok:"✓ Connected to Home Assistant", status_error:"⚠ No API Connection. Check Token.",
        sec_settings:"1. Settings", sec_add:"2. Add / Edit Widget", sec_preview:"3. Dashboard Preview (Click to Edit)", sec_code:"Your YAML Code:",
        dash_title:"Dashboard Title (Filename)", label_entity:"Select Entity (Home Assistant)", label_dashboard:"Dashboard filename (e.g. joan3)",
        label_type:"Widget Type", label_name:"Title on Screen", label_icon:"Icon", label_preview:"Preview", label_size:"Size",
        btn_add:"+ ADD TO ROW", btn_update:"SAVE CHANGES", btn_cancel:"Cancel", btn_new_row:"+ Add New Row", btn_generate:"GENERATE .DASH CODE",
        btn_import_toggle:"📂 Import / Edit Code", header_paste_code:"Paste .dash file here:", btn_load_dash:"Load Dashboard",
        info_step1:"1. Save code to file:", info_step2:"2. Dashboard preview:",
        state_on:"ON", state_off:"OFF", state_open:"OPEN", state_closed:"CLOSED"
    }
};

// State
let currentLang='pl';
let rows=[];
let activeRowIndex=0;
let editingIndices=null;
let importedDefsMap={};

// --- LOGIC START ---

function formatNameFromId(id){
    if(!id) return "";
    const last = id.includes('.') ? id.split('.').pop() : id;
    let n = last.replace(/[_\-]+/g,' ').trim();
    n = n.replace(/\b(esp|node|sensor|switch|light|binary sensor|input boolean|media player|climate|script|lock|cover|person|device tracker)\b/gi,'');
    n = n.replace(/\s{2,}/g,' ').trim();
    return n.toLowerCase().replace(/\b\w/g, l => l.toUpperCase());
}
function ensureMdi(icon){ if(!icon) return ""; return icon.startsWith('mdi-') ? icon : 'mdi-'+icon; }

function inferTypeFromIdOrEntity(val){
    const v = (val||'').toLowerCase();
    if(v.startsWith('lock.')) return 'lock';
    if(v.startsWith('person.') || v.startsWith('device_tracker.')) return 'person';
    if(v.startsWith('input_number.')) return 'input_number';
    if(v.startsWith('input_select.')) return 'input_select';
    if(v.startsWith('weather.')) return 'weather';
    if(v.startsWith('alarm')) return 'alarm_control_panel';
    if(v.startsWith('sensor.')) return 'sensor';
    if(v.startsWith('binary_sensor.')) return 'binary_sensor';
    if(v.startsWith('cover.')) return 'cover';
    if(v.startsWith('media_player.')) return 'media_player';
    if(v.startsWith('climate.')) return 'climate';
    if(v.startsWith('fan.')) return 'fan';
    if(v.startsWith('script.')) return 'script';
    if(v.startsWith('scene.')) return 'scene';
    if(v.startsWith('light.') || v.startsWith('switch.') || v.startsWith('input_boolean.')) return 'switch';
    if(v.startsWith('navigate.')) return 'navigate';
    return 'switch';
}

// Smart Icon Mapping
const smartIconMap = [
    {k:['hydrofor','pump','water pump','zbiornik','tank'],on:'mdi-water-pump',off:'mdi-water-pump-off'},
    {k:['cwu','boiler','woda','water'],on:'mdi-water-outline',off:'mdi-water-off'},
    {k:['grzejnik','radiator','ogrzew','heat'],on:'mdi-radiator',off:'mdi-radiator-off'},
    // Gate fix: ensure it doesn't match "navigate"
    {k:['gate','brama'],on:'mdi-gate-open',off:'mdi-gate'}, 
    {k:['garage','garaz','garaż'],on:'mdi-garage-open',off:'mdi-garage'},
    {k:['blind','roleta','shutter','okno','window'],on:'mdi-window-shutter-open',off:'mdi-window-shutter'},
    {k:['door','drzwi'],on:'mdi-door-open',off:'mdi-door-closed'},
    {k:['lock','zamek'],on:'mdi-lock-open',off:'mdi-lock'},
    {k:['light','lamp','swiatlo','światło','zarowka','żarówka'],on:'mdi-lightbulb-on',off:'mdi-lightbulb-outline'},
    {k:['fan','wentyl'],on:'mdi-fan',off:'mdi-fan-off'},
    {k:['speaker','radio','media_player','spotify','audio'],on:'mdi-speaker',off:'mdi-speaker-off'},
    {k:['climate','klima','hvac','thermostat','temp','temperatura','temperature'],on:'mdi-thermometer',off:'mdi-thermometer-off'},
    {k:['battery','bateria'],base:'mdi-battery'},
    {k:['wilgotn','humid','humidity'],base:'mdi-water-percent'},
    {k:['pressure','cisnienie','ciśnienie'],base:'mdi-gauge'},
    {k:['sensor','czujnik'],base:'mdi-gauge'},
    {k:['power','moc','energia','energy'],base:'mdi-flash'}
];

function findIconPairById(id){
    const lower = (id||'').toLowerCase();
    // SKIP "gate" check if it is navigate
    if(lower.startsWith('navigate')) return ['mdi-arrow-right-circle','mdi-arrow-right-circle'];

    for(const e of smartIconMap){
        if(e.k && e.k.some(k => lower.includes(k))){
            if(e.on && e.off) return [e.on,e.off];
            if(e.base) return [e.base,e.base];
        }
    }
    return ['mdi-toggle-switch','mdi-toggle-switch-off'];
}

function findBaseIconByIdAndType(id,type){
    const lower = (id||'').toLowerCase();
    // FIX: Navigate check first
    if(type === 'navigate' || lower.startsWith('navigate')) return 'mdi-arrow-right-circle';

    for(const e of smartIconMap){
        if(e.k && e.k.some(k => lower.includes(k))){
            return ensureMdi(e.base || e.on || 'mdi-help-circle-outline');
        }
    }
    const fallback = {switch:'mdi-toggle-switch',binary_sensor:'mdi-alert-circle-outline',sensor:'mdi-gauge',cover:'mdi-window-shutter',media_player:'mdi-speaker',climate:'mdi-thermometer',script:'mdi-script-text-outline',navigate:'mdi-arrow-right-circle',fan:'mdi-fan',label:'mdi-label-outline',light:'mdi-lightbulb',lock:'mdi-lock',person:'mdi-account',clock:'mdi-clock-outline',reload:'mdi-refresh',iframe:'mdi-image-area',scene:'mdi-palette'};
    return ensureMdi(fallback[type] || 'mdi-help-circle-outline');
}

function getLiveStateText(ent, type){
    if(!ent) return '';
    const raw = String(ent.state).toLowerCase();
    const t = i18n[currentLang];
    if(type==='sensor' || type==='input_number'){
        let val=ent.state;
        if(!isNaN(parseFloat(val)) && String(val).includes('.')) val=parseFloat(val).toFixed(1);
        return ent.unit ? `${val} ${ent.unit}` : val;
    }
    if(['switch','binary_sensor','script','media_player','climate','fan','light','input_boolean','lock'].includes(type) || ent.id?.startsWith?.('input_boolean.')){
        if(['on','playing','open','unlocked','heat','cool','true','1','opening'].includes(raw)) return t.state_on;
        if(['off','closed','locked','idle','stopped','standby','false','0','closing'].includes(raw)) return t.state_off;
        return raw.toUpperCase();
    }
    return ent.state;
}

function pickPreviewIcon(widget){
    const ent = (entitiesData||[]).find(e=>e.id===widget.id);
    const actionable = ['switch','binary_sensor','cover','media_player','climate','script','fan','light','lock','input_boolean'].includes(widget.type) || widget.id.startsWith('input_boolean.');
    if(actionable){
        const pair = findIconPairById(widget.id);
        const state = ent ? String(ent.state).toLowerCase() : 'off';
        const isOn = ['on','open','playing','unlocked','heat','cool','true','1','opening','home'].includes(state);
        return ensureMdi(isOn ? (widget.icon_on || pair[0]) : (widget.icon_off || pair[1]));
    }
    return ensureMdi(widget.icon || findBaseIconByIdAndType(widget.id, widget.type));
}

function resolveImportedTitle(id) {
    if (importedDefsMap[id] && importedDefsMap[id].title) return importedDefsMap[id].title;
    const shortId = id.split('.').pop();
    if (importedDefsMap[shortId] && importedDefsMap[shortId].title) return importedDefsMap[shortId].title;
    for(let key in importedDefsMap) {
        if(importedDefsMap[key].entity === id && importedDefsMap[key].title) return importedDefsMap[key].title;
    }
    return '';
}

// --- APP LOGIC ---
function applySmartForForm(userAction=false){
    const typeSel = document.getElementById('new-widget-type');
    const entityInput = document.getElementById('new-entity-id');
    const nameInput = document.getElementById('new-widget-name');
    const iconInput = document.getElementById('new-widget-icon');
    const groupEntity = document.getElementById('group-entity');
    const groupNav = document.getElementById('group-nav');
    const sizeInput = document.getElementById('new-widget-size');

    if(typeSel.value==='navigate'){
        groupEntity.classList.add('hidden'); groupNav.classList.remove('hidden');
        if(!iconInput.value) iconInput.value='mdi-arrow-right-circle';
        updateIconPreview();
        return;
    } else {
        groupEntity.classList.remove('hidden'); groupNav.classList.add('hidden');
    }

    const idRaw = (entityInput.value||'').trim();
    if(!idRaw && !userAction){ updateIconPreview(); return; }
    const id = idRaw.toLowerCase();

    if(userAction) {
        // AGGRESSIVE SMART UPDATE
        const newType = inferTypeFromIdOrEntity(id);
        typeSel.value = newType;
        
        nameInput.value = formatNameFromId(idRaw);
        
        if((typeSel.value==='media_player' || typeSel.value==='climate' || typeSel.value==='weather' || typeSel.value==='clock') && !sizeInput.value) sizeInput.value='(2x2)';
        
        const actionable = ['switch','binary_sensor','cover','media_player','climate','script','fan','light','lock'].includes(typeSel.value) || id.startsWith('input_boolean.');
        if(actionable){
            const pair = findIconPairById(idRaw);
            iconInput.value = pair[0]; 
        } else {
            iconInput.value = findBaseIconByIdAndType(idRaw, typeSel.value);
        }
    }
    updateIconPreview();
}

function updateIconPreview(){
    const icon = document.getElementById('new-widget-icon').value.trim();
    document.getElementById('icon-preview-i').className = (icon && icon.startsWith('mdi-')) ? ('mdi '+icon) : 'mdi mdi-help-circle-outline';
}

function saveWidget(){
    applySmartForForm(false);
    const type = document.getElementById('new-widget-type').value || 'switch';
    let id='';
    if(type==='navigate'){
        const dashName = document.getElementById('new-dashboard-name').value.trim();
        if(!dashName){ alert(currentLang==='pl'?'Wymagana nazwa dashboardu':'Dashboard name required'); return; }
        id = 'navigate.' + dashName;
    }else{
        id = document.getElementById('new-entity-id').value.trim();
        if(!id && type !== 'clock' && type !== 'label' && type !== 'reload'){ alert(currentLang==='pl'?'Wymagana encja':'Entity required'); return; }
        if(!id) id = type + '.' + Date.now(); 
    }
    
    let name = document.getElementById('new-widget-name').value.trim();
    if(!name && type!=='clock' && type!=='reload') name = formatNameFromId(id);

    let icon = document.getElementById('new-widget-icon').value.trim();
    const size = document.getElementById('new-widget-size').value;

    const actionable = ['switch','binary_sensor','cover','media_player','climate','script','fan','light','lock'].includes(type) || id.toLowerCase().startsWith('input_boolean.');
    let icon_on='', icon_off='';
    if(actionable){
        const pair = findIconPairById(id);
        icon_on = ensureMdi(pair[0]);
        icon_off = ensureMdi(pair[1]);
        icon = ''; // clear main icon for actionable
    }else{
        if(!icon) icon = ensureMdi(findBaseIconByIdAndType(id, type));
    }

    const widget = { id, type, name, icon: ensureMdi(icon), icon_on, icon_off, size };

    if(editingIndices){
        rows[editingIndices.r][editingIndices.w] = widget;
        editingIndices=null;
        document.getElementById('btn-cancel').classList.add('hidden');
        document.getElementById('widget-form-box').classList.remove('editing');
    }else{
        if(!rows.length) addNewRow();
        rows[activeRowIndex].push(widget);
    }
    clearFormInputs();
    renderRows();
    applyTranslations();
}

function editWidget(r,w){
    editingIndices={r,w};
    const widget = rows[r][w];
    activeRowIndex=r; highlightActiveRow();
    document.getElementById('new-widget-type').value = widget.type;
    const groupEntity = document.getElementById('group-entity');
    const groupNav = document.getElementById('group-nav');
    if(widget.type==='navigate'){
        groupEntity.classList.add('hidden'); groupNav.classList.remove('hidden');
        document.getElementById('new-dashboard-name').value = widget.id.replace('navigate.','');
        document.getElementById('new-entity-id').value = '';
    }else{
        groupEntity.classList.remove('hidden'); groupNav.classList.add('hidden');
        document.getElementById('new-dashboard-name').value = '';
        document.getElementById('new-entity-id').value = widget.id.includes(widget.type+'.') && !widget.id.includes('_') ? '' : widget.id;
    }
    document.getElementById('new-widget-name').value = widget.name;
    document.getElementById('new-widget-icon').value = widget.icon || widget.icon_on || '';
    document.getElementById('new-widget-size').value = widget.size || '';
    document.getElementById('btn-cancel').classList.remove('hidden');
    document.getElementById('widget-form-box').classList.add('editing');
    updateIconPreview(); applyTranslations(); renderRows();
}

function cancelEdit(){
    editingIndices=null;
    document.getElementById('btn-cancel').classList.add('hidden');
    document.getElementById('widget-form-box').classList.remove('editing');
    clearFormInputs();
    applyTranslations();
    renderRows();
}

function clearFormInputs(){
    ['new-dashboard-name','new-entity-id','new-widget-name','new-widget-icon','new-widget-size'].forEach(id=>document.getElementById(id).value='');
    updateIconPreview();
}

function removeWidget(r,w){
    if(editingIndices && editingIndices.r===r && editingIndices.w===w) cancelEdit();
    rows[r].splice(w,1);
    renderRows();
}

function addNewRow(){ rows.push([]); activeRowIndex=rows.length-1; renderRows(); applyTranslations(); }
function deleteRow(rowIndex){ if(editingIndices && editingIndices.r===rowIndex) cancelEdit(); rows.splice(rowIndex,1); if(activeRowIndex>=rows.length) activeRowIndex=rows.length-1; renderRows(); applyTranslations(); }
function highlightActiveRow(){ document.querySelectorAll('.eink-row').forEach(el=>el.classList.remove('active')); const act = document.getElementById('row-'+activeRowIndex); if(act) act.classList.add('active'); }

function renderRows(){
    const container = document.getElementById('rows-container');
    container.innerHTML='';
    rows.forEach((rowWidgets,index)=>{
        const rowDiv=document.createElement('div');
        rowDiv.className='eink-row';
        rowDiv.id='row-'+index;
        rowDiv.onclick=()=>{ if(editingIndices) cancelEdit(); activeRowIndex=index; highlightActiveRow(); applyTranslations(); };
        const label=document.createElement('div');
        label.style.position='absolute'; label.style.top='-10px'; label.style.left='5px';
        label.style.fontSize='10px'; label.style.fontWeight='900'; label.style.color='#666';
        label.textContent=(currentLang==='pl'?'WIERSZ ':'ROW ')+(index+1);
        rowDiv.appendChild(label);
        if(rows.length>1){
          const del=document.createElement('button');
          del.className='btn-remove-row';
          del.textContent = currentLang==='pl'?'USUŃ':'DELETE';
          del.onclick=(e)=>{ e.stopPropagation(); deleteRow(index); };
          rowDiv.appendChild(del);
        }
        rowWidgets.forEach((widget,wIndex)=>{
          const wDiv=document.createElement('div');
          wDiv.className='eink-widget';
          if(editingIndices && editingIndices.r===index && editingIndices.w===wIndex) wDiv.classList.add('being-edited');
          let w=140,h=110;
          if(widget.size){ const dims=widget.size.replace(/[()]/g,'').split('x'); const cols=parseInt(dims[0])||2; const rs=parseInt(dims[1])||1; w=(cols*70)+((cols-1)*6); h=(rs*90)+((rs-1)*6); }
          wDiv.style.width=w+'px'; wDiv.style.height=h+'px';
          wDiv.onclick=(e)=>{ e.stopPropagation(); editWidget(index,wIndex); };
          const ent = (entitiesData||[]).find(e=>e.id===widget.id);
          const stateText = getLiveStateText(ent, widget.type);
          const iconClass = pickPreviewIcon(widget);
          wDiv.innerHTML = `<div class="ew-title">${widget.name}</div><i class="mdi ${iconClass} ew-icon"></i><div class="ew-state">${stateText || ' '}</div><div class="ew-delete" onclick="removeWidget(${index},${wIndex}); event.stopPropagation();">X</div>`;
          rowDiv.appendChild(wDiv);
        });
        container.appendChild(rowDiv);
    });
    highlightActiveRow();
}

function toggleImport(){ document.getElementById('import-area').classList.toggle('visible'); }

function importYaml(){
  const code = document.getElementById('import-code').value;
  if(!code) return;
  try{
    const lines = code.split('\n');
    let parsingLayout=false, currentKey=null, globalTitleSet=false;
    const layoutLines=[]; const defs={};
    const ignore=['global_parameters','widget_dimensions','widget_size','widget_margins','columns','rows','skin'];
    for(const raw of lines){
      const cut = raw.split('#')[0];
      const line = (cut || '').trim();
      if(!line) continue;
      if(!parsingLayout && /^title\s*:/i.test(line) && !globalTitleSet){
        const val = line.split(':').slice(1).join(':').trim().replace(/^["']|["']$/g,'');
        if(val) document.getElementById('dash-title').value = val;
        globalTitleSet=true; continue;
      }
      if(/^layout\s*:/i.test(line)){ parsingLayout=true; continue; }
      if(parsingLayout){
        if(line.startsWith('-')){ layoutLines.push(line); continue; }
        if(/^[A-Za-z0-9_.-]+\s*:/i.test(line)){ parsingLayout=false; }
      }
      const root = line.match(/^([A-Za-z0-9_.-]+)\s*:/);
      if(root){
        const key = root[1];
        if(!ignore.includes(key)){ currentKey=key; defs[key]=defs[key]||{}; } else currentKey=null;
        continue;
      }
      if(currentKey && line.includes(':')){
        const k = line.split(':')[0].trim();
        let v = line.substring(line.indexOf(':')+1).trim().replace(/^["']|["']$/g,'');
        defs[currentKey][k]=v;
      }
    }
    importedDefsMap={};
    Object.entries(defs).forEach(([k,v])=>{
      importedDefsMap[k]=v;
      if(v.entity){ importedDefsMap[v.entity]=v; const short = v.entity.split('.').pop(); importedDefsMap[short]=v; }
    });
    rows=[];
    layoutLines.forEach(l=>{
      const content = l.replace(/^-+\s*/,'').trim();
      const items = content.split(',').map(x=>x.trim()).filter(Boolean);
      const rowWidgets=[];
      items.forEach(item=>{
        const sizeMatch = item.match(/\(\d+x\d+\)/);
        const size = sizeMatch ? sizeMatch[0] : '';
        const rawId = item.replace(size,'').trim();
        const def = importedDefsMap[rawId] || importedDefsMap[rawId.split('.').pop()] || {};
        const sourceEntity = def.entity || rawId;
        let type = def.widget_type || inferTypeFromIdOrEntity(sourceEntity);
        
        let name = resolveImportedTitle(rawId);
        if(!name && def.title) name = def.title;
        if(!name) name = formatNameFromId(rawId);

        // Handle specific navigation icon logic
        let icon = ensureMdi(def.icon || def.icon_inactive || '');
        if(type==='navigate' && !icon) icon='mdi-arrow-right-circle';

        let icon_on = ensureMdi(def.icon_on || def.icon_active || '');
        let icon_off = ensureMdi(def.icon_off || def.icon_inactive || '');

        const actionable = ['switch','binary_sensor','cover','media_player','climate','script','fan','light','lock'].includes(type) || sourceEntity.startsWith('input_boolean.');
        if(actionable){
          const pair = findIconPairById(sourceEntity);
          if(!icon_on) icon_on = ensureMdi(pair[0]);
          if(!icon_off) icon_off = ensureMdi(pair[1]);
        }else{
          if(!icon) icon = ensureMdi(findBaseIconByIdAndType(sourceEntity, type));
        }
        rowWidgets.push({ id: sourceEntity, type, name, icon, icon_on, icon_off, size });
      });
      if(rowWidgets.length) rows.push(rowWidgets);
    });
    if(!rows.length){ alert(currentLang==='pl'?'Brak layout w imporcie':'No layout found'); return; }
    activeRowIndex=rows.length-1; renderRows(); applyTranslations(); toggleImport(); alert(currentLang==='pl'?'Import zakończony':'Import completed');
  }catch(e){ alert((currentLang==='pl'?'Błąd importu: ':'Import error: ')+e.message); }
}

// --- SUBMIT ---
function prepareAndSubmit(e){
  e.preventDefault();
  try{
    const title = (document.getElementById('dash-title').value || 'Dashboard').replace(/"/g,'');
    const yaml = [buildHeader(title), buildLayout(), buildWidgetsSection()].join("\n");
    document.getElementById('generated_yaml_client').value = yaml;
    document.getElementById('widgets_full_json').value = JSON.stringify(rows);
    document.getElementById('layout_data_json').value = JSON.stringify(rows.map(r=>r.map(w=>w.id+(w.size? " "+w.size:""))));
    
    const host = window.location.hostname;
    document.getElementById('client-yaml-section').classList.remove('hidden');
    document.getElementById('client-yaml-output').value = yaml;
    document.getElementById('client-path-code').innerText = `\\\\${host}\\addon_configs\\appdaemon\\dashboards\\${title.toLowerCase().replace(/\s+/g,'_')}.dash`;
    const link = `http://${host}:5050/${title.toLowerCase().replace(/\s+/g,'_')}`;
    const linkEl = document.getElementById('client-dashboard-link');
    linkEl.href = link; linkEl.innerText = link;
    document.getElementById('client-yaml-section').scrollIntoView({ behavior: "smooth" });
  }catch(err){ console.error(err); alert("Błąd generowania: " + err.message); }
}

// --- YAML GENERATORS ---
function buildHeader(title){
  return [
    "# --- JOAN 6 E-INK DASHBOARD ---",
    `# File: ${title.toLowerCase().replace(/\s+/g,'_')}.dash`,
    "# Location: \\\\IP_HA\\addon_configs\\appdaemon\\dashboards\\",
    "# --------------------------------", "",
    `title: ${title}`, "widget_dimensions: [117, 117]", "widget_size: [2, 1]", "widget_margins: [8, 8]", "columns: 6", `rows: ${(rows.length||8)} # auto`,
    "global_parameters:", "  refresh: 0", "  use_comma: 0", "  precision: 1", "  use_hass_icon: 1", "  namespace: default",
    "  state_text: 1", "  white_text_style: \"color: #000000 !important; font-weight: 700 !important;\"",
    "  state_text_style: \"color: #000000 !important; font-weight: 700 !important; font-size: 16px !important;\"",
    "  widget_style: \"color: #000000 !important; background-color: #FFFFFF !important; border: 2px solid #000000 !important;\"",
    "skin: simplyred", "", "layout:"
  ].join("\n");
}
function buildLayout(){ return rows.map(r=>"  - "+r.map(w=>w.id+(w.size? " "+w.size:"")).join(", ")).join("\n"); }
function buildWidgetsSection(){
  const seen = new Set(); const defs = []; defs.push("# --- DEFINICJE WIDŻETÓW ---");
  rows.flat().forEach(w => { if(seen.has(w.id)) return; seen.add(w.id); defs.push(widgetYaml(w)); });
  return defs.join("\n\n");
}
function widgetYaml(w){
  const t=i18n[currentLang];
  const lines=[];
  lines.push(`${w.id}:`);
  lines.push(`  widget_type: ${w.type==='fan'?'switch':w.type}`);
  if(w.type==='navigate'){
    lines.push(`  title: "${w.name.replace(/"/g,'\\"')}"`); lines.push(`  dashboard: ${w.id.replace('navigate.','')}`);
    lines.push(`  icon_inactive: ${ensureMdi(w.icon||'mdi-arrow-right-circle')}`);
    lines.push(`  title_style: "color:#000; font-size:24px; font-weight:700; text-align:center; padding-top:5px; width:100%;"`);
    lines.push(`  widget_style: "background-color:#FFFFFF !important; border-radius:8px !important; padding:10px !important; color:#000 !important;"`);
    return lines.join("\n");
  }
  if(w.type==='label'){
    lines.push(`  text: "${w.name.replace(/"/g,'\\"')}"`);
    lines.push(`  widget_style: "background-color:#FFFFFF !important; color:#000 !important;"`);
    lines.push(`  text_style: "color:#000 !important; font-size:24px; font-weight:bold;"`);
    return lines.join("\n");
  }
  if(w.type==='clock'){
    lines.push(`  time_format: 24hr`); lines.push(`  show_seconds: 0`);
    lines.push(`  date_style: "color:#000 !important;"`); lines.push(`  time_style: "color:#000 !important; font-size:40px !important;"`);
    lines.push(`  widget_style: "background-color:#FFFFFF !important; color:#000 !important;"`);
    return lines.join("\n");
  }
  lines.push(`  entity: ${w.id}`); lines.push(`  title: "${w.name.replace(/"/g,'\\"')}"`);
  const actionable = ['switch','binary_sensor','cover','media_player','climate','script','fan','light','lock'].includes(w.type) || w.id.startsWith('input_boolean.');
  if(actionable){
    const pair = findIconPairById(w.id);
    lines.push(`  icon_on: ${ensureMdi(w.icon_on||pair[0])}`); lines.push(`  icon_off: ${ensureMdi(w.icon_off||pair[1])}`);
    lines.push(`  state_text: 1`);
    lines.push(`  title_style: "color:#000; font-size:20px; font-weight:700; text-align:center; padding-top:3px; width:100%;"`);
    lines.push(`  text_style: "color:#000 !important; font-weight:700 !important;"`);
    lines.push(`  widget_style: "color:#000 !important; background-color:#FFFFFF !important; border:2px solid #000 !important;"`);
    lines.push(`  state_map:`);
    if(w.type==='cover'){ lines.push(`    "open": "${t.state_open}"`); lines.push(`    "closed": "${t.state_closed}"`); }
    else if(w.type==='lock'){ lines.push(`    "locked": "${t.state_locked}"`); lines.push(`    "unlocked": "${t.state_unlocked}"`); }
    else { lines.push(`    "on": "${t.state_on}"`); lines.push(`    "off": "${t.state_off}"`); }
    lines.push(`  icon_style_active: "color:#000 !important;"`); lines.push(`  icon_style_inactive: "color:#000 !important;"`);
  } else if(w.type==='sensor'){
    lines.push(`  icon: ${ensureMdi(w.icon||findBaseIconByIdAndType(w.id,'sensor'))}`);
    lines.push(`  title_style: "color:#000; font-size:20px; font-weight:700; text-align:center; padding-top:5px; width:100%;"`);
    lines.push(`  text_style: "color:#000 !important;"`);
    lines.push(`  value_style: "color:#000 !important; font-size:44px !important; font-weight:700 !important;"`);
    lines.push(`  unit_style: "color:#000 !important;"`);
    lines.push(`  widget_style: "color:#000 !important; background-color:#FFFFFF !important;"`);
  } else {
    lines.push(`  icon: ${ensureMdi(w.icon||findBaseIconByIdAndType(w.id,w.type))}`);
    lines.push(`  title_style: "color:#000; font-size:20px; font-weight:700; text-align:center; padding-top:3px; width:100%;"`);
    lines.push(`  widget_style: "color:#000 !important; background-color:#FFFFFF !important;"`);
  }
  return lines.join("\n");
}

// Init
window.addEventListener('DOMContentLoaded', ()=>{
  const host=window.location.hostname;
  document.getElementById('client-path-code').innerText = document.getElementById('client-path-code').innerText.replace('IP_HA', host);
  const linkDash=document.getElementById('client-dashboard-link');
  if(linkDash){ linkDash.href = linkDash.href.replace('IP_HA', host); linkDash.innerText = linkDash.innerText.replace('IP_HA', host); }
  const savedLang = localStorage.getItem('joan_lang') || 'pl';
  const savedTheme = localStorage.getItem('joan_theme') || 'light';
  updateWidgetTypeOptions(savedLang);
  setLang(savedLang);
  if(savedTheme==='dark'){ document.body.classList.add('dark-mode'); document.getElementById('btn-theme').innerText='☀️'; }
  fetchIcons();
  if(!rows.length) addNewRow();
  applySmartForForm(false);
  renderRows();
});

// Helper to populate dropdown (MUST BE CALLED)
function updateWidgetTypeOptions(lang) {
  const select = document.getElementById('new-widget-type');
  const currentVal = select.value; 
  select.innerHTML = '';
  widgetTypesConfig.forEach(type => {
    const opt = document.createElement('option');
    opt.value = type.value;
    opt.innerText = (lang === 'pl') ? type.pl : type.en;
    select.appendChild(opt);
  });
  if(currentVal) select.value = currentVal; else select.value = 'switch';
}
</script>
</body>
</html>
