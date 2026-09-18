from datetime import datetime, timedelta, time
import json
import os
import pandas as pd
import pytz
import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore

st.set_page_config(
    page_title="Gestione Turni Gattile", page_icon="🐱", layout="wide"
)

# Tag aggiornati con versione forzata (?v=12) per aggirare la cache testarda di iOS
st.markdown(
    """
    <head>
        <link rel="manifest" href="manifest.json">
        <link rel="apple-touch-icon" href="https://github.com/lallag/turni-gattile/blob/main/icona.jpg?raw=true&v=12">
    </head>
""",
    unsafe_allow_html=True,
)

# --- INIZIALIZZAZIONE FIREBASE & GESTIONE DATI PERSISTENTI ---
if not firebase_admin._apps:
    cred_dict = dict(st.secrets["firebase"])
    if "private_key" in cred_dict:
        cred_dict["private_key"] = cred_dict["private_key"].replace("\\n", "\n")
    cred = credentials.Certificate(cred_dict)
    firebase_admin.initialize_app(cred)

db = firestore.client()

DB_TURNI = "turni_gattile.json"
DB_BOX = "box_gattile.json"
DB_LPU = "lpu_gattile.json"
DB_TURNI_LPU = "turni_lpu.json"


def carica_file_json(filename, default_val):
    try:
        doc_id = filename.replace(".json", "")
        doc = db.collection("gattile_data").document(doc_id).get()
        if doc.exists:
            data = doc.to_dict().get("data")
            return data if data is not None else default_val
        return default_val
    except Exception as e:
        st.error(f"Errore nel caricamento da database ({filename}): {e}")
        return default_val


def salva_file_json(filename, data):
    try:
        doc_id = filename.replace(".json", "")
        db.collection("gattile_data").document(doc_id).set({"data": data})
    except Exception as e:
        st.error(f"Errore nel salvataggio su database ({filename}): {e}")


# Inizializzazione stato box e lpu di default
BOX_DEFAULT = {
    "Box 1 (Ingresso)": ["Milo", "Nina"],
    "Box 2 (Cuccioli)": ["Romeo", "Pallina"],
    "Box 3 (Sala Comune)": ["Simba", "Luna"],
    "Reparto Degenza": ["Arturo", "Mimì"],
}

LPU_DEFAULT = {}

# Sincronizzazione immediata con Firebase Firestore
if "struttura_box" not in st.session_state:
    val_box = carica_file_json(DB_BOX, None)
    if val_box is None:
        st.session_state.struttura_box = BOX_DEFAULT
        salva_file_json(DB_BOX, BOX_DEFAULT)
    else:
        st.session_state.struttura_box = val_box

if "lpu_data" not in st.session_state:
    st.session_state.lpu_data = carica_file_json(DB_LPU, LPU_DEFAULT)

if "turni_lpu" not in st.session_state:
    st.session_state.turni_lpu = carica_file_json(DB_TURNI_LPU, [])

if "turni" not in st.session_state:
    st.session_state.turni = carica_file_json(DB_TURNI, [])

if "is_admin" not in st.session_state:
    st.session_state.is_admin = False

# --- GESTIONE ORARIO ITALIANO ESATTO (Bypassa il fuso orario del server cloud) ---
tz_italia = pytz.timezone("Europe/Rome")
adesso = datetime.now(tz_italia)
giorno_settimana = adesso.weekday()  # 0=Lunedì, 4=Venerdì, 5=Sabato, 6=Domenica
ora_attuale = adesso.hour

# Il weekend parte da venerdì alle 17:00 fino a domenica notte
is_weekend_reale = (giorno_settimana > 4) or (
    giorno_settimana == 4 and ora_attuale >= 17
)
is_weekend_o_venerdi_sera = is_weekend_reale

# --- BARRA LATERALE (SIDEBAR) PER: I MIEI TURNI & ADMIN ---
with st.sidebar:
    if os.path.exists("icona.jpg"):
        st.image("icona.jpg", width=80)

    st.title("🐱 Menu Rapido")

    st.markdown("---")

    # Sezione "I miei turni" nella sidebar
    with st.expander("🔍 Cerca i miei turni", expanded=False):
        volontari_esistenti_side = carica_file_json(DB_TURNI, [])
        nomi_side = sorted(
            list(
                set(
                    t.get("volontario", "").strip()
                    for t in volontari_esistenti_side
                    if t.get("volontario")
                )
            )
        )

        if not nomi_side:
            st.info("Nessun turno registrato nel sistema.")
        else:
            nome_cercato_side = st.selectbox(
                "Seleziona il tuo nome:",
                nomi_side,
                key="selettore_miei_turni_sidebar",
            )
            turni_pers_side = [
                t
                for t in volontari_esistenti_side
                if t.get("volontario", "").strip().lower()
                == nome_cercato_side.lower()
            ]

            if not turni_pers_side:
                st.write("Nessun turno trovato.")
            else:
                for tp in turni_pers_side:
                    box_str = ", ".join(tp.get("box_fatti", []))
                    st.markdown(
                        f"• **{tp.get('settimana')}**<br>📅 {tp.get('giorno')}"
                        f" ({tp.get('fascia')})<br>⏰"
                        f" {tp.get('orario')}<br> [{box_str}]",
                        unsafe_allow_html=True,
                    )
                    st.markdown("---")

    st.markdown("---")

    # Sezione "Admin / Simulatore" nella sidebar
    with st.expander("🔒 Area Admin", expanded=False):
        ADMIN_PASSWORD_CORRETTA = "gattile2026"
        if not st.session_state.is_admin:
            with st.form("form_login_admin_side"):
                pwd_input = st.text_input(
                    "Password:", type="password", key="pwd_side"
                )
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
                key="selettore_simulazione_side",
            )

            if scelta_simulazione == "⚠️ Simula Weekend":
                is_weekend_o_venerdi_sera = True
            elif scelta_simulazione == "🟢 Simula Feriale":
                is_weekend_o_venerdi_sera = False
            else:
                is_weekend_o_venerdi_sera = is_weekend_reale

            if st.button("🔒 Esci Admin", key="esci_admin_side"):
                st.session_state.is_admin = False
                st.rerun()

# --- INTESTAZIONE PRINCIPALE ---
st.title("🐱 Turni Gattile")

# --- MENU PRINCIPALE IN ALTO ---
opzioni_base = [
    "📅 Inserisci",
    "👀 Panoramica",
    "📦 Box & Gatti",
    "📊 Statistiche",
    "📚 Archivio",
]

if st.session_state.is_admin:
    opzioni_menu = opzioni_base + ["🛠️ Gestione LPU (Admin)"]
else:
    opzioni_menu = opzioni_base

menu = st.pills("Seleziona sezione:", opzioni_menu, default=opzioni_menu[0])
st.markdown("---")


def get_intervalli_settimane():
    oggi = datetime.now(tz_italia)
    lunedi_corrente = oggi - timedelta(days=oggi.weekday())
    domenica_corrente = lunedi_corrente + timedelta(days=6)

    lunedi_prossimo = lunedi_corrente + timedelta(days=7)
    domenica_prossima = domenica_corrente + timedelta(days=7)

    fmt = "%d/%m/%Y"
    str_corr = f"Settimana Corrente ({lunedi_corrente.strftime(fmt)} - {domenica_corrente.strftime(fmt)})"
    str_pros = f"Prossima Settimana ({lunedi_prossimo.strftime(fmt)} - {domenica_prossima.strftime(fmt)})"

    return str_corr, str_pros


label_corr, label_pros = get_intervalli_settimane()

if is_weekend_o_venerdi_sera:
    st.warning(
        "⚠️ **Promemoria Gattile:** È iniziato il fine settimana! Ricordati di"
        " toccare la **'Prossima Settimana'** qui sotto per inserire i tuoi"
        " turni per la settimana che sta per arrivare."
    )


def get_lista_volontari():
    turni_esistenti = carica_file_json(DB_TURNI, [])
    nomi = set()
    for t in turni_esistenti:
        nome = t.get("volontario", "").strip()
        if nome:
            nomi.add(nome)
    return sorted(list(nomi))


def get_box_frequenti_volontario(nome_volontario):
    if (
        not nome_volontario
        or nome_volontario == "➕ Altro / Nuovo volontario"
        or nome_volontario == "-- Seleziona il tuo nome --"
    ):
        return []

    turni_esistenti = carica_file_json(DB_TURNI, [])
    conteggio_box = {}

    struttura_box_corrente = carica_file_json(DB_BOX, BOX_DEFAULT)

    for t in turni_esistenti:
        if (
            t.get("volontario", "").strip().lower()
            == nome_volontario.strip().lower()
        ):
            for b in t.get("box_fatti", []):
                if b in struttura_box_corrente:
                    conteggio_box[b] = conteggio_box.get(b, 0) + 1

    box_ordinati = sorted(
        conteggio_box.items(), key=lambda x: x[1], reverse=True
    )
    return [b[0] for b in box_ordinati if b[1] >= 1]


if menu == "📅 Inserisci":
    st.header("Gestione Turni")

    if is_weekend_o_venerdi_sera:
        opzioni_settimana = [label_corr, label_pros]
    else:
        opzioni_settimana = [label_corr]

    settimana_scelta = st.radio(
        "Per quale settimana vuoi inserire il turno?",
        opzioni_settimana,
        horizontal=True,
    )

    volontari_registrati = get_lista_volontari()

    # --- SEZIONE NOME FUORI DAL FORM PER ESSERE LIBERA E REATTIVA ---
    st.markdown("### 👤 1. Il tuo Nome")
    scelte_volontario = (
        ["-- Seleziona il tuo nome --"]
        + volontari_registrati
        + ["➕ Altro / Nuovo volontario"]
    )

    scelta_volontario_dropdown = st.selectbox(
        "Seleziona o inserisci il tuo Nome e Cognome:",
        scelte_volontario,
        key="selettore_nome_principale",
    )

    volontario_finale = ""
    if scelta_volontario_dropdown == "➕ Altro / Nuovo volontario":
        volontario_nuovo_input = st.text_input(
            "Scrivi qui il tuo Nome e Cognome:",
            key="input_nuovo_volontario_libero",
        )
        volontario_finale = volontario_nuovo_input.strip()
    elif scelta_volontario_dropdown != "-- Seleziona il tuo nome --":
        volontario_finale = scelta_volontario_dropdown

    st.markdown("---")

    # --- FORM PER IL RESTO DEL TURNO ---
    with st.form("form_turno"):
        st.markdown("### 🕒 2. Dettagli Turno e Box")
        col1, col2 = st.columns(2)

        with col1:
            giorno = st.selectbox(
                "Giorno della settimana:",
                [
                    "Lunedì",
                    "Martedì",
                    "Mercoledì",
                    "Giovedì",
                    "Venerdì",
                    "Sabato",
                    "Domenica",
                ],
            )
            fascia = st.selectbox("Fascia oraria:", ["Mattina", "Pomeriggio"])

        with col2:
            st.markdown(f"**Orario per {fascia}:**")

            default_inizio = time(8, 30) if fascia == "Mattina" else time(14, 30)
            default_fine = time(12, 0) if fascia == "Mattina" else time(18, 0)

            col_ora1, col_ora2 = st.columns(2)
            with col_ora1:
                ora_inizio = st.time_input("Da:", value=default_inizio)

            senza_fine = st.checkbox(
                "Senza orario di fine (da quest'ora in poi)"
            )

            with col_ora2:
                if not senza_fine:
                    ora_fine = st.time_input("A:", value=default_fine)
                else:
                    st.markdown(
                        "<br><i>Nessun limite</i>", unsafe_allow_html=True
                    )

            if senza_fine:
                orario = f"Dalle {ora_inizio.strftime('%H:%M')}"
            else:
                orario = (
                    f"{ora_inizio.strftime('%H:%M')} -"
                    f" {ora_fine.strftime('%H:%M')}"
                )

            note = st.text_area("Note aggiuntive (opzionale):")

        st.session_state.struttura_box = carica_file_json(DB_BOX, BOX_DEFAULT)
        lista_nomi_box = list(st.session_state.struttura_box.keys())
        box_suggeriti = get_box_frequenti_volontario(volontario_finale)

        col_box_op1, col_box_op2 = st.columns([1, 1])
        with col_box_op1:
            seleziona_tutti_box = st.checkbox("📦 Seleziona TUTTI i Box")
        with col_box_op2:
            if box_suggeriti:
                st.caption(
                    f"💡 Suggerimento abitudini: {', '.join(box_suggeriti)}"
                )

        if seleziona_tutti_box:
            box_fatti = st.multiselect(
                "✅ Box / Zone di cui ti occupi (obbligatorio selezionarne"
                " almeno uno):",
                lista_nomi_box,
                default=lista_nomi_box,
            )
        elif box_suggeriti:
            box_fatti = st.multiselect(
                "✅ Box / Zone di cui ti occupi (obbligatorio selezionarne"
                " almeno uno):",
                lista_nomi_box,
                default=box_suggeriti,
            )
        else:
            box_fatti = st.multiselect(
                "✅ Box / Zone di cui ti occupi (obbligatorio selezionarne"
                " almeno uno):",
                lista_nomi_box,
            )

        submit_button = st.form_submit_button(label="Registra Turno 🚀")

        if submit_button:
            ora_limite_divisione = time(14, 0)
            errore_fascia = False

            if fascia == "Mattina" and ora_inizio >= ora_limite_divisione:
                st.error(
                    "❌ **Errore:** Hai scelto la fascia **Mattina**, ma"
                    " l'orario di inizio è pomeridiano (dalle 14:00 in poi)."
                )
                errore_fascia = True
            elif fascia == "Pomeriggio" and ora_inizio < ora_limite_divisione:
                st.error(
                    "❌ **Errore:** Hai scelto la fascia **Pomeriggio**, ma"
                    " l'orario di inizio è mattutino (prima delle 14:00)."
                )
                errore_fascia = True

            if not errore_fascia:
                if not volontario_finale:
                    st.warning(
                        "⚠️ Per favore, seleziona il tuo nome dal menu a"
                        " tendina o scrivi il tuo nome e cognome nell'apposita"
                        " casella in alto prima di registrare."
                    )
                elif not box_fatti:
                    st.error(
                        "❌ **Errore:** Devi selezionare almeno un box o zona"
                        " per poter registrare il turno!"
                    )
                else:
                    lista_turni = carica_file_json(DB_TURNI, [])

                    volontario_normalizzato = volontario_finale.strip().lower()
                    doppione_trovato = any(
                        t.get("volontario", "").strip().lower()
                        == volontario_normalizzato
                        and t.get("settimana") == settimana_scelta
                        and t.get("giorno") == giorno
                        and t.get("fascia") == fascia
                        for t in lista_turni
                    )

                    if doppione_trovato:
                        st.error(
                            f"⚠️ **Attenzione:** {volontario_finale} risulta"
                            f" già registrato per {giorno} ({fascia}) in questa"
                            " settimana!"
                        )
                    else:
                        nuovo_turno = {
                            "id": str(datetime.now().timestamp()),
                            "settimana": settimana_scelta,
                            "volontario": volontario_finale,
                            "giorno": giorno,
                            "fascia": fascia,
                            "orario": orario,
                            "box_fatti": box_fatti,
                            "note": note,
                        }
                        lista_turni.append(nuovo_turno)
                        salva_file_json(DB_TURNI, lista_turni)
                        st.success(
                            f"Turno registrato con successo per"
                            f" {volontario_finale}!"
                        )

elif menu == "👀 Panoramica":
    st.header("Gestione Turni e Copertura Box")

    turni_attuali = carica_file_json(DB_TURNI, [])
    st.session_state.struttura_box = carica_file_json(DB_BOX, BOX_DEFAULT)

    if is_weekend_o_venerdi_sera:
        scelte_visualizzazione = [label_corr, label_pros]
    else:
        scelte_visualizzazione = [label_corr]

    settimana_vista = st.radio(
        "Seleziona la settimana da visualizzare:",
        scelte_visualizzazione,
        horizontal=True,
    )

    turni_filtrati = [
        t for t in turni_attuali if t.get("settimana") == settimana_vista
    ]

    if not turni_filtrati:
        st.info("Nessun turno inserito al momento per questo periodo.")
    else:
        giorni_settimana = [
            "Lunedì",
            "Martedì",
            "Mercoledì",
            "Giovedì",
            "Venerdì",
            "Sabato",
            "Domenica",
        ]

        lista_tutti_box = list(st.session_state.struttura_box.keys())

        for giorno in giorni_settimana:
            st.markdown(f"## 📌 {giorno}")
            turni_giorno = [t for t in turni_filtrati if t["giorno"] == giorno]

            col_m, col_p = st.columns(2)

            def mostra_fascia_calendario(fascia_nome, col_container):
                with col_container:
                    st.markdown(f"### ☀️ {fascia_nome}")
                    turni_fascia = [
                        t for t in turni_giorno if t["fascia"] == fascia_nome
                    ]

                    if not turni_fascia:
                        st.caption("Nessun volontario registrato.")
                        st.markdown("**Box scoperti:**")
                        for b in sorted(lista_tutti_box):
                            gatti_nel_box = ", ".join(
                                st.session_state.struttura_box.get(b, [])
                            )
                            st.error(f"❌ **{b}** (🐱 {gatti_nel_box})")
                        return

                    st.markdown("**Volontari presenti:**")
                    for t in turni_fascia:
                        box_str = (
                            ", ".join(t["box_fatti"])
                            if t["box_fatti"]
                            else "Nessuno"
                        )
                        st.write(
                            f"• **{t['volontario']}** ({t['orario']}) 📦"
                            f" [{box_str}]"
                        )
                        if t["note"]:
                            st.caption(f"Note: {t['note']}")

                        if st.session_state.is_admin:
                            col_mod, col_del = st.columns(2)
                            with col_mod:
                                if st.button(
                                    f"✏️ Modifica ({t['volontario']})",
                                    key=f"mod_btn_{giorno}_{fascia_nome}_{t['id']}",
                                ):
                                    st.session_state[f"editing_{t['id']}"] = (
                                        not st.session_state.get(
                                            f"editing_{t['id']}", False
                                        )
                                    )
                                    st.rerun()
                            with col_del:
                                if st.button(
                                    f"🗑️ Elimina ({t['volontario']})",
                                    key=f"del_{giorno}_{fascia_nome}_{t['id']}",
                                ):
                                    lista_aggiornata = [
                                        item
                                        for item in carica_file_json(
                                            DB_TURNI, []
                                        )
                                        if item["id"] != t["id"]
                                    ]
                                    salva_file_json(
                                        DB_TURNI, lista_aggiornata
                                    )
                                    if f"editing_{t['id']}" in st.session_state:
                                        del st.session_state[
                                            f"editing_{t['id']}"
                                        ]
                                    st.success("Turno eliminato!")
                                    st.rerun()

                            if st.session_state.get(
                                f"editing_{t['id']}", False
                            ):
                                with st.form(key=f"form_mod_{t['id']}"):
                                    st.subheader(
                                        f"Modifica Turno di {t['volontario']}"
                                    )

                                    col_m1, col_m2 = st.columns(2)
                                    with col_m1:
                                        m_inizio = st.time_input(
                                            "Ora Inizio:",
                                            value=time(8, 30),
                                            key=f"min_{t['id']}",
                                        )
                                    with col_m2:
                                        m_fine = st.time_input(
                                            "Ora Fine:",
                                            value=time(12, 0),
                                            key=f"mfin_{t['id']}",
                                        )

                                    nuovo_orario = f"{m_inizio.strftime('%H:%M')} - {m_fine.strftime('%H:%M')}"
                                    nuove_note = st.text_area(
                                        "Note:",
                                        value=t.get("note", ""),
                                        key=f"note_mod_{t['id']}",
                                    )

                                    nuovi_box = st.multiselect(
                                        "Box gestiti:",
                                        lista_tutti_box,
                                        default=[
                                            b
                                            for b in t["box_fatti"]
                                            if b in lista_tutti_box
                                        ],
                                        key=f"box_mod_{t['id']}",
                                    )
                                    btn_salva_mod = st.form_submit_button(
                                        "Salva Modifiche ✅"
                                    )
                                    if btn_salva_mod:
                                        if not nuovi_box:
                                            st.error(
                                                "Errore: seleziona almeno un"
                                                " box."
                                            )
                                        else:
                                            lista_completa = carica_file_json(
                                                DB_TURNI, []
                                            )
                                            for item in lista_completa:
                                                if item["id"] == t["id"]:
                                                    item["orario"] = (
                                                        nuovo_orario
                                                    )
                                                    item["note"] = nuove_note
                                                    item[
                                                        "box_fatti"
                                                    ] = nuovi_box
                                            salva_file_json(
                                                DB_TURNI, lista_completa
                                            )
                                            st.session_state[
                                                f"editing_{t['id']}"
                                            ] = False
                                            st.success(
                                                "Turno modificato con"
                                                " successo!"
                                            )
                                            st.rerun()

                    box_coperti = set()
                    for t in turni_fascia:
                        for b in t["box_fatti"]:
                            box_coperti.add(b)

                    box_scoperti = [
                        b for b in lista_tutti_box if b not in box_coperti
                    ]

                    st.markdown("**Box scoperti:**")
                    if box_scoperti:
                        for b in sorted(box_scoperti):
                            gatti_nel_box = ", ".join(
                                st.session_state.struttura_box.get(b, [])
                            )
                            st.error(f"❌ **{b}** (🐱 {gatti_nel_box})")
                    else:
                        st.success("Tutti i box sono coperti!")

            with col_m:
                mostra_fascia_calendario("Mattina", col_m)
            with col_p:
                mostra_fascia_calendario("Pomeriggio", col_p)

            st.markdown("---")

elif menu == "📦 Box & Gatti":
    st.header("Anagrafica Box e Gatti")

    st.session_state.struttura_box = carica_file_json(DB_BOX, BOX_DEFAULT)

    if not st.session_state.is_admin:
        st.warning(
            "🔒 Questa sezione è protetta. Apri l'area 'Admin' nella barra"
            " laterale a sinistra per inserire la password per aggiungere o"
            " modificare i box."
        )
        st.markdown("---")
        for nome_box, lista_gatti in st.session_state.struttura_box.items():
            gatti_str = (
                ", ".join(lista_gatti)
                if lista_gatti
                else "Nessun gatto registrato in questo box"
            )
            st.markdown(
                f" **{nome_box}**<br>&nbsp;&nbsp;&nbsp;&nbsp;🐱 *Gatti"
                f" presenti:* {gatti_str}",
                unsafe_allow_html=True,
            )
            st.markdown("---")
    else:
        st.markdown(
            "Gestisci i box del gattile e vedi quali gatti ci sono dentro"
            " (Modalità Admin attiva)."
        )

        with st.form("form_aggiungi_box"):
            st.subheader("Crea un nuovo Box / Zona")
            nuovo_nome_box = st.text_input("Nome del Box (es. Box Infermeria):")
            nuovi_gatti_box = st.text_input(
                "Gatti presenti separati da virgola (es. Briciola, Oscar):"
            )
            btn_crea_box = st.form_submit_button("Aggiungi Box 📦")

            if btn_crea_box:
                if not nuovo_nome_box.strip():
                    st.error("Inserisci un nome valido per il box.")
                elif nuovo_nome_box.strip() in st.session_state.struttura_box:
                    st.warning("Esiste già un box con questo nome.")
                else:
                    gatti_list = [
                        g.strip()
                        for g in nuovi_gatti_box.split(",")
                        if g.strip()
                    ]
                    st.session_state.struttura_box[
                        nuovo_nome_box.strip()
                    ] = gatti_list
                    salva_file_json(DB_BOX, st.session_state.struttura_box)
                    st.success(
                        f"Box '{nuovo_nome_box}' aggiunto e salvato su database con successo!"
                    )
                    st.rerun()

        st.markdown("---")
        st.subheader("Box e Gatti Attuali:")

        for nome_box, lista_gatti in list(
            st.session_state.struttura_box.items()
        ):
            col_b1, col_b2 = st.columns([3, 1])
            with col_b1:
                gatti_str = (
                    ", ".join(lista_gatti) if lista_gatti else "Nessun gatto"
                )
                st.markdown(
                    f" **{nome_box}**<br>&nbsp;&nbsp;&nbsp;&nbsp;🐱"
                    f" *Gatti:* {gatti_str}",
                    unsafe_allow_html=True,
                )
            with col_b2:
                if st.button("Elimina Box", key=f"del_box_{nome_box}"):
                    del st.session_state.struttura_box[nome_box]
                    salva_file_json(DB_BOX, st.session_state.struttura_box)
                    st.success("Box eliminato e database aggiornato!")
                    st.rerun()

            with st.expander(f"Modifica gatti in {nome_box}"):
                with st.form(key=f"form_mod_gatti_{nome_box}"):
                    stringa_attuale = ", ".join(lista_gatti)
                    stringa_modificata = st.text_input(
                        "Elenco gatti:",
                        value=stringa_attuale,
                        key=f"input_gatti_{nome_box}",
                    )
                    btn_salva_gatti = st.form_submit_button(
                        "Aggiorna Gatti del Box"
                    )
                    if btn_salva_gatti:
                        nuova_lista = [
                            g.strip()
                            for g in stringa_modificata.split(",")
                            if g.strip()
                        ]
                        st.session_state.struttura_box[nome_box] = nuova_lista
                        salva_file_json(DB_BOX, st.session_state.struttura_box)
                        st.success(
                            "Lista gatti aggiornata e salvata nel database!"
                        )
                        st.rerun()
            st.markdown("---")

elif menu == "📊 Statistiche":
    st.header("📊 Statistiche Presenze Box")

    tutti_i_turni = carica_file_json(DB_TURNI, [])
    st.session_state.struttura_box = carica_file_json(DB_BOX, BOX_DEFAULT)
    tutte_le_settimane = sorted(
        list(set(t.get("settimana") for t in tutti_i_turni))
    )

    if label_corr not in tutte_le_settimane:
        tutte_le_settimane.insert(0, label_corr)
    if label_pros not in tutte_le_settimane and is_weekend_o_venerdi_sera:
        tutte_le_settimane.append(label_pros)

    settimana_stat = st.selectbox(
        "Seleziona settimana da analizzare:", tutte_le_settimane
    )

    turni_stat = [
        t for t in tutti_i_turni if t.get("settimana") == settimana_stat
    ]

    lista_tutti_box = list(st.session_state.struttura_box.keys())
    presenze_per_box = {box: 0 for box in lista_tutti_box}

    giorni_settimana = [
        "Lunedì",
        "Martedì",
        "Mercoledì",
        "Giovedì",
        "Venerdì",
        "Sabato",
        "Domenica",
    ]

    for giorno in giorni_settimana:
        for fascia in ["Mattina", "Pomeriggio"]:
            turni_fascia = [
                t
                for t in turni_stat
                if t.get("giorno") == giorno and t.get("fascia") == fascia
            ]
            box_in_questa_fascia = set()
            for t in turni_fascia:
                for b in t.get("box_fatti", []):
                    box_in_questa_fascia.add(b)

            for b in box_in_questa_fascia:
                if b in presenze_per_box:
                    presenze_per_box[b] += 1

    if not lista_tutti_box:
        st.info("Nessun box registrato nel sistema.")
    else:
        st.markdown("---")
        st.subheader("🎯 Riepilogo Attività per Box")
        cols = st.columns(3)

        lista_box_ordinata = sorted(
            presenze_per_box.items(), key=lambda x: x[1], reverse=True
        )

        for idx, (box, conteggio) in enumerate(lista_box_ordinata):
            col_corrente = cols[idx % 3]
            with col_corrente:
                st.metric(label=f" {box}", value=f"{conteggio} turni")

        st.markdown("---")
        col_grafico, col_tabella = st.columns([1.5, 1])

        with col_grafico:
            st.subheader("📈 Grafico a Barre")
            if sum(presenze_per_box.values()) == 0:
                st.info(
                    "Nessuna attività registrata per i box in questa"
                    " settimana."
                )
            else:
                df_stat = pd.DataFrame(
                    list(presenze_per_box.items()),
                    columns=["Box", "Numero Turni"],
                ).set_index("Box")
                st.bar_chart(df_stat)

        with col_tabella:
            st.subheader("📋 Tabella Dati")
            df_tabella = (
                pd.DataFrame(
                    list(presenze_per_box.items()), columns=["Box", "Turni"]
                )
                .sort_values(by="Turni", ascending=False)
                .reset_index(drop=True)
            )
            st.dataframe(df_tabella, use_container_width=True)

elif menu == "📚 Archivio":
    st.header("📚 Archivio Storico delle Settimane Passate")

    tutti_i_turni = carica_file_json(DB_TURNI, [])
    tutte_le_settimane = sorted(
        list(set(t.get("settimana") for t in tutti_i_turni))
    )
    settimane_storiche = [
        s for s in tutte_le_settimane if s != label_corr and s != label_pros
    ]

    settimane_disponibili = (
        settimane_storiche if settimane_storiche else tutte_le_settimane
    )

    if not settimane_disponibili:
        st.info("Nessun dato presente nell'archivio storico.")
    else:
        storico_scelto = st.selectbox(
            "Seleziona la settimana dall'archivio:", settimane_disponibili
        )

        turni_storico = [
            t for t in tutti_i_turni if t.get("settimana") == storico_scelto
        ]

        giorni_settimana = [
            "Lunedì",
            "Martedì",
            "Mercoledì",
            "Giovedì",
            "Venerdì",
            "Sabato",
            "Domenica",
        ]

        for giorno in giorni_settimana:
            st.markdown(f"## 📌 {giorno}")
            turni_giorno = [t for t in turni_storico if t["giorno"] == giorno]
            col_m, col_p = st.columns(2)

            def mostra_fascia_storica(fascia_nome, col_container):
                with col_container:
                    st.markdown(f"### ☀️ {fascia_nome}")
                    turni_fascia = [
                        t for t in turni_giorno if t["fascia"] == fascia_nome
                    ]

                    if not turni_fascia:
                        st.caption(
                            "Nessun volontario registrato in questa fascia."
                        )
                        return

                    st.markdown("**Volontari presenti:**")
                    for t in turni_fascia:
                        box_str = (
                            ", ".join(t["box_fatti"])
                            if t["box_fatti"]
                            else "Nessuno"
                        )
                        st.write(
                            f"• **{t['volontario']}** ({t['orario']}) 📦"
                            f" [{box_str}]"
                        )
                        if t["note"]:
                            st.caption(f"Note: {t['note']}")

            with col_m:
                mostra_fascia_storica("Mattina", col_m)
            with col_p:
                mostra_fascia_storica("Pomeriggio", col_p)

            st.markdown("---")

elif menu == "🛠️ Gestione LPU (Admin)":
    st.header("🛠️ Gestione Lavori Socialmente Utili (LPU)")

    if not st.session_state.is_admin:
        st.error("Area riservata esclusivamente agli amministratori.")
    else:
        st.markdown(
            "Gestisci il personale LPU, inserisci e modifica i turni con"
            " relative ore e monitora il monte ore totale e mancante."
        )

        tab_lpu_anagrafica, tab_lpu_inserisci, tab_lpu_storico = st.tabs(
            [
                "📋 Monte Ore & Ore Mancanti",
                "➕ Assegna Turno LPU",
                "📚 Storico & Modifica Turni LPU",
            ]
        )

        with tab_lpu_anagrafica:
            st.subheader("➕ Aggiungi o Configura un LPU")
            with st.form("form_aggiungi_lpu"):
                nome_lpu = st.text_input("Nome e Cognome LPU:")
                ore_totali_obbligatorie = st.number_input(
                    "Monte ore totale richiesto:",
                    min_value=1.0,
                    value=50.0,
                    step=1.0,
                )

                btn_salva_lpu = st.form_submit_button("Crea / Salva LPU 📝")
                if btn_salva_lpu:
                    if not nome_lpu.strip():
                        st.error("Inserisci un nome valido.")
                    else:
                        if nome_lpu.strip() not in st.session_state.lpu_data:
                            st.session_state.lpu_data[nome_lpu.strip()] = {
                                "ore_totali": float(ore_totali_obbligatorie),
                                "ore_fatte": 0.0,
                            }
                        else:
                            st.session_state.lpu_data[nome_lpu.strip()][
                                "ore_totali"
                            ] = float(ore_totali_obbligatorie)

                        salva_file_json(DB_LPU, st.session_state.lpu_data)
                        st.success(f"LPU '{nome_lpu}' salvato con successo!")
                        st.rerun()

            st.markdown("---")
            st.subheader("📋 Monitoraggio Ore LPU (Fatte e Mancanti)")

            lpu_dict = st.session_state.lpu_data
            if not lpu_dict:
                st.info("Nessun LPU registrato nel sistema.")
            else:
                dati_tabella_lpu = []
                for nome, info in lpu_dict.items():
                    tot = info.get("ore_totali", 0.0)
                    fatte = info.get("ore_fatte", 0.0)
                    mancanti = max(0.0, tot - fatte)

                    dati_tabella_lpu.append(
                        {
                            "Nome LPU": nome,
                            "Ore Totali": tot,
                            "Ore Fatte": fatte,
                            "Ore Mancanti": mancanti,
                        }
                    )

                df_lpu = pd.DataFrame(dati_tabella_lpu)
                st.dataframe(df_lpu, use_container_width=True)

                st.markdown("### 🗑️ Gestione LPU")
                for nome in list(lpu_dict.keys()):
                    col_del_lpu, col_btn_lpu = st.columns([3, 1])
                    with col_del_lpu:
                        st.write(
                            f"• **{nome}** (Fatte:"
                            f" {lpu_dict[nome]['ore_fatte']}h / Totali:"
                            f" {lpu_dict[nome]['ore_totali']}h)"
                        )
                    with col_btn_lpu:
                        if st.button("Elimina 🗑️", key=f"btn_del_lpu_{nome}"):
                            del lpu_dict[nome]
                            salva_file_json(DB_LPU, lpu_dict)
                            st.success("LPU rimosso.")
                            st.rerun()

        with tab_lpu_inserisci:
            st.subheader("📅 Registra un Turno per LPU")
            lpu_nomi_disponibili = list(st.session_state.lpu_data.keys())
            st.session_state.struttura_box = carica_file_json(
                DB_BOX, BOX_DEFAULT
            )

            if not lpu_nomi_disponibili:
                st.warning(
                    "Prima devi registrare almeno un LPU nella scheda 'Monte"
                    " Ore & Ore Mancanti'."
                )
            else:
                with st.form("form_turno_lpu"):
                    lpu_scelto = st.selectbox(
                        "Seleziona LPU:", lpu_nomi_disponibili
                    )
                    settimana_lpu = st.selectbox(
                        "Settimana:", [label_corr, label_pros]
                    )
                    giorno_lpu = st.selectbox(
                        "Giorno:",
                        [
                            "Lunedì",
                            "Martedì",
                            "Mercoledì",
                            "Giovedì",
                            "Venerdì",
                            "Sabato",
                            "Domenica",
                        ],
                        key="g_lpu",
                    )
                    fascia_lpu = st.selectbox(
                        "Fascia:", ["Mattina", "Pomeriggio"], key="f_lpu"
                    )

                    col_ol1, col_ol2 = st.columns(2)
                    with col_ol1:
                        ora_i_lpu = st.time_input(
                            "Ora Inizio:", value=time(8, 30), key="oi_lpu"
                        )
                    with col_ol2:
                        ora_f_lpu = st.time_input(
                            "Ora Fine:", value=time(12, 0), key="of_lpu"
                        )

                    orario_lpu_str = (
                        f"{ora_i_lpu.strftime('%H:%M')} -"
                        f" {ora_f_lpu.strftime('%H:%M')}"
                    )
                    ore_svolte_val = st.number_input(
                        "Quante ore di lavoro aggiungere al monte ore?",
                        min_value=0.5,
                        value=3.5,
                        step=0.5,
                    )

                    lista_box_lpu = list(st.session_state.struttura_box.keys())
                    box_assegnati_lpu = st.multiselect(
                        "Box assegnati:", lista_box_lpu, key="box_lpu_sel"
                    )
                    nota_lpu = st.text_area("Note turno LPU:", key="note_lpu_in")

                    btn_registra_turno_lpu = st.form_submit_button(
                        "Assegna Turno e Aggiorna Ore 🚀"
                    )
                    if btn_registra_turno_lpu:
                        if not box_assegnati_lpu:
                            st.error("Seleziona almeno un box.")
                        else:
                            id_univoco = str(datetime.now().timestamp())
                            nuovo_t_lpu = {
                                "id": id_univoco,
                                "lpu": lpu_scelto,
                                "settimana": settimana_lpu,
                                "giorno": giorno_lpu,
                                "fascia": fascia_lpu,
                                "orario": orario_lpu_str,
                                "ore": float(ore_svolte_val),
                                "box": box_assegnati_lpu,
                                "note": nota_lpu,
                            }
                            st.session_state.turni_lpu.append(nuovo_t_lpu)
                            salva_file_json(DB_TURNI_LPU, st.session_state.turni_lpu)

                            st.session_state.lpu_data[lpu_scelto][
                                "ore_fatte"
                            ] += float(ore_svolte_val)
                            salva_file_json(DB_LPU, st.session_state.lpu_data)

                            turno_generale_equivalente = {
                                "id": f"lpu_{id_univoco}",
                                "settimana": settimana_lpu,
                                "volontario": f"{lpu_scelto} (LPU)",
                                "giorno": giorno_lpu,
                                "fascia": fascia_lpu,
                                "orario": orario_lpu_str,
                                "box_fatti": box_assegnati_lpu,
                                "note": (
                                    f"[LPU - {ore_svolte_val}h] {nota_lpu}"
                                ),
                            }
                            turni_gen = carica_file_json(DB_TURNI, [])
                            turni_gen.append(turno_generale_equivalente)
                            salva_file_json(DB_TURNI, turni_gen)

                            st.success(
                                f"Turno registrato per {lpu_scelto}! Aggiunte"
                                f" {ore_svolte_val} ore."
                            )
                            st.rerun()

        with tab_lpu_storico:
            st.subheader("📚 Storico, Modifica ed Eliminazione Turni LPU")
            tutti_turni_lpu = carica_file_json(DB_TURNI_LPU, [])

            if not tutti_turni_lpu:
                st.info("Nessun turno LPU registrato.")
            else:
                for tl in reversed(tutti_turni_lpu):
                    box_s = ", ".join(tl.get("box", []))
                    st.markdown(
                        f"• **{tl.get('lpu')}** - {tl.get('settimana')} | 📅"
                        f" {tl.get('giorno')} ({tl.get('fascia')} -"
                        f" {tl.get('orario')}) | ⏱️ **{tl.get('ore')} ore** |"
                        f" 📦 [{box_s}]"
                    )
                    if tl.get("note"):
                        st.caption(f"Note: {tl.get('note')}")

                    col_m_lpu, col_d_lpu = st.columns(2)
                    with col_m_lpu:
                        if st.button(
                            "✏️ Modifica Ore/Dettagli",
                            key=f"edit_lpu_btn_{tl['id']}",
                        ):
                            st.session_state[f"editing_lpu_{tl['id']}"] = (
                                not st.session_state.get(
                                    f"editing_lpu_{tl['id']}", False
                                )
                            )
                            st.rerun()
                    with col_d_lpu:
                        if st.button(
                            "🗑️ Elimina Turno LPU", key=f"del_lpu_turno_{tl['id']}"
                        ):
                            nome_lpu_riferimento = tl.get("lpu")
                            ore_da_stornare = tl.get("ore", 0.0)

                            if nome_lpu_riferimento in st.session_state.lpu_data:
                                st.session_state.lpu_data[
                                    nome_lpu_riferimento
                                ]["ore_fatte"] = max(
                                    0.0,
                                    st.session_state.lpu_data[
                                        nome_lpu_riferimento
                                    ]["ore_fatte"]
                                    - ore_da_stornare,
                                )
                                salva_file_json(
                                    DB_LPU, st.session_state.lpu_data
                                )

                            nuovo_storico_lpu = [
                                item
                                for item in carica_file_json(DB_TURNI_LPU, [])
                                if item["id"] != tl["id"]
                            ]
                            salva_file_json(DB_TURNI_LPU, nuovo_storico_lpu)

                            turni_gen_aggiornato = [
                                item
                                for item in carica_file_json(DB_TURNI, [])
                                if item["id"] != f"lpu_{tl['id']}"
                            ]
                            salva_file_json(DB_TURNI, turni_gen_aggiornato)

                            st.success(
                                "Turno LPU eliminato e ore stornate con"
                                " successo!"
                            )
                            st.rerun()

                    if st.session_state.get(f"editing_lpu_{tl['id']}", False):
                        with st.form(key=f"form_mod_lpu_turno_{tl['id']}"):
                            st.subheader(f"Modifica Turno di {tl.get('lpu')}")
                            nuove_ore_val = st.number_input(
                                "Nuovo monte ore:",
                                min_value=0.5,
                                value=float(tl.get("ore", 3.5)),
                                step=0.5,
                                key=f"n_ore_{tl['id']}",
                            )
                            nuove_note_val = st.text_area(
                                "Note:",
                                value=tl.get("note", ""),
                                key=f"n_note_{tl['id']}",
                            )

                            st.session_state.struttura_box = carica_file_json(
                                DB_BOX, BOX_DEFAULT
                            )
                            lista_box_mod_lpu = list(
                                st.session_state.struttura_box.keys()
                            )
                            nuovi_box_val = st.multiselect(
                                "Box assegnati:",
                                lista_box_mod_lpu,
                                default=[
                                    b
                                    for b in tl.get("box", [])
                                    if b in lista_box_mod_lpu
                                ],
                                key=f"n_box_{tl['id']}",
                            )

                            btn_salva_mod_lpu = st.form_submit_button(
                                "Salva Modifiche LPU ✅"
                            )
                            if btn_salva_mod_lpu:
                                if not nuovi_box_val:
                                    st.error("Seleziona almeno un box.")
                                else:
                                    vecchie_ore = tl.get("ore", 0.0)
                                    differenza_ore = nuove_ore_val - vecchie_ore

                                    tutti_lpu_file = carica_file_json(
                                        DB_TURNI_LPU, []
                                    )
                                    for item in tutti_lpu_file:
                                        if item["id"] == tl["id"]:
                                            item["ore"] = float(nuove_ore_val)
                                            item["note"] = nuove_note_val
                                            item["box"] = nuovi_box_val
                                    salva_file_json(
                                        DB_TURNI_LPU, tutti_lpu_file
                                    )

                                    nome_lpu_riferimento = tl.get("lpu")
                                    if (
                                        nome_lpu_riferimento
                                        in st.session_state.lpu_data
                                    ):
                                        st.session_state.lpu_data[
                                            nome_lpu_riferimento
                                        ]["ore_fatte"] = max(
                                            0.0,
                                            st.session_state.lpu_data[
                                                nome_lpu_riferimento
                                            ]["ore_fatte"]
                                            + differenza_ore,
                                        )
                                        salva_file_json(
                                            DB_LPU, st.session_state.lpu_data
                                        )

                                    turni_gen_file = carica_file_json(
                                        DB_TURNI, []
                                    )
                                    for item in turni_gen_file:
                                        if item["id"] == f"lpu_{tl['id']}":
                                            item["box_fatti"] = nuovi_box_val
                                            item["note"] = (
                                                f"[LPU - {nuove_ore_val}h]"
                                                f" {nuove_note_val}"
                                            )
                                    salva_file_json(
                                        DB_TURNI, turni_gen_file
                                    )

                                    st.session_state[
                                        f"editing_lpu_{tl['id']}"
                                    ] = False
                                    st.success(
                                        "Turno LPU modificato con successo!"
                                    )
                                    st.rerun()

                    st.markdown("---")
