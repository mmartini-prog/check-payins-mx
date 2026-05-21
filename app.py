import streamlit as st
import pandas as pd
from io import BytesIO
from datetime import datetime
from rules_mx import RULES_MX_DLOCAL, RULES_MX_DEMERGE

st.set_page_config(page_title="Check Payins MX", page_icon="📊", layout="wide")

# ─────────────────────────────────────────────────────────────
# STYLE
# ─────────────────────────────────────────────────────────────

st.markdown("""
<style>
    .stApp { background-color: #05051a; color: #ffffff; }
    .block-container { padding-top: 2rem; padding-left: 2.5rem; padding-right: 2.5rem; }
    section[data-testid="stSidebar"] { background-color: #07071f; border-right: 1px solid #1a1aff; }
    h1, h2, h3 { color: #ffffff !important; font-weight: 800 !important; }
    p, label, span, div { color: #c8d4ff; }

    div[data-testid="metric-container"] {
        background: linear-gradient(135deg, #0a0a2e, #101050);
        border: 1px solid #1a1aff;
        border-radius: 16px;
        padding: 1rem;
        box-shadow: 0 0 18px rgba(26, 26, 255, 0.25);
    }

    div[data-testid="metric-container"] label { color: #a0b4ff !important; }
    div[data-testid="metric-container"] div { color: #ffffff !important; }

    .stButton button, .stDownloadButton button {
        background: linear-gradient(90deg, #1a1aff, #4b5cff);
        color: white;
        border: none;
        border-radius: 12px;
        font-weight: 700;
        padding: 0.7rem 1.4rem;
    }

    .stDataFrame {
        border: 1px solid #1a1aff;
        border-radius: 12px;
        overflow: hidden;
    }

    .stFileUploader {
        background-color: #0a0a2e;
        border: 1px dashed #4b5cff;
        border-radius: 14px;
        padding: 0.8rem;
    }

    .hero {
        background: linear-gradient(135deg, #07071f, #101050);
        border: 1px solid #1a1aff;
        border-radius: 22px;
        padding: 2rem;
        margin-bottom: 2rem;
        box-shadow: 0 0 30px rgba(26, 26, 255, 0.25);
    }

    .hero-title {
        color: #ffffff;
        font-size: 2.4rem;
        font-weight: 900;
        margin-bottom: 0.4rem;
    }

    .hero-subtitle {
        color: #a0b4ff;
        font-size: 1rem;
    }
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="hero">
    <div class="hero-title">Check Payins México</div>
    <div class="hero-subtitle">
        Comparación de movimientos bancarios Kyriba contra estimaciones de Payins.
    </div>
</div>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────
# SIDEBAR
# ─────────────────────────────────────────────────────────────

entity = st.sidebar.selectbox("Entidad", ["Dlocal Mexico", "Demerge Mexico"])

tolerance = st.sidebar.number_input(
    "Tolerancia sin alerta (%)",
    value=10,
    min_value=0,
    max_value=100,
    step=1
)

st.sidebar.markdown("---")
st.sidebar.subheader("Columnas Payins estimados")
st.sidebar.caption("Dejalo vacío para autodetectar columnas.")

col_date = st.sidebar.text_input("Fecha", value="")
col_amount = st.sidebar.text_input("Monto", value="")
col_processor = st.sidebar.text_input("Procesador", value="")

# ─────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────

def get_rules(entity_name):
    return RULES_MX_DLOCAL if entity_name == "Dlocal Mexico" else RULES_MX_DEMERGE


def normalize_text(value):
    return str(value).strip().lower().replace("_", " ").replace("-", " ")


def normalize_account_value(value):
    clean = str(value).strip()
    if clean.endswith(".0"):
        clean = clean[:-2]
    clean = clean.replace(" ", "")
    return clean


def find_column(df, possible_names):
    normalized_cols = {normalize_text(c): c for c in df.columns}

    for name in possible_names:
        n = normalize_text(name)
        if n in normalized_cols:
            return normalized_cols[n]

    for name in possible_names:
        n = normalize_text(name)
        for col_norm, original_col in normalized_cols.items():
            if n in col_norm or col_norm in n:
                return original_col

    return None


def find_header_row(file_bytes, file_name):
    import io

    is_csv = file_name.lower().endswith(".csv")
    buf = io.BytesIO(file_bytes)

    try:
        if is_csv:
            raw = pd.read_csv(buf, header=None, nrows=80, encoding="utf-8-sig")
        else:
            raw = pd.read_excel(buf, header=None, nrows=80)
    except Exception:
        return None

    header_keywords = [
        "transaction date",
        "value date",
        "booking date",
        "date",
        "payment date",
        "account code",
        "account id",
        "description",
        "credit",
        "debit",
        "amount",
        "total local amount",
        "total usd amount",
        "name",
        "processor",
        "code",
        "complementary info",
    ]

    best_row = None
    best_score = 0

    for i, row in raw.iterrows():
        row_text = " | ".join([normalize_text(v) for v in row.values])
        score = sum(1 for kw in header_keywords if kw in row_text)

        if score > best_score:
            best_score = score
            best_row = i

    return best_row if best_score >= 2 else None


def clean_amount(series):
    return pd.to_numeric(
        series.astype(str)
        .str.replace(",", "", regex=False)
        .str.replace("$", "", regex=False)
        .str.replace("MXN", "", regex=False)
        .str.replace("USD", "", regex=False)
        .str.replace("(", "-", regex=False)
        .str.replace(")", "", regex=False)
        .str.strip(),
        errors="coerce"
    ).fillna(0)


# ─────────────────────────────────────────────────────────────
# PROCESSORS
# ─────────────────────────────────────────────────────────────

def get_processor_mx(text_to_match, account_id=None, account_code=None, entity_name="Dlocal Mexico"):
    if not isinstance(text_to_match, str):
        return None

    text_clean = text_to_match.upper()
    account_id_clean = normalize_account_value(account_id)
    account_code_clean = normalize_account_value(account_code).upper()

    for keyword, processor, expected_account_id, expected_account_code in get_rules(entity_name):
        keyword_clean = str(keyword).replace('"', '').strip().upper()
        expected_account_id = normalize_account_value(expected_account_id)
        expected_account_code = normalize_account_value(expected_account_code).upper()

        keyword_matches = keyword_clean and keyword_clean in text_clean
        account_matches = (
            expected_account_id in account_id_clean
            or expected_account_code in account_code_clean
        )

        if keyword_matches and account_matches:
            return processor

    return None


def normalize_processor(name):
    if not isinstance(name, str):
        return None

    clean = normalize_text(name)

    processor_map = {
        # BANORTE
        "banorte": "Banorte",
        "banco banorte": "Banorte",
        "banorte mx": "Banorte",
        "dlocal banorte": "Banorte",
        "demerge banorte": "Banorte",

        # EVO
        "evo mpgs": "EVO MPGs",
        "evopaymx": "EVO MPGs",
        "evo payments": "EVO MPGs",
        "evo": "EVO MPGs",

        # BANREGIO
        "hey banregio": "Hey Banregio",
        "banregio": "Hey Banregio",
        "banco banregio": "Hey Banregio",

        # MERCADOPAGO
        "mercadopago": "Mercadopago",
        "mercado pago": "Mercadopago",
        "mp": "Mercadopago",
        "mercado pago mx": "Mercadopago",
        "mercado pago referencia": "Mercadopago",

        # OPENPAY
        "openpay": "Openpay",
        "dlocal openpay": "Openpay",
        "openpay mx": "Openpay",
        "openpay spei": "Openpay",
        "openpay_spei": "Openpay",

        # PAYNET
        "openpay paynet": "Openpay_paynet",
        "openpay_paynet": "Openpay_paynet",
        "paynet": "Openpay_paynet",
        "paynet mx": "Openpay_paynet",

        # OXXO
        "oxxo pay": "OXXO Pay",
        "oxxopay": "OXXO Pay",
        "oxxo": "OXXO Pay",
        "oxxo mx": "OXXO Pay",

        # ARCUS
        "arcus": "Arcus",
        "arcus mx": "Arcus",
        "dlocal arcus": "Arcus",

        # KUSHKI
        "kushki": "Kushki",
        "kushki mx": "Kushki",
        "dlocal kushki": "Kushki",
    }

    return processor_map.get(clean, str(name).strip())


# ─────────────────────────────────────────────────────────────
# PARSE KYRIBA
# ─────────────────────────────────────────────────────────────

@st.cache_data(show_spinner=False)
def parse_kyriba(file_bytes, file_name, entity_name):
    try:
        import io

        is_csv = file_name.lower().endswith(".csv")
        header_row = find_header_row(file_bytes, file_name)

        if header_row is None:
            st.error(f"No encontré encabezados Kyriba en: {file_name}")
            return pd.DataFrame()

        buf = io.BytesIO(file_bytes)

        if is_csv:
            df = pd.read_csv(
                buf,
                header=header_row,
                dtype=str,
                encoding="utf-8-sig"
            )
        else:
            df = pd.read_excel(
                buf,
                header=header_row,
                dtype=str
            )

        df.columns = [str(c).strip() for c in df.columns]
        df = df.dropna(how="all")

        account_code_col = find_column(df, ["Account code", "Account Code", "Account", "Cuenta"])
        account_id_col = find_column(df, ["Account ID", "Account Id", "Bank account", "Account number", "Número de cuenta"])
        date_col = find_column(df, ["Transaction date", "Value date", "Booking date", "Date", "Fecha"])
        description_col = find_column(df, ["Description", "Transaction description", "Concept", "Concepto", "Descripción"])
        complementary_col = find_column(df, ["Complementary info", "Complementary Info", "Additional info", "Reference", "Referencia"])
        credit_col = find_column(df, ["Credit", "Credit (MXN)", "Credit MXN", "Credit amount", "Deposit", "Crédito"])
        amount_col = find_column(df, ["Amount", "Amount (MXN)", "Transaction amount", "Importe"])
        debit_col = find_column(df, ["Debit", "Debit (MXN)", "Debit MXN", "Débito"])

        missing = []
        if not date_col:
            missing.append("Transaction date / Date")
        if not description_col:
            missing.append("Description")
        if not credit_col and not amount_col:
            missing.append("Credit / Amount")

        if missing:
            st.error(f"Faltan columnas en Kyriba {file_name}: {missing}")
            st.write("Columnas disponibles:", list(df.columns))
            return pd.DataFrame()

        work = pd.DataFrame()
        work["Account code"] = df[account_code_col] if account_code_col else ""
        work["Account ID"] = df[account_id_col] if account_id_col else ""
        work["Transaction date"] = df[date_col]
        work["Description"] = df[description_col]
        work["Complementary info"] = df[complementary_col] if complementary_col else ""

        if credit_col:
            work["Credit"] = clean_amount(df[credit_col])
        else:
            work["Credit"] = clean_amount(df[amount_col])

        if debit_col:
            work["Debit"] = clean_amount(df[debit_col])
        else:
            work["Debit"] = 0

        work = work[
            ~work["Description"].isin([
                "Opening balance",
                "Closing balance",
                "Description"
            ])
        ]

        work["Transaction date"] = pd.to_datetime(
            work["Transaction date"],
            errors="coerce"
        )

        work = work[work["Transaction date"].notna()]

        work["Text to match"] = (
            work["Description"].astype(str)
            + " "
            + work["Complementary info"].astype(str)
        )

        work["Processor"] = work.apply(
            lambda r: get_processor_mx(
                text_to_match=r["Text to match"],
                account_id=r["Account ID"],
                account_code=r["Account code"],
                entity_name=entity_name,
            ),
            axis=1,
        )

        # Conservamos también movimientos no identificados para diagnóstico.
        # Se filtran más abajo, justo antes del análisis.
        work = work[work["Credit"] > 0].copy()

        work["Day"] = work["Transaction date"].dt.strftime("%d/%m/%Y")
        work["Source file"] = file_name

        return work

    except Exception as e:
        st.error(f"Error leyendo Kyriba {file_name}: {e}")
        return pd.DataFrame()


# ─────────────────────────────────────────────────────────────
# PARSE PAYINS
# ─────────────────────────────────────────────────────────────

@st.cache_data(show_spinner=False)
def parse_payins(file_bytes, file_name, col_date, col_amount, col_processor):
    try:
        import io

        is_csv = file_name.lower().endswith(".csv")
        header_row = find_header_row(file_bytes, file_name)

        # Fallback para exports de Accounting Payins donde el header viene arriba
        if header_row is None:
            header_row = 0

        buf = io.BytesIO(file_bytes)

        if is_csv:
            df = pd.read_csv(
                buf,
                header=header_row,
                encoding="utf-8-sig"
            )
        else:
            df = pd.read_excel(
                buf,
                header=header_row
            )

        df.columns = [str(c).strip() for c in df.columns]
        df = df.dropna(how="all")

        if col_date:
            date_col = col_date if col_date in df.columns else find_column(df, [col_date])
        else:
            date_col = find_column(df, [
                "Payment Date",
                "Approved Date",
                "Payins Creation Date",
                "Creation Date",
                "Created Date",
                "Date",
                "Day",
                "Fecha"
            ])

        if col_amount:
            amount_col = col_amount if col_amount in df.columns else find_column(df, [col_amount])
        else:
            amount_col = find_column(df, [
                "Total Local Amount",
                "Approved Amount Local",
                "Approved amount local",
                "Local Amount",
                "LC Amount",
                "$ Approved Amount Local",
                "Amount Local",
                "Amount",
                "Approved Amount",
                "Monto"
            ])

        if col_processor:
            processor_col = col_processor if col_processor in df.columns else find_column(df, [col_processor])
        else:
            processor_col = find_column(df, [
                "Name",
                "Procesador",
                "Processor",
                "Payins Processor",
                "Payment Processor",
                "Acquirer",
                "Gateway"
            ])

        missing = []
        if not date_col:
            missing.append("Fecha")
        if not amount_col:
            missing.append("Monto")
        if not processor_col:
            missing.append("Procesador")

        if missing:
            st.error(f"Faltan columnas en Payins estimados {file_name}: {missing}")
            st.write("Columnas disponibles:", list(df.columns))
            return pd.DataFrame()

        work = pd.DataFrame()
        work["Date"] = df[date_col]
        work["Amount"] = clean_amount(df[amount_col])
        work["Processor"] = df[processor_col].apply(normalize_processor)

        code_col = find_column(df, ["Code", "Payment Method Code", "Payment Method", "PM Code"])
        work["Payment Method Code"] = df[code_col] if code_col else ""

        country_col = find_column(df, ["Country", "Pais", "País"])
        work["Country"] = df[country_col] if country_col else ""

        work["Date"] = pd.to_datetime(work["Date"], errors="coerce")
        work = work[work["Date"].notna()]
        work = work[work["Processor"].notna()]
        work = work[work["Amount"] != 0]

        work["Day"] = work["Date"].dt.strftime("%d/%m/%Y")
        work["Source file"] = file_name

        return work

    except Exception as e:
        st.error(f"Error leyendo Payins estimados {file_name}: {e}")
        return pd.DataFrame()


# ─────────────────────────────────────────────────────────────
# EXPORT
# ─────────────────────────────────────────────────────────────

def build_excel(summary_df, detail_df, kyriba_raw_df, payins_raw_df):
    output = BytesIO()

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        summary_df.to_excel(writer, index=False, sheet_name="Resumen")
        detail_df.to_excel(writer, index=False, sheet_name="Detalle")
        kyriba_raw_df.to_excel(writer, index=False, sheet_name="Kyriba combinado")
        payins_raw_df.to_excel(writer, index=False, sheet_name="Payins combinado")

    output.seek(0)
    return output


# ─────────────────────────────────────────────────────────────
# UPLOADERS
# ─────────────────────────────────────────────────────────────

col1, col2 = st.columns(2)

with col1:
    kyriba_files = st.file_uploader(
        "🏦 Archivos Kyriba / Banco",
        type=["xlsx", "xls", "csv"],
        accept_multiple_files=True
    )

with col2:
    payins_files = st.file_uploader(
        "📋 Archivos estimaciones Payins",
        type=["xlsx", "xls", "csv"],
        accept_multiple_files=True
    )


# ─────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────

if kyriba_files and payins_files:
    kyriba_dfs = []

    with st.spinner("Leyendo archivos Kyriba..."):
        for file in kyriba_files:
            file_bytes = file.read()
            temp_df = parse_kyriba(file_bytes, file.name, entity)

            if not temp_df.empty:
                kyriba_dfs.append(temp_df)

    if not kyriba_dfs:
        st.error("No pude leer ningún archivo Kyriba válido.")
        st.stop()

    kyriba_df = pd.concat(kyriba_dfs, ignore_index=True)
    st.success(f"Archivos Kyriba combinados: {len(kyriba_dfs)}")

    with st.expander("🔎 Movimientos Kyriba no identificados"):
        unmapped = kyriba_df[kyriba_df["Processor"].isna()].copy()
        st.write(f"Movimientos no identificados: {len(unmapped)}")
        if not unmapped.empty:
            cols = [
                "Transaction date", "Account code", "Account ID",
                "Description", "Complementary info", "Credit", "Source file"
            ]
            existing_cols = [c for c in cols if c in unmapped.columns]
            st.dataframe(
                unmapped[existing_cols].sort_values("Credit", ascending=False),
                use_container_width=True,
                hide_index=True
            )

    payins_dfs = []

    with st.spinner("Leyendo archivos Payins..."):
        for file in payins_files:
            file_bytes = file.read()
            temp_df = parse_payins(file_bytes, file.name, col_date, col_amount, col_processor)

            if not temp_df.empty:
                payins_dfs.append(temp_df)

    if not payins_dfs:
        st.error("No pude leer ningún archivo Payins válido.")
        st.stop()

    payins_df = pd.concat(payins_dfs, ignore_index=True)
    st.success(f"Archivos Payins combinados: {len(payins_dfs)}")

    # ── DEBUG PROCESSORS ─────────────────────────────────────

    with st.expander("🔎 Debug processors detectados"):
        st.write("Processors Kyriba:", sorted(kyriba_df["Processor"].dropna().unique()))
        st.write("Processors Payins:", sorted(payins_df["Processor"].dropna().unique()))

    # ── FILTRO DE FECHAS COMÚN ─────────────────────────────

    kyriba_min = kyriba_df["Transaction date"].min().date()
    kyriba_max = kyriba_df["Transaction date"].max().date()

    payins_min = payins_df["Date"].min().date()
    payins_max = payins_df["Date"].max().date()

    st.warning(
        f"Rango Kyriba: {kyriba_min} al {kyriba_max} | "
        f"Rango Payins: {payins_min} al {payins_max}"
    )

    default_start = max(kyriba_min, payins_min)
    default_end = min(kyriba_max, payins_max)

    if default_start > default_end:
        st.error("No hay fechas en común entre Kyriba y Payins. Revisá los archivos cargados.")
        st.stop()

    date_range = st.date_input(
        "Seleccioná el rango de fechas a comparar",
        value=(default_start, default_end),
        min_value=min(kyriba_min, payins_min),
        max_value=max(kyriba_max, payins_max)
    )

    if len(date_range) != 2:
        st.stop()

    start_date, end_date = date_range

    kyriba_df = kyriba_df[
        (kyriba_df["Transaction date"].dt.date >= start_date)
        & (kyriba_df["Transaction date"].dt.date <= end_date)
    ]

    payins_df = payins_df[
        (payins_df["Date"].dt.date >= start_date)
        & (payins_df["Date"].dt.date <= end_date)
    ]

    st.info(f"Comparando únicamente: {start_date} al {end_date}")

    # Para el análisis usamos solo movimientos Kyriba identificados.
    kyriba_df = kyriba_df[kyriba_df["Processor"].notna()].copy()

    # ── FILTRAR PAYINS SOLO A PROCESADORES QUE EXISTEN EN KYRIBA ──

    kyriba_processors = set(kyriba_df["Processor"].dropna().unique())
    payins_processors_original = set(payins_df["Processor"].dropna().unique())

    payins_excluded = sorted(payins_processors_original - kyriba_processors)

    with st.expander("🔎 Procesadores Payins excluidos por no existir en Kyriba"):
        if payins_excluded:
            st.write(payins_excluded)
        else:
            st.write("No se excluyó ningún procesador.")

    payins_df = payins_df[
        payins_df["Processor"].isin(kyriba_processors)
    ].copy()

    processors = sorted(kyriba_processors)

    selected_processors = st.multiselect(
        "Procesadores a analizar",
        options=processors,
        default=processors
    )

    if st.button("▶ Analizar conciliación", type="primary"):
        kyriba_filtered = kyriba_df[kyriba_df["Processor"].isin(selected_processors)]
        payins_filtered = payins_df[payins_df["Processor"].isin(selected_processors)]

        banco_grouped = (
            kyriba_filtered
            .groupby(["Processor", "Day"], as_index=False)["Credit"]
            .sum()
            .rename(columns={"Credit": "Banco MXN"})
        )

        payins_grouped = (
            payins_filtered
            .groupby(["Processor", "Day"], as_index=False)["Amount"]
            .sum()
            .rename(columns={"Amount": "Payins estimados MXN"})
        )

        detail = pd.merge(
            banco_grouped,
            payins_grouped,
            on=["Processor", "Day"],
            how="outer"
        ).fillna(0)

        detail["Diferencia MXN"] = detail["Banco MXN"] - detail["Payins estimados MXN"]

        detail["Dif %"] = detail.apply(
            lambda r: (r["Diferencia MXN"] / r["Payins estimados MXN"] * 100)
            if r["Payins estimados MXN"] != 0 else 0,
            axis=1
        )

        detail["Estado"] = detail.apply(
            lambda r: "⚠️ Sin dato Payins"
            if r["Payins estimados MXN"] == 0
            else (
                "✅ OK"
                if abs(r["Dif %"]) <= tolerance
                else ("🔴 Banco menor" if r["Diferencia MXN"] < 0 else "🟡 Banco mayor")
            ),
            axis=1
        )

        summary = (
            detail
            .groupby("Processor", as_index=False)
            .agg({
                "Banco MXN": "sum",
                "Payins estimados MXN": "sum",
                "Diferencia MXN": "sum"
            })
        )

        summary["Dif %"] = summary.apply(
            lambda r: (r["Diferencia MXN"] / r["Payins estimados MXN"] * 100)
            if r["Payins estimados MXN"] != 0 else 0,
            axis=1
        )

        summary["Estado"] = summary.apply(
            lambda r: "⚠️ Sin dato Payins"
            if r["Payins estimados MXN"] == 0
            else (
                "✅ OK"
                if abs(r["Dif %"]) <= tolerance
                else ("🔴 Banco menor" if r["Diferencia MXN"] < 0 else "🟡 Banco mayor")
            ),
            axis=1
        )

        st.subheader("📈 KPIs")

        total_banco = summary["Banco MXN"].sum()
        total_payins = summary["Payins estimados MXN"].sum()
        total_diff = total_banco - total_payins
        total_pct = total_diff / total_payins * 100 if total_payins else 0

        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Banco MXN", f"{total_banco:,.0f}")
        k2.metric("Payins estimados MXN", f"{total_payins:,.0f}")
        k3.metric("Diferencia MXN", f"{total_diff:,.0f}")
        k4.metric("Dif. %", f"{total_pct:.1f}%")

        st.subheader("📊 Resumen por procesador")
        st.dataframe(summary, use_container_width=True, hide_index=True)

        st.subheader("📅 Detalle por día")
        st.dataframe(detail, use_container_width=True, hide_index=True)

        with st.expander("Ver Kyriba combinado"):
            st.dataframe(kyriba_df, use_container_width=True, hide_index=True)

        with st.expander("Ver Payins combinados"):
            st.dataframe(payins_df, use_container_width=True, hide_index=True)

        excel_file = build_excel(summary, detail, kyriba_df, payins_df)

        st.download_button(
            label="⬇️ Descargar Excel conciliación",
            data=excel_file,
            file_name=f"check_payins_mx_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

else:
    st.info("Subí uno o más archivos Kyriba y uno o más archivos de estimaciones Payins.")
