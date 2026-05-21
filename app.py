
import streamlit as st
import pandas as pd
from io import BytesIO
from datetime import datetime
import re

try:
    from rules_mx import RULES_MX_DLOCAL, RULES_MX_DEMERGE
except Exception:
    RULES_MX_DLOCAL = []
    RULES_MX_DEMERGE = []

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

currency_filter = st.sidebar.selectbox(
    "Moneda Kyriba a comparar",
    ["MXN", "USD", "Todas"],
    index=0
)

use_account_fallback = st.sidebar.checkbox(
    "Si no hay regla, usar banco/cuenta Kyriba como processor",
    value=True
)

st.sidebar.markdown("---")
st.sidebar.subheader("Columnas Payins estimados")
st.sidebar.caption("Dejalo vacío para autodetectar columnas.")

col_date = st.sidebar.text_input("Fecha", value="")
col_amount = st.sidebar.text_input("Monto", value="")
col_processor = st.sidebar.text_input("Procesador", value="")
col_agent = st.sidebar.text_input("Entidad / Collection Agent", value="")

st.sidebar.markdown("---")
st.sidebar.subheader("Mapping manual Kyriba")
st.sidebar.caption("Formato: CODIGO=Processor, una línea por cuenta. Esto pisa reglas y autodetección.")
manual_mapping_text = st.sidebar.text_area(
    "Cuenta Kyriba → Processor",
    value=(
        "AA639=Banco Santander\n"
        "AB184=STP\n"
        "AB072=Banorte\n"
        "AA566=CITI\n"
        "AA640=Banco Santander\n"
        "AB279=Banco Santander"
    ),
    height=150
)

# ─────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────

def get_rules(entity_name):
    return RULES_MX_DLOCAL if entity_name == "Dlocal Mexico" else RULES_MX_DEMERGE


def normalize_text(value):
    return str(value).strip().lower().replace("_", " ").replace("-", " ")


def normalize_key(value):
    return normalize_text(value).replace(".", "").replace(",", "").replace("/", " ").strip()


def parse_manual_mapping(text):
    mapping = {}
    for line in str(text).splitlines():
        line = line.strip()
        if not line or "=" not in line:
            continue
        k, v = line.split("=", 1)
        if k.strip() and v.strip():
            mapping[k.strip().upper()] = normalize_processor(v.strip())
    return mapping


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

    if is_csv:
        raw = pd.read_csv(buf, header=None, nrows=100, encoding="utf-8-sig")
    else:
        raw = pd.read_excel(buf, header=None, nrows=100)

    header_keywords = [
        "transaction date",
        "value date",
        "booking date",
        "date",
        "payment date",
        "accounting date",
        "account code",
        "account id",
        "description",
        "credit",
        "debit",
        "amount",
        "total local amount",
        "amount approved",
        "name",
        "processor",
        "processor name",
        "collection agent",
        "complementary info",
        "code",
    ]

    best_row = None
    best_score = 0

    for i, row in raw.iterrows():
        row_text = " | ".join([normalize_text(v) for v in row.values])
        score = sum(1 for kw in header_keywords if kw in row_text)

        if score > best_score:
            best_score = score
            best_row = i

    if best_score >= 2:
        return best_row

    return None


def read_raw_preview(file_bytes, file_name, nrows=5):
    import io
    is_csv = file_name.lower().endswith(".csv")
    buf = io.BytesIO(file_bytes)
    if is_csv:
        return pd.read_csv(buf, header=None, nrows=nrows, encoding="utf-8-sig")
    return pd.read_excel(buf, header=None, nrows=nrows)


def extract_account_bank_from_preview(preview):
    """Lee línea tipo: Account: AA639 Santander - MX - MX03 - M - 655... - MXN"""
    try:
        joined = " ".join(str(x) for x in preview.astype(str).values.flatten())
        match = re.search(r"Account:\s*([A-Z0-9]+)\s+([^-]+)-", joined, flags=re.I)
        if match:
            code = match.group(1).strip().upper()
            bank = match.group(2).strip()
            return code, normalize_processor(bank)
    except Exception:
        pass
    return None, None


def clean_amount(series):
    cleaned = (
        series.astype(str)
        .str.replace(",", "", regex=False)
        .str.replace("$", "", regex=False)
        .str.replace("MXN", "", regex=False)
        .str.replace("USD", "", regex=False)
        .str.replace("(", "-", regex=False)
        .str.replace(")", "", regex=False)
        .str.strip()
    )
    return pd.to_numeric(cleaned, errors="coerce").fillna(0)


def get_credit_col_and_currency(df):
    # Priorizar MXN si existe, luego USD, luego Credit genérico
    for c in df.columns:
        cn = normalize_text(c)
        if "credit" in cn and "mxn" in cn:
            return c, "MXN"
    for c in df.columns:
        cn = normalize_text(c)
        if "credit" in cn and "usd" in cn:
            return c, "USD"
    for c in df.columns:
        cn = normalize_text(c)
        if "credit" in cn or "deposit" in cn:
            return c, ""
    return None, ""


def get_debit_col(df):
    for c in df.columns:
        cn = normalize_text(c)
        if "debit" in cn:
            return c
    return None


# ─────────────────────────────────────────────────────────────
# PROCESSORS
# ─────────────────────────────────────────────────────────────

def normalize_processor(name):
    if not isinstance(name, str):
        return None

    clean = normalize_key(name)

    processor_map = {
        # bancos / processors principales
        "banorte": "Banorte",
        "banco banorte": "Banorte",
        "banorte mx": "Banorte",
        "dlocal banorte": "Banorte",
        "demerge banorte": "Banorte",

        "banco bancomer": "Banco Bancomer",
        "bancomer": "Banco Bancomer",
        "bbva": "Banco Bancomer",

        "banco santander": "Banco Santander",
        "santander": "Banco Santander",
        "santander mx": "Banco Santander",

        "citi": "CITI",
        "citibank": "CITI",

        "stp": "STP",

        "evo mpgs": "EVO MPGs",
        "evopaymx": "EVO MPGs",
        "evo payments": "EVO MPGs",
        "evo": "EVO MPGs",

        "hey banregio": "Hey Banregio",
        "banregio": "Hey Banregio",
        "banco banregio": "Hey Banregio",

        "mercadopago": "Mercadopago",
        "mercado pago": "Mercadopago",
        "mp": "Mercadopago",
        "mercado pago mx": "Mercadopago",
        "mercado pago referencia": "Mercadopago",

        "openpay": "Openpay",
        "dlocal openpay": "Openpay",
        "openpay mx": "Openpay",
        "openpay spei": "Openpay",
        "openpay_spei": "Openpay",

        "openpay paynet": "Openpay_paynet",
        "openpay_paynet": "Openpay_paynet",
        "paynet": "Openpay_paynet",
        "paynet mx": "Openpay_paynet",

        "oxxo pay": "OXXO Pay",
        "oxxopay": "OXXO Pay",
        "oxxo": "OXXO Pay",
        "oxxo mx": "OXXO Pay",

        "arcus": "Arcus",
        "arcus mx": "Arcus",
        "dlocal arcus": "Arcus",

        "kushki": "Kushki",
        "kushki card present": "Kushki Card Present",

        "worldpay mx": "Worldpay MX",
        "worldpay": "Worldpay MX",

        "kueski": "Kueski",
        "conekta": "Conekta",
        "topps giftcard": "Topps GiftCard",
        "datalogic": "Datalogic",
        "didi bnpl": "Didi BNPL",
        "affipay": "Affipay",
        "astropaycard": "Astropaycard",
        "bac credomatic international pa": "BAC Credomatic International PA",
    }

    return processor_map.get(clean, str(name).strip())


def get_processor_mx(text_to_match, account_id=None, account_code=None, entity_name="Dlocal Mexico"):
    if not isinstance(text_to_match, str):
        return None

    text_clean = text_to_match.upper()
    account_id_clean = str(account_id).strip()
    account_code_clean = str(account_code).strip().upper()

    for keyword, processor, expected_account_id, expected_account_code in get_rules(entity_name):
        if keyword.upper() in text_clean:
            if (
                str(expected_account_id).strip() == account_id_clean
                or str(expected_account_code).strip().upper() == account_code_clean
                or not expected_account_id
                or not expected_account_code
            ):
                return normalize_processor(processor)

    return None


def infer_processor_from_kyriba_row(row, manual_mapping, account_bank=None):
    code = str(row.get("Account code", "")).strip().upper()
    if code in manual_mapping:
        return manual_mapping[code]

    processor = get_processor_mx(
        text_to_match=row.get("Text to match", ""),
        account_id=row.get("Account ID", ""),
        account_code=code,
        entity_name=entity,
    )
    if processor:
        return processor

    if use_account_fallback:
        if account_bank:
            return account_bank
        return normalize_processor(code)

    return None


# ─────────────────────────────────────────────────────────────
# PARSE KYRIBA
# ─────────────────────────────────────────────────────────────

@st.cache_data(show_spinner=False)
def parse_kyriba(file_bytes, file_name, entity_name, manual_mapping_text, currency_filter, use_fallback):
    try:
        import io

        manual_mapping = parse_manual_mapping(manual_mapping_text)
        is_csv = file_name.lower().endswith(".csv")
        preview = read_raw_preview(file_bytes, file_name, nrows=5)
        _, account_bank = extract_account_bank_from_preview(preview)

        header_row = find_header_row(file_bytes, file_name)

        if header_row is None:
            st.error(f"No encontré encabezados Kyriba en: {file_name}")
            return pd.DataFrame()

        buf = io.BytesIO(file_bytes)

        if is_csv:
            df = pd.read_csv(buf, header=header_row, dtype=str, encoding="utf-8-sig")
        else:
            df = pd.read_excel(buf, header=header_row, dtype=str)

        df.columns = [str(c).strip() for c in df.columns]
        df = df.dropna(how="all")

        account_code_col = find_column(df, ["Account code", "Account Code", "Account"])
        account_id_col = find_column(df, ["Account ID", "Account Id", "Bank account", "Account number"])
        date_col = find_column(df, ["Transaction date", "Value date", "Booking date", "Date", "Fecha"])
        description_col = find_column(df, ["Description", "Transaction description", "Concept", "Concepto"])
        complementary_col = find_column(df, ["Complementary info", "Complementary Info", "Additional info", "Reference"])
        credit_col, detected_currency = get_credit_col_and_currency(df)
        amount_col = find_column(df, ["Amount", "Amount (MXN)", "Transaction amount", "Importe"])
        debit_col = get_debit_col(df)

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

        if currency_filter != "Todas" and detected_currency and detected_currency != currency_filter:
            # Archivo USD cuando se está conciliando MXN, etc.
            return pd.DataFrame()

        work = pd.DataFrame()
        work["Account code"] = df[account_code_col] if account_code_col else ""
        work["Account ID"] = df[account_id_col] if account_id_col else ""
        work["Transaction date"] = df[date_col]
        work["Description"] = df[description_col]
        work["Complementary info"] = df[complementary_col] if complementary_col else ""
        work["Currency"] = detected_currency or currency_filter
        work["Account bank"] = account_bank or ""

        if credit_col:
            work["Credit"] = clean_amount(df[credit_col])
        else:
            work["Credit"] = clean_amount(df[amount_col])

        if debit_col:
            work["Debit"] = clean_amount(df[debit_col])
        else:
            work["Debit"] = 0

        work = work[
            ~work["Description"].astype(str).isin([
                "Opening balance",
                "Closing balance",
                "Description"
            ])
        ]

        work["Transaction date"] = pd.to_datetime(work["Transaction date"], errors="coerce")
        work = work[work["Transaction date"].notna()]

        work["Text to match"] = (
            work["Description"].astype(str)
            + " "
            + work["Complementary info"].astype(str)
        )

        # Solo créditos positivos para comparar depósitos/entradas
        work = work[work["Credit"] > 0].copy()

        # Excluir intereses/saldos si entran como crédito muy chico o balance
        exclude_patterns = [
            "OPENING BALANCE",
            "CLOSING BALANCE",
            "ABO POR INTERESES",
            "INTERESES DEL PERIODO",
        ]
        mask_excl = work["Text to match"].astype(str).str.upper().apply(
            lambda x: any(p in x for p in exclude_patterns)
        )
        work = work[~mask_excl].copy()

        # Processor: manual mapping > regla > banco de cuenta
        work["Processor"] = work.apply(
            lambda r: infer_processor_from_kyriba_row(r, manual_mapping, account_bank=account_bank if use_fallback else None),
            axis=1,
        )

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
def parse_payins(file_bytes, file_name, col_date, col_amount, col_processor, col_agent, entity_name):
    try:
        import io

        is_csv = file_name.lower().endswith(".csv")
        header_row = find_header_row(file_bytes, file_name)

        if header_row is None:
            header_row = 0

        buf = io.BytesIO(file_bytes)

        if is_csv:
            df = pd.read_csv(buf, header=header_row, encoding="utf-8-sig")
        else:
            df = pd.read_excel(buf, header=header_row)

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
                "Accounting Date",
                "Date",
                "Day",
                "Fecha"
            ])

        if col_amount:
            amount_col = col_amount if col_amount in df.columns else find_column(df, [col_amount])
        else:
            amount_col = find_column(df, [
                "PI | Amount Approved | LC",
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
                "Processor Name",
                "Name",
                "Procesador",
                "Processor",
                "Payins Processor",
                "Payment Processor",
                "Acquirer",
                "Gateway"
            ])

        if col_agent:
            agent_col = col_agent if col_agent in df.columns else find_column(df, [col_agent])
        else:
            agent_col = find_column(df, [
                "Collection Agent",
                "Agent",
                "Legal Entity",
                "Entity",
                "Company",
                "Merchant"
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

        if agent_col:
            work["Collection Agent"] = df[agent_col].astype(str).str.strip()
            # Si el archivo trae entidad, filtrar según entidad elegida
            expected_agent = entity_name
            work = work[work["Collection Agent"].str.lower() == expected_agent.lower()].copy()
        else:
            work["Collection Agent"] = ""

        code_col = find_column(df, ["Code", "Payment Method Code", "Payment Method", "PM Code"])
        work["Payment Method Code"] = df[code_col] if code_col else ""

        country_col = find_column(df, ["Country", "Country Transaction", "Pais", "País"])
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

def build_excel(summary_df, detail_df, kyriba_raw_df, payins_raw_df, unmapped_df, excluded_df):
    output = BytesIO()

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        summary_df.to_excel(writer, index=False, sheet_name="Resumen")
        detail_df.to_excel(writer, index=False, sheet_name="Detalle")
        kyriba_raw_df.to_excel(writer, index=False, sheet_name="Kyriba combinado")
        payins_raw_df.to_excel(writer, index=False, sheet_name="Payins combinado")
        unmapped_df.to_excel(writer, index=False, sheet_name="Kyriba sin processor")
        excluded_df.to_excel(writer, index=False, sheet_name="Payins excluidos")

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
    skipped_kyriba = []

    with st.spinner("Leyendo archivos Kyriba..."):
        for file in kyriba_files:
            file_bytes = file.read()
            temp_df = parse_kyriba(
                file_bytes,
                file.name,
                entity,
                manual_mapping_text,
                currency_filter,
                use_account_fallback
            )

            if not temp_df.empty:
                kyriba_dfs.append(temp_df)
            else:
                skipped_kyriba.append(file.name)

    if not kyriba_dfs:
        st.error("No pude leer ningún archivo Kyriba válido para la moneda seleccionada.")
        if skipped_kyriba:
            st.write("Archivos omitidos:", skipped_kyriba)
        st.stop()

    kyriba_df = pd.concat(kyriba_dfs, ignore_index=True)
    st.success(f"Archivos Kyriba combinados: {len(kyriba_dfs)}")

    if skipped_kyriba:
        with st.expander("Archivos Kyriba omitidos"):
            st.write(skipped_kyriba)

    payins_dfs = []

    with st.spinner("Leyendo archivos Payins..."):
        for file in payins_files:
            file_bytes = file.read()
            temp_df = parse_payins(
                file_bytes,
                file.name,
                col_date,
                col_amount,
                col_processor,
                col_agent,
                entity
            )

            if not temp_df.empty:
                payins_dfs.append(temp_df)

    if not payins_dfs:
        st.error("No pude leer ningún archivo Payins válido.")
        st.stop()

    payins_df = pd.concat(payins_dfs, ignore_index=True)
    st.success(f"Archivos Payins combinados: {len(payins_dfs)}")

    # Debug e identificación
    unmapped_kyriba = kyriba_df[kyriba_df["Processor"].isna()].copy()
    kyriba_mapped_df = kyriba_df[kyriba_df["Processor"].notna()].copy()

    with st.expander("🔎 Debug processors y cuentas detectadas"):
        st.write("Processors Kyriba:", sorted(kyriba_mapped_df["Processor"].dropna().unique()))
        st.write("Processors Payins:", sorted(payins_df["Processor"].dropna().unique()))
        st.write("Cuentas Kyriba:", sorted(kyriba_df["Account code"].dropna().unique()))
        st.write("Bancos de cuenta:", sorted(kyriba_df["Account bank"].dropna().unique()))
        st.write("Monedas Kyriba:", sorted(kyriba_df["Currency"].dropna().unique()))
        if not unmapped_kyriba.empty:
            st.warning(f"Movimientos Kyriba sin processor: {len(unmapped_kyriba)}")
            st.dataframe(
                unmapped_kyriba[[
                    "Transaction date", "Account code", "Account ID", "Account bank",
                    "Currency", "Description", "Complementary info", "Credit", "Source file"
                ]].head(300),
                use_container_width=True,
                hide_index=True
            )

    if kyriba_mapped_df.empty:
        st.error("Kyriba se leyó, pero ningún movimiento quedó con Processor. Revisá el mapping manual de cuentas.")
        st.stop()

    kyriba_df = kyriba_mapped_df

    # Fechas comunes
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

    # Filtrar payins solo a processors existentes en Kyriba
    kyriba_processors = set(kyriba_df["Processor"].dropna().unique())
    payins_processors_original = set(payins_df["Processor"].dropna().unique())

    payins_excluded_processors = sorted(payins_processors_original - kyriba_processors)
    payins_excluded_df = payins_df[~payins_df["Processor"].isin(kyriba_processors)].copy()

    with st.expander("🔎 Procesadores Payins excluidos por no existir en Kyriba"):
        if payins_excluded_processors:
            st.write(payins_excluded_processors)
            st.dataframe(payins_excluded_df, use_container_width=True, hide_index=True)
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
            .rename(columns={"Credit": "Banco"})
        )

        payins_grouped = (
            payins_filtered
            .groupby(["Processor", "Day"], as_index=False)["Amount"]
            .sum()
            .rename(columns={"Amount": "Payins estimados"})
        )

        detail = pd.merge(
            banco_grouped,
            payins_grouped,
            on=["Processor", "Day"],
            how="outer"
        ).fillna(0)

        detail["Diferencia"] = detail["Banco"] - detail["Payins estimados"]

        detail["Dif %"] = detail.apply(
            lambda r: (r["Diferencia"] / r["Payins estimados"] * 100)
            if r["Payins estimados"] != 0 else 0,
            axis=1
        )

        detail["Estado"] = detail.apply(
            lambda r: "⚠️ Sin dato Payins"
            if r["Payins estimados"] == 0
            else (
                "✅ OK"
                if abs(r["Dif %"]) <= tolerance
                else ("🔴 Banco menor" if r["Diferencia"] < 0 else "🟡 Banco mayor")
            ),
            axis=1
        )

        summary = (
            detail
            .groupby("Processor", as_index=False)
            .agg({
                "Banco": "sum",
                "Payins estimados": "sum",
                "Diferencia": "sum"
            })
        )

        summary["Dif %"] = summary.apply(
            lambda r: (r["Diferencia"] / r["Payins estimados"] * 100)
            if r["Payins estimados"] != 0 else 0,
            axis=1
        )

        summary["Estado"] = summary.apply(
            lambda r: "⚠️ Sin dato Payins"
            if r["Payins estimados"] == 0
            else (
                "✅ OK"
                if abs(r["Dif %"]) <= tolerance
                else ("🔴 Banco menor" if r["Diferencia"] < 0 else "🟡 Banco mayor")
            ),
            axis=1
        )

        st.subheader("📈 KPIs")

        total_banco = summary["Banco"].sum()
        total_payins = summary["Payins estimados"].sum()
        total_diff = total_banco - total_payins
        total_pct = total_diff / total_payins * 100 if total_payins else 0

        k1, k2, k3, k4 = st.columns(4)
        k1.metric(f"Banco {currency_filter}", f"{total_banco:,.0f}")
        k2.metric(f"Payins estimados", f"{total_payins:,.0f}")
        k3.metric("Diferencia", f"{total_diff:,.0f}")
        k4.metric("Dif. %", f"{total_pct:.1f}%")

        st.subheader("📊 Resumen por procesador")
        st.dataframe(summary, use_container_width=True, hide_index=True)

        st.subheader("📅 Detalle por día")
        st.dataframe(detail, use_container_width=True, hide_index=True)

        with st.expander("Ver Kyriba combinado"):
            st.dataframe(kyriba_df, use_container_width=True, hide_index=True)

        with st.expander("Ver Payins combinados"):
            st.dataframe(payins_df, use_container_width=True, hide_index=True)

        excel_file = build_excel(summary, detail, kyriba_df, payins_df, unmapped_kyriba, payins_excluded_df)

        st.download_button(
            label="⬇️ Descargar Excel conciliación",
            data=excel_file,
            file_name=f"check_payins_mx_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

else:
    st.info("Subí uno o más archivos Kyriba y uno o más archivos de estimaciones Payins.")
