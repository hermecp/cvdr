import re
import pandas as pd
import streamlit as st
import altair as alt
from pathlib import Path
from datetime import datetime, date, timedelta
import hashlib
from urllib.parse import quote_plus

# =========================
# CONFIG / PATHS
# =========================
st.set_page_config(page_title="Mini-CRM CVDR v12.5", layout="wide")
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

# =========================
# USUARIOS Y ROLES
# =========================
DEFAULT_USER_ROWS = [
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
                existing = pd.concat([existing, pd.DataFrame([{"username": u, "name": name, "role": role, "pass_hash": ph}])], ignore_index=True)
        existing[["username","name","role","pass_hash"]].to_csv(p, index=False)
    else:
        pd.DataFrame(DEFAULT_USER_ROWS, columns=["username","name","role","pass_hash"]).to_csv(p, index=False)

def load_users() -> dict:
    ensure_or_update_users_csv()
    df = pd.read_csv(FILES["usuarios"], dtype=str).fillna("")
    return {str(r["username"]).strip().lower(): {"name": r["name"], "role": r["role"], "pass_hash": r["pass_hash"]} for _, r in df.iterrows()}

USERS = load_users()

def is_logged() -> bool: return bool(st.session_state.get("user"))
def require_login():
    if not is_logged(): st.stop()
def owner_name_default() -> str:
    if not is_logged(): return "Asesor"
    return st.session_state["user"]["name"]
def current_role() -> str:
    return st.session_state["user"]["role"] if is_logged() else ""

# =========================
# EMBUDO
# =========================
STAGE_ORDER = ["Awareness","Contacted","MQL","SQL","Nurturing","Demo_Booked","Won","Lost","Re_Engaged"]
STAGE_LABEL = {
    "Awareness":"Awareness (Captado)","Contacted":"Contacted (Contactado)","MQL":"MQL (Info enviada)",
    "SQL":"SQL (Interesado / Oportunidad)","Nurturing":"Nurturing (En seguimiento / Temario)",
    "Demo_Booked":"Demo_Booked (Depósito / Preinscripción)","Won":"Won (Inscrito / Cliente)",
    "Lost":"Lost (Perdido)","Re_Engaged":"Re_Engaged (Reactivado)",
}
SPANISH_TO_EN = {
    "Captado":"Awareness","Contactado":"Contacted","Info enviada":"MQL","Info_enviada":"MQL","MQL":"MQL",
    "Interesado":"SQL","En seguimiento":"Nurturing","En_seguimiento":"Nurturing",
    "Depósito":"Demo_Booked","Preinscripción":"Demo_Booked",
    "Inscrito":"Won","Inscrita":"Won","Perdido":"Lost","Reactivado":"Re_Engaged",
}
STAGE_COLORS = {
    "Awareness":("#F8FAFC","#0F172A"),"Contacted":("#EFF6FF","#075985"),"MQL":("#FEFCE8","#713F12"),
    "SQL":("#ECFDF5","#14532D"),"Nurturing":("#F5F3FF","#4C1D95"),"Demo_Booked":("#FFF1F2","#9F1239"),
    "Won":("#F0FDF4","#065F46"),"Lost":("#FEF2F2","#7F1D1D"),"Re_Engaged":("#EEF2FF","#3730A3"),
}

def normalize_stage(v: str) -> str:
    if not isinstance(v, str) or not v.strip(): return "Awareness"
    v = v.strip()
    if v in STAGE_ORDER: return v
    return SPANISH_TO_EN.get(v, "Awareness")

def looks_like_stage(v: str) -> bool:
    if not isinstance(v, str): return False
    s = v.strip()
    if not s: return False
    if s in STAGE_ORDER: return True
    if s in SPANISH_TO_EN: return True
    if s.lower() in [x.lower() for x in STAGE_ORDER]: return True
    return False

def stage_value(row: pd.Series) -> str:
    f = row.get("funnel_etapas","")
    l = row.get("lead_status","")
    if looks_like_stage(f): return normalize_stage(f)
    if looks_like_stage(l): return normalize_stage(l)
    return "Unspecified"

# =========================
# SCHEMAS / CATÁLOGOS
# =========================
SCHEMA_LEADS = [
    "id_lead","fecha_registro","hora_registro","nombre","apellidos","genero","edad",
    "celular","telefono","correo","interes_curso","como_enteraste","lead_status","funnel_etapas",
    "fecha_ultimo_contacto","observaciones","owner","proxima_accion_fecha","proxima_accion_desc",
    "lead_score","probabilidad_cierre","monto_estimado","motivo_perdida","fecha_entrada_etapa",
]
SCHEMA_SEGS = ["id_seguimiento","id_lead","fecha","hora","etapa","proxima_accion_fecha","tipo_mensaje","estado_mensaje","canal","atendido_por","observaciones"]
DEFAULTS = {"genero":"","edad":"","telefono":"","fecha_ultimo_contacto":"","observaciones":"","owner":"",
            "proxima_accion_fecha":"","proxima_accion_desc":"","lead_score":"0","probabilidad_cierre":"0.2",
            "monto_estimado":"","motivo_perdida":"","fecha_entrada_etapa":"","funnel_etapas":""}
COURSE_OPTIONS = [
    "IA profesionales inmobiliarios","IA educación básica","IA educación universitaria",
    "IA empresas","IA para gobierno","Inglés","Polivirtual Bach.","Polivirtual Lic.",
]
CHANNEL_OPTIONS = ["WhatsApp","Teléfono","Correo","Facebook","Instagram","Google","Referido","Otro"]
GENDER_OPTIONS = ["Mujer","Hombre","No binario","Prefiero no decir","Otro"]

# =========================
# HELPERS CSV / FECHAS / HORAS
# =========================
@st.cache_data(ttl=30)
def load_csv(path: str, dtype=None):
    p = Path(path)
    if not p.exists(): return pd.DataFrame()
    return pd.read_csv(p, dtype=dtype).fillna("")

def save_csv(df: pd.DataFrame, path: str):
    p = Path(path); tmp = p.with_suffix(".tmp.csv")
    df.to_csv(tmp, index=False); tmp.replace(p); load_csv.clear()

def ensure_columns(df: pd.DataFrame, ordered_cols: list, defaults: dict) -> pd.DataFrame:
    if df is None or df.empty: df = pd.DataFrame(columns=ordered_cols)
    for c in ordered_cols:
        if c not in df.columns: df[c] = defaults.get(c, "")
    extras = [c for c in df.columns if c not in ordered_cols]
    return df[ordered_cols + extras]

def next_id(df: pd.DataFrame, id_col: str) -> int:
    if df is None or df.empty or id_col not in df.columns: return 1
    try: return int(pd.to_numeric(df[id_col], errors="coerce").fillna(0).max()) + 1
    except Exception: return 1

def now_date() -> str: return datetime.now().strftime("%Y-%m-%d")
def now_time() -> str: return datetime.now().strftime("%H:%M:%S")

def norm_phone(s: str) -> str:
    import re as _re
    return _re.sub(r"\D","",str(s or ""))

def norm_email(s: str) -> str:
    return str(s or "").strip().lower()

def parse_time_safe(x):
    s = str(x or "").strip()
    for fmt in ("%H:%M:%S","%H:%M"):
        try: return pd.to_datetime(s, format=fmt)
        except Exception: pass
    return pd.NaT

def parse_age_to_int(s: str, default: int = 0) -> int:
    if s is None: return default
    s = str(s).strip()
    if s == "": return default
    m = re.search(r"(\d+)\s*[-–—aA]\s*(\d+)", s)
    if m: return int(round((int(m.group(1))+int(m.group(2)))/2))
    m = re.search(r"(\d+)\s*\+", s)
    if m: return int(m.group(1))
    m = re.search(r"\d+", s)
    if m: return int(m.group(0))
    return default

def parse_date_smart(x):
    """Primero intenta YYYY-MM-DD; si falla, intenta con dayfirst=True. Devuelve Timestamp."""
    if isinstance(x, pd.Series):
        s1 = pd.to_datetime(x, errors="coerce", format="%Y-%m-%d")
        if s1.isna().any():
            s2 = pd.to_datetime(x[s1.isna()], errors="coerce", dayfirst=True)
            s1.loc[s1.isna()] = s2
        return s1
    s = pd.to_datetime(x, errors="coerce", format="%Y-%m-%d")
    if pd.isna(s): s = pd.to_datetime(x, errors="coerce", dayfirst=True)
    return s

def to_date_value(x) -> date:
    if isinstance(x, date): return x
    ts = parse_date_smart(x)
    return ts.date() if not pd.isna(ts) else date.today()

def compute_lead_score(row: pd.Series) -> int:
    score = 0
    if row.get("como_enteraste") in ["Referido","Facebook","Google","WhatsApp"]: score += 10
    et = stage_value(row)
    if normalize_stage(et) in ["SQL","Demo_Booked"]: score += 20
    edad_val = parse_age_to_int(row.get("edad",""), 0)
    if 25 <= edad_val <= 45: score += 10
    if str(row.get("owner","")).strip(): score += 5
    return min(score, 100)

# =========================
# ARCHIVOS BASE + CARGA
# =========================
for k in REQUIRED:
    p = Path(FILES[k])
    if not p.exists():
        save_csv(pd.DataFrame(columns=SCHEMA_LEADS if k=="leads" else SCHEMA_SEGS), FILES[k])
if not Path(FILES["embudo"]).exists():
    save_csv(pd.DataFrame({"stage": STAGE_ORDER}), FILES["embudo"])

leads = ensure_columns(load_csv(FILES["leads"], dtype=str), SCHEMA_LEADS, DEFAULTS)
segs  = ensure_columns(load_csv(FILES["seguimientos"], dtype=str), SCHEMA_SEGS, {})
# normaliza nombres de columnas
leads.columns = leads.columns.str.strip()
segs.columns  = segs.columns.str.strip()

emb_raw = load_csv(FILES["embudo"], dtype=str)
emb = emb_raw[["stage"]].drop_duplicates() if "stage" in emb_raw.columns else pd.DataFrame({"stage": STAGE_ORDER})

# Derivados
leads["edad"] = leads["edad"].astype(str).fillna("")
leads["edad_num"] = leads["edad"].apply(lambda s: parse_age_to_int(s,0)).astype(int)
leads["etapa_mostrar"] = leads.apply(stage_value, axis=1)
leads["lead_score"] = leads.apply(compute_lead_score, axis=1).astype(str)

# =========================
# ESTILOS
# =========================
st.markdown("""
<style>
  .app-title {font-weight:800;font-size:22px;margin-bottom:4px;}
  .muted {opacity:.9}
  .wa-actions .btn {display:inline-block;border:1px solid #e5e7eb;border-radius:10px;padding:6px 10px;margin-right:8px;}
</style>
""", unsafe_allow_html=True)

# =========================
# LOGIN SIDEBAR
# =========================
def login_sidebar():
    with st.sidebar:
        st.markdown("<div class='app-title'>Mini-CRM CVDR</div><div class='muted'>Acceso</div>", unsafe_allow_html=True)
        if not is_logged():
            u = st.text_input("Usuario"); p = st.text_input("Contraseña", type="password")
            if st.button("Iniciar sesión", use_container_width=True):
                info = USERS.get(u.strip().lower())
                if not info or info["pass_hash"] != _hash(p):
                    st.error("Usuario o contraseña incorrectos."); st.stop()
                st.session_state["user"] = {"username": u.strip().lower(), "name": info["name"], "role": info["role"]}
                st.query_params["user"] = u.strip().lower(); st.rerun()
        else:
            user = st.session_state["user"]; st.success(f"Conectado: {user['name']} • {user['role']}")
            if st.button("Cerrar sesión", use_container_width=True):
                for k in list(st.session_state.keys()): del st.session_state[k]
                for k in ["menu","lead","user"]: st.query_params.pop(k, None)
                st.rerun()
login_sidebar()
require_login()

# =========================
# NAV
# =========================
if "menu" not in st.session_state:
    qp = st.query_params
    st.session_state["menu"] = qp.get("menu", ["👤 Leads"])[0] if "menu" in qp else "👤 Leads"

c_nav = st.container()
with c_nav:
    col1, col2, col3 = st.columns([1,1,1])
    if col1.button("👤 Leads", use_container_width=True): st.session_state["menu"]="👤 Leads"; st.query_params["menu"]="👤 Leads"; st.rerun()
    if col2.button("✉️ Seguimiento", use_container_width=True): st.session_state["menu"]="✉️ Seguimiento"; st.query_params["menu"]="✉️ Seguimiento"; st.rerun()
    if col3.button("📊 Dashboard", use_container_width=True): st.session_state["menu"]="📊 Dashboard"; st.query_params["menu"]="📊 Dashboard"; st.rerun()
menu = st.session_state["menu"]

# =========================
# UI HELPERS
# =========================
def stage_badge(stage_en: str) -> str:
    bg, fg = STAGE_COLORS.get(stage_en, ("#F1F5F9","#0F172A"))
    label = STAGE_LABEL.get(stage_en, stage_en)
    return f"<span style='background:{bg};color:{fg};padding:2px 8px;border-radius:999px;font-size:12px;font-weight:700'>{label}</span>"

def owner_badge(owner: str) -> str:
    if not owner: owner = "—"
    return f"<span style='background:#ECFDF5;color:#065F46;padding:2px 8px;border-radius:999px;'>Owner: {owner}</span>"

def lead_label(r: pd.Series) -> str:
    name = f"{r.get('nombre','')} {r.get('apellidos','')}".strip()
    genero = str(r.get("genero","")).strip()
    tel = r.get("celular","") or r.get("telefono","")
    return f"{name}{(' • '+genero) if genero else ''}{(' • '+tel) if tel else ''}"

# =========================
# PÁGINA LEADS
# =========================
def page_leads():
    global leads
    st.markdown("## 👤 Leads")

    today_str = now_date()
    if not leads.empty and "fecha_registro" in leads.columns:
        hoy = leads[leads["fecha_registro"] == today_str].copy()
        if not hoy.empty:
            st.info(f"🟢 Agregados hoy ({today_str}): {len(hoy)}")
            if "hora_registro" in hoy.columns:
                hoy = hoy.copy()
                hoy["__h"] = hoy["hora_registro"].apply(parse_time_safe)
                hoy = hoy.sort_values("__h", ascending=False)
            cols_hoy = ["id_lead","fecha_registro","hora_registro","nombre","apellidos","genero",
                        "celular","correo","interes_curso","lead_status","owner"]
            for c in cols_hoy:
                if c not in hoy.columns: hoy[c] = ""
            st.dataframe(hoy[cols_hoy], use_container_width=True, hide_index=True)

    with st.expander("🔎 Filtros", expanded=True):
        f1, f2, f3, f4, f5 = st.columns([1.6,1.2,1.2,1.4,1.1])
        q = f1.text_input("Buscar (nombre, email, teléfono)", key="leads_search")
        etapas_disp = [s for s in STAGE_ORDER if s in leads["etapa_mostrar"].unique()]
        fil_stage = f2.multiselect("Etapa (embudo)", etapas_disp, default=[])
        fil_curso = f3.multiselect("Curso", sorted([c for c in leads.get("interes_curso","").unique() if str(c).strip()]), default=[])
        owners = sorted([o for o in leads.get("owner","").unique() if str(o).strip()])
        fil_owner = f4.multiselect("Owner", owners, default=[])
        fil_genero = f5.multiselect("Género", GENDER_OPTIONS, default=[])
        reset = st.button("Restablecer filtros")
    if reset:
        st.session_state["leads_search"] = ""
        fil_stage, fil_curso, fil_owner, fil_genero = [], [], [], []

    L = leads.copy()
    if q:
        ql = q.lower()
        cols_texto = ["nombre","apellidos","genero","correo","celular","telefono"]
        L = L[L[cols_texto].astype(str).apply(lambda r: ql in " ".join(r).lower(), axis=1)]
    if fil_stage: L = L[L["etapa_mostrar"].isin(fil_stage)]
    if fil_curso: L = L[L["interes_curso"].isin(fil_curso)]
    if fil_owner: L = L[L["owner"].isin(fil_owner)]
    if fil_genero: L = L[L["genero"].isin(fil_genero)]

    cols_vista = ["id_lead","fecha_registro","hora_registro","nombre","apellidos","genero","celular","correo",
                  "interes_curso","como_enteraste","owner","etapa_mostrar","funnel_etapas","lead_status",
                  "proxima_accion_fecha","proxima_accion_desc","fecha_ultimo_contacto","lead_score"]
    for c in cols_vista:
        if c not in L.columns: L[c] = ""
    L = L.copy()
    L["__fecha"] = parse_date_smart(L["fecha_registro"])
    L["__hora"]  = L["hora_registro"].apply(parse_time_safe)
    L = L.sort_values(["__fecha","__hora"], ascending=[False, False])

    st.caption(f"Coincidencias: {len(L)}")
    st.download_button("⬇️ Descargar (filtrado) CSV", data=L[cols_vista].to_csv(index=False).encode("utf-8"),
                       file_name="leads_filtrado.csv", mime="text/csv")
    st.dataframe(L[cols_vista], use_container_width=True, hide_index=True)

    st.divider()
    st.subheader("Editar lead (búsqueda global)")
    with st.expander("Buscar y editar", expanded=True):
        q_edit = st.text_input("Buscar (nombre, apellidos, correo, teléfono o ID)", key="edit_search_global")
        base_edit = leads.copy()
        if q_edit:
            ql = str(q_edit).strip().lower()
            cols_texto = ["id_lead","nombre","apellidos","genero","correo","celular","telefono"]
            base_edit = base_edit[base_edit[cols_texto].astype(str).apply(lambda r: ql in " ".join(r).lower(), axis=1)]
        id_to_label = {str(r["id_lead"]): lead_label(r) for _, r in base_edit.iterrows()}
        lead_edit_id = st.selectbox("Selecciona lead a editar",
                                    [""] + list(id_to_label.keys()),
                                    index=0,
                                    format_func=lambda k: id_to_label.get(k, "—") if k else "—")
        if lead_edit_id:
            st.query_params["lead"] = str(lead_edit_id)
            editar_lead_por_id(lead_edit_id)

    st.divider()
    st.subheader("Registrar nuevo lead")
    with st.form("form_new_lead", clear_on_submit=True):
        c1,c2,c3 = st.columns(3)
        nombre = c1.text_input("Nombre/Alias")
        apellidos = c2.text_input("Apellidos")
        genero = c3.selectbox("Género", [""] + GENDER_OPTIONS, index=0)

        c4,c5,c6 = st.columns(3)
        edad = c4.number_input("Edad", 0, 120, 0, 1, format="%d")
        celular = c5.text_input("Celular")
        correo = c6.text_input("Correo")

        c7,c8 = st.columns(2)
        interes = c7.selectbox("Tipo de curso / interés", COURSE_OPTIONS, 0)
        canal = c8.selectbox("¿Cómo te enteraste?", CHANNEL_OPTIONS, 0)

        c9, c10 = st.columns(2)
        prox_fecha_new = c9.date_input("Próxima acción (fecha)", value=None, format="YYYY-MM-DD")
        prox_desc_new  = c10.text_input("Próxima acción (descripción)", value="")

        stages = emb["stage"].tolist()
        lead_status_lbl = st.selectbox("Etapa", [STAGE_LABEL[s] for s in stages], 0)
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
                "nombre": (nombre or "").strip(), "apellidos": (apellidos or "").strip(),
                "genero": (genero or "").strip(),
                "edad": str(int(edad)) if str(edad) != "" else "",
                "celular": norm_phone(celular), "telefono": "",
                "correo": norm_email(correo),
                "interes_curso": interes, "como_enteraste": canal,
                "lead_status": lead_status_en,
                "funnel_etapas": lead_status_en,  # sincronizamos
                "fecha_ultimo_contacto": "", "observaciones": (obs or "").strip(),
                "owner": owner_name_default(),
                "proxima_accion_fecha": prox_fecha_new.strftime("%Y-%m-%d") if isinstance(prox_fecha_new, date) else "",
                "proxima_accion_desc": (prox_desc_new or "").strip(),
                "lead_score": "0", "probabilidad_cierre": "0.2",
                "monto_estimado": "", "motivo_perdida": "", "fecha_entrada_etapa": now_date(),
            }
            leads_local = pd.DataFrame([new_row])
            leads_local["edad_num"] = leads_local["edad"].apply(lambda s: parse_age_to_int(s,0)).astype(int)
            leads_local["etapa_mostrar"] = leads_local.apply(stage_value, axis=1)
            leads_local["lead_score"] = leads_local.apply(compute_lead_score, axis=1).astype(str)
            leads = pd.concat([leads_local, leads], ignore_index=True)
            save_csv(leads.drop(columns=[c for c in ["edad_num"] if c in leads.columns]), FILES["leads"])
            leads["edad"] = leads["edad"].astype(str).fillna("")
            leads["edad_num"] = leads["edad"].apply(lambda s: parse_age_to_int(s,0)).astype(int)
            leads["etapa_mostrar"] = leads.apply(stage_value, axis=1)
            leads["lead_score"] = leads.apply(compute_lead_score, axis=1).astype(str)
            st.success(f"Lead guardado (ID {new_id})."); st.rerun()

# =========================
# EDICIÓN DE LEAD
# =========================
def editar_lead_por_id(lead_edit_id: str):
    global leads
    st.subheader("Editar lead")
    mask = leads["id_lead"].astype(str) == str(lead_edit_id)
    if not mask.any():
        st.warning("El lead a editar ya no existe."); return
    row = leads.loc[mask].iloc[0].copy()
    edad_default = int(row.get("edad_num", 0)) if "edad_num" in row else parse_age_to_int(row.get("edad",""), 0)

    with st.form(f"form_edit_{lead_edit_id}"):
        c1,c2,c3 = st.columns(3)
        nombre_e = c1.text_input("Nombre/Alias", value=row.get("nombre",""))
        apellidos_e = c2.text_input("Apellidos", value=row.get("apellidos",""))
        genero_e = c3.selectbox("Género", [""] + GENDER_OPTIONS,
                                index=([""] + GENDER_OPTIONS).index(row.get("genero","")) if row.get("genero","") in ([""] + GENDER_OPTIONS) else 0)

        c4,c5,c6 = st.columns(3)
        edad_e = c4.number_input("Edad", min_value=0, max_value=120, value=edad_default, step=1, format="%d")
        celular_e = c5.text_input("Celular", value=row.get("celular",""))
        correo_e  = c6.text_input("Correo",  value=row.get("correo",""))

        c7,c8 = st.columns(2)
        interes_e = c7.selectbox("Tipo de curso / interés", COURSE_OPTIONS,
                                 index=(COURSE_OPTIONS.index(row.get("interes_curso", COURSE_OPTIONS[0]))
                                        if row.get("interes_curso","") in COURSE_OPTIONS else 0))
        canal_e = c8.selectbox("¿Cómo te enteraste?", CHANNEL_OPTIONS,
                               index=(CHANNEL_OPTIONS.index(row.get("como_enteraste", CHANNEL_OPTIONS[0]))
                                      if row.get("como_enteraste","") in CHANNEL_OPTIONS else 0))

        stages = emb["stage"].tolist()
        idx = 0
        try: idx = stages.index(normalize_stage(row.get("etapa_mostrar","Awareness")))
        except Exception: idx = 0
        estado_e_lbl = st.selectbox("Etapa", [STAGE_LABEL[s] for s in stages], idx)

        obs_e = st.text_area("Observaciones", value=row.get("observaciones",""))
        _prox_date_val = to_date_value(row.get("proxima_accion_fecha",""))
        prox_f = st.date_input("Próxima acción (fecha)", value=_prox_date_val)
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
            prev_stage = row.get("etapa_mostrar","Awareness")

            leads.loc[mask, [
                "nombre","apellidos","genero","edad","celular","correo","interes_curso","como_enteraste",
                "lead_status","funnel_etapas","observaciones","proxima_accion_fecha","proxima_accion_desc",
            ]] = [
                (nombre_e or "").strip(), (apellidos_e or "").strip(), (genero_e or "").strip(),
                str(int(edad_e)) if str(edad_e) != "" else "",
                norm_phone(celular_e), norm_email(correo_e), interes_e, canal_e,
                estado_en, estado_en, (obs_e or "").strip(),
                prox_f.strftime("%Y-%m-%d") if isinstance(prox_f, date) else "", prox_d,
            ]

            leads.loc[mask, "edad_num"] = leads.loc[mask, "edad"].apply(lambda s: parse_age_to_int(s,0)).astype(int)
            leads.loc[mask, "etapa_mostrar"] = leads.loc[mask].apply(stage_value, axis=1)
            row_now = leads.loc[mask].iloc[0]
            leads.loc[mask,"lead_score"] = str(compute_lead_score(row_now))
            if prev_stage != estado_en:
                leads.loc[mask,"fecha_entrada_etapa"] = now_date()

            save_csv(leads.drop(columns=[c for c in ["edad_num"] if c in leads.columns]), FILES["leads"])
            leads["edad"] = leads["edad"].astype(str).fillna("")
            leads["edad_num"] = leads["edad"].apply(lambda s: parse_age_to_int(s,0)).astype(int)
            leads["etapa_mostrar"] = leads.apply(stage_value, axis=1)
            leads["lead_score"] = leads.apply(compute_lead_score, axis=1).astype(str)
            st.success("Lead actualizado."); st.rerun()

# =========================
# PÁGINA SEGUIMIENTO (una sola ETAPA)
# =========================
STAGE_TEMPLATES = {
    "Awareness":   {"tipo": "Bienvenida", "canal": "WhatsApp",
                    "plantilla": "Hola {nombre}, gracias por tu interés en {curso}. Te comparto info (temario, costo y fechas)."},
    "Contacted":   {"tipo": "Seguimiento inicial", "canal": "WhatsApp",
                    "plantilla": "Hola {nombre}, te escribo para dar seguimiento a {curso}. ¿Te comparto próximas fechas y costos?"},
    "MQL":         {"tipo": "Envío de información", "canal": "WhatsApp",
                    "plantilla": "Aquí tienes el temario y detalles de {curso} (duración, modalidad y costo)."},
    "SQL":         {"tipo": "Cierre suave", "canal": "WhatsApp",
                    "plantilla": "Por lo que me comentas, {curso} te ayudaría bastante. ¿Te comparto datos para inscripción?"},
    "Nurturing":   {"tipo": "Contenido de valor", "canal": "WhatsApp",
                    "plantilla": "Te comparto material breve sobre {curso}. La fecha límite de inscripción es {fecha_limite}."},
    "Demo_Booked": {"tipo": "Preinscripción/Depósito", "canal": "WhatsApp",
                    "plantilla": "Para asegurar tu lugar en {curso}, realiza el depósito de preinscripción. Te paso los datos."},
    "Won":         {"tipo": "Bienvenida alumno", "canal": "WhatsApp",
                    "plantilla": "¡Bienvenido(a), {nombre}! Tu registro en {curso} quedó confirmado."},
    "Lost":        {"tipo": "Cierre cordial", "canal": "WhatsApp",
                    "plantilla": "Gracias por tu tiempo, {nombre}. Si deseas retomar {curso} más adelante, con gusto te apoyamos."},
    "Re_Engaged":  {"tipo": "Reactivación", "canal": "WhatsApp",
                    "plantilla": "Tenemos nuevas fechas y opciones de {curso}. ¿Te comparto horarios y promociones?"},
}

def render_tpl(text: str, lead_row: pd.Series) -> str:
    ctx = {k: lead_row.get(k, "") for k in lead_row.index}
    ctx.update({"nombre": lead_row.get("nombre",""), "curso": lead_row.get("interes_curso",""),
                "fecha_limite": "", "precio": lead_row.get("monto_estimado","")})
    try: return text.format(**ctx)
    except KeyError: return text

def page_followup():
    global leads, segs
    st.markdown("## ✉️ Seguimiento")

    with st.expander("🎯 Filtros de acciones", expanded=True):
        dcol1, dcol2, dcol3 = st.columns([1.1,1.1,1.8])
        selected_date = dcol1.date_input("📅 Fecha (próxima acción)", value=date.today(), key="fu_date")
        solo_mios = dcol1.checkbox("Solo mis leads", value=False, key="fu_only_mine")

        etapas_disp = [s for s in STAGE_ORDER if s in leads["etapa_mostrar"].unique()]
        opticursos = sorted([c for c in leads.get("interes_curso","").unique() if str(c).strip()])
        owners = sorted([o for o in leads.get("owner","").unique() if str(o).strip()])

        fil_stage = dcol2.multiselect("Etapa", etapas_disp, default=[])
        fil_curso = dcol2.multiselect("Curso", opticursos, default=[])
        fil_owner = dcol3.multiselect("Owner", owners, default=[],
                                      help="Activa 'Solo mis leads' para ver solo los tuyos.")
        q = st.text_input("🔎 Buscar lead (nombre, correo o teléfono)", key="fu_search")

    base = leads.copy()
    if solo_mios:
        base = base[base["owner"] == owner_name_default()]
    if q:
        ql = q.lower()
        def _m(r):
            s = " ".join([str(r.get('nombre','')), str(r.get('apellidos','')), str(r.get('correo','')),
                          str(r.get('celular','')), str(r.get('telefono',''))]).lower()
            return ql in s
        base = base[base.apply(_m, axis=1)]
    if fil_stage: base = base[base["etapa_mostrar"].isin(fil_stage)]
    if fil_curso: base = base[base["interes_curso"].isin(fil_curso)]
    if fil_owner: base = base[base["owner"].isin(fil_owner)]

    # Columna segura de próxima acción
    if "proxima_accion_fecha" not in base.columns:
        base["proxima_accion_fecha"] = ""
    base["_prox"] = parse_date_smart(base["proxima_accion_fecha"].astype(str)).dt.date
    due = base[base["_prox"] == selected_date].copy()

    st.caption(f"Acciones para {selected_date.strftime('%Y-%m-%d')}: {len(due)}")
    if due.empty:
        st.info("No hay acciones programadas según los filtros.")
    else:
        due = due.copy()
        due["__h"] = due.get("hora_registro","").apply(parse_time_safe)
        due = due.sort_values("__h", ascending=False)
        for _, row in due.iterrows():
            with st.container(border=True):
                cA,cB,cC = st.columns([5,3,2])
                cA.markdown(f"**{row.get('nombre','')} {row.get('apellidos','')}** • {row.get('genero','')} • {row.get('celular','')}")
                cB.markdown(stage_badge(row.get("etapa_mostrar","Awareness")), unsafe_allow_html=True)
                if cC.button("📨 Abrir", key=f"open_{row.get('id_lead','')}"):
                    st.session_state["fu_selected_lead_id"] = str(row.get("id_lead",""))
                    st.query_params["lead"] = str(row.get("id_lead",""))
                    st.rerun()
                st.caption(f"➡️ {row.get('proxima_accion_desc','') or '—'}  \n👤 {row.get('owner','—')}")

    st.divider()

    if "fu_selected_lead_id" not in st.session_state:
        qp = st.query_params
        if "lead" in qp: st.session_state["fu_selected_lead_id"] = qp.get("lead", [""])[0]

    selected_lead_id = st.session_state.get("fu_selected_lead_id","")

    if not selected_lead_id:
        base2 = base
        id_to_label = {str(r["id_lead"]): lead_label(r) for _, r in base2.iterrows()}
        opts = [""] + list(id_to_label.keys())
        lead_pick = st.selectbox("Selecciona lead", opts, index=0, format_func=lambda k: id_to_label.get(k, "—") if k else "—")
        if not lead_pick: return
        st.session_state["fu_selected_lead_id"] = lead_pick
        st.query_params["lead"] = lead_pick
        st.rerun()
    else:
        mask_lead = leads["id_lead"].astype(str) == str(selected_lead_id)
        if not mask_lead.any():
            st.warning("El lead seleccionado ya no existe.")
            st.session_state.pop("fu_selected_lead_id", None)
            st.query_params.pop("lead", None); st.rerun()
        lead_ctx = leads.loc[mask_lead].iloc[0]

        top = st.container()
        with top:
            c1,c2,c3,c4 = st.columns([5,3,2,1.5])
            c1.markdown(f"### {lead_ctx.get('nombre','')} {lead_ctx.get('apellidos','')}  \n📞 {lead_ctx.get('celular','—')} • ✉️ {lead_ctx.get('correo','—')}")
            c2.markdown(stage_badge(lead_ctx.get("etapa_mostrar","Awareness")), unsafe_allow_html=True)
            c3.markdown(owner_badge(lead_ctx.get("owner","")), unsafe_allow_html=True)
            if c4.button("Cambiar lead", use_container_width=True):
                for stage in STAGE_ORDER: st.session_state.pop(f"tpl_{stage}_{selected_lead_id}", None)
                st.session_state.pop("fu_stage_select", None)
                st.session_state.pop("fu_selected_lead_id", None)
                st.query_params.pop("lead", None)
                st.rerun()

        st.subheader("Historial del lead (ordenado por fecha/hora)")
        hist = segs[segs["id_lead"].astype(str) == str(selected_lead_id)].copy() if not segs.empty else pd.DataFrame(columns=SCHEMA_SEGS)
        hist_cols = ["fecha","hora","etapa","proxima_accion_fecha","tipo_mensaje","estado_mensaje","canal","atendido_por","observaciones"]
        for c in hist_cols:
            if c not in hist.columns: hist[c] = ""
        if "proxima_accion_fecha" not in hist.columns:
            hist["proxima_accion_fecha"] = ""
        hist["__fecha"] = parse_date_smart(hist["fecha"])
        hist["__hora"]  = hist["hora"].apply(parse_time_safe)
        hist = hist.sort_values(["__fecha","__hora"])
        st.dataframe(hist[hist_cols], use_container_width=True, hide_index=True)
        st.download_button("⬇️ Descargar historial", data=hist[hist_cols].to_csv(index=False).encode("utf-8"),
                           file_name=f"historial_lead_{selected_lead_id}.csv", mime="text/csv")

        st.subheader("Plantillas por etapa")
        selected_stage_override = None
        previews = []
        for stage in STAGE_ORDER:
            t = STAGE_TEMPLATES.get(stage); desc = STAGE_LABEL.get(stage, stage)
            bg, fg = STAGE_COLORS.get(stage, ("#F1F5F9","#0F172A"))
            with st.expander(f"• {desc}"):
                st.markdown(f"<div style='display:inline-block;background:{bg};color:{fg};padding:2px 8px;border-radius:999px;font-size:12px;font-weight:700'>{stage}</div>", unsafe_allow_html=True)
                usar = st.checkbox(f"Usar plantilla de {stage}", key=f"tpl_{stage}_{selected_lead_id}")
                pre = render_tpl(t["plantilla"], lead_ctx)
                st.caption(f"Sugerido: {t['canal']} • Tipo: {t['tipo']}")
                pre_edit = st.text_area("Previsualización (editable)", value=pre, height=110, key=f"preview_{stage}_{selected_lead_id}")
                st.code(pre_edit, language=None)
                if usar:
                    previews.append(pre_edit)
                    selected_stage_override = stage

        st.subheader("Mensaje a enviar")
        composed_default = "\n\n".join(previews) if previews else ""
        msg = st.text_area("Redacta aquí el mensaje final", value=composed_default, height=160, key=f"composer_{selected_lead_id}")
        st.code(msg or "", language=None)

        cwa1, cwa2 = st.columns([2,4])
        usar_tel_lead = cwa1.checkbox("Usar número del lead", value=True)
        tel_obj = norm_phone(lead_ctx.get("celular","")) if usar_tel_lead else ""
        msg_enc = quote_plus(msg or "")
        url_wa_web = f"https://api.whatsapp.com/send?phone={tel_obj}&text={msg_enc}" if tel_obj else f"https://api.whatsapp.com/send?text={msg_enc}"
        cwa2.markdown(f"<div class='wa-actions'><a class='btn' href='{url_wa_web}' target='_blank'>🌐 Abrir en WhatsApp Web</a></div>", unsafe_allow_html=True)

        st.subheader("Envío y próxima acción")
        stages = emb["stage"].tolist(); labels = [STAGE_LABEL[s] for s in stages]
        curr_stage = selected_stage_override or lead_ctx.get("etapa_mostrar","Awareness")
        idx_default = labels.index(STAGE_LABEL.get(curr_stage, curr_stage)) if STAGE_LABEL.get(curr_stage, curr_stage) in labels else 0

        c1,c2,c3 = st.columns(3)
        canal = c1.selectbox("Canal", CHANNEL_OPTIONS, (CHANNEL_OPTIONS.index("WhatsApp") if "WhatsApp" in CHANNEL_OPTIONS else 0))
        atendido_por = c2.text_input("Atendido por", value=owner_name_default())
        estado_msg = c3.selectbox("Estado del mensaje", ["Enviado","Sin respuesta","Respondido","Perdido"])

        cNA,cNB = st.columns(2)
        _pf = to_date_value(lead_ctx.get("proxima_accion_fecha",""))
        prox_fecha = cNA.date_input("Próxima acción (fecha)", value=_pf)
        prox_desc  = cNB.text_input("Próxima acción (descripción)", value=lead_ctx.get("proxima_accion_desc",""))

        close_today = st.checkbox("Cerrar acción de la fecha seleccionada (quitar del calendario)", value=False)

        etapa_lbl = st.selectbox("Etapa del embudo", labels, idx_default, key="fu_stage_select")
        etapa_en = stages[labels.index(etapa_lbl)]
        st.markdown(stage_badge(etapa_en), unsafe_allow_html=True)

        if st.button("Registrar seguimiento(s)"):
            if not previews and not (msg or "").strip():
                st.warning("Selecciona al menos una plantilla o redacta un mensaje.")
            else:
                new_id = next_id(segs, "id_seguimiento")
                to_add = {
                    "id_seguimiento": str(new_id), "id_lead": str(selected_lead_id),
                    "fecha": now_date(), "hora": now_time(),
                    "etapa": etapa_en,
                    "proxima_accion_fecha": prox_fecha.strftime("%Y-%m-%d"),
                    "tipo_mensaje": "WhatsApp (compuesto)",
                    "estado_mensaje": estado_msg, "canal": canal, "atendido_por": atendido_por,
                    "observaciones": (msg or "").strip(),
                }
                segs_local = pd.DataFrame([to_add])
                segs = pd.concat([segs, segs_local], ignore_index=True)
                save_csv(segs, FILES["seguimientos"])

                mask = leads["id_lead"].astype(str) == str(selected_lead_id)
                if not mask.any():
                    st.warning("El lead seleccionado ya no existe."); st.rerun()

                prev_stage = leads.loc[mask].iloc[0].get("etapa_mostrar","Awareness")
                selected_str = selected_date.strftime("%Y-%m-%d")
                prox_str = prox_fecha.strftime("%Y-%m-%d")

                leads.loc[mask, ["lead_status","funnel_etapas"]] = [etapa_en, etapa_en]
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
                leads["etapa_mostrar"] = leads.apply(stage_value, axis=1)
                save_csv(leads.drop(columns=[c for c in ["edad_num"] if c in leads.columns]), FILES["leads"])
                st.success("Seguimiento registrado y lead actualizado.")
                st.rerun()

# =========================
# DASHBOARD
# =========================
def _btn_download_df(label: str, df: pd.DataFrame, fname: str):
    st.download_button(label, data=df.to_csv(index=False).encode("utf-8"), file_name=fname, mime="text/csv")

def _chart_by_stage(df: pd.DataFrame):
    if df.empty: return None, pd.DataFrame()
    order = [s for s in STAGE_ORDER if s in df["etapa_mostrar"].unique()]
    colors = [STAGE_COLORS[s][0] for s in order]
    color_scale = alt.Scale(domain=order, range=colors)
    agg = df.groupby("etapa_mostrar").size().rename("conteo").reset_index()
    agg["% del total"] = (agg["conteo"]/len(df)*100).round(1)
    chart = alt.Chart(agg).mark_bar().encode(
        x=alt.X("conteo:Q", title="Leads"),
        y=alt.Y("etapa_mostrar:N", sort=order, title="Etapa (Embudo)"),
        color=alt.Color("etapa_mostrar:N", scale=color_scale, legend=None),
        tooltip=["etapa_mostrar","conteo","% del total"]
    ).properties(height=360)
    labels = chart.mark_text(align="left", dx=3).encode(text="conteo:Q")
    return chart + labels, agg

def page_dashboard():
    st.markdown("## 📊 Dashboard Analítico")

    with st.expander("🔎 Filtros (opcionales)", expanded=False):
        c1, c2, c3 = st.columns(3)
        cursos = sorted([c for c in leads.get("interes_curso","").unique() if str(c).strip()])
        owners = sorted([o for o in leads.get("owner","").unique() if str(o).strip()])
        etapas = [s for s in STAGE_ORDER if s in leads["etapa_mostrar"].unique()]
        f_curso = c1.multiselect("Curso", ["(Todos)"]+cursos, default=["(Todos)"])
        f_owner = c2.multiselect("Owner", ["(Todos)"]+owners, default=["(Todos)"])
        f_etapa = c3.multiselect("Etapa", ["(Todas)"]+etapas, default=["(Todas)"])

    L = leads.copy()
    if f_curso and "(Todos)" not in f_curso: L = L[L["interes_curso"].isin(f_curso)]
    if f_owner and "(Todos)" not in f_owner: L = L[L["owner"].isin(f_owner)]
    if f_etapa and "(Todas)" not in f_etapa: L = L[L["etapa_mostrar"].isin(f_etapa)]

    st.subheader("1) ¿Cuántos leads hay y en qué etapa están?")
    st.metric("👥 Total de leads (filtro)", len(L))

    chart, tabla = _chart_by_stage(L)
    c1, c2 = st.columns([2,1])
    with c1:
        if chart is not None: st.altair_chart(chart, use_container_width=True)
        else: st.info("No hay datos para graficar.")
    with c2:
        st.markdown("**Tabla por etapa**")
        st.dataframe(tabla, use_container_width=True, hide_index=True)
        if not tabla.empty: _btn_download_df("⬇️ Descargar (etapas)", tabla, "resumen_etapas.csv")
        won = int(tabla.loc[tabla["etapa_mostrar"]=="Won","conteo"].sum()) if not tabla.empty else 0
        lost = int(tabla.loc[tabla["etapa_mostrar"]=="Lost","conteo"].sum()) if not tabla.empty else 0
        st.caption(f"✅ Won: **{won}** • ❌ Lost: **{lost}**")

    st.divider()
    st.subheader("2) Desgloses descargables")
    if not L.empty:
        t1 = pd.crosstab(L["interes_curso"], L["etapa_mostrar"]).reset_index()
        st.markdown("**Curso × Etapa**"); st.dataframe(t1, use_container_width=True, hide_index=True)
        _btn_download_df("⬇️ Descargar Curso×Etapa", t1, "curso_etapa.csv")
        t2 = pd.crosstab(L["owner"], L["etapa_mostrar"]).reset_index()
        st.markdown("**Owner × Etapa**"); st.dataframe(t2, use_container_width=True, hide_index=True)
        _btn_download_df("⬇️ Descargar Owner×Etapa", t2, "owner_etapa.csv")
    else:
        st.info("No hay datos con los filtros actuales.")

# =========================
# ROUTER
# =========================
if "menu" not in st.session_state:
    st.session_state["menu"] = "👤 Leads"

if menu == "👤 Leads":
    page_leads()
elif menu == "✉️ Seguimiento":
    page_followup()
elif menu == "📊 Dashboard":
    page_dashboard()

st.caption("Mini-CRM CVDR v12.5 • Seguimiento con UNA sola 'Etapa' (normalizada). Fechas robustas, edición/alta y dashboard con descargas.")
