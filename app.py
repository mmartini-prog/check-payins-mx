import streamlit as st
import pandas as pd
from io import BytesIO
from datetime import datetime
from rules_mx import RULES_MX_DLOCAL, RULES_MX_DEMERGE

st.set_page_config(page_title="Check Payins MX", page_icon="📊", layout="wide")

st.title("📊 Check Payins México")
st.write("Dashboard para comparar movimientos bancarios Kyriba contra estimaciones de Payins.")

# ─────────────────────────────────────────────────────────────
# SIDEBAR
# ─────────────────────────────────────────────────────────────

entity = st.sidebar.selectbox(
    "Entidad",
    ["Dlocal Mexico", "Demerge Mexico"]
)

tolerance = st.sidebar.number_input(
    "Tolerancia sin alerta (%)",
    value=10,
    min_value=0,
    max_value=100,
    step=1
)

st.sidebar.markdown("---")
st.sidebar.subheader("Columnas Payins estimados")

col_date = st.sidebar.text_input(
    "Fecha",
    value="Approved Date"
)

col_amount = st.sidebar.text_input(
    "Monto",
    value="Approved Amount Local"
)

col_processor = st.sidebar.text_input(
    "Procesador",
    value="Processor"
)

# ─────────────────────────────────────────────────────────────
# RULES
# ─────────────────────────────────────────────────────────────

def get_rules(entity):
    return RULES_MX_DLOCAL if entity == "Dlocal Mexico" else RULES_MX_DEMERGE


def get_processor_mx(description, account_id=None, account_code=None, entity="Dlocal Mexico"):
    if not isinstance(description, str):
        return None

    description_clean = description.upper()
    account_id_clean = str(account_id).strip()
    account_code_clean = str(account_code).strip()

    for keyword, processor, expected_account_id, expected_account_code in get_rules(entity):
        if keyword.upper() in description_clean:
            if (
                account_id_clean == expected_account_id
                or account_code_clean == expected_account_code
            ):
                return processor

    return None


# ─────────────────────────────────────────────────────────────
# NORMALIZE PROCESSORS
# ─────────────────────────────────────────────────────────────

def normalize_processor(name):
    if not isinstance(name, str):
        return None

    clean = name.strip().lower()

    processor_map = {
        "banorte": "Banorte",
        "evo mpgs": "EVO MPGs",
        "evopaymx": "EVO MPGs",
        "hey banregio": "Hey Banregio",
        "mercadopago": "Mercadopago",
        "mercado pago": "Mercadopago",
        "openpay": "Openpay",
        "openpay_paynet": "Openpay_paynet",
        "oxxo pay": "OXXO Pay",
        "oxxopay": "OXXO Pay",
        "arcus": "Arcus",
    }

    return processor_map.get(clean, name.strip())


# ─────────────────────────────────────────────────────────────
# PARSE KYRIBA
# ─────────────────────────────────────────────────────────────

@st.cache_data(show_spinner=False)
def parse_kyriba(file_bytes, file_name, entity):
    try:
        import io

        is_csv = file_name.lower().endswith(".csv")
        raw_buf = io.BytesIO(file_bytes)

        if is_csv:
            raw = pd.read_csv(
                raw_buf,
                header=None,
                nrows=30,
                encoding="utf-8-sig"
            )
        else:
            raw = pd.read_excel(
                raw_buf,
                header=None,
                nrows=30
            )

        header_row = None

        for i, row in raw.iterrows():
            row_values = [str(v) for v in row.values]

            if any("Transaction date" in v for v in row_values):
                header_row = i
                break

        if header_row is None:
            st.error(f"No encontré encabezados Kyriba en: {file_name}")
            return pd.DataFrame()

        raw_buf = io.BytesIO(file_bytes)

        if is_csv:
            df = pd.read_csv(
                raw_buf,
                header=header_row,
                dtype=str,
                encoding="utf-8-sig"
            )
        else:
            df = pd.read_excel(
                raw_buf,
                header=header_row,
                dtype=str
            )

        df.columns = [str(c).strip() for c in df.columns]

        required = [
            "Account code",
            "Account ID",
            "Transaction date",
            "Description",
            "Credit"
        ]

        missing = [c for c in required if c not in df.columns]

        if missing:
            st.error(f"Faltan columnas en Kyriba {file_name}: {missing}")
            st.write("Columnas disponibles:", list(df.columns))
            return pd.DataFrame()

        df = df[required].copy()

        df = df[df["Account code"].notna()]

        df = df[
            ~df["Description"].isin([
                "Opening balance",
                "Closing balance",
                "Description"
            ])
        ]

        df["Transaction date"] = pd.to_datetime(
            df["Transaction date"],
            errors="coerce"
        )

        df = df[df["Transaction date"].notna()]

        df["Credit"] = (
            df["Credit"]
            .astype(str)
            .str.replace(",", "", regex=False)
            .str.replace("$", "", regex=False)
        )

        df["Credit"] = pd.to_numeric(
            df["Credit"],
            errors="coerce"
        ).fillna(0)

        df["Processor"] = df.apply(
            lambda r: get_processor_mx(
                description=r["Description"],
                account_id=r["Account ID"],
                account_code=r["Account code"],
                entity=entity,
            ),
            axis=1,
        )

        df = df[df["Processor"].notna()].copy()

        df["Day"] = df["Transaction date"].dt.strftime("%d/%m/%Y")

        df["Source file"] = file_name

        return df

    except Exception as e:
        st.error(f"Error leyendo Kyriba {file_name}: {e}")
        return pd.DataFrame()


# ─────────────────────────────────────────────────────────────
# PARSE PAYINS
# ─────────────────────────────────────────────────────────────

@st.cache_data(show_spinner=False)
def parse_payins(
    file_bytes,
    file_name,
    col_date,
    col_amount,
    col_processor
):
    try:
        import io

        is_csv = file_name.lower().endswith(".csv")

        buf = io.BytesIO(file_bytes)

        if is_csv:
            df = pd.read_csv(buf)
        else:
            df = pd.read_excel(buf)

        df.columns = [str(c).strip() for c in df.columns]

        required = [
            col_date,
            col_amount,
            col_processor
        ]

        missing = [c for c in required if c not in df.columns]

        if missing:
            st.error(f"Faltan columnas en Payins estimados: {missing}")
            st.write("Columnas disponibles:", list(df.columns))
            return pd.DataFrame()

        df = df[
            [
                col_date,
                col_amount,
                col_processor
            ]
        ].copy()

        df.columns = [
            "Date",
            "Amount",
            "Processor"
        ]

        df["Date"] = pd.to_datetime(
            df["Date"],
            errors="coerce"
        )

        df = df[df["Date"].notna()]

        df["Amount"] = (
            df["Amount"]
            .astype(str)
            .str.replace(",", "", regex=False)
            .str.replace("$", "", regex=False)
        )

        df["Amount"] = pd.to_numeric(
            df["Amount"],
            errors="coerce"
        ).fillna(0)

        df["Processor"] = df["Processor"].apply(
            normalize_processor
        )

        df = df[df["Processor"].notna()].copy()

        df["Day"] = df["Date"].dt.strftime("%d/%m/%Y")

        return df

    except Exception as e:
        st.error(f"Error leyendo Payins estimados: {e}")
        return pd.DataFrame()


# ─────────────────────────────────────────────────────────────
# BUILD EXCEL
# ─────────────────────────────────────────────────────────────

def build_excel(summary_df, detail_df, kyriba_raw_df):
    output = BytesIO()

    with pd.ExcelWriter(
        output,
        engine="openpyxl"
    ) as writer:

        summary_df.to_excel(
            writer,
            index=False,
            sheet_name="Resumen"
        )

        detail_df.to_excel(
            writer,
            index=False,
            sheet_name="Detalle"
        )

        kyriba_raw_df.to_excel(
            writer,
            index=False,
            sheet_name="Kyriba combinado"
        )

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

    # ── KYRIBA ─────────────────────

    kyriba_dfs = []

    with st.spinner("Leyendo archivos Kyriba..."):

        for file in kyriba_files:

            file_bytes = file.read()

            temp_df = parse_kyriba(
                file_bytes,
                file.name,
                entity
            )

            if not temp_df.empty:
                kyriba_dfs.append(temp_df)

    if not kyriba_dfs:
        st.error("No pude leer ningún archivo Kyriba válido.")
        st.stop()

    kyriba_df = pd.concat(
        kyriba_dfs,
        ignore_index=True
    )

    st.success(f"Archivos Kyriba combinados: {len(kyriba_dfs)}")

    # ── PAYINS ─────────────────────

    payins_dfs = []

    with st.spinner("Leyendo archivos Payins..."):

        for file in payins_files:

            file_bytes = file.read()

            temp_df = parse_payins(
                file_bytes,
                file.name,
                col_date,
                col_amount,
                col_processor
            )

            if not temp_df.empty:
                temp_df["Source file"] = file.name
                payins_dfs.append(temp_df)

    if not payins_dfs:
        st.error("No pude leer ningún archivo Payins válido.")
        st.stop()

    payins_df = pd.concat(
        payins_dfs,
        ignore_index=True
    )

    st.success(f"Archivos Payins combinados: {len(payins_dfs)}")

    # ── PROCESSORS ─────────────────

    processors = sorted(
        set(kyriba_df["Processor"].unique())
        | set(payins_df["Processor"].unique())
    )

    selected_processors = st.multiselect(
        "Procesadores a analizar",
        options=processors,
        default=processors
    )

    # ── RUN ────────────────────────

    if st.button(
        "▶ Analizar conciliación",
        type="primary"
    ):

        kyriba_filtered = kyriba_df[
            kyriba_df["Processor"].isin(selected_processors)
        ]

        payins_filtered = payins_df[
            payins_df["Processor"].isin(selected_processors)
        ]

        banco_grouped = (
            kyriba_filtered
            .groupby(
                ["Processor", "Day"],
                as_index=False
            )["Credit"]
            .sum()
            .rename(columns={
                "Credit": "Banco MXN"
            })
        )

        payins_grouped = (
            payins_filtered
            .groupby(
                ["Processor", "Day"],
                as_index=False
            )["Amount"]
            .sum()
            .rename(columns={
                "Amount": "Payins estimados MXN"
            })
        )

        detail = pd.merge(
            banco_grouped,
            payins_grouped,
            on=["Processor", "Day"],
            how="outer"
        ).fillna(0)

        detail["Diferencia MXN"] = (
            detail["Banco MXN"]
            - detail["Payins estimados MXN"]
        )

        detail["Dif %"] = detail.apply(
            lambda r: (
                r["Diferencia MXN"]
                / r["Payins estimados MXN"]
                * 100
            )
            if r["Payins estimados MXN"] != 0
            else 0,
            axis=1
        )

        detail["Estado"] = detail.apply(
            lambda r:
            "⚠️ Sin dato Payins"
            if r["Payins estimados MXN"] == 0
            else (
                "✅ OK"
                if abs(r["Dif %"]) <= tolerance
                else (
                    "🔴 Banco menor"
                    if r["Diferencia MXN"] < 0
                    else "🟡 Banco mayor"
                )
            ),
            axis=1
        )

        # ── SUMMARY ─────────────────

        summary = (
            detail
            .groupby(
                "Processor",
                as_index=False
            )
            .agg({
                "Banco MXN": "sum",
                "Payins estimados MXN": "sum",
                "Diferencia MXN": "sum"
            })
        )

        summary["Dif %"] = summary.apply(
            lambda r: (
                r["Diferencia MXN"]
                / r["Payins estimados MXN"]
                * 100
            )
            if r["Payins estimados MXN"] != 0
            else 0,
            axis=1
        )

        summary["Estado"] = summary.apply(
            lambda r:
            "⚠️ Sin dato Payins"
            if r["Payins estimados MXN"] == 0
            else (
                "✅ OK"
                if abs(r["Dif %"]) <= tolerance
                else (
                    "🔴 Banco menor"
                    if r["Diferencia MXN"] < 0
                    else "🟡 Banco mayor"
                )
            ),
            axis=1
        )

        # ── KPIS ────────────────────

        st.subheader("📈 KPIs")

        total_banco = summary["Banco MXN"].sum()

        total_payins = summary[
            "Payins estimados MXN"
        ].sum()

        total_diff = (
            total_banco
            - total_payins
        )

        total_pct = (
            total_diff
            / total_payins
            * 100
        ) if total_payins else 0

        k1, k2, k3, k4 = st.columns(4)

        k1.metric(
            "Banco MXN",
            f"{total_banco:,.0f}"
        )

        k2.metric(
            "Payins estimados MXN",
            f"{total_payins:,.0f}"
        )

        k3.metric(
            "Diferencia MXN",
            f"{total_diff:,.0f}"
        )

        k4.metric(
            "Dif. %",
            f"{total_pct:.1f}%"
        )

        # ── TABLES ──────────────────

        st.subheader("📊 Resumen por procesador")

        st.dataframe(
            summary,
            use_container_width=True,
            hide_index=True
        )

        st.subheader("📅 Detalle por día")

        st.dataframe(
            detail,
            use_container_width=True,
            hide_index=True
        )

        # ── RAW DATA ────────────────

        with st.expander("Ver Kyriba combinado"):
            st.dataframe(
                kyriba_df,
                use_container_width=True,
                hide_index=True
            )

        with st.expander("Ver Payins combinados"):
            st.dataframe(
                payins_df,
                use_container_width=True,
                hide_index=True
            )

        # ── DOWNLOAD ────────────────

        excel_file = build_excel(
            summary,
            detail,
            kyriba_df
        )

        st.download_button(
            label="⬇️ Descargar Excel conciliación",
            data=excel_file,
            file_name=(
                f"check_payins_mx_"
                f"{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
            ),
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

else:
    st.info(
        "Subí uno o más archivos Kyriba y uno o más archivos de estimaciones Payins."
    )
