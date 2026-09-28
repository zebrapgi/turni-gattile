from datetime import datetime, timedelta, time
import json
import os
import uuid
import pandas as pd
import pytz
import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore

st.set_page_config(
    page_title="Gestione Turni Gattile", page_icon="🐱", layout="wide"
)

# --- INIZIALIZZAZIONE FIREBASE FIRESTORE SICURA ---
if not firebase_admin._apps:
    try:
        cred_dict = dict(st.secrets["firebase"])
        if "private_key" in cred_dict:
            cred_dict["private_key"] = cred_dict["private_key"].replace("\\n", "\n")
        cred = credentials.Certificate(cred_dict)
        firebase_admin.initialize_app(cred)
    except Exception as e:
        st.error(f"Errore di connessione a Firebase: {e}")
        st.stop()

db = firestore.client()

# --- FUNZIONI DI GESTIONE DATABASE FIRESTORE (PULITE E STANDARD) ---
def carica_da_firestore(collezione_nome, default_val):
    try:
        docs = list(db.collection(collezione_nome).stream())
        
        if collezione_nome == "gattile_data":
            for doc in docs:
                diz = doc.to_dict()
                if "data" in diz:
                    val_data = diz["data"]
                    if isinstance(val_data, list):
                        return {box: [] for box in val_data}
                    elif isinstance(val_data, dict):
                        return val_data
            return default_val
            
        elif collezione_nome == "volontari_gattile":
            data = {doc.id: doc.to_dict() for doc in docs}
            if "lista" in data:
                return data["lista"].get("elementi", default_val)
            return default_val
            
        elif collezione_nome == "lpu_data_gattile":
            data = {doc.id: doc.to_dict() for doc in docs}
            return data if data else default_val
            
        elif collezione_nome == "turni_gattile" or collezione_nome == "turni_lpu_gattile":
            tutti_i_turni = []
            for doc in docs:
                doc_data = doc.to_dict()
                if isinstance(doc_data, dict) and doc_data:
                    if "id" not in doc_data:
                        doc_data["id"] = doc.id
                    tutti_i_turni.append(doc_data)
            return tutti_i_turni if tutti_i_turni else default_val
            
        return default_val
    except Exception as e:
        st.error(f"Errore di caricamento: {e}")
        return default_val

def salva_su_firestore(collezione_nome, doc_id, data_dict):
    try:
        db.collection(collezione_nome).document(str(doc_id)).set(data_dict)
        return True
    except Exception as e:
        st.error(f"Errore di salvataggio su Firebase: {e}")
        return False

def elimina_da_firestore(collezione_nome, doc_id):
    try:
        db.collection(collezione_nome).document(str(doc_id)).delete()
        return True
    except Exception as e:
        st.error(f"Errore di eliminazione: {e}")
        return False

# Inizializzazione stato con Firebase
BOX_DEFAULT = {
    "🔴 Box rosso": [],
    "🔵 Box blu": [],
    "🏠 Box Castioni": [],
    "🟡 Box giallo": [],
    "🟠 Box arancione": [],
    "🟢 Box verde": [],
    "🌿 Esterni (oasi felina)": [],
    "🩺 Infermieria": [],
    "🍼 Nursery": [],
}

if "struttura_box" not in st.session_state:
    box_caricati = carica_da_firestore("gattile_data", None)
    if box_caricati and isinstance(box_caricati, dict):
        st.session_state.struttura_box = box_caricati
    else:
        st.session_state.struttura_box = BOX_DEFAULT

if "volontari_db_gattile" not in st.session_state:
    vol_caricati = carica_da_firestore("volontari_gattile", None)
    if vol_caricati and isinstance(vol_caricati, list):
        st.session_state.volontari_db_gattile = vol_caricati
    else:
        turni_temp = carica_da_firestore("turni_gattile", [])
        nomi_iniziali = sorted(list(set(t.get("volontario", "").strip() for t in turni_temp if t.get("volontario"))))
        st.session_state.volontari_db_gattile = nomi_iniziali
        db.collection("volontari_gattile").document("lista").set({"elementi": nomi_iniziali})

if "lpu_data" not in st.session_state:
    lpu_caricati = list(db.collection("lpu_data_gattile").stream())
    lpu_dict = {doc.id: doc.to_dict() for doc in lpu_caricati}
    st.session_state.lpu_data = lpu_dict if lpu_dict else {}

if "turni_lpu" not in st.session_state:
    turni_lpu_docs = list(db.collection("turni_lpu_gattile").stream())
    st.session_state.turni_lpu = [doc.to_dict() for doc in turni_lpu_docs]

if "turni" not in st.session_state:
    st.session_state.turni = carica_da_firestore("turni_gattile", [])

if "is_admin" not in st.session_state:
    st.session_state.is_admin = False

# --- GESTIONE ORARIO ITALIANO ESATTO ---
tz_italia = pytz.timezone("Europe/Rome")
adesso = datetime.now(tz_italia)
giorno_settimana = adesso.weekday()
ora_attuale = adesso.hour

is_weekend_reale = (giorno_settimana > 4) or (
    giorno_settimana == 4 and ora_attuale >= 17
)
is_weekend_o_venerdi_sera = is_weekend_reale

# --- FUNZIONE GESTIONE INTERVALLI E CHIAVI SETTIMANA (ISO WEEKS) ---
def get_info_settimane():
    oggi = datetime.now(tz_italia)
    lunedi_corrente = oggi - timedelta(days=oggi.weekday())
    domenica_corrente = lunedi_corrente + timedelta(days=6)

    lunedi_prossimo = lunedi_corrente + timedelta(days=7)
    domenica_prossima = domenica_corrente + timedelta(days=7)

    fmt = "%d/%m/%Y"
    
    anno_corr, num_sett_corr, _ = oggi.isocalendar()
    chiave_corr = f"{anno_corr}-W{num_sett_corr:02d}"
    
    data_prossima = oggi + timedelta(days=7)
    anno_pros, num_sett_pros, _ = data_prossima.isocalendar()
    chiave_pros = f"{anno_pros}-W{num_sett_pros:02d}"

    label_corr = f"Settimana Corrente ({lunedi_corrente.strftime(fmt)} - {domenica_corrente.strftime(fmt)})"
    label_pros = f"Prossima Settimana ({lunedi_prossimo.strftime(fmt)} - {domenica_prossima.strftime(fmt)})"

    return {
        chiave_corr: label_corr,
        chiave_pros: label_pros,
        "chiave_corr": chiave_corr,
        "chiave_pros": chiave_pros,
        "label_corr": label_corr,
        "label_pros": label_pros
    }

info_sett = get_info_settimane()
label_corr = info_sett["label_corr"]
label_pros = info_sett["label_pros"]
chiave_corr = info_sett["chiave_corr"]
chiave_pros = info_sett["chiave_pros"]

# --- BARRA LATERALE (SIDEBAR) ---
with st.sidebar:
    st.title("🐱 Menu Rapido")
    
    with st.expander("🔍 Cerca i miei turni", expanded=False):
        turni_esistenti_side = carica_da_firestore("turni_gattile", [])
        nomi_side = sorted(list(set(t.get("volontario", "").strip() for t in turni_esistenti_side if t.get("volontario"))))
        
        if not nomi_side:
            st.info("Nessun turno registrato nel sistema.")
        else:
            nome_cercato_side = st.selectbox("Seleziona il tuo nome:", nomi_side, key="selettore_miei_turni_sidebar_gatti")
            turni_pers_side = [t for t in turni_esistenti_side if t.get("volontario", "").strip().lower() == nome_cercato_side.lower()]
            
            if not turni_pers_side:
                st.write("Nessun turno trovato.")
            else:
                for tp in turni_pers_side:
                    box_str = ", ".join(tp.get("box_fatti", []))
                    if box_str:
                        dettaglio_str = f"📦 [{box_str}]"
                    else:
                        dettaglio_str = "🧹 *Pulizie / LPU*"
                    
                    s_key = tp.get("settimana_chiave", tp.get("settimana"))
                    s_label = info_sett.get(s_key, f"Settimana {s_key}")
                    
                    st.markdown(f"• **{s_label}**<br>📅 {tp.get('giorno')} ({tp.get('fascia')})<br>⏰ {tp.get('orario')}<br>{dettaglio_str}", unsafe_allow_html=True)
                    st.markdown("---")

    st.markdown("---")

    with st.expander("🎛️ Filtra Panoramica", expanded=False):
        tutti_i_box_presenti = sorted(list(st.session_state.struttura_box.keys()))
        filtro_box = st.selectbox("Filtra per box:", ["Tutti i box"] + tutti_i_box_presenti, key="filtro_box_side")
        
        turni_temp = carica_da_firestore("turni_gattile", [])
        tutti_i_volontari = sorted(list(set(t.get("volontario") for t in turni_temp if t.get("volontario"))))
        filtro_volontario = st.selectbox("Filtra per volontario:", ["Tutti i volontari"] + tutti_i_volontari, key="filtro_vol_side_gatti")

    st.markdown("---")

    with st.expander("🔒 Area Admin", expanded=False):
        ADMIN_PASSWORD_CORRETTA = st.secrets.get("ADMIN_PASSWORD", "gattile2026")
        if not st.session_state.is_admin:
            with st.form("form_login_admin_side_gatti"):
                pwd_input = st.text_input("Password:", type="password", key="pwd_side_gatti")
                btn_login = st.form_submit_button("Sblocca")
                if btn_login:
                    if pwd_input == ADMIN_PASSWORD_CORRETTA:
                        st.session_state.is_admin = True
                        st.success("Sbloccato!")
                        st.rerun()
                    else:
                        st.error("Errata.")
        else:
            st.success("🔓 Admin attivo")
            scelta_simulazione = st.selectbox(
                "Simulazione:",
                [
                    "📅 Automatico",
                    "⚠️ Simula Weekend",
                    "🟢 Simula Feriale",
                ],
                key="selettore_simulazione_side_gatti",
            )

            if scelta_simulazione == "⚠️ Simula Weekend":
                is_weekend_o_venerdi_sera = True
            elif scelta_simulazione == "🟢 Simula Feriale":
                is_weekend_o_venerdi_sera = False
            else:
                is_weekend_o_venerdi_sera = is_weekend_reale

            if st.button("🔒 Esci Admin", key="esci_admin_side_gatti"):
                st.session_state.is_admin = False
                st.rerun()

# --- INTESTAZIONE PRINCIPALE ---
st.title("🐱 Turni Gattile")

with st.container():
    turni_notifiche = carica_da_firestore("turni_gattile", [])
    
    giorni_map_ita = ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato", "Domenica"]
    giorno_oggi_str = giorni_map_ita[adesso.weekday()]
    
    turni_oggi = [
        t for t in turni_notifiche 
        if t.get("giorno") == giorno_oggi_str and t.get("settimana_chiave") == chiave_corr
    ]
    
    turni_coperti_oggi = len(turni_oggi)
    totale_turni_previsti = 7
    turni_scoperti_oggi = max(0, totale_turni_previsti - turni_coperti_oggi)

    if turni_scoperti_oggi > 0:
        with st.expander("🔔 Avis Gattile del Giorno", expanded=True):
            st.warning(f"⚠️ **Attenzione ({giorno_oggi_str}):** Mancano {turni_scoperti_oggi} turni scoperti oggi (totale registrati: {turni_coperti_oggi}/{totale_turni_previsti})[cite: 2].")

# --- MENU PRINCIPALE IN ALTO ---
opzioni_base = [
    "📅 Inserisci",
    "👀 Panoramica",
    "📦 Box & Gatti",
    "📊 Statistiche",
    "📚 Archivio",
]

if st.session_state.is_admin:
    opzioni_menu = opzioni_base + ["👥 Volontari", "🛠️ Gestione LPU (Admin)"]
else:
    opzioni_menu = opzioni_base

menu = st.pills("Seleziona sezione:", opzioni_menu, default=opzioni_menu[0])
st.markdown("---")

if is_weekend_o_venerdi_sera:
    st.warning(
        "⚠️ **Promemoria Gattile:** È iniziato il fine settimana! Ricordati di"
        " selezionare la **'Prossima Settimana'** qui sotto per inserire i tuoi"
        " turni per la settimana che sta per arrivare."
    )

def get_lista_volontari():
    return sorted(list(set(st.session_state.volontari_db_gattile)))

def get_box_frequenti_volontario(nome_volontario):
    if not nome_volontario or nome_volontario == "➕ Altro / Nuovo volontario" or nome_volontario == "-- Seleziona il tuo nome --":
        return []
    
    turni_esistenti = carica_da_firestore("turni_gattile", [])
    conteggio_box = {}
    
    for t in turni_esistenti:
        if t.get("volontario", "").strip().lower() == nome_volontario.strip().lower():
            for b in t.get("box_fatti", []):
                if b in st.session_state.struttura_box:
                    conteggio_box[b] = conteggio_box.get(b, 0) + 1
                    
    box_ordinati = sorted(conteggio_box.items(), key=lambda x: x[1], reverse=True)
    return [b[0] for b in box_ordinati if b[1] >= 1]

if menu == "📅 Inserisci":
    st.header("Gestione Turni")

    if is_weekend_o_venerdi_sera:
        opzioni_settimana_scelta = [label_corr, label_pros]
        chiavi_mappa_scelta = {label_corr: chiave_corr, label_pros: chiave_pros}
    else:
        opzioni_settimana_scelta = [label_corr]
        chiavi_mappa_scelta = {label_corr: chiave_corr}

    settimana_scelta_label = st.radio(
        "Per quale settimana vuoi inserire il turno?",
        opzioni_settimana_scelta,
        horizontal=True,
    )
    settimana_scelta_chiave = chiavi_mappa_scelta[settimana_scelta_label]

    volontari_registrati = get_lista_volontari()

    st.markdown("### 👤 1. Il tuo Nome")
    scelte_volontario = ["-- Seleziona il tuo nome --"] + volontari_registrati + ["➕ Altro / Nuovo volontario"]
    
    scelta_volontario_dropdown = st.selectbox("Seleziona o inserisci il tuo Nome e Cognome:", scelte_volontario, key="selettore_nome_principale_gatti")
    
    volontario_finale = ""
    if scelta_volontario_dropdown == "➕ Altro / Nuovo volontario":
        volontario_nuovo_input = st.text_input("Scrivi qui il tuo Nome e Cognome:", key="input_nuovo_volontario_libero_gatti")
        volontario_finale = volontario_nuovo_input.strip()
    elif scelta_volontario_dropdown != "-- Seleziona il tuo nome --":
        volontario_finale = scelta_volontario_dropdown

    st.markdown("---")

    col_f1, col_f2 = st.columns(2)
    with col_f1:
        giorno = st.selectbox(
            "Giorno della settimana:",
            [
                "Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato", "Domenica",
            ],
            key="giorno_form_dinamico_gatti"
        )
    with col_f2:
        fascia = st.selectbox(
            "Fascia oraria:", 
            ["Mattina", "Pomeriggio"], 
            key="selettore_fascia_form_gatti"
        )

    if fascia == "Mattina":
        default_inizio = time(8, 30)
        default_fine = time(12, 0)
    else:
        default_inizio = time(14, 30)
        default_fine = time(18, 0)

    st.markdown("### 🕒 2. Dettagli Turno e Box")
    col1, col2 = st.columns(2)

    with col1:
        st.markdown(f"**Orario per {fascia}:**")

        col_ora1, col_ora2 = st.columns(2)
        with col_ora1:
            ora_inizio = st.time_input("Da:", value=default_inizio, key=f"ora_inizio_dinamica_gatti_{fascia}")
        
        senza_fine = st.checkbox("Senza orario di fine (da quest'ora in poi)", key="senza_fine_dinamico_gatti")

        with col_ora2:
            if not senza_fine:
                ora_fine = st.time_input("A:", value=default_fine, key=f"ora_fine_dinamica_gatti_{fascia}")
            else:
                st.markdown("<br><i>Nessun limite</i>", unsafe_allow_html=True)
        
        if senza_fine:
            orario = f"Dalle {ora_inizio.strftime('%H:%M')}"
        else:
            orario = f"{ora_inizio.strftime('%H:%M')} - {ora_fine.strftime('%H:%M')}"

    with col2:
        note = st.text_area("Note aggiuntive (opzionale):", key="note_dinamiche_gatti")

    lista_nomi_box = list(st.session_state.struttura_box.keys())
    box_suggeriti = get_box_frequenti_volontario(volontario_finale)

    col_box_op1, col_box_op2 = st.columns([1, 1])
    with col_box_op1:
        seleziona_tutti = st.checkbox("📦 Seleziona TUTTI i box", key="seleziona_tutti_dinamico_gatti")
    with col_box_op2:
        if box_suggeriti:
            st.caption(f"💡 Suggerimento abitudini: {', '.join(box_suggeriti)}")

    if seleziona_tutti:
        box_fatti = st.multiselect(
            "✅ Box / Zone di cui ti occupi (obbligatorio selezionarne almeno uno):",
            lista_nomi_box,
            default=lista_nomi_box,
            key="multiselect_box_tutti"
        )
    elif box_suggeriti:
        box_fatti = st.multiselect(
            "✅ Box / Zone di cui ti occupi (obbligatorio selezionarne almeno uno):",
            lista_nomi_box,
            default=box_suggeriti,
            key="multiselect_box_sugg"
        )
    else:
        box_fatti = st.multiselect(
            "✅ Box / Zone di cui ti occupi (obbligatorio selezionarne almeno uno):", 
            lista_nomi_box,
            key="multiselect_box_vuoto"
        )

    submit_button = st.button(label="Registra Turno 🚀", key="btn_submit_turno_gatti")

    if submit_button:
        ora_limite_divisione = time(14, 0)
        errore_fascia = False
        
        if fascia == "Mattina" and ora_inizio >= ora_limite_divisione:
            st.error("❌ **Errore:** Hai scelto la fascia **Mattina**, ma l'orario di inizio è pomeridiano (dalle 14:00 in poi).")
            errore_fascia = True
        elif fascia == "Pomeriggio" and ora_inizio < ora_limite_divisione:
            st.error("❌ **Errore:** Hai scelto la fascia **Pomeriggio**, ma l'orario di inizio è mattutino (prima delle 14:00).")
            errore_fascia = True

        if not errore_fascia:
            if not volontario_finale:
                st.warning("⚠️ Per favore, seleziona il tuo nome dal menu a tendina o scrivi il tuo nome e cognome nell'apposita casella in alto prima di registrare.")
            elif not box_fatti:
                st.error("❌ **Errore:** Devi selezionare almeno un box per poter registrare il turno!")
            else:
                if volontario_finale not in st.session_state.volontari_db_gattile:
                    st.session_state.volontari_db_gattile.append(volontario_finale)
                    db.collection("volontari_gattile").document("lista").set({"elementi": st.session_state.volontari_db_gattile})

                lista_turni = carica_da_firestore("turni_gattile", [])
                
                volontario_normalizzato = volontario_finale.strip().lower()
                doppione_trovato = any(
                    t.get("volontario", "").strip().lower() == volontario_normalizzato and
                    t.get("settimana_chiave") == settimana_scelta_chiave and
                    t.get("giorno") == giorno and
                    t.get("fascia") == fascia
                    for t in lista_turni
                )

                if doppione_trovato:
                    st.error(f"⚠️ **Attenzione:** {volontario_finale} risulta già registrato per {giorno} ({fascia}) in questa settimana!")
                else:
                    id_turno = str(int(datetime.now().timestamp() * 1000))
                    nuovo_turno = {
                        "id": id_turno,
                        "settimana": settimana_scelta_label,
                        "settimana_chiave": settimana_scelta_chiave,
                        "volontario": volontario_finale,
                        "giorno": giorno,
                        "fascia": fascia,
                        "orario": orario,
                        "box_fatti": box_fatti,
                        "note": note,
                    }
                    if salva_su_firestore("turni_gattile", id_turno, nuovo_turno):
                        st.toast(f"Turno registrato con successo per {volontario_finale}!", icon="🎉")
                        st.rerun()

elif menu == "👀 Panoramica":
    st.header("Gestione Turni e Copertura Giornaliera")

    turni_attuali = carica_da_firestore("turni_gattile", [])

    if is_weekend_o_venerdi_sera:
        scelte_visualizzazione = [label_corr, label_pros]
        mappa_scelte_vis = {label_corr: chiave_corr, label_pros: chiave_pros}
    else:
        scelte_visualizzazione = [label_corr]
        mappa_scelte_vis = {label_corr: chiave_corr}

    settimana_vista_label = st.radio(
        "Seleziona la settimana da visualizzare:",
        scelte_visualizzazione,
        horizontal=True,
    )
    settimana_vista_chiave = mappa_scelte_vis[settimana_vista_label]

    turni_filtrati = [
        t for t in turni_attuali if t.get("settimana_chiave") == settimana_vista_chiave
    ]

    if st.session_state.get("filtro_box_side", "Tutti i box") != "Tutti i box":
        box_scelto = st.session_state["filtro_box_side"]
        turni_filtrati = [t for t in turni_filtrati if box_scelto in t.get("box_fatti", [])]

    if st.session_state.get("filtro_vol_side_gatti", "Tutti i volontari") != "Tutti i volontari":
        vol_scelto = st.session_state["filtro_vol_side_gatti"]
        turni_filtrati = [t for t in turni_filtrati if str(t.get("volontario", "")).strip().lower() == vol_scelto.strip().lower()]

    if not turni_filtrati:
        st.info("Nessun turno trovato con i filtri selezionati per questo periodo.")
    else:
        giorni_settimana = [
            "Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato", "Domenica",
        ]

        lista_tutti_box = list(st.session_state.struttura_box.keys())

        for giorno in giorni_settimana:
            turni_giorno = [t for t in turni_filtrati if t.get("giorno") == giorno]
            if not turni_giorno:
                continue
                
            st.markdown(f"## 📌 {giorno}")

            col_m, col_p = st.columns(2)

            def mostra_fascia_calendario(fascia_nome, col_container):
                with col_container:
                    with st.container(border=True):
                        icona_fascia = "🌅" if fascia_nome == "Mattina" else "🌇"
                        st.markdown(f"### {icona_fascia} {fascia_nome}")
                        
                        turni_fascia = [
                            t for t in turni_giorno if t.get("fascia") == fascia_nome
                        ]

                        if not turni_fascia:
                            st.caption("Nessun volontario registrato.")
                        else:
                            st.markdown("**Volontari presenti:**")
                            for t in turni_fascia:
                                box_str = ", ".join(t.get("box_fatti", [])) if t.get("box_fatti") else ""
                                if box_str:
                                    dettaglio_mostra = f"📦 [{box_str}]"
                                else:
                                    dettaglio_mostra = "🧹 *Pulizie / LPU*"

                                st.write(
                                    f"• **{t.get('volontario')}** ({t.get('orario', '')}) {dettaglio_mostra}"
                                )
                                if t.get("note"):
                                    st.caption(f"Note: {t.get('note')}")

                                if st.session_state.is_admin:
                                    col_mod, col_del = st.columns(2)
                                    with col_mod:
                                        if not str(t.get('id', '')).startswith("lpu_"):
                                            if st.button(
                                                f"✏️ Modifica ({t.get('volontario')})",
                                                key=f"mod_btn_gatti_{giorno}_{fascia_nome}_{t.get('id')}",
                                            ):
                                                st.session_state[f"editing_{t.get('id')}"] = not st.session_state.get(f"editing_{t.get('id')}", False)
                                                st.rerun()
                                    with col_del:
                                        with st.popover(f"🗑️ Elimina ({t.get('volontario')})"):
                                            st.write("Confermi l'eliminazione?")
                                            if st.button("Conferma 🛑", key=f"conf_del_gatti_{t.get('id')}"):
                                                tid = t.get('id')
                                                if str(tid).startswith("lpu_"):
                                                    orig_id = str(tid).replace("lpu_", "")
                                                    tutti_lpu = carica_da_firestore("turni_lpu_gattile", [])
                                                    lpu_trovato = next((item for item in tutti_lpu if str(item.get("id")) == orig_id), None)
                                                    if lpu_trovato:
                                                        nome_lp = lpu_trovato.get("lpu")
                                                        ore_st = lpu_trovato.get("ore", 0.0)
                                                        if nome_lp in st.session_state.lpu_data:
                                                            st.session_state.lpu_data[nome_lp]["ore_fatte"] = max(
                                                                0.0, st.session_state.lpu_data[nome_lp]["ore_fatte"] - ore_st
                                                            )
                                                            salva_su_firestore("lpu_data_gattile", nome_lp, st.session_state.lpu_data[nome_lp])
                                                        elimina_da_firestore("turni_lpu_gattile", orig_id)
                                                
                                                elimina_da_firestore("turni_gattile", tid)
                                                if f"editing_{tid}" in st.session_state:
                                                    del st.session_state[f"editing_{tid}"]
                                                st.success("Eliminato!")
                                                st.rerun()

                                    if not str(t.get('id', '')).startswith("lpu_") and st.session_state.get(f"editing_{t.get('id')}", False):
                                        with st.form(key=f"form_mod_gatti_{t.get('id')}"):
                                            st.subheader(f"Modifica Turno di {t.get('volontario')}")
                                            col_m1, col_m2 = st.columns(2)
                                            with col_m1:
                                                m_inizio = st.time_input("Ora Inizio:", value=time(8, 30), key=f"min_gatti_{t.get('id')}")
                                            with col_m2:
                                                m_fine = st.time_input("Ora Fine:", value=time(12, 0), key=f"mfin_gatti_{t.get('id')}")
                                            
                                            nuovo_orario = f"{m_inizio.strftime('%H:%M')} - {m_fine.strftime('%H:%M')}"
                                            nuove_note = st.text_area("Note:", value=t.get("note", ""), key=f"note_mod_gatti_{t.get('id')}")
                                            nuovi_box = st.multiselect(
                                                "Box gestiti:",
                                                lista_tutti_box,
                                                default=[b for b in t.get("box_fatti", []) if b in lista_tutti_box],
                                                key=f"box_mod_gatti_{t.get('id')}"
                                            )
                                            if st.form_submit_button("Salva Modifiche ✅"):
                                                if not nuovi_box:
                                                    st.error("Seleziona almeno un box.")
                                                else:
                                                    t_agg = {
                                                        "id": t.get('id'),
                                                        "settimana": t.get('settimana'),
                                                        "settimana_chiave": t.get('settimana_chiave'),
                                                        "volontario": t.get('volontario'),
                                                        "giorno": t.get('giorno'),
                                                        "fascia": t.get('fascia'),
                                                        "orario": nuovo_orario,
                                                        "box_fatti": nuovi_box,
                                                        "note": nuove_note
                                                    }
                                                    salva_su_firestore("turni_gattile", t.get('id'), t_agg)
                                                    st.session_state[f"editing_{t.get('id')}"] = False
                                                    st.success("Modificato con successo!")
                                                    st.rerun()

                            st.markdown("---")
                            st.markdown("**Copertura turni:**")
                            
                            totale_previsti_fascia = 3 if fascia_nome == "Mattina" else 4  # Totale 7 turni giornalieri suddivisi
                            turni_registrati_fascia = len(turni_fascia)
                            turni_scoperti_fascia = max(0, totale_previsti_fascia - turni_registrati_fascia)

                            if turni_scoperti_fascia > 0:
                                st.error(f"❌ Mancano **{turni_scoperti_fascia} turni** scoperti in questa fascia (registrati {turni_registrati_fascia}/{totale_previsti_fascia})[cite: 2].")
                            else:
                                st.success("Tutti i turni di questa fascia sono coperti![cite: 2]")

            with col_m:
                mostra_fascia_calendario("Mattina", col_m)
            with col_p:
                mostra_fascia_calendario("Pomeriggio", col_p)

            st.markdown("---")

elif menu == "📦 Box & Gatti":
    st.header("Anagrafica Box e Gatti")

    if not st.session_state.is_admin:
        st.warning("🔒 Sezione protetta. Apri l'area 'Admin' nella barra laterale.")
        for nome_box, lista_gatti in st.session_state.struttura_box.items():
            gatti_str = ", ".join(lista_gatti) if lista_gatti else "Nessun gatto"
            st.markdown(f"📦 **{nome_box}** - 🐱 Gatti: {gatti_str}")
    else:
        new_box = st.text_input("Nome del nuovo box:")
        new_gatti = st.text_input("Gatti presenti (separati da virgola):")
        if st.button("Aggiungi Box"):
            if new_box.strip() and new_box.strip() not in st.session_state.struttura_box:
                lista_g = [g.strip() for g in new_gatti.split(",") if g.strip()]
                st.session_state.struttura_box[new_box.strip()] = lista_g
                db.collection("gattile_data").document("struttura").set({"data": st.session_state.struttura_box})
                st.success(f"Box '{new_box}' aggiunto!")
                st.rerun()

        for nome_box, lista_gatti in list(st.session_state.struttura_box.items()):
            col_b1, col_b2 = st.columns([4, 1])
            with col_b1:
                gatti_str = ", ".join(lista_gatti) if lista_gatti else "Nessun gatto"
                st.markdown(f"📦 **{nome_box}** - 🐱 Gatti: {gatti_str}")
            with col_b2:
                with st.popover("Elimina"):
                    if st.button("Conferma", key=f"conf_del_box_{nome_box}"):
                        del st.session_state.struttura_box[nome_box]
                        db.collection("gattile_data").document("struttura").set({"data": st.session_state.struttura_box})
                        st.success("Eliminato.")
                        st.rerun()

elif menu == "👥 Volontari":
    st.header("Gestione Anagrafica Volontari")

    if not st.session_state.is_admin:
        st.error("Area riservata agli amministratori.")
    else:
        new_vol = st.text_input("Aggiungi manualmente un volontario:")
        if st.button("Aggiungi Volontario"):
            if new_vol.strip() and new_vol.strip() not in st.session_state.volontari_db_gattile:
                st.session_state.volontari_db_gattile.append(new_vol.strip())
                db.collection("volontari_gattile").document("lista").set({"elementi": st.session_state.volontari_db_gattile})
                st.success("Aggiunto!")
                st.rerun()

        for vol in sorted(st.session_state.volontari_db_gattile):
            col_v1, col_v2 = st.columns([4, 1])
            with col_v1:
                st.write(f"👤 **{vol}**")
            with col_v2:
                with st.popover("Elimina", key=f"pop_del_vol_{vol}"):
                    if st.button("Conferma", key=f"conf_del_vol_{vol}"):
                        st.session_state.volontari_db_gattile.remove(vol)
                        db.collection("volontari_gattile").document("lista").set({"elementi": st.session_state.volontari_db_gattile})
                        st.success("Rimosso.")
                        st.rerun()

elif menu == "📊 Statistiche":
    st.header("📊 Statistiche Presenze Box")
    
    tutti_i_turni = carica_da_firestore("turni_gattile", [])
    
    settimane_map_stat = {}
    for t in tutti_i_turni:
        s_chiave = t.get("settimana_chiave", "")
        s_label = t.get("settimana", s_chiave)
        if s_chiave:
            settimane_map_stat[s_chiave] = s_label

    if chiave_corr not in settimane_map_stat:
        settimane_map_stat[chiave_corr] = label_corr
    if is_weekend_o_venerdi_sera and chiave_pros not in settimane_map_stat:
        settimane_map_stat[chiave_pros] = label_pros

    scelta_chiave_stat = st.selectbox(
        "Seleziona settimana da analizzare:",
        options=list(settimane_map_stat.keys()),
        format_func=lambda x: settimane_map_stat.get(x, x)
    )

    turni_stat = [
        t for t in tutti_i_turni if t.get("settimana_chiave") == scelta_chiave_stat
    ]

    presenze_per_box = {box: 0 for box in st.session_state.struttura_box.keys()}
    giorni_settimana = ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato", "Domenica"]

    for giorno in giorni_settimana:
        for fascia in ["Mattina", "Pomeriggio"]:
            turni_fascia = [
                t for t in turni_stat
                if t.get("giorno") == giorno and t.get("fascia") == fascia
            ]
            box_in_questa_fascia = set()
            for t in turni_fascia:
                for b in t.get("box_fatti", []):
                    box_in_questa_fascia.add(b)

            for b in box_in_questa_fascia:
                if b in presenze_per_box:
                    presenze_per_box[b] += 1

    if not st.session_state.struttura_box:
        st.info("Nessun box registrato.")
    else:
        st.markdown("---")
        cols = st.columns(3)
        lista_box_ordinata = sorted(presenze_per_box.items(), key=lambda x: x[1], reverse=True)

        for idx, (box, conteggio) in enumerate(lista_box_ordinata):
            col_corrente = cols[idx % 3]
            with col_corrente:
                st.metric(label=f"📦 {box}", value=f"{conteggio} turni")

        st.markdown("---")
        col_grafico, col_tabella = st.columns([1.5, 1])

        with col_grafico:
            st.subheader("📈 Grafico a Barre")
            df_stat = pd.DataFrame(list(presenze_per_box.items()), columns=["Box", "Numero Turni"]).set_index("Box")
            st.bar_chart(df_stat)

        with col_tabella:
            st.subheader("📋 Tabella Dati")
            df_tabella = pd.DataFrame(list(presenze_per_box.items()), columns=["Box", "Turni"]).sort_values(by="Turni", ascending=False).reset_index(drop=True)
            st.dataframe(df_tabella, use_container_width=True)

elif menu == "📚 Archivio":
    st.header("📚 Archivio Storico")
    
    tutti_i_turni = carica_da_firestore("turni_gattile", [])
    
    settimane_archivio_map = {}
    for t in tutti_i_turni:
        s_chiave = t.get("settimana_chiave", "")
        s_label = t.get("settimana", s_chiave)
        if s_chiave and s_chiave != chiave_corr and s_chiave != chiave_pros:
            settimane_archivio_map[s_chiave] = s_label

    chiavi_storiche_ordinate = sorted(list(settimane_archivio_map.keys()), reverse=True)

    if not chiavi_storiche_ordinate:
        st.info("Nessun dato storico presente.")
    else:
        storico_scelto_chiave = st.selectbox(
            "Seleziona settimana dall'archivio:",
            options=chiavi_storiche_ordinate,
            format_func=lambda x: settimane_archivio_map[x]
        )

        turni_storico = [
            t for t in tutti_i_turni if t.get("settimana_chiave") == storico_scelto_chiave
        ]

        giorni_settimana = ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato", "Domenica"]

        for giorno in giorni_settimana:
            turni_giorno = [t for t in turni_storico if t.get("giorno") == giorno]
            if not turni_giorno:
                continue
            st.markdown(f"## 📌 {giorno}")
            col_m, col_p = st.columns(2)

            def mostra_fascia_storica(fascia_nome, col_container):
                with col_container:
                    with st.container(border=True):
                        st.markdown(f"### ☀️ {fascia_nome}")
                        turni_fascia = [t for t in turni_giorno if t.get("fascia") == fascia_nome]
                        if not turni_fascia:
                            st.caption("Nessun volontario.")
                        else:
                            for t in turni_fascia:
                                box_str = ", ".join(t.get("box_fatti", [])) if t.get("box_fatti") else "🧹 Pulizie / LPU"
                                st.write(f"• **{t.get('volontario')}** ({t.get('orario')}) - {box_str}")
                                if t.get("note"):
                                    st.caption(f"Note: {t.get('note')}")

            with col_m:
                mostra_fascia_storica("Mattina", col_m)
            with col_p:
                mostra_fascia_storica("Pomeriggio", col_p)
            st.markdown("---")

elif menu == "🛠️ Gestione LPU (Admin)":
    st.header("🛠️ Gestione Lavori Socialmente Utili (LPU)")

    if not st.session_state.is_admin:
        st.error("Area riservata agli amministratori.")
    else:
        tab_lpu_anagrafica, tab_lpu_inserisci, tab_lpu_storico = st.tabs(
            [
                "📋 Monte Ore & Ore Mancanti",
                "➕ Assegna Turno LPU",
                "📚 Storico & Modifica Turni LPU",
            ]
        )

        with tab_lpu_anagrafica:
            st.subheader("➕ Aggiungi o Configura un LPU")
            with st.form("form_aggiungi_lpu_gatti"):
                nome_lpu = st.text_input("Nome e Cognome LPU:")
                ore_totali_obbligatorie = st.number_input("Monte ore totale richiesto:", min_value=1.0, value=50.0, step=1.0)

                if st.form_submit_button("Crea / Salva LPU 📝"):
                    if not nome_lpu.strip():
                        st.error("Inserisci un nome valido.")
                    else:
                        nome_pulito = nome_lpu.strip()
                        if nome_pulito not in st.session_state.lpu_data:
                            st.session_state.lpu_data[nome_pulito] = {"ore_totali": float(ore_totali_obbligatorie), "ore_fatte": 0.0}
                        else:
                            st.session_state.lpu_data[nome_pulito]["ore_totali"] = float(ore_totali_obbligatorie)

                        salva_su_firestore("lpu_data_gattile", nome_pulito, st.session_state.lpu_data[nome_pulito])
                        st.success("Salvato con successo!")
                        st.rerun()

            st.markdown("---")
            st.subheader("📋 Monitoraggio Ore LPU")
            lpu_dict = st.session_state.lpu_data
            if not lpu_dict:
                st.info("Nessun LPU registrato.")
            else:
                dati_tabella_lpu = []
                for nome, info in lpu_dict.items():
                    tot = info.get("ore_totali", 0.0)
                    fatte = info.get("ore_fatte", 0.0)
                    mancanti = max(0.0, tot - fatte)
                    dati_tabella_lpu.append({"Nome LPU": nome, "Ore Totali": tot, "Ore Fatte": fatte, "Ore Mancanti": mancanti})

                st.dataframe(pd.DataFrame(dati_tabella_lpu), use_container_width=True)

                for nome in list(lpu_dict.keys()):
                    col_del_lpu, col_btn_lpu = st.columns([3, 1])
                    with col_del_lpu:
                        st.write(f"• **{nome}** (Fatte: {lpu_dict[nome]['ore_fatte']}h / Totali: {lpu_dict[nome]['ore_totali']}h)")
                    with col_btn_lpu:
                        if st.button("Elimina 🗑️", key=f"btn_del_lpu_{nome}"):
                            del lpu_dict[nome]
                            elimina_da_firestore("lpu_data_gattile", nome)
                            st.success("Rimosso.")
                            st.rerun()

        with tab_lpu_inserisci:
            st.subheader("📅 Registra un Turno per LPU")
            lpu_nomi_disponibili = list(st.session_state.lpu_data.keys())

            if not lpu_nomi_disponibili:
                st.warning("Registra prima un LPU nella scheda precedente.")
            else:
                with st.form("form_turno_lpu_gatti"):
                    lpu_scelto = st.selectbox("Seleziona LPU:", lpu_nomi_disponibili)
                    
                    if is_weekend_o_venerdi_sera:
                        opzioni_lpu_labels = [label_corr, label_pros]
                        opzioni_lpu_chiavi = {label_corr: chiave_corr, label_pros: chiave_pros}
                    else:
                        opzioni_lpu_labels = [label_corr]
                        opzioni_lpu_chiavi = {label_corr: chiave_corr}

                    settimana_lpu_label = st.selectbox("Settimana:", opzioni_lpu_labels)
                    settimana_lpu_chiave = opzioni_lpu_chiavi[settimana_lpu_label]

                    giorno_lpu = st.selectbox("Giorno:", ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato", "Domenica"], key="g_lpu")
                    fascia_lpu = st.selectbox("Fascia:", ["Mattina", "Pomeriggio"], key="f_lpu")

                    col_ol1, col_ol2 = st.columns(2)
                    with col_ol1:
                        ora_i_lpu = st.time_input("Ora Inizio:", value=time(8, 30), key="oi_lpu")
                    with col_ol2:
                        ora_f_lpu = st.time_input("Ora Fine:", value=time(12, 0), key="of_lpu")

                    orario_lpu_str = f"{ora_i_lpu.strftime('%H:%M')} - {ora_f_lpu.strftime('%H:%M')}"
                    ore_svolte_val = st.number_input("Ore di lavoro da aggiungere:", min_value=0.5, value=3.5, step=0.5)
                    nota_lpu = st.text_area("Note / Attività:", value="Pulizie generali struttura gattile", key="note_lpu_in")

                    if st.form_submit_button("Assegna Turno e Aggiorna Ore 🚀"):
                        id_univoco = str(int(datetime.now().timestamp() * 1000))
                        nuovo_t_lpu = {
                            "id": id_univoco,
                            "lpu": lpu_scelto,
                            "settimana": settimana_lpu_label,
                            "settimana_chiave": settimana_lpu_chiave,
                            "giorno": giorno_lpu,
                            "fascia": fascia_lpu,
                            "orario": orario_lpu_str,
                            "ore": float(ore_svolte_val),
                            "note": nota_lpu,
                        }
                        salva_su_firestore("turni_lpu_gattile", id_univoco, nuovo_t_lpu)

                        st.session_state.lpu_data[lpu_scelto]["ore_fatte"] += float(ore_svolte_val)
                        salva_su_firestore("lpu_data_gattile", lpu_scelto, st.session_state.lpu_data[lpu_scelto])

                        turno_generale_equivalente = {
                            "id": f"lpu_{id_univoco}",
                            "settimana": settimana_lpu_label,
                            "settimana_chiave": settimana_lpu_chiave,
                            "volontario": f"{lpu_scelto} (LPU)",
                            "giorno": giorno_lpu,
                            "fascia": fascia_lpu,
                            "orario": orario_lpu_str,
                            "box_fatti": [],
                            "note": f"[LPU - Pulizie / {ore_svolte_val}h] {nota_lpu}",
                        }
                        salva_su_firestore("turni_gattile", f"lpu_{id_univoco}", turno_generale_equivalente)

                        st.success(f"Turno registrato per {lpu_scelto}!")
                        st.rerun()

        with tab_lpu_storico:
            st.subheader("📚 Storico Turni LPU")
            tutti_turni_lpu = carica_da_firestore("turni_lpu_gattile", [])

            if not tutti_turni_lpu:
                st.info("Nessun turno LPU registrato.")
            else:
                for tl in reversed(tutti_turni_lpu):
                    st.markdown(f"• **{tl.get('lpu')}** - {tl.get('settimana')} | 📅 {tl.get('giorno')} ({tl.get('fascia')} - {tl.get('orario')}) | ⏱️ **{tl.get('ore')} ore**")
                    if tl.get("note"):
                        st.caption(f"Note: {tl.get('note')}")

                    if st.button("🗑️ Elimina Turno LPU", key=f"del_lpu_{tl.get('id')}"):
                        nome_lpu_rif = tl.get("lpu")
                        ore_storno = tl.get("ore", 0.0)

                        if nome_lpu_rif in st.session_state.lpu_data:
                            st.session_state.lpu_data[nome_lpu_rif]["ore_fatte"] = max(
                                0.0, st.session_state.lpu_data[nome_lpu_rif]["ore_fatte"] - ore_storno
                            )
                            salva_su_firestore("lpu_data_gattile", nome_lpu_rif, st.session_state.lpu_data[nome_lpu_rif])

                        elimina_da_firestore("turni_lpu_gattile", tl.get('id'))
                        elimina_da_firestore("turni_gattile", f"lpu_{tl.get('id')}")
                        st.success("Turno LPU eliminato e ore stornate.")
                        st.rerun()
                    st.markdown("---")
