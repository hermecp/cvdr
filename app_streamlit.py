# app.py
# ──────────────────────────────────────────────────────────────────────────────
# CRM de Leads (Streamlit)
# - Login por usuario+contraseña
# - Leads: consultar / agregar / editar
# - Seguimiento: Hoy / Por fecha / Todos (con filtro rápido)
# - Historial UNIFICADO opcional (tabla)
# - Dashboard bilingüe (ES/EN) con gráficas y tablas
# - FIX: id_lead autoincremental continuo (L0001, L0002, …)
# ──────────────────────────────────────────────────────────────────────────────

from __future__ import annotations
import re
import hashlib
from pathlib import Path
from datetime import datetime, date, timedelta

import altair as alt
import pandas as pd
import streamlit as st

# ===================== Config & Paths =====================
st.set_page_config(page_title="CRM Leads", page_icon="🧑‍💼", layout="wide")
DATA_PATH = Path("leads.csv")
USERS_PATH = Path("users.csv")

# ===================== Usuarios (default + helpers) =====================
DEFAULT_USER_ROWS = [
    ["admin","Admin","Admin","ba26148e3bc77341163135d123a4dc26664ff0497da04c0b3e83218c97f70c45"],         # 
    ["director","Director","Director","c34926c2783dca6cf34d1160ed5a04e1615cb813d3b5798efc29cc590cce4c91"],   # 
    ["subdirector","Subdirector","Subdirector","58845944d08671209339de539469a100c8e9d6e17dcee9a447c7751937f7cb48"],  #
    ["favio","Favio","Ventas","e28ebb5d991f9ebbc5f2d26b199586e9bfb8fffd3b76dca200efd75eb68e999d"],          # 
    ["nancy","Nancy","Ventas","64b1bce63509372952ad7191af86bddcb9939772404c236ff67b89d0442496d0"],          # 
    ["rosario","Rosario","Ventas","706f42010b29d6376c768d717a19b49dc50b8b7133bffa1ae36d0fbbc32d59bc"],       # 
    ["haydee","Haydee","Comunicación","6b90d996f7c98698cd95d0d86f1298dbb9df89df34f16136b259a4efcaba04d8"],   # 
    ["nora","Nora","Comunicación","f54fd67046eeca39cd1f760730d3b48b1c00d3830f0c5b9fa5ace0a7683a22058"],      # 
]
USER_COLUMNS = ["username","name","role","password_hash"]

def sha256_hex(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()

def ensure_users_csv():
    if not USERS_PATH.exists():
        pd.DataFrame(DEFAULT_USER_ROWS, columns=USER_COLUMNS).to_csv(USERS_PATH, index=False, encoding="utf-8")
    else:
        dfu = pd.read_csv(USERS_PATH, dtype=str).fillna("")
        for c in USER_COLUMNS:
            if c not in dfu.columns:
                dfu[c] = ""
        dfu = dfu[USER_COLUMNS]
        dfu.to_csv(USERS_PATH, index=False, encoding="utf-8")

@st.cache_data(ttl=60)
def load_users() -> pd.DataFrame:
    ensure_users_csv()
    return pd.read_csv(USERS_PATH, dtype=str).fillna("")

def try_login(username: str, password: str):
    users = load_users()
    row = users[users["username"].str.lower() == (username or "").strip().lower()]
    if row.empty: return None
    ok = (row.iloc[0]["password_hash"] == sha256_hex(password or ""))
    if not ok: return None
    return {"username": row.iloc[0]["username"], "name": row.iloc[0]["name"], "role": row.iloc[0]["role"]}

def logout():
    for k in ["user","selected_lead_id","filters"]:
        if k in st.session_state: del st.session_state[k]

# ===================== Constantes & Catálogos de CRM =====================
COLUMNS_BASE = [
    "id_lead","fecha_registro","hora_registro","nombre/alias","apellidos","genero","edad","celular",
    "telefono","correo","interes_curso(puede sellecionar varios)","como_enteraste","funnel_etapas",
    "fecha_ultimo_contacto","observaciones","atendido_por","proxima_accion_fecha","proxima_accion_desc"
]
COLUMNS_EXTRA = [
    "estado_color","fecha_cambio_color","amarillo_contador",
    "historial_color","historial_atenciones","total_atenciones"
]

CAT_CURSOS = [
    "IA profesionales inmobiliarios","IA educación básica","IA educación universitaria",
    "IA empresas","IA para gobierno","Inglés","Polivirtual Bach.","Polivirtual Lic."
]
CAT_COMO = [
    "Facebook","Instagram","WhatsApp","Correo electrónico","Sitio web",
    "Recomendación","Volante/Impreso","Evento/Conferencia","Otro",
]

# Embudo (solo para 🟡) — inglés (español)
FUNNEL_YELLOW = [
    "Follow-up (Seguimiento)",
    "Materials (Materiales/flyer/videos)",
    "Bank details (Datos bancarios)",
    "Proposal (Propuesta)",
    "Negotiation (Negociación)",
    "Nurturing (Nutrición)",
]
STAGE_DESC = {
    "Follow-up (Seguimiento)": "Primeras interacciones y agendar siguiente contacto.",
    "Materials (Materiales/flyer/videos)": "Se enviaron temarios, flyers o videos.",
    "Bank details (Datos bancarios)": "Se compartieron datos para pago/inscripción.",
    "Proposal (Propuesta)": "Propuesta formal enviada.",
    "Negotiation (Negociación)": "Ajustes/condiciones finales.",
    "Nurturing (Nutrición)": "Aún no listo; nutrir con contenido.",
    "Won (Ganado)": "Cerrado con pago.",
    "Lost (Perdido)": "Descartado o sin interés.",
    "Contacted (Contactado)": "Contacto inicial.",
}
STAGE_COLORS = {
    "Follow-up (Seguimiento)": "#3b82f6",
    "Materials (Materiales/flyer/videos)": "#10b981",
    "Bank details (Datos bancarios)": "#f59e0b",
    "Proposal (Propuesta)": "#8b5cf6",
    "Negotiation (Negociación)": "#ef4444",
    "Nurturing (Nutrición)": "#6b7280",
    "Won (Ganado)": "#22c55e",
    "Lost (Perdido)": "#ef4444",
    "Contacted (Contactado)": "#eab308",
}

CONTACT_OUTCOMES = [
    "📵 No responde","ℹ️ Pide información","✅ Interesado (propuesta)",
    "💳 Envió comprobante","🚫 No interesado",
]
OUTCOME_RULES = {
    "📵 No responde":               ("🟡", "Follow-up (Seguimiento)",            2, "Reintentar contacto"),
    "ℹ️ Pide información":          ("🟡", "Materials (Materiales/flyer/videos)", 1, "Enviar materiales"),
    "✅ Interesado (propuesta)":     ("🟡", "Bank details (Datos bancarios)",      1, "Enviar datos bancarios"),
    "💳 Envió comprobante":         ("🟢", "Won (Ganado)",                        0, "Pago confirmado"),
    "🚫 No interesado":             ("🔴", "Lost (Perdido)",                      0, "Cierre por no interés"),
}

# ===================== Utilidades generales =====================
def today() -> date: return date.today()
def ts_now() -> str: return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
def timestamp_pair():
    dt = datetime.now(); return dt.date().isoformat(), dt.strftime("%H:%M:%S")

def parse_date_safe(s):
    """
    Acepta ISO (YYYY-MM-DD), YYYY/MM/DD y dd/mm/YYYY o dd-mm-YYYY,
    sin warnings. Devuelve date o None.
    """
    if s is None:
        return None
    s_str = str(s).strip()
    if not s_str:
        return None

    # Intentos con formatos explícitos
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(s_str, fmt).date()
        except ValueError:
            pass

    # Fallback robusto: parser de pandas con dayfirst=True y control de NaT
    ts = pd.to_datetime(s_str, dayfirst=True, errors="coerce")
    return ts.date() if pd.notna(ts) else None

def str_to_list(s: str) -> list[str]:
    if not s or pd.isna(s): return []
    return [x.strip() for x in str(s).split("|") if x.strip()]

def list_to_str(vals: list[str]) -> str:
    return " | ".join([v for v in vals if v])

# ===================== IO CSV Leads =====================
def ensure_csv():
    if not DATA_PATH.exists():
        pd.DataFrame(columns=COLUMNS_BASE + COLUMNS_EXTRA).to_csv(DATA_PATH, index=False, encoding="utf-8")
    else:
        df = pd.read_csv(DATA_PATH, dtype=str).fillna("")
        for c in COLUMNS_BASE + COLUMNS_EXTRA:
            if c not in df.columns:
                df[c] = "" if c not in ("amarillo_contador","total_atenciones") else "0"
        df = df[COLUMNS_BASE + COLUMNS_EXTRA]
        df.to_csv(DATA_PATH, index=False, encoding="utf-8")

@st.cache_data(ttl=10)
def load_data() -> pd.DataFrame:
    ensure_csv()
    return pd.read_csv(DATA_PATH, dtype=str).fillna("")

def save_data(df: pd.DataFrame):
    for c in COLUMNS_BASE + COLUMNS_EXTRA:
        if c not in df.columns:
            df[c] = "" if c not in ("amarillo_contador","total_atenciones") else "0"
    df = df[COLUMNS_BASE + COLUMNS_EXTRA].copy().fillna("")
    df.to_csv(DATA_PATH, index=False, encoding="utf-8")
    load_data.clear()

# ---------- ID autoincremental ----------
def next_lead_id(df: pd.DataFrame) -> str:
    """
    Genera el siguiente id_lead tipo L0001… tomando el mayor número
    encontrado al final del id_lead actual (si no hay, empieza en 1).
    """
    if df.empty:
        return "L0001"
    ids = df["id_lead"].astype(str).tolist()
    nums = []
    for s in ids:
        m = re.search(r"(\d+)$", s)
        if m:
            try:
                nums.append(int(m.group(1)))
            except:
                pass
    n = (max(nums) + 1) if nums else (len(ids) + 1)
    return f"L{n:04d}"

# ===================== Lógica de estado/orden =====================
def etapa_is_won(etapa: str) -> bool:
    e = str(etapa or "")
    return ("Ganado" in e) or e.startswith("Won")

def etapa_is_lost(etapa: str) -> bool:
    e = str(etapa or "")
    return ("Perdido" in e) or e.startswith("Lost")

def compute_color(row) -> str:
    color = str(row.get("estado_color","")).strip()
    if color in {"🔴","🟡","🟢"}: return color
    etapa = str(row.get("funnel_etapas","")).strip()
    ult = parse_date_safe(row.get("fecha_ultimo_contacto",""))
    if etapa_is_won(etapa): return "🟢"
    if etapa_is_lost(etapa): return "🔴"
    if ult and (today() - ult).days > 30: return "🔴"
    return "🟡"

def enrich(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty: return df
    df = df.copy()
    df["estado_color"] = df.apply(compute_color, axis=1)
    df["_prox"] = df["proxima_accion_fecha"].apply(parse_date_safe)
    df["_reg"]  = df["fecha_registro"].apply(parse_date_safe)
    df["_ord"]  = df["estado_color"].map({"🔴":0,"🟡":1,"🟢":2}).fillna(9)
    df = df.sort_values(by=["_ord","_prox","_reg"], ascending=[True,True,False])
    return df

def add_attention(base: pd.DataFrame, idx: int, old_c: str, new_c: str, nota: str, user: str):
    ts = ts_now()
    if old_c != new_c:
        hist = str(base.loc[idx,"historial_color"] or "")
        base.loc[idx,"historial_color"] = (hist + ("\n" if hist else "") + f"{ts} | {old_c} → {new_c}")
        base.loc[idx,"fecha_cambio_color"] = ts
    cnt = int(str(base.loc[idx,"amarillo_contador"] or "0") or 0)
    if new_c == "🟡": cnt += 1
    base.loc[idx,"amarillo_contador"] = str(cnt)
    hist_att = str(base.loc[idx,"historial_atenciones"] or "")
    base.loc[idx,"historial_atenciones"] = (hist_att + ("\n" if hist_att else "") + f"{ts} | {user or 'sin usuario'} | {nota or 'sin nota'}")
    total = int(str(base.loc[idx,"total_atenciones"] or "0") or 0)
    base.loc[idx,"total_atenciones"] = str(total + 1)
    return base

def sla_badges(row):
    prox = parse_date_safe(row.get("proxima_accion_fecha",""))
    if prox and prox < today():
        st.error(f"⏰ Próxima acción VENCIDA ({prox.isoformat()})")
    elif prox and prox == today():
        st.markdown("<div style='padding:8px;border-radius:8px;background:#3b0d0d;color:#fff;'>📌 Próxima acción HOY</div>", unsafe_allow_html=True)
    elif not prox:
        st.info("📭 Sin próxima acción programada")

def apply_outcome(row, outcome: str, nota: str, user: str):
    color, stage, delta, desc = OUTCOME_RULES[outcome]
    next_date = today() + timedelta(days=delta) if delta > 0 else None
    next_desc = (row.get("proxima_accion_desc","") or desc)
    nota_final = nota or outcome
    return color, stage, next_date, next_desc, nota_final

# ===================== Estado global (UI) =====================
if "selected_lead_id" not in st.session_state: st.session_state.selected_lead_id = None
if "filters" not in st.session_state: st.session_state.filters = {"q":"", "resp":"", "color_idx":0}

def set_selected(lead_id: str | None):
    if lead_id: st.session_state.selected_lead_id = str(lead_id)

# ===================== Componentes UI Reutilizables =====================
def ui_filtros(df: pd.DataFrame) -> pd.DataFrame:
    with st.expander("🔎 Filtros", expanded=False):
        c1,c2,c3 = st.columns(3)
        q  = c1.text_input("Buscar (nombre/correo/teléfono):", st.session_state.filters["q"]).strip().lower()
        rp = c2.text_input("Responsable:", st.session_state.filters["resp"]).strip().lower()
        opt = ["(Todos)","🔴 Rojo","🟡 Amarillo","🟢 Verde"]
        col = c3.selectbox("Estado:", opt, index=st.session_state.filters["color_idx"])
    st.session_state.filters = {"q":q,"resp":rp,"color_idx":opt.index(col)}

    if q:
        df = df[df.apply(lambda r: any(
            q in str(r.get(k,"")).lower() for k in ["nombre/alias","apellidos","correo","celular","telefono"]
        ), axis=1)]
    if rp: df = df[df["atendido_por"].str.lower().str.contains(rp, na=False)]
    if col != "(Todos)": df = df[df["estado_color"] == col.split(" ")[0]]
    return df

def ui_tabla(df: pd.DataFrame, height=420):
    if df.empty: st.info("No hay leads."); return
    cols = ["estado_color","id_lead","nombre/alias","apellidos","correo","celular","telefono",
            "proxima_accion_fecha","proxima_accion_desc","fecha_ultimo_contacto","atendido_por",
            "amarillo_contador","total_atenciones","funnel_etapas"]
    st.dataframe(df[cols], use_container_width=True, height=height)

def ui_lead_radio(df: pd.DataFrame) -> str | None:
    if df.empty:
        st.info("Sin leads con los filtros actuales."); return None
    df = df.copy(); df["id_lead"] = df["id_lead"].astype(str)
    def label(r):
        prox = r.get("proxima_accion_fecha","—") or "—"
        return f"🧑 {r.get('estado_color','')}  {r.get('nombre/alias','')} {r.get('apellidos','')} • {prox}"
    ids = df["id_lead"].tolist()
    labels = {r["id_lead"]: label(r) for _,r in df.iterrows()}
    pre = ids.index(st.session_state.selected_lead_id) if st.session_state.selected_lead_id in ids else 0
    choice = st.radio("Selecciona un lead:", options=ids, index=pre, format_func=lambda k: labels.get(k,k), key="lead_radio")
    yc = int(str(df[df["id_lead"]==choice].iloc[0].get("amarillo_contador","0") or 0))
    st.metric("Veces en 🟡", yc)
    set_selected(choice)
    return choice

# ---------- Historial unificado ----------
_TS = r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})"
def _rows_color(t):
    out=[]
    for s in (t or "").splitlines():
        s=s.strip()
        if not s: continue
        m=re.match(rf"^{_TS}\s*\|\s*(.+)$",s)
        if m:
            ts,rest=m.groups(); m2=re.search(r"([🔴🟡🟢])\s*→\s*([🔴🟡🟢])",rest)
            out.append({"Fecha":ts,"Tipo":"Cambio de color","Usuario":"","Detalle":rest,"De":(m2.group(1) if m2 else ""),"A":(m2.group(2) if m2 else "")})
        else:
            out.append({"Fecha":"","Tipo":"Cambio de color","Usuario":"","Detalle":s,"De":"","A":""})
    return out

def _rows_att(t):
    out=[]
    for s in (t or "").splitlines():
        s=s.strip()
        if not s: continue
        m=re.match(rf"^{_TS}\s*\|\s*([^|]+)\|\s*(.*)$",s)
        if m:
            ts,u,nota=m.groups()
            out.append({"Fecha":ts,"Tipo":"Atención","Usuario":u.strip(),"Detalle":nota.strip(),"De":"","A":""})
        else:
            out.append({"Fecha":"","Tipo":"Atención","Usuario":"","Detalle":s,"De":"","A":""})
    return out

def _rows_obs(t):
    out=[]; first=True
    for s in (t or "").splitlines():
        s=s.rstrip()
        if not s: continue
        if first and not re.match(rf"^{_TS}",s):
            out.append({"Fecha":"","Tipo":"Observación","Usuario":"","Detalle":s,"De":"","A":""}); first=False; continue
        first=False
        m=re.match(rf"^{_TS}\s*\|\s*([^|]+)\|\s*(.*)$",s)
        if m:
            ts,u,obs=m.groups()
            out.append({"Fecha":ts,"Tipo":"Observación","Usuario":u.strip(),"Detalle":obs.strip(),"De":"","A":""})
        else:
            out.append({"Fecha":"","Tipo":"Observación","Usuario":"","Detalle":s,"De":"","A":""})
    return out

def history_df(row: pd.Series) -> pd.DataFrame:
    rows = _rows_color(row.get("historial_color","")) + _rows_att(row.get("historial_atenciones","")) + _rows_obs(row.get("observaciones",""))
    dfh = pd.DataFrame(rows, columns=["Fecha","Tipo","Usuario","Detalle","De","A"])
    if dfh.empty: return dfh
    dfh["Fecha"] = pd.to_datetime(dfh["Fecha"], errors="coerce")
    order = {"Atención":0,"Cambio de color":1,"Observación":2}
    dfh["__ord"] = dfh["Tipo"].map(order).fillna(9).astype(int)
    dfh = dfh.sort_values(["Fecha","__ord"], ascending=[False,True], na_position="last").drop(columns="__ord")
    return dfh

# ===================== Páginas: Leads / Seguimiento / Dashboard =====================
def page_leads():
    st.title("🧑‍💼 Leads")
    sub = st.radio("Menú:", ["Consultar","Agregar","Editar"], horizontal=True)

    if sub == "Consultar":
        df = ui_filtros(enrich(load_data()))
        ui_tabla(df)
        st.download_button("⬇️ Exportar CSV", data=load_data().to_csv(index=False).encode("utf-8"),
            file_name="leads_export.csv", mime="text/csv", use_container_width=True)

    elif sub == "Agregar":
        st.subheader("➕ Agregar")
        df = load_data()
        with st.form("form_new"):
            ctop = st.columns([1,1,1,1])
            with ctop[0]:
                # Mostrar el siguiente ID que se asignará
                st.caption(f"Siguiente ID asignado: **{next_lead_id(df)}**")
            c1,c2,c3,c4 = st.columns(4)
            nombre = c1.text_input("👤 Nombre / alias")
            apellidos = c2.text_input("👥 Apellidos")
            genero = c3.selectbox("⚧️ Género", ["","Femenino","Masculino","No binario","Prefiere no decir"], index=0)
            edad = c4.text_input("🎂 Edad")
            c5,c6,c7 = st.columns(3)
            celular = c5.text_input("📱 Celular"); telefono = c6.text_input("☎️ Teléfono"); correo = c7.text_input("✉️ Correo")
            interes = st.multiselect("📚 Interés en curso(s)", options=CAT_CURSOS, default=[])
            c8,c9 = st.columns(2)
            como = c8.selectbox("🧭 ¿Cómo se enteraste?", CAT_COMO, index=0)
            if como == "Otro":
                otro = c8.text_input("Especifica otro canal", ""); como = (otro.strip() or como)
            atendido_por_name = st.session_state.user["name"]
            c9.text_input("👨‍💼 Atendido por", value=atendido_por_name, disabled=True)
            c10,c11 = st.columns(2)
            prox_fecha = c10.date_input("📅 Próxima acción", value=today()+timedelta(days=3))
            prox_desc  = c11.text_input("📝 Descripción próxima acción")
            ok = st.form_submit_button("Guardar")

        if ok:
            fid = next_lead_id(df)  # ← AUTOINCREMENTAL
            f_fecha, f_hora = timestamp_pair()
            row = {
                "id_lead": fid, "fecha_registro": f_fecha, "hora_registro": f_hora,
                "nombre/alias": nombre, "apellidos": apellidos, "genero": genero, "edad": str(edad).strip(),
                "celular": celular, "telefono": telefono, "correo": correo,
                "interes_curso(puede sellecionar varios)": list_to_str(interes),
                "como_enteraste": como, "funnel_etapas": "Follow-up (Seguimiento)",
                "fecha_ultimo_contacto": f_fecha, "observaciones": "",
                "atendido_por": atendido_por_name,
                "proxima_accion_fecha": prox_fecha.isoformat(),
                "proxima_accion_desc": prox_desc,
                "estado_color": "🟡","fecha_cambio_color": ts_now(),
                "amarillo_contador": "1","historial_color": f"{ts_now()} | ∅ → 🟡",
                "historial_atenciones": "","total_atenciones": "0",
            }
            save_data(pd.concat([df, pd.DataFrame([row])], ignore_index=True))
            st.success(f"✅ Lead creado: {fid}")

    else:  # Editar
        st.subheader("✏️ Editar")
        df = load_data()
        if df.empty:
            st.info("No hay leads."); return
        df["_label"] = "🧑 " + df["id_lead"].astype(str) + " | " + df["nombre/alias"].fillna("") + " " + df["apellidos"].fillna("")
        pick = st.selectbox("Lead", options=df["_label"].tolist())
        sel_id = pick.split(" | ")[0].replace("🧑","").strip()
        rec = df[df["id_lead"].astype(str)==sel_id].iloc[0].to_dict()

        with st.form(f"form_edit_{sel_id}"):
            c1,c2,c3,c4 = st.columns(4)
            nombre = c1.text_input("👤 Nombre / alias", rec.get("nombre/alias",""))
            apellidos = c2.text_input("👥 Apellidos", rec.get("apellidos",""))
            genero = c3.selectbox("⚧️ Género", ["","Femenino","Masculino","No binario","Prefiere no decir"], index=0)
            edad = c4.text_input("🎂 Edad", rec.get("edad",""))
            c5,c6,c7 = st.columns(3)
            celular = c5.text_input("📱 Celular", rec.get("celular",""))
            telefono = c6.text_input("☎️ Teléfono", rec.get("telefono",""))
            correo = c7.text_input("✉️ Correo", rec.get("correo",""))
            interes_vals = [v for v in str_to_list(rec.get("interes_curso(puede sellecionar varios)","")) if v in CAT_CURSOS]
            interes = st.multiselect("📚 Interés en curso(s)", options=CAT_CURSOS, default=interes_vals)
            c8,c9 = st.columns(2)
            como_actual = rec.get("como_enteraste","") or CAT_COMO[0]
            opciones_ed = [como_actual] + [x for x in CAT_COMO if x != como_actual]
            como = c8.selectbox("🧭 ¿Cómo se enteraste?", opciones_ed, index=0)
            if como == "Otro":
                otro = c8.text_input("Especifica otro canal", ""); como = (otro.strip() or como)
            atendido_por_name = st.session_state.user["name"]
            c9.text_input("👨‍💼 Atendido por (se asignará a tu usuario)", value=atendido_por_name, disabled=True)
            c10,c11 = st.columns(2)
            prox_fecha = c10.date_input("📅 Próxima acción", value=parse_date_safe(rec.get("proxima_accion_fecha","")) or today()+timedelta(days=3))
            prox_desc  = c11.text_input("📝 Descripción próxima acción", rec.get("proxima_accion_desc",""))
            ok = st.form_submit_button("Guardar cambios")

        if ok:
            idx = df.index[df["id_lead"].astype(str) == sel_id][0]
            updates = {
                "nombre/alias":nombre,"apellidos":apellidos,"genero":genero,"edad":str(edad).strip(),
                "celular":celular,"telefono":telefono,"correo":correo,
                "interes_curso(puede sellecionar varios)": list_to_str(interes),
                "como_enteraste":como,
                "atendido_por":atendido_por_name,
                "proxima_accion_fecha": prox_fecha.isoformat(),"proxima_accion_desc":prox_desc
            }
            for k,v in updates.items(): df.loc[idx,k]=v
            save_data(df); st.success("💾 Lead actualizado.")

# ---------- Seguimiento ----------
def filter_by_mode(base: pd.DataFrame, mode: str, ref: date | None = None) -> pd.DataFrame:
    if mode == "Hoy": return base[base["_prox"].apply(lambda d: d is not None and d == today())]
    if mode == "Por fecha":
        if not isinstance(ref, date): return base.iloc[0:0].copy()
        return base[base["_prox"].apply(lambda d: d is not None and d == ref)]
    return base  # "Todos"

def page_seguimiento():
    st.title("🎯 Seguimiento")
    st.caption("🟢 Won (Ganado) · 🟡 In progress (En curso) · 🔴 Lost (Perdido)")

    base_all = enrich(load_data())
    if base_all.empty:
        st.info("No hay leads."); return

    cnt = base_all["estado_color"].value_counts()
    tot_md = f"**Totales — 🟢 {cnt.get('🟢',0)} · 🟡 {cnt.get('🟡',0)} · 🔴 {cnt.get('🔴',0)}**"
    _, right = st.columns([3,1])
    with right:
        st.markdown(f"<div style='text-align:right'>{tot_md}</div>", unsafe_allow_html=True)

    vista = st.radio("Vista:", ["Hoy","Por fecha","Todos"], horizontal=True)
    fecha_sel = st.date_input("Selecciona fecha", value=today()) if vista=="Por fecha" else None
    df = filter_by_mode(base_all, vista, fecha_sel)

    # Buscador sencillo para "Todos"
    if vista == "Todos":
        qlist = st.text_input("Filtro rápido (nombre / correo / teléfono):").strip().lower()
        if qlist:
            df = df[df.apply(lambda r: any(
                qlist in str(r.get(k,"")).lower() for k in ["nombre/alias","apellidos","correo","celular","telefono"]
            ), axis=1)]

    left, right = st.columns([1,2], gap="large")
    with left:
        st.subheader("👥 Lista")
        sel = ui_lead_radio(df)
        if sel: set_selected(sel)

    with right:
        st.subheader("⚡ Acción rápida")
        base2 = enrich(load_data())
        ids = base2["id_lead"].astype(str).tolist()
        if st.session_state.selected_lead_id not in ids:
            st.info("Selecciona un lead en la lista."); return
        idx = base2.index[base2["id_lead"].astype(str)==st.session_state.selected_lead_id][0]
        row = base2.loc[idx]

        c1,c2,c3 = st.columns(3)
        with c1:
            st.caption(f"🧑 {row['id_lead']} • {row['nombre/alias']} {row['apellidos']} {row['estado_color']}")
            st.write(f"📱 {row['celular'] or '—'} · ✉️ {row['correo'] or '—'}")
        with c2:
            st.write(f"👨‍💼 Responsable actual: **{st.session_state.user['name']}**")
            st.write(f"📅 Próxima: **{row['proxima_accion_fecha'] or '—'}** · {row['proxima_accion_desc'] or '—'}")
        with c3:
            yc = int(str(row.get("amarillo_contador","0") or 0)); st.metric("Veces en 🟡", yc)
            st.write(f"🔎 Etapa: **{row['funnel_etapas'] or '—'}**")
        sla_badges(row)
        st.markdown("---")

        cA, cB = st.columns([2,1])
        with cA:
            outcome = st.selectbox("Resultado del contacto", CONTACT_OUTCOMES, index=1, key=f"out_{row['id_lead']}")
            nota    = st.text_input("🗒️ Nota para historial", key=f"nota_{row['id_lead']}")
        with cB:
            usuario = st.session_state.user["name"]
            st.text_input("👨‍💼 Atendido por", value=usuario, disabled=True, key=f"user_{row['id_lead']}")

        rule_color, rule_stage, rule_delta, rule_desc = OUTCOME_RULES[outcome]
        preview_next = today() + timedelta(days=rule_delta) if rule_delta>0 else None
        st.caption(f"💡 Sugerencia: 📅 {preview_next.isoformat() if preview_next else '—'} · {rule_desc}")

        etapa_final = rule_stage
        if rule_color == "🟡":
            def fmt(s): d = STAGE_DESC.get(s,""); return f"{s} — {d}" if d else s
            etapa_final = st.selectbox("🧭 Funnel stage (Etapa del embudo, solo 🟡):",
                                       FUNNEL_YELLOW,
                                       index=FUNNEL_YELLOW.index(rule_stage),
                                       format_func=fmt, key=f"stg_{row['id_lead']}")

        cD,cE = st.columns(2)
        with cD:
            manual_date = st.date_input("📅 Próxima acción (opcional)", value=parse_date_safe(row["proxima_accion_fecha"]) or preview_next)
        with cE:
            manual_desc = st.text_input("📝 Descripción (opcional)", value=row["proxima_accion_desc"])

        st.markdown("---")
        if st.button("💾 Guardar cambios", use_container_width=True):
            new_color, _, next_date, next_desc, nota_final = apply_outcome(row, outcome, nota, usuario)
            if new_color == "🟢":
                new_stage = "Won (Ganado)"
            elif new_color == "🔴":
                new_stage = "Lost (Perdido)"
            else:
                new_stage = etapa_final if etapa_final in FUNNEL_YELLOW else "Follow-up (Seguimiento)"

            if manual_date: next_date = manual_date
            if manual_desc and manual_desc.strip(): next_desc = manual_desc.strip()

            base3 = enrich(load_data())
            i3 = base3.index[base3["id_lead"].astype(str)==str(row["id_lead"])][0]
            old = compute_color(base3.loc[i3])
            base3 = add_attention(base3, i3, old, new_color, nota_final, usuario)
            updates = {
                "estado_color":new_color,"funnel_etapas":new_stage,
                "proxima_accion_fecha": next_date.isoformat() if next_date else "",
                "proxima_accion_desc": next_desc or "",
                "fecha_ultimo_contacto": today().isoformat(),
                "atendido_por":usuario
            }
            for k,v in updates.items(): base3.loc[i3,k]=v
            if nota_final:
                obs = str(base3.loc[i3,"observaciones"] or "")
                base3.loc[i3,"observaciones"] = (obs + ("\n" if obs else "") + f"{ts_now()} | {usuario or 'sin usuario'} | {nota_final}")
            save_data(base3); st.success("✅ Seguimiento actualizado.")

        st.markdown("---")
        if st.toggle("👀 Mostrar historial completo del lead", value=False, key=f"h_{row['id_lead']}"):
            info = load_data(); info = info[info["id_lead"].astype(str)==st.session_state.selected_lead_id]
            if not info.empty:
                rf = info.iloc[0]
                ficha = rf[["id_lead","nombre/alias","apellidos","atendido_por","funnel_etapas",
                            "estado_color","total_atenciones","amarillo_contador","fecha_registro","proxima_accion_fecha"]].to_frame().T
                st.subheader("🧾 Ficha del lead"); st.dataframe(ficha, use_container_width=True, height=120)
                st.subheader("📜 Historial de seguimiento")
                dfh = history_df(rf)
                if dfh.empty:
                    st.info("Sin historial.")
                else:
                    st.dataframe(dfh, use_container_width=True, height=520)

# ---------- Dashboard (ES/EN) ----------
def _explode_intereses(df):
    if df.empty: return df.iloc[0:0].copy()
    tmp = df[["id_lead","interes_curso(puede sellecionar varios)"]].copy()
    tmp["interes"] = tmp["interes_curso(puede sellecionar varios)"].apply(lambda s: [x for x in str_to_list(s) if x])
    tmp = tmp.explode("interes")
    return tmp[tmp["interes"].notna() & (tmp["interes"]!="")]

def _bar(df, x, y, color_field=None, domain=None, range_colors=None, title="", h=220):
    enc = dict(x=alt.X(x, sort='-y'), y=alt.Y(y), tooltip=[x, y])
    if color_field:
        enc["color"] = alt.Color(color_field, scale=alt.Scale(domain=domain, range=range_colors), legend=None)
    return alt.Chart(df).mark_bar().encode(**enc).properties(height=h, title=title)

def page_dashboard():
    st.title("📊 Dashboard / Tablero")

    df = enrich(load_data())
    if df.empty:
        st.info("No hay datos.")
        return

    total=len(df)
    won=((df["funnel_etapas"]=="Won (Ganado)") | (df["funnel_etapas"]=="Ganado")).sum()
    lost=((df["funnel_etapas"]=="Lost (Perdido)") | (df["funnel_etapas"]=="Perdido")).sum()
    in_prog= total-won-lost
    hoy = df["_prox"].apply(lambda d:d==today()).sum()
    venc = df["_prox"].apply(lambda d: d is not None and d<today()).sum()
    sinp = df["_prox"].isna().sum()
    prom_att = pd.to_numeric(df["total_atenciones"].replace("", "0")).mean().round(2)

    c1,c2,c3,c4,c5,c6 = st.columns(6)
    c1.metric("👥 Leads (Total)", total)
    c2.metric("✅ Ganados (Won)", won)
    c3.metric("🟡 En curso (In progress)", in_prog)
    c4.metric("🔴 Perdidos (Lost)", lost)
    c5.metric("📅 Vencen hoy (Due today)", hoy)
    c6.metric("⏰ Atrasados (Overdue)", venc)
    st.caption(f"📭 Sin próxima acción (Without next action): {sinp} • 🧮 Promedio de atenciones/lead (Avg. touches/lead): {prom_att}")
    st.markdown("---")

    etapas = df["funnel_etapas"].replace("", "Contacted (Contactado)").replace({
        "Ganado":"Won (Ganado)","Perdido":"Lost (Perdido)","Contactado":"Contacted (Contactado)"
    }).value_counts().rename_axis("stage").reset_index(name="qty")
    dom_all = [e for e in STAGE_COLORS.keys() if e in etapas["stage"].tolist()]
    rng_all = [STAGE_COLORS[k] for k in dom_all]
    ch_etapas = _bar(etapas, "stage:N","qty:Q","stage:N", dom_all, rng_all, "Funnel stages (Etapas del embudo)")
    st.altair_chart(ch_etapas, use_container_width=True)

    amar = df.copy()
    amar["funnel_etapas"] = amar["funnel_etapas"].replace({
        "Ganado":"Won (Ganado)","Perdido":"Lost (Perdido)","Contactado":"Contacted (Contactado)"
    })
    amar = amar[amar["funnel_etapas"].isin(FUNNEL_YELLOW)]
    if not amar.empty:
        etapas_y = amar["funnel_etapas"].value_counts().rename_axis("stage").reset_index(name="qty")
        dom_y = [e for e in FUNNEL_YELLOW if e in etapas_y["stage"].tolist()]
        rng_y = [STAGE_COLORS[k] for k in dom_y]
        ch_y = _bar(etapas_y, "stage:N","qty:Q","stage:N", dom_y, rng_y, "Yellow-state detail (Detalle 🟡)")
        st.altair_chart(ch_y, use_container_width=True)
    st.markdown("---")

    r0,r1 = today()-timedelta(days=30), today()
    df30 = df[(df["_reg"]>=r0) & (df["_reg"]<=r1)].copy()
    a,b,c = st.columns(3)

    reg = df30.groupby("_reg")["id_lead"].count().reset_index()
    a.subheader("🗓️ Leads nuevos (30 días) / New leads (30d)")
    if not reg.empty:
        ch_reg = alt.Chart(reg).mark_line(point=True).encode(x="_reg:T", y="id_lead:Q").properties(height=200)
        a.altair_chart(ch_reg, use_container_width=True)
    else:
        a.info("Sin datos / No data")

    prox = df.dropna(subset=["_prox"]).groupby("_prox")["id_lead"].count().reset_index()
    b.subheader("📅 Próximas acciones / Next actions")
    if not prox.empty:
        ch_prox = _bar(prox,"_prox:T","id_lead:Q", title="")
        b.altair_chart(ch_prox, use_container_width=True)
    else:
        b.info("Sin datos / No data")

    canal = df["como_enteraste"].replace("", "No indicado").value_counts().rename_axis("channel").reset_index(name="qty")
    c.subheader("🧭 Canales de adquisición / Acquisition channels")
    if not canal.empty:
        ch_canal = _bar(canal,"channel:N","qty:Q", title="")
        c.altair_chart(ch_canal, use_container_width=True)
    else:
        c.info("Sin datos / No data")

    st.markdown("---")

    d,e,f = st.columns(3)
    users = (pd.DataFrame({"user": df["atendido_por"].replace("", "Sin asignar"),
                           "touches": pd.to_numeric(df["total_atenciones"].replace("", "0"))})
             .groupby("user", dropna=False)["touches"].sum().sort_values(ascending=False).reset_index())
    d.subheader("👨‍💼 Atenciones por responsable / Touches by owner")
    if not users.empty:
        ch_users = _bar(users,"user:N","touches:Q", title="")
        d.altair_chart(ch_users, use_container_width=True)
    else:
        d.info("Sin datos / No data")

    e.subheader("📈 Conversión semanal / Weekly conversion")
    if not df30.empty:
        conv = df30.assign(week=df30["_reg"].apply(lambda d: pd.to_datetime(d).to_period("W").start_time))
        conv = conv.groupby("week").apply(
            lambda g: ((g["funnel_etapas"]=="Won (Ganado)") | (g["funnel_etapas"]=="Ganado")).sum()/len(g)
        ).reset_index(name="rate")
        ch_conv = alt.Chart(conv).mark_line(point=True).encode(
            x="week:T", y=alt.Y("rate:Q", axis=alt.Axis(format='%'))
        ).properties(height=200)
        e.altair_chart(ch_conv, use_container_width=True)
    else:
        e.info("Sin datos / No recent data")

    inter = _explode_intereses(df)
    f.subheader("📚 Intereses (Top) / Interests (Top)")
    if not inter.empty:
        top = inter["interes"].value_counts().rename_axis("interest").reset_index(name="qty")
        ch_inter = _bar(top, "interest:N", "qty:Q", title="")
        f.altair_chart(ch_inter, use_container_width=True)
    else:
        f.info("Sin datos / No data")

    st.markdown("---")

    t1,t2 = st.columns(2)
    etapas_tbl = etapas.copy(); etapas_tbl["color_hex"] = etapas_tbl["stage"].map(STAGE_COLORS).fillna("#999")
    t1.markdown("**Por etapa (By stage)**"); t1.dataframe(etapas_tbl, use_container_width=True, height=240)
    resp_tbl = df["atendido_por"].replace("","Sin asignar").value_counts().rename_axis("owner").reset_index(name="qty")
    t2.markdown("**Por responsable (By owner)**"); t2.dataframe(resp_tbl, use_container_width=True, height=240)

    t3,t4 = st.columns(2)
    t3.markdown("**Por canal (By channel)**"); t3.dataframe(canal, use_container_width=True, height=240)
    sla_tbl = pd.DataFrame({"Métrica / Metric":["Vencen hoy / Due today","Atrasados / Overdue","Sin próxima acción / No next action"],
                            "Cantidad / Qty":[int(hoy), int(venc), int(sinp)]})
    t4.markdown("**SLA de próximas acciones / Next actions SLA**"); t4.dataframe(sla_tbl, use_container_width=True, height=240)

    st.markdown("**Conversión general / Overall conversion**")
    conv_gen = pd.DataFrame({"Total":[total],"Ganados / Won":[won],"Perdidos / Lost":[lost],"En curso / In progress":[in_prog],
                             "Tasa de conversión / Conversion rate":[round(won/max(total,1),3)]})
    st.dataframe(conv_gen, use_container_width=True, height=120)

# ===================== Login Page (usuario + password) =====================
def page_login():
    st.title("🔐 Inicio de sesión")

    with st.form("login_form", clear_on_submit=False):
        u = st.text_input("Usuario", placeholder="ej. favio")
        p = st.text_input("Contraseña", type="password", placeholder="•••••••")
        ok = st.form_submit_button("Ingresar", use_container_width=True)

    if ok:
        info = try_login(u, p)
        if info:
            st.session_state.user = info
            st.success(f"Bienvenido, {info['name']} ({info['role']})")
            st.rerun()  # actualizado (antes: st.experimental_rerun)
        else:
            st.error("Usuario o contraseña incorrectos.")

# ===================== Router con sesión =====================
ensure_users_csv()
if "user" not in st.session_state:
    page_login()
else:
    with st.sidebar:
        st.markdown(f"**👤 {st.session_state.user['name']}**  \n`{st.session_state.user['role']}`")
        if st.button("Cerrar sesión", use_container_width=True):
            logout()
            st.rerun()  # actualizado (antes: st.experimental_rerun)
        st.markdown("---")
        page = st.radio("Ir a:", ["🧑‍💼 Leads","🎯 Seguimiento","📊 Dashboard / Tablero"], index=0)
        st.caption("CSV: leads.csv • users.csv")

    if page.startswith("🧑‍💼"):
        page_leads()
    elif page.startswith("🎯"):
        page_seguimiento()
    else:
        page_dashboard()
