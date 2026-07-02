import json
import os
import sys

import pandas as pd
import streamlit as st
from PIL import Image

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND_DIR = os.path.join(BASE_DIR, "backend")
UPLOAD_DIR = os.path.join(BACKEND_DIR, "uploads")
ANNOTATED_DIR = os.path.join(BACKEND_DIR, "annotated")

if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from database import get_connection, init_db

REQUIRED_COLUMNS = {
    "id": None,
    "branch_code": "",
    "image_name": "",
    "detected_model": None,
    "model_score": None,
    "result": None,
    "missing_count": 0,
    "missing_items_json": "[]",
    "status": "PENDING",
    "error_message": None,
    "annotated_image_name": None,
    "created_at": None,
    "updated_at": None,
}


def safe_str(value):
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass
    return str(value).strip()


st.set_page_config(page_title="Shelf Audit AI Dashboard", layout="wide")

if "refresh_counter" not in st.session_state:
    st.session_state.refresh_counter = 0

if st.button("Refresh now"):
    st.session_state.refresh_counter += 1
    st.rerun()

st.markdown(
    """
    <style>
        :root {
            color-scheme: dark;
        }
        .stApp {
            background: linear-gradient(135deg, #07111f 0%, #12253f 45%, #1f3d68 100%);
        }
        [data-testid="stHeader"] {
            background: rgba(7, 17, 31, 0.45);
            backdrop-filter: blur(10px);
        }
        .stTitle, .stCaption, .stMarkdown {
            color: #f7fbff;
        }
        .hero {
            padding: 1.2rem 1.3rem;
            margin-bottom: 1rem;
            border-radius: 22px;
            background: linear-gradient(135deg, rgba(255,255,255,0.14), rgba(255,255,255,0.06));
            border: 1px solid rgba(255,255,255,0.16);
            box-shadow: 0 10px 30px rgba(4, 12, 24, 0.25);
            backdrop-filter: blur(14px);
        }
        .hero h1 {
            margin-bottom: 0.25rem;
            font-size: 2rem;
            color: #ffffff;
        }
        .hero p {
            margin: 0;
            color: #d7e4f4;
            font-size: 1rem;
        }
        .hero-badge {
            display: inline-block;
            margin-top: 0.7rem;
            padding: 0.4rem 0.75rem;
            border-radius: 999px;
            background: rgba(114, 224, 255, 0.16);
            color: #8be8ff;
            border: 1px solid rgba(114, 224, 255, 0.25);
            font-size: 0.9rem;
        }
        div[data-testid="stMetric"] {
            background: rgba(255,255,255,0.08);
            border: 1px solid rgba(255,255,255,0.14);
            border-radius: 18px;
            padding: 0.8rem 0.9rem;
            box-shadow: 0 8px 24px rgba(0, 0, 0, 0.18);
        }
        div[data-testid="stMetricLabel"] {
            color: #b9cce4;
        }
        div[data-testid="stMetricValue"] {
            color: #72e0ff;
            font-weight: 700;
        }
        div[data-testid="stVerticalBlockBorderWrapper"] {
            background: rgba(255,255,255,0.05);
            border: 1px solid rgba(255,255,255,0.12);
            border-radius: 18px;
            padding: 0.9rem;
            backdrop-filter: blur(10px);
        }
        .section-title {
            margin: 0.5rem 0 0.4rem;
            color: #ffffff;
            font-size: 1.15rem;
            font-weight: 700;
        }
        .section-subtitle {
            color: #b9cce4;
            margin-bottom: 0.7rem;
        }
        .stSelectbox > div > div {
            background: rgba(255,255,255,0.08);
            border: 1px solid rgba(255,255,255,0.16);
            border-radius: 12px;
        }
        .stTextInput > div > div > input, .stNumberInput > div > div > input {
            background: rgba(255,255,255,0.08);
            color: #f7fbff;
        }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div class="hero">
        <h1>Smart Shelf Audit</h1>
        <p>Track shelf inspections, model confidence, and missing items in one calm, polished workspace.</p>
        <div class="hero-badge">AI-powered • Retail-ready • Insightful</div>
    </div>
    """,
    unsafe_allow_html=True,
)


def load_data() -> pd.DataFrame:
    try:
        init_db()
        with get_connection() as conn:
            rows = conn.execute("SELECT * FROM inspections ORDER BY id DESC").fetchall()

        if not rows:
            return pd.DataFrame()

        df = pd.DataFrame([dict(row) for row in rows])

        for column, default in REQUIRED_COLUMNS.items():
            if column not in df.columns:
                df[column] = default

        text_columns = [
            "image_name",
            "detected_model",
            "result",
            "status",
            "error_message",
            "annotated_image_name",
        ]
        for column in text_columns:
            df[column] = df[column].apply(safe_str)

        df.loc[df["status"] == "", "status"] = df["result"].apply(
            lambda value: "DONE" if value in ["PASS", "FAIL", "UNKNOWN_MODEL"] else "PENDING"
        )
        df["missing_count"] = df["missing_count"].fillna(0).astype(int)
        return df

    except Exception as e:
        st.error(f"อ่านฐานข้อมูลไม่ได้: {e}")
        return pd.DataFrame()


def parse_missing_items(value):
    try:
        if not value:
            return []
        parsed = json.loads(value)
        return parsed if isinstance(parsed, list) else []
    except Exception:
        return []


def format_score(value) -> str:
    if pd.isna(value):
        return "-"

    try:
        return f"{float(value) * 100:.2f}%"
    except (TypeError, ValueError):
        return "-"


def show_status(status: str, result: str, error_message) -> None:
    if status == "PENDING":
        st.info("Status: PENDING")
    elif status == "PROCESSING":
        st.info("Status: PROCESSING")
    elif status == "FAILED":
        st.error("Status: FAILED")
        if error_message:
            st.write(f"**Error:** {error_message}")
    elif status == "DONE":
        if result == "PASS":
            st.success("Result: PASS")
        elif result == "FAIL":
            st.error("Result: FAIL")
        elif result == "UNKNOWN_MODEL":
            st.warning("Result: UNKNOWN MODEL")
        else:
            st.info(f"Status: DONE / Result: {result or '-'}")
    else:
        st.info(f"Status: {status or '-'}")


df = load_data()

if df.empty:
    st.markdown(
        """
        <div class="hero">
            <h1>No inspections yet</h1>
            <p>Upload a shelf image through the app or the API to start your first audit run.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.info("ลองอัปโหลดภาพผ่านแอปหรือ http://localhost:8000/docs ก่อน")
    st.stop()


df["missing_items"] = df["missing_items_json"].apply(parse_missing_items)

status_series = df["status"].fillna("")
result_series = df["result"].fillna("")

total_count = len(df)
pending_count = len(df[status_series == "PENDING"])
processing_count = len(df[status_series == "PROCESSING"])
done_count = len(df[status_series == "DONE"])
failed_count = len(df[status_series == "FAILED"])
pass_count = len(df[result_series == "PASS"])
fail_count = len(df[result_series == "FAIL"])
unknown_count = len(df[result_series == "UNKNOWN_MODEL"])
score_values = pd.to_numeric(df["model_score"], errors="coerce").dropna()
avg_model_score = float(score_values.mean() * 100) if not score_values.empty else 0.0
total_missing_items = int(df["missing_count"].fillna(0).astype(int).sum())
branch_count = int(df["branch_code"].fillna("").astype(str).str.strip().ne("").nunique())
latest_update = safe_str(df["updated_at"].dropna().iloc[0]) if not df["updated_at"].dropna().empty else "-"

cols = st.columns(8)
cols[0].metric("Total", total_count)
cols[1].metric("Pending", pending_count)
cols[2].metric("Processing", processing_count)
cols[3].metric("Done", done_count)
cols[4].metric("Failed", failed_count)
cols[5].metric("Pass", pass_count)
cols[6].metric("Fail", fail_count)
cols[7].metric("Unknown Model", unknown_count)

st.markdown('<div class="section-title">Operational Snapshot</div>', unsafe_allow_html=True)
snapshot_cols = st.columns(4)
snapshot_cols[0].metric("Branches", branch_count)
snapshot_cols[1].metric("Avg. Model Score", f"{avg_model_score:.1f}%")
snapshot_cols[2].metric("Missing Items", total_missing_items)
snapshot_cols[3].metric("Latest Update", latest_update)

st.divider()

left, middle, right, branch_col = st.columns([1, 1, 1, 1])

with left:
    status_filter = st.selectbox(
        "Filter Status",
        ["ALL", "PENDING", "PROCESSING", "DONE", "FAILED"],
    )

with middle:
    result_filter = st.selectbox(
        "Filter Result",
        ["ALL", "PASS", "FAIL", "UNKNOWN_MODEL", "PENDING"],
    )

with right:
    model_values = sorted(
        [safe_str(value) for value in df["detected_model"].unique().tolist() if safe_str(value)]
    )
    model_filter = st.selectbox("Filter Model", ["ALL"] + model_values)

with branch_col:
    branch_values = sorted(
        [safe_str(value) for value in df["branch_code"].unique().tolist() if safe_str(value)]
    )
    branch_filter = st.selectbox("Filter Branch", ["ALL"] + branch_values)

filtered_df = df.copy()

if status_filter != "ALL":
    filtered_df = filtered_df[filtered_df["status"] == status_filter]

if result_filter != "ALL":
    filtered_df = filtered_df[filtered_df["result"] == result_filter]

if model_filter != "ALL":
    filtered_df = filtered_df[filtered_df["detected_model"] == model_filter]

if branch_filter != "ALL":
    filtered_df = filtered_df[filtered_df["branch_code"] == branch_filter]

st.markdown('<div class="section-title">Inspection Records</div>', unsafe_allow_html=True)
st.markdown('<div class="section-subtitle">A quick overview of recent audit runs and their outcomes.</div>', unsafe_allow_html=True)
st.caption("Auto-refresh every 3 seconds so Pending → Processing → Done updates appear live.")

table_columns = [
    "id",
    "branch_code",
    "status",
    "result",
    "detected_model",
    "model_score",
    "missing_count",
    "annotated_image_name",
    "created_at",
    "updated_at",
]

table_df = filtered_df[table_columns].copy()
table_df["model_score"] = table_df["model_score"].apply(format_score)
st.dataframe(table_df, use_container_width=True)

st.markdown('<div class="section-title">Branch Overview</div>', unsafe_allow_html=True)
st.markdown('<div class="section-subtitle">A schema-based summary grouped by branch code, audit outcome, and missing-item volume.</div>', unsafe_allow_html=True)
branch_summary = (
    filtered_df.groupby("branch_code", dropna=False)
    .agg(
        inspections=("id", "count"),
        completed=("status", lambda values: int((values == "DONE").sum())),
        pending=("status", lambda values: int((values == "PENDING").sum())),
        missing_items=("missing_count", "sum"),
        latest_update=("updated_at", lambda values: safe_str(values.dropna().iloc[0]) if not values.dropna().empty else ""),
    )
    .reset_index()
)
branch_summary["branch_code"] = branch_summary["branch_code"].fillna("").astype(str).str.strip()
branch_summary.loc[branch_summary["branch_code"] == "", "branch_code"] = "UNKNOWN"
st.dataframe(branch_summary, use_container_width=True)

st.divider()
st.markdown('<div class="section-title">AI Visual Audit Result</div>', unsafe_allow_html=True)
st.markdown('<div class="section-subtitle">Detailed inspection cards with image evidence and missing-item findings.</div>', unsafe_allow_html=True)

for _, row in filtered_df.iterrows():
    image_name = safe_str(row.get("image_name", ""))
    annotated_image_name = safe_str(row.get("annotated_image_name", ""))

    if annotated_image_name:
        annotated_image_path = os.path.join(ANNOTATED_DIR, annotated_image_name)
    else:
        annotated_image_path = ""

    image_path = ""
    image_caption = ""

    if annotated_image_path and os.path.exists(annotated_image_path):
        image_path = annotated_image_path
        image_caption = annotated_image_name
    elif image_name:
        image_path = os.path.join(UPLOAD_DIR, image_name)
        image_caption = image_name

    missing_items = row.get("missing_items") or []
    status = safe_str(row.get("status", "")) or "-"
    result = safe_str(row.get("result", "")) or "-"
    error_message = safe_str(row.get("error_message", ""))

    with st.container(border=True):
        c1, c2 = st.columns([2, 1])

        with c1:
            if image_caption and os.path.exists(image_path):
                try:
                    image = Image.open(image_path)
                    st.image(image, caption=image_caption, use_container_width=True)
                except Exception:
                    st.error("เปิดรูปไม่ได้")
            else:
                st.warning("No image available")

        with c2:
            show_status(status, result, error_message)
            st.write(f"**Branch Code:** {safe_str(row.get('branch_code', '')) or '-'}")
            st.write(f"**Detected Model:** {safe_str(row.get('detected_model', '')) or '-'}")
            st.write(f"**Model Score:** {format_score(row.get('model_score'))}")
            st.write(f"**Missing Count:** {int(row.get('missing_count') or 0)}")
            st.write(f"**Created At:** {safe_str(row.get('created_at', '')) or '-'}")
            st.write(f"**Updated At:** {safe_str(row.get('updated_at', '')) or '-'}")

            if len(missing_items) == 0:
                st.write("**Missing Items:** ไม่มีรายการ")
            else:
                st.write("**Missing Items:**")
                missing_table = pd.DataFrame(missing_items)
                if not missing_table.empty:
                    st.dataframe(missing_table, use_container_width=True)
                else:
                    st.write(missing_items)

