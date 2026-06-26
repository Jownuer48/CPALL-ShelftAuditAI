import json
import os
import sqlite3

import pandas as pd
import streamlit as st
from PIL import Image

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND_DIR = os.path.join(BASE_DIR, "backend")
DB_PATH = os.path.join(BACKEND_DIR, "shelf_audit.db")
UPLOAD_DIR = os.path.join(BACKEND_DIR, "uploads")

REQUIRED_COLUMNS = {
    "id": None,
    "branch_code": "",
    "image_name": "",
    "detected_model": None,
    "model_score": None,
    "result": None,
    "missing_count": 0,
    "missing_items_json": "[]",
    "status": "DONE",
    "error_message": None,
    "created_at": None,
    "updated_at": None,
}

st.set_page_config(page_title="Shelf Audit AI Dashboard", layout="wide")
st.title("Shelf Audit AI Dashboard")
st.caption("Dashboard สำหรับตรวจสอบภาพเชลฟ์ / ตรวจโมเดล / ตรวจสินค้าที่หาย")


def load_data() -> pd.DataFrame:
    if not os.path.exists(DB_PATH):
        return pd.DataFrame()

    try:
        conn = sqlite3.connect(DB_PATH)
        table_exists = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='inspections'"
        ).fetchone()

        if not table_exists:
            conn.close()
            return pd.DataFrame()

        df = pd.read_sql_query("SELECT * FROM inspections ORDER BY id DESC", conn)
        conn.close()

        for column, default in REQUIRED_COLUMNS.items():
            if column not in df.columns:
                df[column] = default

        df["status"] = df["status"].fillna("")
        df.loc[df["status"] == "", "status"] = df["result"].apply(
            lambda value: "DONE" if value in ["PASS", "FAIL", "UNKNOWN_MODEL"] else "PENDING"
        )
        df["result"] = df["result"].fillna("")
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
    st.warning("ยังไม่มีข้อมูล ให้ลอง Upload รูปผ่านแอปหรือ http://localhost:8000/docs ก่อน")
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

cols = st.columns(8)
cols[0].metric("Total", total_count)
cols[1].metric("Pending", pending_count)
cols[2].metric("Processing", processing_count)
cols[3].metric("Done", done_count)
cols[4].metric("Failed", failed_count)
cols[5].metric("Pass", pass_count)
cols[6].metric("Fail", fail_count)
cols[7].metric("Unknown Model", unknown_count)

st.divider()

left, middle, right = st.columns([1, 1, 1])

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
        [value for value in df["detected_model"].dropna().unique().tolist() if value]
    )
    model_filter = st.selectbox("Filter Model", ["ALL"] + model_values)

filtered_df = df.copy()

if status_filter != "ALL":
    filtered_df = filtered_df[filtered_df["status"] == status_filter]

if result_filter != "ALL":
    filtered_df = filtered_df[filtered_df["result"] == result_filter]

if model_filter != "ALL":
    filtered_df = filtered_df[filtered_df["detected_model"] == model_filter]

st.subheader("Inspection Records")

table_columns = [
    "id",
    "branch_code",
    "status",
    "result",
    "detected_model",
    "model_score",
    "missing_count",
    "created_at",
    "updated_at",
]

table_df = filtered_df[table_columns].copy()
table_df["model_score"] = table_df["model_score"].apply(format_score)
st.dataframe(table_df, use_container_width=True)

st.divider()
st.subheader("Inspection Images")

for _, row in filtered_df.iterrows():
    image_name = row.get("image_name") or ""
    image_path = os.path.join(UPLOAD_DIR, image_name)
    missing_items = row.get("missing_items") or []
    status = row.get("status") or "-"
    result = row.get("result") or "-"
    error_message = row.get("error_message")

    with st.container(border=True):
        c1, c2 = st.columns([1, 2])

        with c1:
            if image_name and os.path.exists(image_path):
                try:
                    image = Image.open(image_path)
                    st.image(image, caption=image_name, use_container_width=True)
                except Exception:
                    st.error("เปิดรูปไม่ได้")
            else:
                st.error("ไม่พบรูปภาพใน uploads")

        with c2:
            show_status(status, result, error_message)
            st.write(f"**Branch Code:** {row.get('branch_code') or '-'}")
            st.write(f"**Detected Model:** {row.get('detected_model') or '-'}")
            st.write(f"**Model Score:** {format_score(row.get('model_score'))}")
            st.write(f"**Missing Count:** {int(row.get('missing_count') or 0)}")
            st.write(f"**Created At:** {row.get('created_at') or '-'}")
            st.write(f"**Updated At:** {row.get('updated_at') or '-'}")

            if len(missing_items) == 0:
                st.write("**Missing Items:** ไม่มีรายการ")
            else:
                st.write("**Missing Items:**")
                missing_table = pd.DataFrame(missing_items)
                if not missing_table.empty:
                    st.dataframe(missing_table, use_container_width=True)
                else:
                    st.write(missing_items)

