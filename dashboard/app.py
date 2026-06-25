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


st.set_page_config(
    page_title="Shelf Audit AI Dashboard",
    page_icon="🛒",
    layout="wide"
)


st.title("🛒 Shelf Audit AI Dashboard")
st.caption("Dashboard สำหรับตรวจสอบภาพเชลฟ์ / ตรวจโมเดล / ตรวจสินค้าที่หาย")


def load_data():
    if not os.path.exists(DB_PATH):
        return pd.DataFrame()

    try:
        conn = sqlite3.connect(DB_PATH)

        df = pd.read_sql_query("""
            SELECT
                id,
                branch_code,
                image_name,
                detected_model,
                model_score,
                result,
                missing_count,
                missing_items_json,
                created_at
            FROM inspections
            ORDER BY id DESC
        """, conn)

        conn.close()
        return df

    except Exception as e:
        st.error(f"อ่านฐานข้อมูลไม่ได้: {e}")
        return pd.DataFrame()


def parse_missing_items(value):
    try:
        if not value:
            return []
        return json.loads(value)
    except Exception:
        return []


df = load_data()

if df.empty:
    st.warning("ยังไม่มีข้อมูล ให้ลอง Upload รูปผ่าน http://localhost:8000/docs ก่อน")
    st.stop()


df["missing_items"] = df["missing_items_json"].apply(parse_missing_items)

total_count = len(df)
pass_count = len(df[df["result"] == "PASS"])
fail_count = len(df[df["result"] == "FAIL"])
unknown_count = len(df[df["result"] == "UNKNOWN_MODEL"])
avg_model_score = df["model_score"].mean() if total_count > 0 else 0


col1, col2, col3, col4, col5 = st.columns(5)

col1.metric("Total", total_count)
col2.metric("PASS", pass_count)
col3.metric("FAIL", fail_count)
col4.metric("Unknown", unknown_count)
col5.metric("Avg Model Score", f"{avg_model_score * 100:.1f}%")


st.divider()


left, right = st.columns([1, 1])

with left:
    result_filter = st.selectbox(
        "Filter Result",
        ["ALL", "PASS", "FAIL", "UNKNOWN_MODEL"]
    )

with right:
    model_filter = st.selectbox(
        "Filter Model",
        ["ALL"] + sorted(df["detected_model"].dropna().unique().tolist())
    )


filtered_df = df.copy()

if result_filter != "ALL":
    filtered_df = filtered_df[filtered_df["result"] == result_filter]

if model_filter != "ALL":
    filtered_df = filtered_df[filtered_df["detected_model"] == model_filter]


st.subheader("Inspection Records")

table_df = filtered_df[
    [
        "id",
        "branch_code",
        "detected_model",
        "model_score",
        "result",
        "missing_count",
        "created_at"
    ]
].copy()

table_df["model_score"] = table_df["model_score"].apply(
    lambda x: f"{x * 100:.2f}%" if pd.notnull(x) else "-"
)

st.dataframe(table_df, use_container_width=True)


st.divider()


st.subheader("Inspection Images")


for _, row in filtered_df.iterrows():
    image_path = os.path.join(UPLOAD_DIR, row["image_name"])
    missing_items = row["missing_items"]

    with st.container(border=True):
        c1, c2 = st.columns([1, 2])

        with c1:
            if os.path.exists(image_path):
                try:
                    image = Image.open(image_path)
                    st.image(image, caption=row["image_name"], use_container_width=True)
                except Exception:
                    st.error("เปิดรูปไม่ได้")
            else:
                st.error("ไม่พบรูปภาพใน uploads")

        with c2:
            result = row["result"]
            model_score_percent = row["model_score"] * 100

            if result == "PASS":
                st.success("Result: PASS")
            elif result == "FAIL":
                st.error("Result: FAIL")
            elif result == "UNKNOWN_MODEL":
                st.warning("Result: UNKNOWN MODEL")
            else:
                st.info(f"Result: {result}")

            st.write(f"**Branch Code:** {row['branch_code']}")
            st.write(f"**Detected Model:** {row['detected_model']}")
            st.write(f"**Model Score:** {model_score_percent:.2f}%")
            st.write(f"**Missing Count:** {row['missing_count']}")
            st.write(f"**Created At:** {row['created_at']}")

            if len(missing_items) == 0:
                st.write("**Missing Items:** ไม่มีรายการ")
            else:
                st.write("**Missing Items:**")

                missing_table = pd.DataFrame(missing_items)

                if not missing_table.empty:
                    st.dataframe(missing_table, use_container_width=True)
                else:
                    st.write(missing_items)