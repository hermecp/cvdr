# app_streamlit_v10_1.py
# Mini-CRM CVDR — LOGIN + Leads + Seguimiento (Agenda integrada) + Dashboard (mejorado)
# v10.1
# - Leads: tras guardar, el nuevo registro aparece arriba y se resetea la paginación (sin recargar manual).
# - Seguimiento/Agenda: checkbox "Cerrar acción..." para quitar del calendario al registrar seguimiento.
# - Si reprogramas (+días) o cambias la fecha, la acción migra a la nueva fecha.

from __future__ import annotations
import pandas as pd
import streamlit as st
import altair as alt
from pathlib import Path
from datetime import datetime, date, timedelta
import hashlib

st.set_page_config(page_title="Mini-CRM CVDR v10.1", layout="wide")

# =========================
# Login / Usuarios
# =========================
def _hash(p: str) -> str:
    return hashlib.sha256((p or "").encode("utf-8")).hexdigest()

USERS = {
    "admin":        {"name": "Admin",         "role": "Admin",         "pass_hash": _hash("1234")},
    "director":     {"name": "Director",      "role": "Director",      "pass_hash": _hash("1234")},
    "subidirector": {"name": "Subidirector",  "role": "Subidirector",  "pass_hash": _hash("1234")},
    "favio":        {"name": "Favio",         "role": "Ventas",        "pass_hash": _hash("1234")},
    "nancy":        {"name": "Nancy",         "role": "Ventas",        "pass_hash": _hash("1234")},
    "rosario":      {"name": "Rosario",       "role": "Ventas",        "pass_hash": _hash("1234")},
    "hayde":        {"name": "Hayde",         "role": "Comunicación",  "pass_hash": _hash("1234")},
    "nora":         {"name": "Nora",          "role": "Comunicación",  "pass_hash": _hash("1234")},
}

def is_logged() -> bool:
    return bool(st.session_state.get("user"))

def require_login():
    if not is_logged():
        st.stop()

def owner_name_default() -> str:
    if not is_logged(): return "Asesor"
    return st.session_state["user"]["name"]

# =========================
# Archivos y esquemas
# =========================
FILES = {
    "leads": "leads.csv",
    "seguimientos": "seguimientos.csv",
    "embudo": "embudo_etapas.csv",  # opcional
}
REQUIRED = ["leads", "seguimientos"]

STAGE_ORDER = [
    "Awareness", "Contacted", "MQL", "SQL", "Nurturing", "Demo_Booked", "Won", "Lost", "Re_Engaged"
]
STAGE_LABEL = {
    "Awareness": "Awareness (Captado)",
    "Contacted": "Contacted (Contactado)",
    "MQL": "MQL (Info enviada)",
    "SQL": "SQL (Interesado / Oportunidad)",
    "Nurturing": "Nurturing (En seguimiento / Temario)",
    "Demo_Booked": "Demo_Booked (Reunión agendada / Depósito)",
    "Won": "Won (Inscrito / Cliente)",
    "Lost": "Lost (Perdido)",
    "Re_Engaged": "Re_Engaged (Reactivado)",
}
SPANISH_TO_EN = {
    "Captado": "Awareness",
    "Contactado": "Contacted",
    "Info enviada": "MQL", "Info_enviada": "MQL", "MQL": "MQL",
    "Interesado": "SQL",
    "En seguimiento": "Nurturing", "En_seguimiento": "Nurturing",
    "Reunión agendada": "Demo_Booked", "Reunión_agendada": "Demo_Booked",
    "Inscrito": "Won", "Inscrita": "Won",
    "Perdido": "Lost",
    "Reactivado": "Re_Engaged",
}
STAGE_DESC = {
    "Awareness": "Conoce la marca por primera vez.",
    "Contacted": "Se realizó el primer contacto.",
    "MQL": "Marketing lo calificó (info enviada).",
    "SQL": "Validado por ventas como oportunidad real.",
    "Nurturing": "Seguimiento para madurar el interés (temario).",
    "Demo_Booked": "Reunión/demostración agendada (depósito).",
    "Won": "Se convirtió en cliente.",
    "Lost": "No se convirtió en cliente.",
    "Re_Engaged": "Lead reactivado.",
}

# Colores por etapa (fondo, texto)
STAGE_COLORS = {
    "Awareness":    ("#F1F5F9", "#0F172A"),  # slate
    "Contacted":    ("#E0F2FE", "#075985"),  # sky
    "MQL":          ("#FEF9C3", "#713F12"),  # amber
    "SQL":          ("#DCFCE7", "#14532D"),  # green
    "Nurturing":    ("#F5F3FF", "#4C1D95"),  # violet
    "Demo_Booked":  ("#FFE4E6", "#9F1239"),  # rose
    "Won":          ("#E7F8ED", "#065F46"),  # emerald-lite
    "Lost":         ("#FEE2E2", "#7F1D1D"),  # red
    "Re_Engaged":   ("#EDE9FE", "#3730A3"),  # indigo
}

# Plantillas (una por etapa)
STAGE_TEMPLATES = {
    "Awareness":   {"tipo": "Bienvenida",           "canal": "WhatsApp", "plantilla": "Hola {nombre}, gracias por tu interés en {curso}. ¿Te envío información breve?"},
    "Contacted":   {"tipo": "Seguimiento inicial",  "canal": "WhatsApp", "plantilla": "Hola {nombre}, ¿pudiste revisar la info de {curso}? Puedo llamarte 10 min si gustas."},
    "MQL":         {"tipo": "Envio de info",        "canal": "WhatsApp", "plantilla": "Hola {nombre}, te comparto el temario de {curso}. ¿Qué objetivo te gustaría lograr?"},
    "SQL":         {"tipo": "Cierre suave",         "canal": "WhatsApp", "plantilla": "Con lo que me comentaste, {curso} te ayudaría bastante. ¿Confirmamos tu registro?"},
    "Nurturing":   {"tipo": "Contenido de valor",   "canal": "WhatsApp", "plantilla": "Te comparto este recurso de {curso}. ¿Te parece si platicamos el {fecha_limite}?"},
    "Demo_Booked": {"tipo": "Recordatorio",         "canal": "WhatsApp", "plantilla": "Te recuerdo nuestra reunión sobre {curso}. ¿Sigue bien la hora?"},
    "Won":         {"tipo": "Bienvenida alumno",    "canal": "WhatsApp", "plantilla": "¡Bienvenido(a), {nombre}! Tu registro en {curso} quedó confirmado. Te envío indicaciones."},
    "Lost":        {"tipo": "Cierre cordial",       "canal": "WhatsApp", "plantilla": "Gracias por tu tiempo, {nombre}. Si deseas retomar {curso} más adelante, con gusto te apoyamos."},
    "Re_Engaged":  {"tipo": "Reactivación",         "canal": "WhatsApp", "plantilla": "Tenemos nuevas fechas de {curso}. ¿Quieres que te comparta opciones?"},
}

SCHEMA_LEADS = [
    "id_lead", "fecha_registro", "hora_registro",
    "nombre", "apellidos", "alias", "edad",
    "celular", "telefono", "correo",
    "interes_curso", "como_enteraste",
    "lead_status", "funnel_etapas",
    "fecha_ultimo_contacto", "observaciones",
    "owner", "proxima_accion_fecha", "proxima_accion_desc",
    "lead_score", "probabilidad_cierre", "monto_estimado", "motivo_perdida", "fecha_entrada_etapa",
]
SCHEMA_SEGS = [
    "id_seguimiento", "id_lead", "fecha", "hora",
    "tipo_mensaje", "estado_mensaje", "canal",
    "atendido_por", "mensaje_sugerido", "respuesta", "observaciones"
]
DEFAULTS = {
    "alias": "", "edad": "", "telefono": "", "fecha_ultimo_contacto": "", "observaciones": "",
    "owner": "", "proxima_accion_fecha": "", "proxima_accion_desc": "",
    "lead_score": "0", "probabilidad_cierre": "0.2", "monto_estimado": "", "motivo_perdida": "",
    "fecha_entrada_etapa": "", "funnel_etapas": "",
}
COURSE_OPTIONS = [
    "IA profesionales inmobiliarios",
    "IA educación básica",
    "IA educación universitaria",
    "IA empresas",
    "IA para gobierno",
    "Inglés",
    "Polivirtual Bach.",
    "Polivirtual Lic.",
]
CHANNEL_OPTIONS = [
    "WhatsApp", "Teléfono", "Correo", "Facebook", "Instagram", "Google", "Referido", "Otro"
]

# =========================
# CSV helpers
# =========================
@st.cache_data(ttl=30)
def load_csv(path: str, dtype=None):
    p = Path(path)
    if not p.exists():
        return pd.DataFrame()
    return pd.read_csv(p, dtype=dtype).fillna("")

def save_csv(df: pd.DataFrame, path: str):
    p = Path(path)
    tmp = p.with_suffix(".tmp.csv")
    df.to_csv(tmp, index=False)
    tmp.replace(p)
    load_csv.clear()

def ensure_columns(df: pd.DataFrame, ordered_cols: list[str], defaults: dict) -> pd.DataFrame:
    if df is None or df.empty:
        df = pd.DataFrame(columns=ordered_cols)
    for c in ordered_cols:
        if c not in df.columns:
            df[c] = defaults.get(c, "")
    extras = [c for c in df.columns if c not in ordered_cols]
    return df[ordered_cols + extras]

def next_id(df: pd.DataFrame, id_col: str) -> int:
    if df is None or df.empty or id_col not in df.columns:
        return 1
    try:
        return int(pd.to_numeric(df[id_col], errors="coerce").fillna(0).max()) + 1
    except Exception:
        return 1

def now_date() -> str:
    return datetime.now().strftime("%Y-%m-%d")

def now_time() -> str:
    return datetime.now().strftime("%H:%M:%S")

def norm_phone(s: str) -> str:
    import re as _re
    return _re.sub(r"\D", "", str(s or ""))

def norm_email(s: str) -> str:
    return str(s or "").strip().lower()

def normalize_stage(v: str) -> str:
    if not isinstance(v, str) or not v.strip():
        return "Awareness"
    v = v.strip()
    if v in STAGE_ORDER:
        return v
    return SPANISH_TO_EN.get(v, "Awareness")

def compute_lead_score(row: pd.Series) -> int:
    score = 0
    if row.get("como_enteraste") in ["Referido", "Facebook", "Google", "WhatsApp"]:
        score += 10
    if normalize_stage(row.get("lead_status", "")) in ["SQL", "Demo_Booked"]:
        score += 20
    try:
        edad = int(row.get("edad") or 0)
        if 25 <= edad <= 45:
            score += 10
    except Exception:
        pass
    if str(row.get("owner", "")).strip():
        score += 5
    return min(score, 100)

# =========================
# Carga de datos
# =========================
for k in REQUIRED:
    if not Path(FILES[k]).exists():
        if k == "leads":
            save_csv(pd.DataFrame(columns=SCHEMA_LEADS), FILES[k])
        elif k == "seguimientos":
            save_csv(pd.DataFrame(columns=SCHEMA_SEGS), FILES[k])

leads = ensure_columns(load_csv(FILES["leads"], dtype=str), SCHEMA_LEADS, DEFAULTS)
segs  = ensure_columns(load_csv(FILES["seguimientos"], dtype=str), SCHEMA_SEGS, {})

if Path(FILES["embudo"]).exists():
    emb_raw = load_csv(FILES["embudo"], dtype=str)
    if "stage" in emb_raw.columns:
        emb = emb_raw[["stage"]].drop_duplicates()
    elif "etapa" in emb_raw.columns:
        emb = emb_raw[["etapa"]].rename(columns={"etapa": "stage"})
        emb["stage"] = emb["stage"].map(normalize_stage)
        emb = emb[["stage"]].drop_duplicates()
    else:
        emb = pd.DataFrame({"stage": STAGE_ORDER})
else:
    emb = pd.DataFrame({"stage": STAGE_ORDER})

leads["lead_status"] = leads["lead_status"].apply(normalize_stage)
if "funnel_etapas" not in leads.columns:
    leads["funnel_etapas"] = ""
leads["lead_score"] = leads.apply(compute_lead_score, axis=1).astype(str)

# =========================
# Login UI
# =========================
def login_sidebar():
    with st.sidebar:
        st.title("Acceso")
        if not is_logged():
            u = st.text_input("Usuario")
            p = st.text_input("Contraseña", type="password")
            if st.button("Iniciar sesión", use_container_width=True):
                info = USERS.get(u.strip().lower())
                if not info or info["pass_hash"] != _hash(p):
                    st.error("Usuario o contraseña incorrectos.")
                    st.stop()
                st.session_state["user"] = {"username": u.strip().lower(), "name": info["name"], "role": info["role"]}
                st.rerun()
        else:
            user = st.session_state["user"]
            st.success(f"Conectado: {user['name']} • {user['role']}")
            if st.button("Cerrar sesión", use_container_width=True):
                st.session_state.clear()
                st.rerun()

login_sidebar()
require_login()

# =========================
# Menú
# =========================
MENU_ALL = ["👤 Leads", "✉️ Seguimiento", "📊 Dashboard"]
initial_menu = st.session_state.get("menu", "👤 Leads")
with st.sidebar:
    st.markdown("---")
    menu = st.radio("Navegación", MENU_ALL, index=MENU_ALL.index(initial_menu))
st.session_state["menu"] = menu

# =========================
# UI helpers
# =========================
def lead_label(row: pd.Series) -> str:
    name = f"{row.get('nombre','')} {row.get('apellidos','')}".strip()
    alias = row.get("alias", "").strip()
    tel = row.get("celular", "") or row.get("telefono", "")
    tag = f" • {alias}" if alias else ""
    tel = f" • {tel}" if tel else ""
    return f"{name}{tag}{tel}"

def render_tpl(text: str, lead_row: pd.Series) -> str:
    ctx = {k: lead_row.get(k, "") for k in lead_row.index}
    ctx.update({
        "nombre": lead_row.get("nombre", ""),
        "curso": lead_row.get("interes_curso", ""),
        "fecha_limite": "",
        "precio": lead_row.get("monto_estimado", ""),
    })
    try:
        return text.format(**ctx)
    except KeyError:
        return text

def stage_badge(stage_en: str) -> str:
    bg, fg = STAGE_COLORS.get(stage_en, ("#F1F5F9", "#0F172A"))
    label = STAGE_LABEL.get(stage_en, stage_en)
    return f"<span style='background:{bg};color:{fg};padding:2px 8px;border-radius:999px;font-size:12px;font-weight:600'>{label}</span>"

def owner_badge(owner: str) -> str:
    if not owner: owner = "—"
    return f"<span style='background:#ECFDF5;color:#065F46;padding:2px 8px;border-radius:999px;font-size:12px;'>Owner: {owner}</span>"

# =========================
# Páginas
# =========================
def page_leads():
    global leads
    st.title("👤 Leads")

    q = st.text_input("🔎 Buscar (nombre, alias, email o teléfono)", key="leads_search")
    L = leads.copy()
    if q:
        ql = q.lower()
        L = L[L.apply(lambda r: ql in f"{r.get('nombre','')} {r.get('apellidos','')} {r.get('alias','')} {r.get('correo','')} {r.get('celular','')}".lower(), axis=1)]

    st.download_button("⬇️ Descargar leads (CSV)", data=L.to_csv(index=False).encode("utf-8"),
                       file_name="leads.csv", mime="text/csv")

    if "leads_page_idx" not in st.session_state: st.session_state["leads_page_idx"] = 0
    page_size = st.selectbox("Resultados por página", [10, 25, 50, 100], index=0, key="leads_page_size")
    total = len(L); total_pages = max(1, (total + page_size - 1) // page_size)
    if st.session_state.get("leads_last_query", "") != q:
        st.session_state["leads_page_idx"] = 0
        st.session_state["leads_last_query"] = q
    page_idx = max(0, min(st.session_state["leads_page_idx"], total_pages - 1))
    start, end = page_idx * page_size, page_idx * page_size + page_size
    page_df = L.iloc[start:end].reset_index(drop=True)

    st.caption(f"Coincidencias: {total} • Página {page_idx + 1} de {total_pages}")
    cpg1, cpg2, _ = st.columns([1,1,6])
    if cpg1.button("⟵ Anterior", disabled=(page_idx == 0)):
        st.session_state["leads_page_idx"] = page_idx - 1
        st.rerun()
    if cpg2.button("Siguiente ⟶", disabled=(page_idx >= total_pages - 1)):
        st.session_state["leads_page_idx"] = page_idx + 1
        st.rerun()

    if not page_df.empty:
        for _, r in page_df.iterrows():
            with st.container(border=True):
                c1, c2, c3, c4 = st.columns([5,2,2,1])
                c1.markdown(f"**{lead_label(r)}**  —  {r.get('interes_curso','')}  —  {r.get('como_enteraste','')}")
                c2.markdown(stage_badge(r.get('lead_status','Awareness')), unsafe_allow_html=True)
                c3.markdown(owner_badge(r.get('owner','')), unsafe_allow_html=True)
                if c4.button("Editar", key=f"edit_{r['id_lead']}"):
                    st.session_state["lead_to_edit"] = str(r["id_lead"])
                    st.experimental_rerun()

    st.divider()
    st.subheader("Registrar nuevo lead")
    with st.form("form_new_lead", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        nombre = c1.text_input("Nombre")
        apellidos = c2.text_input("Apellidos")
        alias = c3.text_input("Alias (opcional)")
        c4, c5, c6 = st.columns(3)
        edad = c4.number_input("Edad", min_value=0, max_value=120, step=1, format="%d")
        celular = c5.text_input("Celular")
        correo = c6.text_input("Correo")
        c7, c8 = st.columns(2)
        interes = c7.selectbox("Tipo de curso / interés", COURSE_OPTIONS, index=0)
        canal = c8.selectbox("¿Cómo te enteraste?", CHANNEL_OPTIONS, index=0)
        stages = emb["stage"].tolist()
        lead_status_lbl = st.selectbox("Etapa (en) (es)", [STAGE_LABEL[s] for s in stages], index=0)
        obs = st.text_area("Observaciones")
        ok = st.form_submit_button("Guardar lead")
        if ok:
            lead_status_en = stages[[STAGE_LABEL[s] for s in stages].index(lead_status_lbl)]
            new_id = next_id(leads, "id_lead")
            new_row = {
                "id_lead": str(new_id),
                "fecha_registro": now_date(),
                "hora_registro": now_time(),
                "nombre": nombre, "apellidos": apellidos, "alias": alias,
                "edad": int(edad) if str(edad) != "" else "",
                "celular": norm_phone(celular), "telefono": "",
                "correo": norm_email(correo),
                "interes_curso": interes, "como_enteraste": canal,
                "lead_status": lead_status_en,
                "funnel_etapas": "",
                "fecha_ultimo_contacto": "", "observaciones": obs,
                "owner": owner_name_default(),
                "proxima_accion_fecha": "", "proxima_accion_desc": "",
                "lead_score": "0", "probabilidad_cierre": "0.2",
                "monto_estimado": "", "motivo_perdida": "",
                "fecha_entrada_etapa": now_date(),
            }
            # Insertar arriba y recalcular score
            leads_local = pd.DataFrame([new_row])
            leads_local["lead_score"] = leads_local.apply(compute_lead_score, axis=1).astype(str)
            # concatenar al inicio
            leads = pd.concat([leads_local, leads], ignore_index=True)
            save_csv(leads, FILES["leads"])
            # Resetear a página 1 para que se vea arriba
            st.session_state["leads_page_idx"] = 0
            st.success(f"Lead guardado (ID {new_id}).")

    # Editor
    lead_edit_id = st.session_state.get("lead_to_edit")
    if lead_edit_id:
        st.divider()
        st.subheader("Editar lead")
        row = leads[leads["id_lead"].astype(str) == str(lead_edit_id)].iloc[0].copy()
        with st.form(f"form_edit_{lead_edit_id}"):
            c1, c2, c3 = st.columns(3)
            nombre_e = c1.text_input("Nombre", value=row.get("nombre", ""))
            apellidos_e = c2.text_input("Apellidos", value=row.get("apellidos", ""))
            alias_e = c3.text_input("Alias", value=row.get("alias", ""))
            c4, c5, c6 = st.columns(3)
            edad_e = c4.number_input("Edad", min_value=0, max_value=120, step=1, value=int(row.get("edad") or 0))
            celular_e = c5.text_input("Celular", value=row.get("celular", ""))
            correo_e = c6.text_input("Correo", value=row.get("correo", ""))
            c7, c8 = st.columns(2)
            interes_e = c7.selectbox("Tipo de curso / interés", COURSE_OPTIONS, index=(COURSE_OPTIONS.index(row.get("interes_curso", COURSE_OPTIONS[0])) if row.get("interes_curso", "") in COURSE_OPTIONS else 0))
            canal_e = c8.selectbox("¿Cómo te enteraste?", CHANNEL_OPTIONS, index=(CHANNEL_OPTIONS.index(row.get("como_enteraste", CHANNEL_OPTIONS[0])) if row.get("como_enteraste", "") in CHANNEL_OPTIONS else 0))
            stages = emb["stage"].tolist()
            idx = stages.index(normalize_stage(row.get("lead_status", "Awareness"))) if normalize_stage(row.get("lead_status", "Awareness")) in stages else 0
            estado_e_lbl = st.selectbox("Etapa (en) (es)", [STAGE_LABEL[s] for s in stages], index=idx)
            obs_e = st.text_area("Observaciones", value=row.get("observaciones", ""))
            prox_f = st.date_input("Próxima acción (fecha)", value=pd.to_datetime(row.get("proxima_accion_fecha", "") or date.today()).date())
            prox_d = st.text_input("Próxima acción (descripción)", value=row.get("proxima_accion_desc", ""))
            ok = st.form_submit_button("Actualizar")
            if ok:
                estado_en = stages[[STAGE_LABEL[s] for s in stages].index(estado_e_lbl)]
                mask = leads["id_lead"].astype(str) == str(lead_edit_id)
                prev_stage = normalize_stage(row.get("lead_status", "Awareness"))
                leads.loc[mask, [
                    "nombre", "apellidos", "alias", "edad", "celular", "correo",
                    "interes_curso", "como_enteraste",
                    "lead_status", "observaciones",
                    "proxima_accion_fecha", "proxima_accion_desc",
                ]] = [
                    nombre_e, apellidos_e, alias_e, int(edad_e) if str(edad_e) != "" else "",
                    norm_phone(celular_e), norm_email(correo_e),
                    interes_e, canal_e,
                    estado_en, obs_e,
                    prox_f.strftime("%Y-%m-%d") if prox_d else "", prox_d,
                ]
                row_now = leads.loc[mask].iloc[0].to_dict()
                leads.loc[mask, "lead_score"] = str(compute_lead_score(pd.Series(row_now)))
                if prev_stage != estado_en:
                    leads.loc[mask, "fecha_entrada_etapa"] = now_date()
                save_csv(leads, FILES["leads"])
                st.success("Lead actualizado.")

def page_followup():
    global leads, segs
    st.title("✉️ Seguimiento")

    dcol1, dcol2 = st.columns([1,3])
    selected_date = dcol1.date_input("📅 Fecha", value=date.today(), key="fu_date")
    solo_mios = dcol1.checkbox("Solo mis leads", value=False, key="fu_only_mine")
    q = dcol2.text_input("🔎 Buscar lead (nombre, alias, email o teléfono)", key="fu_search")

    base = leads.copy()
    if solo_mios:
        base = base[base["owner"] == owner_name_default()]
    if q:
        ql = q.lower()
        base = base[base.apply(lambda r: ql in f"{r.get('nombre','')} {r.get('apellidos','')} {r.get('alias','')} {r.get('correo','')} {r.get('celular','')}".lower(), axis=1)]
    due = base[base["proxima_accion_fecha"] == selected_date.strftime("%Y-%m-%d")]

    st.caption(f"Acciones para {selected_date.strftime('%Y-%m-%d')}: {len(due)}")
    if due.empty:
        st.info("No hay acciones programadas para la fecha seleccionada.")
    else:
        for _, row in due.iterrows():
            with st.container(border=True):
                cA, cB, cC = st.columns([5,3,2])
                cA.markdown(f"**{row['nombre']} {row['apellidos']}** • {row.get('alias','')} • {row.get('celular','')}")
                cB.markdown(stage_badge(row.get("lead_status","Awareness")), unsafe_allow_html=True)
                if cC.button("📨 Abrir", key=f"open_{row['id_lead']}"):
                    st.session_state["lead_for_followup_id"] = str(row["id_lead"])
                    st.experimental_rerun()
                st.caption(f"➡️ {row.get('proxima_accion_desc','') or '—'}")

    st.divider()

    base2 = leads.copy()
    if q:
        ql = q.lower()
        base2 = base2[base2.apply(lambda r: ql in f"{r.get('nombre','')} {r.get('apellidos','')} {r.get('alias','')} {r.get('correo','')} {r.get('celular','')}".lower(), axis=1)]
    id_to_label = {str(r["id_lead"]): lead_label(r) for _, r in base2.iterrows()}
    options = [""] + list(id_to_label.keys())
    default_idx = 0
    if "lead_for_followup_id" in st.session_state and st.session_state["lead_for_followup_id"] in id_to_label:
        default_idx = options.index(st.session_state["lead_for_followup_id"])
        st.session_state.pop("lead_for_followup_id", None)

    lead_id = st.selectbox("Selecciona lead", options, index=default_idx,
                           format_func=lambda k: id_to_label.get(k, "—") if k else "—")
    if not lead_id:
        return

    lead_ctx = leads[leads["id_lead"].astype(str) == str(lead_id)].iloc[0]

    with st.container(border=True):
        c1, c2, c3 = st.columns([5,3,2])
        c1.markdown(f"### {lead_ctx['nombre']} {lead_ctx['apellidos']}  \n📞 {lead_ctx.get('celular','—')} • ✉️ {lead_ctx.get('correo','—')}")
        c2.markdown(stage_badge(lead_ctx.get("lead_status","Awareness")), unsafe_allow_html=True)
        c3.markdown(owner_badge(lead_ctx.get("owner","")), unsafe_allow_html=True)

    st.subheader("Historial del lead")
    hist = segs[segs["id_lead"].astype(str) == str(lead_id)].sort_values(["fecha", "hora"]) if not segs.empty else pd.DataFrame(columns=SCHEMA_SEGS)
    st.dataframe(hist[["fecha", "hora", "tipo_mensaje", "estado_mensaje", "canal", "atendido_por", "mensaje_sugerido", "respuesta", "observaciones"]], use_container_width=True, hide_index=True)

    st.divider()
    st.subheader("Plantillas por etapa")
    seleccionadas = []
    for stage in STAGE_ORDER:
        t = STAGE_TEMPLATES.get(stage)
        desc = STAGE_DESC.get(stage, "")
        bg, fg = STAGE_COLORS.get(stage, ("#F1F5F9", "#0F172A"))
        with st.expander(f"• {STAGE_LABEL[stage]} — {desc}"):
            st.markdown(f"<div style='display:inline-block;background:{bg};color:{fg};padding:2px 8px;border-radius:999px;font-size:12px;font-weight:600'>{stage}</div>", unsafe_allow_html=True)
            usar = st.checkbox(f"Usar plantilla de {stage}", key=f"tpl_{stage}")
            pre = render_tpl(t["plantilla"], lead_ctx)
            st.caption(f"Sugerido: {t['canal']} • Tipo: {t['tipo']}")
            st.code(t["plantilla"])
            st.text_area("Previsualización", value=pre, height=100, disabled=True)
            if usar:
                seleccionadas.append((stage, t))

    st.subheader("Envío y próxima acción")
    c1, c2, c3, c4 = st.columns(4)
    canal = c1.selectbox("Canal", CHANNEL_OPTIONS, index=(CHANNEL_OPTIONS.index("WhatsApp") if "WhatsApp" in CHANNEL_OPTIONS else 0))
    atendido_por = c2.text_input("Atendido por", value=owner_name_default())
    estado_msg = c3.selectbox("Estado del mensaje", ["Enviado", "Sin respuesta", "Respondido", "Perdido"])
    repro_plus = c4.selectbox("Reprogramar +días (atajo)", [0,1,2,3,5,7,14], index=0)

    cNA, cNB = st.columns(2)
    prox_fecha = cNA.date_input("Próxima acción (fecha)", value=pd.to_datetime(lead_ctx.get("proxima_accion_fecha","") or date.today()).date())
    prox_desc  = cNB.text_input("Próxima acción (descripción)", value=lead_ctx.get("proxima_accion_desc",""))

    # NUEVO: cerrar acción para quitar del calendario
    close_today = st.checkbox("Cerrar acción de la fecha seleccionada (quitar del calendario)", value=True)

    stages = emb["stage"].tolist()
    idx_stage = stages.index(normalize_stage(lead_ctx.get("lead_status","Awareness"))) if normalize_stage(lead_ctx.get("lead_status","Awareness")) in stages else 0
    etapa_lbl = st.selectbox("Etapa del embudo (en) (es)", [STAGE_LABEL[s] for s in stages], index=idx_stage)
    etapa_en = stages[[STAGE_LABEL[s] for s in stages].index(etapa_lbl)]
    st.markdown(stage_badge(etapa_en), unsafe_allow_html=True)

    if st.button("Registrar seguimiento(s)"):
        if not seleccionadas:
            st.warning("Selecciona al menos una plantilla (arriba).")
        else:
            to_add = []
            for stage, t in seleccionadas:
                new_id = next_id(segs, "id_seguimiento")
                to_add.append({
                    "id_seguimiento": str(new_id),
                    "id_lead": str(lead_id),
                    "fecha": now_date(),
                    "hora": now_time(),
                    "tipo_mensaje": f"{t['tipo']} ({stage})",
                    "estado_mensaje": estado_msg,
                    "canal": canal,
                    "atendido_por": atendido_por,
                    "mensaje_sugerido": render_tpl(t["plantilla"], lead_ctx),
                    "respuesta": "",
                    "observaciones": "",
                })
            segs = pd.concat([segs, pd.DataFrame(to_add)], ignore_index=True)
            save_csv(segs, FILES["seguimientos"])

            # Actualizar lead
            mask = leads["id_lead"].astype(str) == str(lead_id)
            prev_stage = normalize_stage(leads.loc[mask].iloc[0].get("lead_status","Awareness"))
            old_next = str(leads.loc[mask].iloc[0].get("proxima_accion_fecha",""))  # para comparación
            leads.loc[mask, "lead_status"] = etapa_en

            selected_str = selected_date.strftime("%Y-%m-%d")
            prox_str = prox_fecha.strftime("%Y-%m-%d")
            # Lógica de agenda:
            # - Si close_today y no reprogramas (+0) y prox_fecha == selected_date -> limpiar (quitar del calendario)
            # - Si reprogramas (>0) -> mover a hoy + N
            # - Si eliges otra fecha manual -> usar esa fecha
            if close_today and int(repro_plus) == 0 and prox_str == selected_str:
                next_date = ""
                next_desc = ""
            elif int(repro_plus) > 0:
                next_date = (date.today() + timedelta(days=int(repro_plus))).strftime("%Y-%m-%d")
                next_desc = prox_desc or "Reprogramado desde seguimiento"
            else:
                next_date = prox_str
                next_desc = prox_desc

            leads.loc[mask, ["proxima_accion_fecha", "proxima_accion_desc"]] = [next_date, next_desc]
            leads.loc[mask, "fecha_ultimo_contacto"] = now_date()
            row_now = leads.loc[mask].iloc[0]
            leads.loc[mask, "lead_score"] = str(compute_lead_score(row_now))
            if prev_stage != etapa_en:
                leads.loc[mask, "fecha_entrada_etapa"] = now_date()
            save_csv(leads, FILES["leads"])

            # Opcional: limpiar selección para no mantener el lead abierto
            # y que se note el "desaparecer" del calendario si aplicó.
            st.session_state.pop("lead_for_followup_id", None)

            st.success("Seguimiento registrado y lead actualizado.")

    st.divider()
    st.subheader("Actualizar estado / respuesta (último mensaje)")
    if not hist.empty:
        last_id = hist.iloc[-1]["id_seguimiento"]
        sel = segs[segs["id_seguimiento"] == last_id].iloc[0]
        with st.form(f"form_resp_{last_id}"):
            estados = ["Enviado", "Sin respuesta", "Respondido", "Perdido"]
            idx = estados.index(sel["estado_mensaje"]) if sel["estado_mensaje"] in estados else 0
            nuevo_estado = st.selectbox("Estado del mensaje", estados, index=idx)
            nueva_resp = st.text_area("Respuesta del lead", value=sel.get("respuesta", ""))
            nueva_obs = st.text_area("Observaciones", value=sel.get("observaciones", ""))
            cA, cB = st.columns(2)
            reprog_plus = cA.selectbox("Reprogramar +días", [0,1,2,3,5,7,14], index=0)
            ok = cB.form_submit_button("Guardar")
            if ok:
                m = segs["id_seguimiento"] == last_id
                segs.loc[m, ["estado_mensaje", "respuesta", "observaciones"]] = [nuevo_estado, nueva_resp, nueva_obs]
                save_csv(segs, FILES["seguimientos"])
                mask = leads["id_lead"].astype(str) == str(lead_id)
                if int(reprog_plus) > 0:
                    nueva = (date.today() + timedelta(days=int(reprog_plus))).strftime("%Y-%m-%d")
                    leads.loc[mask, ["proxima_accion_fecha", "proxima_accion_desc"]] = [nueva, "Reprogramado desde seguimiento"]
                leads.loc[mask, "fecha_ultimo_contacto"] = now_date()
                row_now = leads.loc[mask].iloc[0]
                leads.loc[mask, "lead_score"] = str(compute_lead_score(row_now))
                save_csv(leads, FILES["leads"])
                st.success("Seguimiento actualizado.")

# ===== Helpers de tiempo para el Dashboard =====
def start_of_week(d: date) -> date:
    return d - timedelta(days=d.weekday())

def month_bounds(d: date) -> tuple[date, date]:
    first = d.replace(day=1)
    if d.month == 12:
        next_first = d.replace(year=d.year+1, month=1, day=1)
    else:
        next_first = d.replace(month=d.month+1, day=1)
    last = next_first - timedelta(days=1)
    return first, last

def parse_date_col(df: pd.DataFrame, col: str) -> pd.Series:
    return pd.to_datetime(df[col], errors="coerce")

# =========================
# DASHBOARD (v10)
# =========================
def page_dashboard():
    st.title("📊 Dashboard")

    c1, c2, c3 = st.columns([1.2, 1.2, 2])
    periodo = c1.selectbox("Periodo", ["Hoy", "Esta semana", "Últimos 7 días", "Este mes", "Personalizado"], index=1)
    if periodo == "Personalizado":
        rango = c2.date_input("Rango de fechas", value=(date.today() - timedelta(days=6), date.today()))
        if isinstance(rango, tuple):
            d_from, d_to = rango
        else:
            d_from, d_to = rango[0], rango[-1] if isinstance(rango, list) else (date.today(), date.today())
    elif periodo == "Hoy":
        d_from = d_to = date.today()
    elif periodo == "Esta semana":
        d_from = start_of_week(date.today())
        d_to = d_from + timedelta(days=6)
    elif periodo == "Últimos 7 días":
        d_to = date.today()
        d_from = d_to - timedelta(days=6)
    elif periodo == "Este mes":
        d_from, d_to = month_bounds(date.today())

    f_curso = c3.selectbox("Filtrar por curso (opcional)", ["(Todos)"] + COURSE_OPTIONS, index=0)

    leads["__fecha_reg"] = parse_date_col(leads, "fecha_registro").dt.date
    leads["__fecha_won"] = parse_date_col(leads, "fecha_entrada_etapa").dt.date
    segs["__fecha_seg"]  = parse_date_col(segs, "fecha").dt.date

    mask_period_leads = (leads["__fecha_reg"] >= d_from) & (leads["__fecha_reg"] <= d_to)
    leads_new = leads[mask_period_leads].copy()

    leads_won = leads[(leads["lead_status"] == "Won") & (leads["__fecha_won"] >= d_from) & (leads["__fecha_won"] <= d_to)].copy()

    segs_period = segs[(segs["__fecha_seg"] >= d_from) & (segs["__fecha_seg"] <= d_to)].copy()

    if f_curso != "(Todos)":
        leads_new = leads_new[leads_new["interes_curso"] == f_curso]
        leads_won = leads_won[leads_won["interes_curso"] == f_curso]
        if not segs_period.empty:
            segs_period = segs_period.merge(leads[["id_lead", "interes_curso"]], on="id_lead", how="left")
            segs_period = segs_period[segs_period["interes_curso"] == f_curso]

    k1, k2, k3, k4 = st.columns(4)
    total_leads_period = len(leads_new)
    total_won_period   = len(leads_won)
    total_segs_period  = len(segs_period)
    conv_period = (total_won_period / total_leads_period * 100) if total_leads_period else 0.0

    k1.metric("🆕 Nuevos leads", total_leads_period)
    k2.metric("✅ Inscritos (Won)", total_won_period)
    k3.metric("✉️ Seguimientos", total_segs_period)
    k4.metric("🎯 Conversión periodo", f"{conv_period:.1f}%")

    st.caption(f"Periodo: {d_from} → {d_to}" + ("" if f_curso == "(Todos)" else f" • Curso: {f_curso}"))

    st.subheader("Embudo actual (conteo por etapa)")
    counts = leads.groupby("lead_status").size().rename("count").reset_index()
    counts["orden"] = counts["lead_status"].apply(lambda s: STAGE_ORDER.index(s) if s in STAGE_ORDER else 999)
    counts = counts.sort_values("orden")
    funnel_colors = [STAGE_COLORS[s][0] for s in STAGE_ORDER]
    chart_funnel = alt.Chart(counts).mark_bar().encode(
        x=alt.X("count:Q", title="Leads"),
        y=alt.Y("lead_status:N", sort=STAGE_ORDER, title="Etapa"),
        color=alt.Color("lead_status:N", scale=alt.Scale(domain=STAGE_ORDER, range=funnel_colors), legend=None),
        tooltip=["lead_status", "count"]
    ).properties(height=320)
    st.altair_chart(chart_funnel, use_container_width=True)

    st.divider()
    st.subheader("Tendencia diaria (periodo)")

    idx_days = pd.date_range(pd.to_datetime(d_from), pd.to_datetime(d_to), freq="D").date

    def series_count(df: pd.DataFrame, date_col: str, label: str) -> pd.DataFrame:
        if df.empty:
            base = pd.DataFrame({"fecha": idx_days, "valor": 0})
        else:
            tmp = df.copy()
            tmp["fecha"] = pd.to_datetime(tmp[date_col], errors="coerce").dt.date
            base = pd.DataFrame({"fecha": idx_days})
            tmp = tmp.groupby("fecha").size().rename("valor").reset_index()
            base = base.merge(tmp, on="fecha", how="left").fillna(0)
        base["tipo"] = label
        return base

    serie_leads = series_count(leads_new, "__fecha_reg", "Nuevos leads")
    serie_segs  = series_count(segs_period, "__fecha_seg", "Seguimientos")
    serie_won   = series_count(leads_won, "__fecha_won", "Inscritos (Won)")
    series_all  = pd.concat([serie_leads, serie_segs, serie_won], ignore_index=True)

    line = alt.Chart(series_all).mark_line(point=True).encode(
        x=alt.X("fecha:T", title="Fecha"),
        y=alt.Y("valor:Q", title="Eventos"),
        color=alt.Color("tipo:N", legend=alt.Legend(title="Serie")),
        tooltip=["fecha:T", "tipo:N", "valor:Q"]
    ).properties(height=300)
    st.altair_chart(line, use_container_width=True)

    st.divider()
    st.subheader("Desglose por curso (periodo)")

    grp_new = (leads_new.groupby("interes_curso").size().rename("Nuevos leads").reset_index()) if not leads_new.empty else pd.DataFrame({"interes_curso": [], "Nuevos leads": []})
    grp_seg = pd.DataFrame({"interes_curso": [], "Seguimientos": []})
    if not segs_period.empty:
        segs_with_course = segs_period if "interes_curso" in segs_period.columns else segs_period.merge(leads[["id_lead", "interes_curso"]], on="id_lead", how="left")
        grp_seg = segs_with_course.groupby("interes_curso").size().rename("Seguimientos").reset_index()
    grp_won = (leads_won.groupby("interes_curso").size().rename("Inscritos (Won)").reset_index()) if not leads_won.empty else pd.DataFrame({"interes_curso": [], "Inscritos (Won)": []})

    cA, cB, cC = st.columns(3)
    chart_new = alt.Chart(grp_new).mark_bar().encode(
        x=alt.X("Nuevos leads:Q", title="Nuevos"),
        y=alt.Y("interes_curso:N", sort='-x', title="Curso"),
        tooltip=["interes_curso", "Nuevos leads"]
    ).properties(height=260)
    cA.altair_chart(chart_new, use_container_width=True)

    chart_seg = alt.Chart(grp_seg).mark_bar().encode(
        x=alt.X("Seguimientos:Q", title="Seguimientos"),
        y=alt.Y("interes_curso:N", sort='-x', title="Curso"),
        tooltip=["interes_curso", "Seguimientos"]
    ).properties(height=260)
    cB.altair_chart(chart_seg, use_container_width=True)

    chart_won = alt.Chart(grp_won).mark_bar().encode(
        x=alt.X("Inscritos (Won):Q", title="Inscritos"),
        y=alt.Y("interes_curso:N", sort='-x', title="Curso"),
        tooltip=["interes_curso", "Inscritos (Won)"]
    ).properties(height=260)
    cC.altair_chart(chart_won, use_container_width=True)

    st.caption("Notas: 'Nuevos leads' = fecha_registro en el periodo. 'Inscritos (Won)' = leads con etapa Won cuya fecha_entrada_etapa cae en el periodo. 'Seguimientos' = registros en seguimientos.csv dentro del periodo.")

# =========================
# Enrutamiento
# =========================
if st.session_state["menu"] == "👤 Leads":
    page_leads()
elif st.session_state["menu"] == "✉️ Seguimiento":
    page_followup()
elif st.session_state["menu"] == "📊 Dashboard":
    page_dashboard()

st.caption("Leads: alta visible inmediata. Seguimiento: checkbox para quitar del calendario al registrar. Dashboard con KPIs y colores por etapa.")
