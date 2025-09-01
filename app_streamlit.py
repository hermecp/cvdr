from __future__ import annotations
import pandas as pd
import streamlit as st
import altair as alt
from pathlib import Path
from datetime import datetime, date, timedelta
import hashlib
from urllib.parse import quote_plus

st.set_page_config(page_title="Mini-CRM CVDR v10.3", layout="wide")

# --------------------------
# Carpeta de datos local ./data
# --------------------------
BASE = (Path(__file__).resolve().parent / "data")
BASE.mkdir(parents=True, exist_ok=True)

FILES = {
    "leads":        str(BASE / "leads.csv"),
    "seguimientos": str(BASE / "seguimientos.csv"),
    "embudo":       str(BASE / "embudo_etapas.csv"),
    "usuarios":     str(BASE / "users.csv"),
}
REQUIRED = ["leads", "seguimientos"]

def _hash(p: str) -> str:
    return hashlib.sha256((p or "").encode("utf-8")).hexdigest()

# --------------------------
# Usuarios (CSV con hash)
# Estructura CSV: username,name,role,pass_hash
# Actualiza/crea los usuarios con los hashes solicitados (contraseñas no se exponen).
# --------------------------
DEFAULT_USER_ROWS = [
    # username, name, role, pass_hash( SHA-256 )
    ["admin","Admin","Admin","ba26148e3bc77341163135d123a4dc26664ff0497da04c0b3e83218c97f70c45"],         # CVDR873
    ["director","Director","Director","c34926c2783dca6cf34d1160ed5a04e1615cb813d3b5798efc29cc590cce4c91"],   # CVDR843
    ["subidirector","Subidirector","Subidirector","58845944d08671209339de539469a100c8e9d6e17dcee9a447c7751937f7cb48"],  # CVDR52874
    ["favio","Favio","Ventas","e28ebb5d991f9ebbc5f2d26b199586e9bfb8fffd3b76dca200efd75eb68e999d"],          # CVDR394
    ["nancy","Nancy","Ventas","64b1bce63509372952ad7191af86bddcb9939772404c236ff67b89d0442496d0"],          # CVDR363
    ["rosario","Rosario","Ventas","706f42010b29d6376c768d717a19b49dc50b8b7133bffa1ae36d0fbbc32d59bc"],       # CVDR434
    ["hayde","Hayde","Comunicación","6b90d996f7c98698cd95d0d86f1298dbb9df89df34f16136b259a4efcaba04d8"],     # CVDR152
    ["nora","Nora","Comunicación","f54fd67046eeca39cd1f760730d3b48b1c00d383f0c5b9fa5ace0a7683a22058"],       # CVDR192
]

def ensure_or_update_users_csv():
    p = Path(FILES["usuarios"])
    if p.exists():
        # actualiza/mezcla con los usuarios requeridos (reemplaza pass_hash y datos clave)
        existing = pd.read_csv(p, dtype=str).fillna("")
        ex_idx = {u.strip().lower(): i for i, u in enumerate(existing.get("username", pd.Series(dtype=str)).astype(str))}
        for u, name, role, ph in DEFAULT_USER_ROWS:
            key = u.strip().lower()
            if key in ex_idx:
                i = ex_idx[key]
                existing.at[i, "name"] = name
                existing.at[i, "role"] = role
                existing.at[i, "pass_hash"] = ph
            else:
                existing = pd.concat([
                    existing,
                    pd.DataFrame([{"username": u, "name": name, "role": role, "pass_hash": ph}])
                ], ignore_index=True)
        existing[["username","name","role","pass_hash"]].to_csv(p, index=False)
    else:
        df = pd.DataFrame(DEFAULT_USER_ROWS, columns=["username","name","role","pass_hash"])
        df.to_csv(p, index=False)

def load_users() -> dict:
    ensure_or_update_users_csv()
    df = pd.read_csv(FILES["usuarios"], dtype=str).fillna("")
    users = {}
    for _, r in df.iterrows():
        users[str(r["username"]).strip().lower()] = {
            "name": r["name"], "role": r["role"], "pass_hash": r["pass_hash"]
        }
    return users

USERS = load_users()

def is_logged() -> bool:
    return bool(st.session_state.get("user"))

def require_login():
    if not is_logged():
        st.stop()

def owner_name_default() -> str:
    if not is_logged(): return "Asesor"
    return st.session_state["user"]["name"]

STAGE_ORDER = [
    "Awareness", "Contacted", "MQL", "SQL", "Nurturing", "Demo_Booked", "Won", "Lost", "Re_Engaged"
]
STAGE_LABEL = {
    "Awareness":   "Awareness (Captado)",
    "Contacted":   "Contacted (Contactado)",
    "MQL":         "MQL (Info enviada)",
    "SQL":         "SQL (Interesado / Oportunidad)",
    "Nurturing":   "Nurturing (En seguimiento / Temario)",
    "Demo_Booked": "Demo_Booked (Depósito / Preinscripción)",
    "Won":         "Won (Inscrito / Cliente)",
    "Lost":        "Lost (Perdido)",
    "Re_Engaged":  "Re_Engaged (Reactivado)",
}
SPANISH_TO_EN = {
    "Captado": "Awareness",
    "Contactado": "Contacted",
    "Info enviada": "MQL", "Info_enviada": "MQL", "MQL": "MQL",
    "Interesado": "SQL",
    "En seguimiento": "Nurturing", "En_seguimiento": "Nurturing",
    "Depósito": "Demo_Booked", "Preinscripción": "Demo_Booked",
    "Inscrito": "Won", "Inscrita": "Won",
    "Perdido": "Lost",
    "Reactivado": "Re_Engaged",
}
STAGE_DESC = {
    "Awareness":   "Conoce la marca por primera vez.",
    "Contacted":   "Se realizó el primer contacto.",
    "MQL":         "Se envió información/temario y detalles del curso.",
    "SQL":         "Oportunidad real; tiene intención clara.",
    "Nurturing":   "Seguimiento con temario/contenidos y próximas fechas.",
    "Demo_Booked": "Depósito/Preinscripción para asegurar lugar.",
    "Won":         "Cliente inscrito.",
    "Lost":        "No se convirtió en cliente.",
    "Re_Engaged":  "Lead reactivado con nuevas fechas o promociones.",
}
STAGE_COLORS = {
    "Awareness":    ("#F8FAFC", "#0F172A"),
    "Contacted":    ("#EFF6FF", "#075985"),
    "MQL":          ("#FEFCE8", "#713F12"),
    "SQL":          ("#ECFDF5", "#14532D"),
    "Nurturing":    ("#F5F3FF", "#4C1D95"),
    "Demo_Booked":  ("#FFF1F2", "#9F1239"),
    "Won":          ("#F0FDF4", "#065F46"),
    "Lost":         ("#FEF2F2", "#7F1D1D"),
    "Re_Engaged":   ("#EEF2FF", "#3730A3"),
}
STAGE_TEMPLATES = {
    "Awareness":   {"tipo": "Bienvenida", "canal": "WhatsApp",
                    "plantilla": "Hola {nombre}, gracias por tu interés en {curso}. ¿Te comparto información breve con temario, costo y fechas?"},
    "Contacted":   {"tipo": "Seguimiento inicial", "canal": "WhatsApp",
                    "plantilla": "Hola {nombre}, ¿pudiste revisar la información de {curso}? Si te parece, te envío opciones de fechas y formas de pago."},
    "MQL":         {"tipo": "Envío de información", "canal": "WhatsApp",
                    "plantilla": "Te comparto temario y detalles de {curso} (duración, modalidad y costo). ¿Tienes alguna duda u objetivo específico?"},
    "SQL":         {"tipo": "Cierre suave", "canal": "WhatsApp",
                    "plantilla": "Con lo que me comentaste, {curso} te ayudaría bastante. Para inscribirte, manejamos pago por transferencia o depósito. ¿Te envío los datos?"},
    "Nurturing":   {"tipo": "Contenido de valor", "canal": "WhatsApp",
                    "plantilla": "Te dejo este material breve sobre {curso}. Tenemos grupo próximo; si te interesa, la fecha límite de inscripción es {fecha_limite}."},
    "Demo_Booked": {"tipo": "Preinscripción/Depósito", "canal": "WhatsApp",
                    "plantilla": "Para asegurar tu lugar en {curso}, realiza el depósito de preinscripción. Te comparto monto y datos; al confirmar, te envío acceso."},
    "Won":         {"tipo": "Bienvenida alumno", "canal": "WhatsApp",
                    "plantilla": "¡Bienvenido(a), {nombre}! Tu registro en {curso} quedó confirmado. En breve recibirás instrucciones y acceso."},
    "Lost":        {"tipo": "Cierre cordial", "canal": "WhatsApp",
                    "plantilla": "Gracias por tu tiempo, {nombre}. Si deseas retomar {curso} más adelante, con gusto te apoyamos con próximas fechas."},
    "Re_Engaged":  {"tipo": "Reactivación", "canal": "WhatsApp",
                    "plantilla": "Tenemos nuevas fechas y opciones de {curso}. ¿Te comparto horarios y promociones vigentes?"},
}

SCHEMA_LEADS = [
    "id_lead","fecha_registro","hora_registro","nombre","apellidos","alias","edad",
    "celular","telefono","correo","interes_curso","como_enteraste","lead_status","funnel_etapas",
    "fecha_ultimo_contacto","observaciones","owner","proxima_accion_fecha","proxima_accion_desc",
    "lead_score","probabilidad_cierre","monto_estimado","motivo_perdida","fecha_entrada_etapa",
]
SCHEMA_SEGS = [  # historial solicitado
    "id_seguimiento","id_lead","fecha","hora","etapa","proxima_accion_fecha",
    "tipo_mensaje","estado_mensaje","canal","atendido_por","observaciones"
]
DEFAULTS = {
    "alias":"", "edad":"", "telefono":"", "fecha_ultimo_contacto":"", "observaciones":"",
    "owner":"", "proxima_accion_fecha":"", "proxima_accion_desc":"",
    "lead_score":"0", "probabilidad_cierre":"0.2", "monto_estimado":"", "motivo_perdida":"",
    "fecha_entrada_etapa":"", "funnel_etapas":"",
}
COURSE_OPTIONS = [
    "IA profesionales inmobiliarios","IA educación básica","IA educación universitaria",
    "IA empresas","IA para gobierno","Inglés","Polivirtual Bach.","Polivirtual Lic.",
]
CHANNEL_OPTIONS = ["WhatsApp","Teléfono","Correo","Facebook","Instagram","Google","Referido","Otro"]

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
    if row.get("como_enteraste") in ["Referido","Facebook","Google","WhatsApp"]:
        score += 10
    if normalize_stage(row.get("lead_status","")) in ["SQL","Demo_Booked"]:
        score += 20
    try:
        edad = int(row.get("edad") or 0)
        if 25 <= edad <= 45:
            score += 10
    except Exception:
        pass
    if str(row.get("owner","")).strip():
        score += 5
    return min(score, 100)

# Crear archivos base si no existen
for k in REQUIRED:
    p = Path(FILES[k])
    if not p.exists():
        if k == "leads":
            save_csv(pd.DataFrame(columns=SCHEMA_LEADS), FILES[k])
        elif k == "seguimientos":
            save_csv(pd.DataFrame(columns=SCHEMA_SEGS), FILES[k])
if not Path(FILES["embudo"]).exists():
    save_csv(pd.DataFrame({"stage": STAGE_ORDER}), FILES["embudo"])

leads = ensure_columns(load_csv(FILES["leads"], dtype=str), SCHEMA_LEADS, DEFAULTS)
segs  = ensure_columns(load_csv(FILES["seguimientos"], dtype=str), SCHEMA_SEGS, {})

emb_raw = load_csv(FILES["embudo"], dtype=str)
if "stage" in emb_raw.columns:
    emb = emb_raw[["stage"]].drop_duplicates()
elif "etapa" in emb_raw.columns:
    emb = emb_raw[["etapa"]].rename(columns={"etapa":"stage"})
    emb["stage"] = emb["stage"].map(normalize_stage)
    emb = emb[["stage"]].drop_duplicates()
else:
    emb = pd.DataFrame({"stage": STAGE_ORDER})

leads["lead_status"] = leads["lead_status"].apply(normalize_stage)
if "funnel_etapas" not in leads.columns:
    leads["funnel_etapas"] = ""
leads["lead_score"] = leads.apply(compute_lead_score, axis=1).astype(str)

st.markdown(
    """
    <style>
      .app-title {font-weight:800;font-size:22px;margin-bottom:4px;}
      .muted {opacity:.9}
      .card {border:1px solid #e5e7eb;border-radius:14px;padding:14px;background:#ffffff;}
      .section {padding:10px 14px;border-radius:12px;background:#f8fafc;border:1px solid #e5e7eb;}
      .stApp header {background: transparent;}
      .wa-actions a {text-decoration:none;}
      .wa-actions .btn {display:inline-block;border:1px solid #e5e7eb;border-radius:10px;padding:6px 10px;margin-right:8px;}
    </style>
    """,
    unsafe_allow_html=True
)

def login_sidebar():
    with st.sidebar:
        st.markdown("<div class='app-title'>Mini-CRM CVDR</div><div class='muted'>Acceso</div>", unsafe_allow_html=True)
        st.write("")
        if not is_logged():
            u = st.text_input("Usuario")
            p = st.text_input("Contraseña", type="password")
            if st.button("Iniciar sesión", use_container_width=True):
                info = USERS.get(u.strip().lower())
                if not info or info["pass_hash"] != _hash(p):
                    st.error("Usuario o contraseña incorrectos."); st.stop()
                st.session_state["user"] = {"username": u.strip().lower(), "name": info["name"], "role": info["role"]}
                st.rerun()
        else:
            user = st.session_state["user"]
            st.success(f"Conectado: {user['name']} • {user['role']}")
            if st.button("Cerrar sesión", use_container_width=True):
                st.session_state.clear(); st.rerun()

login_sidebar()
require_login()

if "menu" not in st.session_state:
    st.session_state["menu"] = "👤 Leads"

c_nav = st.container()
with c_nav:
    col1, col2, col3 = st.columns([1,1,1])
    if col1.button("👤 Leads", use_container_width=True):
        st.session_state["menu"] = "👤 Leads"; st.rerun()
    if col2.button("✉️ Seguimiento", use_container_width=True):
        st.session_state["menu"] = "✉️ Seguimiento"; st.rerun()
    if col3.button("📊 Dashboard", use_container_width=True):
        st.session_state["menu"] = "📊 Dashboard"; st.rerun()

menu = st.session_state["menu"]

def lead_label(row: pd.Series) -> str:
    name = f"{row.get('nombre','')} {row.get('apellidos','')}".strip()
    alias = row.get("alias","").strip()
    tel = row.get("celular","") or row.get("telefono","")
    tag = f" • {alias}" if alias else ""
    tel = f" • {tel}" if tel else ""
    return f"{name}{tag}{tel}"

def render_tpl(text: str, lead_row: pd.Series) -> str:
    ctx = {k: lead_row.get(k, "") for k in lead_row.index}
    ctx.update({"nombre": lead_row.get("nombre",""), "curso": lead_row.get("interes_curso",""),
                "fecha_limite": "", "precio": lead_row.get("monto_estimado","")})
    try: return text.format(**ctx)
    except KeyError: return text

def stage_badge(stage_en: str) -> str:
    bg, fg = STAGE_COLORS.get(stage_en, ("#F1F5F9", "#0F172A"))
    label = STAGE_LABEL.get(stage_en, stage_en)
    return f"<span style='background:{bg};color:{fg};padding:2px 8px;border-radius:999px;font-size:12px;font-weight:700'>{label}</span>"

def owner_badge(owner: str) -> str:
    if not owner: owner = "—"
    return f"<span style='background:#ECFDF5;color:#065F46;padding:2px 8px;border-radius:999px;'>Owner: {owner}</span>"

# ---------------------- Leads ----------------------
def page_leads():
    global leads
    st.markdown("## 👤 Leads")

    q = st.text_input("🔎 Buscar (nombre, alias, email o teléfono)", key="leads_search")

    L = leads.copy()
    if q:
        ql = q.lower()
        def _hay_coincidencia(r):
            s = " ".join([
                str(r.get('nombre','')),
                str(r.get('apellidos','')),
                str(r.get('alias','')),
                str(r.get('correo','')),
                str(r.get('celular','')),
            ]).lower()
            return ql in s
        L = L[L.apply(_hay_coincidencia, axis=1)]

    cols_vista = [
        "id_lead","nombre","apellidos","alias","celular","correo","interes_curso",
        "como_enteraste","lead_status","owner","proxima_accion_fecha","proxima_accion_desc","fecha_ultimo_contacto","lead_score"
    ]
    for c in cols_vista:
        if c not in L.columns: L[c] = ""

    st.download_button("⬇️ Descargar leads (CSV)", data=L.to_csv(index=False).encode("utf-8"),
                       file_name="leads.csv", mime="text/csv")

    if "leads_page_idx" not in st.session_state: st.session_state["leads_page_idx"] = 0
    page_size = st.selectbox("Resultados por página", [10,25,50,100], 0, key="leads_page_size")
    total = len(L); total_pages = max(1, (total + page_size - 1) // page_size)

    if st.session_state.get("leads_last_query","") != q:
        st.session_state["leads_page_idx"] = 0
        st.session_state["leads_last_query"] = q

    page_idx = max(0, min(st.session_state["leads_page_idx"], total_pages - 1))
    start, end = page_idx*page_size, page_idx*page_size+page_size
    page_df = L.iloc[start:end].reset_index(drop=True)

    st.caption(f"Coincidencias: {total} • Página {page_idx+1} de {total_pages}")
    cpg1, cpg2, _ = st.columns([1,1,6])
    if cpg1.button("⟵ Anterior", disabled=(page_idx==0)):
        st.session_state["leads_page_idx"] = page_idx-1; st.rerun()
    if cpg2.button("Siguiente ⟶", disabled=(page_idx>=total_pages-1)):
        st.session_state["leads_page_idx"] = page_idx+1; st.rerun()

    st.dataframe(page_df[cols_vista], use_container_width=True, hide_index=True)

    st.divider()
    st.subheader("Editar lead (selección rápida)")
    ids_en_pagina = page_df["id_lead"].astype(str).tolist()
    if ids_en_pagina:
        lead_edit_id = st.selectbox("ID en página", [""] + ids_en_pagina, index=0)
        if lead_edit_id:
            editar_lead_por_id(lead_edit_id)
    else:
        st.info("No hay leads para editar en esta página.")

    st.divider()
    st.subheader("Registrar nuevo lead")
    with st.form("form_new_lead", clear_on_submit=True):
        c1,c2,c3 = st.columns(3)
        nombre = c1.text_input("Nombre")
        apellidos = c2.text_input("Apellidos")
        alias = c3.text_input("Alias (opcional)")
        c4,c5,c6 = st.columns(3)
        edad = c4.number_input("Edad", 0, 120, 0, 1, format="%d")
        celular = c5.text_input("Celular")
        correo = c6.text_input("Correo")
        c7,c8 = st.columns(2)
        interes = c7.selectbox("Tipo de curso / interés", COURSE_OPTIONS, 0)
        canal = c8.selectbox("¿Cómo te enteraste?", CHANNEL_OPTIONS, 0)
        stages = emb["stage"].tolist()
        lead_status_lbl = st.selectbox("Etapa (en) (es)", [STAGE_LABEL[s] for s in stages], 0)
        obs = st.text_area("Observaciones")
        ok = st.form_submit_button("Guardar lead")
        if ok:
            if not (nombre or "").strip():
                st.error("El nombre es obligatorio."); st.stop()
            if not (norm_phone(celular) or norm_email(correo)):
                st.error("Debes capturar al menos **celular** o **correo**."); st.stop()
            if (correo or "").strip() and "@" not in correo:
                st.error("El correo no parece válido."); st.stop()
            lead_status_en = stages[[STAGE_LABEL[s] for s in stages].index(lead_status_lbl)]
            new_id = next_id(leads, "id_lead")
            new_row = {
                "id_lead": str(new_id),
                "fecha_registro": now_date(), "hora_registro": now_time(),
                "nombre": (nombre or "").strip(), "apellidos": (apellidos or "").strip(), "alias": (alias or "").strip(),
                "edad": int(edad) if str(edad) != "" else "",
                "celular": norm_phone(celular), "telefono": "",
                "correo": norm_email(correo),
                "interes_curso": interes, "como_enteraste": canal,
                "lead_status": lead_status_en, "funnel_etapas": "",
                "fecha_ultimo_contacto": "", "observaciones": (obs or "").strip(),
                "owner": owner_name_default(), "proxima_accion_fecha": "", "proxima_accion_desc": "",
                "lead_score": "0", "probabilidad_cierre": "0.2",
                "monto_estimado": "", "motivo_perdida": "", "fecha_entrada_etapa": now_date(),
            }
            leads_local = pd.DataFrame([new_row])
            leads_local["lead_score"] = leads_local.apply(compute_lead_score, axis=1).astype(str)
            leads = pd.concat([leads_local, leads], ignore_index=True)
            save_csv(leads, FILES["leads"])
            st.session_state["leads_page_idx"] = 0
            st.success(f"Lead guardado (ID {new_id})."); st.rerun()

def editar_lead_por_id(lead_edit_id: str):
    global leads
    st.subheader("Editar lead")
    mask = leads["id_lead"].astype(str) == str(lead_edit_id)
    if not mask.any():
        st.warning("El lead a editar ya no existe."); return
    row = leads.loc[mask].iloc[0].copy()
    with st.form(f"form_edit_{lead_edit_id}"):
        c1,c2,c3 = st.columns(3)
        nombre_e = c1.text_input("Nombre", value=row.get("nombre",""))
        apellidos_e = c2.text_input("Apellidos", value=row.get("apellidos",""))
        alias_e = c3.text_input("Alias", value=row.get("alias",""))
        c4,c5,c6 = st.columns(3)
        edad_e = c4.number_input("Edad", 0, 120, int(row.get("edad") or 0), 1)
        celular_e = c5.text_input("Celular", value=row.get("celular",""))
        correo_e = c6.text_input("Correo", value=row.get("correo",""))
        c7,c8 = st.columns(2)
        interes_e = c7.selectbox("Tipo de curso / interés", COURSE_OPTIONS, (COURSE_OPTIONS.index(row.get("interes_curso", COURSE_OPTIONS[0])) if row.get("interes_curso","") in COURSE_OPTIONS else 0))
        canal_e = c8.selectbox("¿Cómo te enteraste?", CHANNEL_OPTIONS, (CHANNEL_OPTIONS.index(row.get("como_enteraste", CHANNEL_OPTIONS[0])) if row.get("como_enteraste","") in CHANNEL_OPTIONS else 0))
        stages = emb["stage"].tolist()
        idx = stages.index(normalize_stage(row.get("lead_status","Awareness"))) if normalize_stage(row.get("lead_status","Awareness")) in stages else 0
        estado_e_lbl = st.selectbox("Etapa (en) (es)", [STAGE_LABEL[s] for s in stages], idx)
        obs_e = st.text_area("Observaciones", value=row.get("observaciones",""))
        prox_f = st.date_input("Próxima acción (fecha)", value=pd.to_datetime(row.get("proxima_accion_fecha","") or date.today()).date())
        prox_d = st.text_input("Próxima acción (descripción)", value=row.get("proxima_accion_desc",""))
        ok = st.form_submit_button("Actualizar")
        if ok:
            if not (nombre_e or "").strip():
                st.error("El nombre es obligatorio."); st.stop()
            if not (norm_phone(celular_e) or norm_email(correo_e)):
                st.error("Debes capturar al menos **celular** o **correo**."); st.stop()
            if (correo_e or "").strip() and "@" not in correo_e:
                st.error("El correo no parece válido."); st.stop()
            estado_en = stages[[STAGE_LABEL[s] for s in stages].index(estado_e_lbl)]
            prev_stage = normalize_stage(row.get("lead_status","Awareness"))
            leads.loc[mask, [
                "nombre","apellidos","alias","edad","celular","correo","interes_curso","como_enteraste",
                "lead_status","observaciones","proxima_accion_fecha","proxima_accion_desc",
            ]] = [
                (nombre_e or "").strip(), (apellidos_e or "").strip(), (alias_e or "").strip(),
                int(edad_e) if str(edad_e) != "" else "",
                norm_phone(celular_e), norm_email(correo_e), interes_e, canal_e,
                estado_en, (obs_e or "").strip(),
                prox_f.strftime("%Y-%m-%d") if prox_d else "", prox_d,
            ]
            row_now = leads.loc[mask].iloc[0].to_dict()
            leads.loc[mask,"lead_score"] = str(compute_lead_score(pd.Series(row_now)))
            if prev_stage != estado_en:
                leads.loc[mask,"fecha_entrada_etapa"] = now_date()
            save_csv(leads, FILES["leads"])
            st.success("Lead actualizado."); st.rerun()

# ---------------------- Seguimiento (usabilidad + COMPOSER WhatsApp) ----------------------
def page_followup():
    global leads, segs
    st.markdown("## ✉️ Seguimiento")

    # ----- Filtros superiores
    dcol1, dcol2 = st.columns([1,3])
    selected_date = dcol1.date_input("📅 Fecha", value=date.today(), key="fu_date")
    solo_mios = dcol1.checkbox("Solo mis leads", value=False, key="fu_only_mine")
    q = dcol2.text_input("🔎 Buscar lead (nombre, alias, email o teléfono)", key="fu_search")

    base = leads.copy()
    if solo_mios:
        base = base[base["owner"] == owner_name_default()]
    if q:
        ql = q.lower()
        def _match_due(r):
            s = " ".join([
                str(r.get('nombre','')),
                str(r.get('apellidos','')),
                str(r.get('alias','')),
                str(r.get('correo','')),
                str(r.get('celular','')),
            ]).lower()
            return ql in s
        base = base[base.apply(_match_due, axis=1)]
    due = base[base["proxima_accion_fecha"] == selected_date.strftime("%Y-%m-%d")]

    st.caption(f"Acciones para {selected_date.strftime('%Y-%m-%d')}: {len(due)}")
    if due.empty:
        st.info("No hay acciones programadas para la fecha seleccionada.")
    else:
        for _, row in due.iterrows():
            with st.container(border=True):
                cA,cB,cC = st.columns([5,3,2])
                cA.markdown(f"**{row['nombre']} {row['apellidos']}** • {row.get('alias','')} • {row.get('celular','')}")
                cB.markdown(stage_badge(row.get("lead_status","Awareness")), unsafe_allow_html=True)
                if cC.button("📨 Abrir", key=f"open_{row['id_lead']}"):
                    st.session_state["fu_selected_lead_id"] = str(row["id_lead"])
                    st.rerun()
                st.caption(f"➡️ {row.get('proxima_accion_desc','') or '—'}")

    st.divider()

    # ----- Selección / bloqueo de lead
    selected_lead_id = st.session_state.get("fu_selected_lead_id", "")

    if not selected_lead_id:
        # Modo libre: seleccionar desde un selectbox solo si NO hay lead bloqueado
        base2 = leads.copy()
        if q:
            ql = q.lower()
            def _match_pick(r):
                s = " ".join([
                    str(r.get('nombre','')),
                    str(r.get('apellidos','')),
                    str(r.get('alias','')),
                    str(r.get('correo','')),
                    str(r.get('celular','')),
                ]).lower()
                return ql in s
            base2 = base2[base2.apply(_match_pick, axis=1)]
        id_to_label = {str(r["id_lead"]): lead_label(r) for _, r in base2.iterrows()}
        opts = [""] + list(id_to_label.keys())
        lead_pick = st.selectbox("Selecciona lead", opts, index=0,
                                 format_func=lambda k: id_to_label.get(k, "—") if k else "—")
        if not lead_pick:
            return
        # En cuanto el usuario elige, lo bloqueamos y recargamos
        st.session_state["fu_selected_lead_id"] = lead_pick
        st.rerun()
    else:
        # Lead bloqueado
        mask_lead = leads["id_lead"].astype(str) == str(selected_lead_id)
        if not mask_lead.any():
            st.warning("El lead seleccionado ya no existe.")
            st.session_state.pop("fu_selected_lead_id", None)
            st.rerun()
        lead_ctx = leads.loc[mask_lead].iloc[0]

        top = st.container()
        with top:
            c1,c2,c3,c4 = st.columns([5,3,2,1.5])
            c1.markdown(f"### {lead_ctx['nombre']} {lead_ctx['apellidos']}  \n📞 {lead_ctx.get('celular','—')} • ✉️ {lead_ctx.get('correo','—')}")
            c2.markdown(stage_badge(lead_ctx.get("lead_status","Awareness")), unsafe_allow_html=True)
            c3.markdown(owner_badge(lead_ctx.get("owner","")), unsafe_allow_html=True)
            if c4.button("Cambiar lead", use_container_width=True):
                # Limpiar selección y estados de checkboxes por lead
                for stage in STAGE_ORDER:
                    st.session_state.pop(f"tpl_{stage}_{selected_lead_id}", None)
                st.session_state.pop("fu_stage_select", None)
                st.session_state.pop("fu_selected_lead_id", None)
                st.rerun()

        # ----- Historial
        st.subheader("Historial del lead")
        hist_cols = ["fecha","hora","etapa","proxima_accion_fecha","tipo_mensaje","estado_mensaje","canal","atendido_por","observaciones"]
        hist = segs[segs["id_lead"].astype(str) == str(selected_lead_id)].sort_values(["fecha","hora"]) if not segs.empty else pd.DataFrame(columns=hist_cols)
        for c in hist_cols:
            if c not in hist.columns: hist[c] = ""
        st.dataframe(hist[hist_cols], use_container_width=True, hide_index=True)

        st.divider()
        st.subheader("Plantillas por etapa")

        selected_stage_override = None
        seleccionadas = []
        previews = []
        for stage in STAGE_ORDER:
            t = STAGE_TEMPLATES.get(stage)
            desc = STAGE_DESC.get(stage, "")
            bg, fg = STAGE_COLORS.get(stage, ("#F1F5F9", "#0F172A"))
            with st.expander(f"• {STAGE_LABEL[stage]} — {desc}"):
                st.markdown(f"<div style='display:inline-block;background:{bg};color:{fg};padding:2px 8px;border-radius:999px;font-size:12px;font-weight:700'>{stage}</div>", unsafe_allow_html=True)
                # KEY por lead para no mezclar estado si se cambia de lead
                usar = st.checkbox(f"Usar plantilla de {stage}", key=f"tpl_{stage}_{selected_lead_id}")
                pre = render_tpl(t["plantilla"], lead_ctx)
                st.caption(f"Sugerido: {t['canal']} • Tipo: {t['tipo']}")
                # Previsualización editable (para personalizar antes de enviar)
                pre_edit = st.text_area("Previsualización (editable)", value=pre, height=110, key=f"preview_{stage}_{selected_lead_id}")
                # Bloque con botón de copiar (propio de st.code)
                st.code(pre_edit, language=None)
                if usar:
                    seleccionadas.append((stage, t))
                    previews.append(pre_edit)
                    selected_stage_override = stage

        # -------- COMPOSER: mensaje final (copiable + WhatsApp Web)
        st.subheader("Mensaje a enviar")
        composed_default = "\n\n".join(previews) if previews else ""
        msg = st.text_area("Redacta aquí el mensaje final (puedes pegar/editar libremente)", value=composed_default, height=160, key=f"composer_{selected_lead_id}")
        st.code(msg or "", language=None)

        cwa1, cwa2 = st.columns([2,4])
        usar_tel_lead = cwa1.checkbox("Usar número del lead", value=True)
        tel_obj = norm_phone(lead_ctx.get("celular","")) if usar_tel_lead else ""
        # ÚNICO botón: WhatsApp Web
        msg_enc = quote_plus(msg or "")
        if tel_obj:
            url_wa_web = f"https://api.whatsapp.com/send?phone={tel_obj}&text={msg_enc}"
        else:
            url_wa_web = f"https://api.whatsapp.com/send?text={msg_enc}"
        cwa2.markdown(f"<div class='wa-actions'><a class='btn' href='{url_wa_web}' target='_blank'>🌐 Abrir en WhatsApp Web</a></div>", unsafe_allow_html=True)

        st.caption("Tip: usa el botón de copiar del bloque de código para llevar el texto al portapapeles.")

        st.subheader("Envío y próxima acción")

        stages = emb["stage"].tolist()
        labels = [STAGE_LABEL[s] for s in stages]
        curr_stage = selected_stage_override or normalize_stage(lead_ctx.get("lead_status","Awareness"))
        idx_default = labels.index(STAGE_LABEL.get(curr_stage, curr_stage)) if STAGE_LABEL.get(curr_stage, curr_stage) in labels else 0

        c1,c2,c3 = st.columns(3)
        canal = c1.selectbox("Canal", CHANNEL_OPTIONS, (CHANNEL_OPTIONS.index("WhatsApp") if "WhatsApp" in CHANNEL_OPTIONS else 0))
        atendido_por = c2.text_input("Atendido por", value=owner_name_default())
        estado_msg = c3.selectbox("Estado del mensaje", ["Enviado","Sin respuesta","Respondido","Perdido"])

        cNA,cNB = st.columns(2)
        prox_fecha = cNA.date_input("Próxima acción (fecha)", value=pd.to_datetime(lead_ctx.get("proxima_accion_fecha","") or date.today()).date())
        prox_desc  = cNB.text_input("Próxima acción (descripción)", value=lead_ctx.get("proxima_accion_desc",""))

        close_today = st.checkbox("Cerrar acción de la fecha seleccionada (quitar del calendario)", True)

        etapa_lbl = st.selectbox("Etapa del embudo (en) (es)", labels, idx_default, key="fu_stage_select")
        etapa_en = stages[labels.index(etapa_lbl)]
        st.markdown(stage_badge(etapa_en), unsafe_allow_html=True)

        if st.button("Registrar seguimiento(s)"):
            if not previews and not (msg or "").strip():
                st.warning("Selecciona al menos una plantilla (arriba) o redacta un mensaje.")
            else:
                to_add = []
                # Guardamos un único registro con el composed message como 'observaciones'
                new_id = next_id(segs, "id_seguimiento")
                to_add.append({
                    "id_seguimiento": str(new_id), "id_lead": str(selected_lead_id),
                    "fecha": now_date(), "hora": now_time(),
                    "etapa": etapa_en,
                    "proxima_accion_fecha": prox_fecha.strftime("%Y-%m-%d"),
                    "tipo_mensaje": "WhatsApp (compuesto)",
                    "estado_mensaje": estado_msg, "canal": canal, "atendido_por": atendido_por,
                    "observaciones": (msg or "").strip(),
                })
                segs_local = pd.DataFrame(to_add)
                segs = pd.concat([segs, segs_local], ignore_index=True)
                save_csv(segs, FILES["seguimientos"])

                mask = leads["id_lead"].astype(str) == str(selected_lead_id)
                if not mask.any():
                    st.warning("El lead seleccionado ya no existe."); st.rerun()

                prev_stage = normalize_stage(leads.loc[mask].iloc[0].get("lead_status","Awareness"))
                selected_str = selected_date.strftime("%Y-%m-%d")
                prox_str = prox_fecha.strftime("%Y-%m-%d")

                leads.loc[mask, "lead_status"] = etapa_en
                if close_today and prox_str == selected_str:
                    next_date, next_desc = "", ""
                else:
                    next_date, next_desc = prox_str, prox_desc

                leads.loc[mask, ["proxima_accion_fecha","proxima_accion_desc"]] = [next_date, next_desc]
                leads.loc[mask, "fecha_ultimo_contacto"] = now_date()
                row_now = leads.loc[mask].iloc[0]
                leads.loc[mask,"lead_score"] = str(compute_lead_score(row_now))
                if prev_stage != etapa_en:
                    leads.loc[mask,"fecha_entrada_etapa"] = now_date()
                save_csv(leads, FILES["leads"])

                st.success("Seguimiento registrado y lead actualizado.")
                st.rerun()

# -------- Utilidades Dashboard --------
def start_of_week(d: date) -> date: return d - timedelta(days=d.weekday())
def month_bounds(d: date) -> tuple[date, date]:
    first = d.replace(day=1)
    next_first = d.replace(year=d.year+1, month=1, day=1) if d.month == 12 else d.replace(month=d.month+1, day=1)
    last = next_first - timedelta(days=1)
    return first, last
def parse_date_col(df: pd.DataFrame, col: str) -> pd.Series: return pd.to_datetime(df[col], errors="coerce")

# ---------------------- Dashboard ----------------------
def page_dashboard():
    st.markdown("## 📊 Dashboard")
    c1,c2,c3 = st.columns([1.2,1.2,2])
    periodo = c1.selectbox("Periodo", ["Hoy","Esta semana","Últimos 7 días","Este mes","Personalizado"], 1)
    if periodo == "Personalizado":
        rango = c2.date_input("Rango de fechas", value=(date.today() - timedelta(days=6), date.today()))
        if isinstance(rango, tuple):
            d_from, d_to = rango
        else:
            d_from, d_to = rango[0], rango[-1] if isinstance(rango, list) else (date.today(), date.today())
    elif periodo == "Hoy":
        d_from = d_to = date.today()
    elif periodo == "Esta semana":
        d_from = start_of_week(date.today()); d_to = d_from + timedelta(days=6)
    elif periodo == "Últimos 7 días":
        d_to = date.today(); d_from = d_to - timedelta(days=6)
    elif periodo == "Este mes":
        d_from, d_to = month_bounds(date.today())

    f_curso = c3.selectbox("Filtrar por curso (opcional)", ["(Todos)"] + COURSE_OPTIONS, 0)

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
            segs_period = segs_period.merge(leads[["id_lead","interes_curso"]], on="id_lead", how="left")
            segs_period = segs_period[segs_period["interes_curso"] == f_curso]

    k1,k2,k3,k4 = st.columns(4)
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
        tooltip=["lead_status","count"]
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
        tooltip=["fecha:T","tipo:N","valor:Q"]
    ).properties(height=300)
    st.altair_chart(line, use_container_width=True)

    st.divider()
    st.subheader("Desglose por curso (periodo)")
    grp_new = (leads_new.groupby("interes_curso").size().rename("Nuevos leads").reset_index()) if not leads_new.empty else pd.DataFrame({"interes_curso": [], "Nuevos leads": []})
    grp_seg = pd.DataFrame({"interes_curso": [], "Seguimientos": []})
    if not segs_period.empty:
        segs_with_course = segs_period if "interes_curso" in segs_period.columns else segs_period.merge(leads[["id_lead","interes_curso"]], on="id_lead", how="left")
        grp_seg = segs_with_course.groupby("interes_curso").size().rename("Seguimientos").reset_index()
    grp_won = (leads_won.groupby("interes_curso").size().rename("Inscritos (Won)").reset_index()) if not leads_won.empty else pd.DataFrame({"interes_curso": [], "Inscritos (Won)": []})
    cA,cB,cC = st.columns(3)
    cA.altair_chart(alt.Chart(grp_new).mark_bar().encode(x=alt.X("Nuevos leads:Q", title="Nuevos"), y=alt.Y("interes_curso:N", sort='-x', title="Curso"), tooltip=["interes_curso","Nuevos leads"]).properties(height=260), use_container_width=True)
    cB.altair_chart(alt.Chart(grp_seg).mark_bar().encode(x=alt.X("Seguimientos:Q", title="Seguimientos"), y=alt.Y("interes_curso:N", sort='-x', title="Curso"), tooltip=["interes_curso","Seguimientos"]).properties(height=260), use_container_width=True)
    cC.altair_chart(alt.Chart(grp_won).mark_bar().encode(x=alt.X("Inscritos (Won):Q", title="Inscritos"), y=alt.Y("interes_curso:N", sort='-x', title="Curso"), tooltip=["interes_curso","Inscritos (Won)"]).properties(height=260), use_container_width=True)
    st.caption("Notas: 'Nuevos leads' = fecha_registro en el periodo. 'Inscritos (Won)' = leads con etapa Won cuya fecha_entrada_etapa cae en el periodo. 'Seguimientos' = registros en seguimientos.csv dentro del periodo.")

# Router
if menu == "👤 Leads":
    page_leads()
elif menu == "✉️ Seguimiento":
    page_followup()
elif menu == "📊 Dashboard":
    page_dashboard()

st.caption("Usuarios desde ./data/users.csv (hash), Leads con paginación, Seguimiento con composer copiable y botón de WhatsApp Web, Historial con columnas solicitadas.")
