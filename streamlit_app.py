from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import pandas as pd
import streamlit as st

APP_DB = Path(__file__).parent / "data" / "app.db"
DEFAULT_TRACKING_DOMAIN = "https://tracking.example.com"


@dataclass(frozen=True)
class Variant:
    variant_id: str
    subject: str
    body: str


st.set_page_config(
    page_title="フォーム送信オートメーション",
    page_icon="📨",
    layout="wide",
)


@st.cache_data
def load_csv(uploaded_file: st.runtime.uploaded_file_manager.UploadedFile) -> pd.DataFrame:
    return pd.read_csv(uploaded_file)


def init_db() -> None:
    APP_DB.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(APP_DB) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS member_usage (
                member_id TEXT NOT NULL,
                month TEXT NOT NULL,
                sent_count INTEGER NOT NULL,
                PRIMARY KEY (member_id, month)
            )
            """
        )


def get_month_key(reference: dt.date | None = None) -> str:
    if reference is None:
        reference = dt.date.today()
    return reference.strftime("%Y-%m")


def get_usage(member_id: str) -> int:
    month = get_month_key()
    with sqlite3.connect(APP_DB) as conn:
        cursor = conn.execute(
            "SELECT sent_count FROM member_usage WHERE member_id = ? AND month = ?",
            (member_id, month),
        )
        row = cursor.fetchone()
    return int(row[0]) if row else 0


def update_usage(member_id: str, increment: int) -> None:
    month = get_month_key()
    with sqlite3.connect(APP_DB) as conn:
        cursor = conn.execute(
            "SELECT sent_count FROM member_usage WHERE member_id = ? AND month = ?",
            (member_id, month),
        )
        row = cursor.fetchone()
        if row:
            conn.execute(
                "UPDATE member_usage SET sent_count = ? WHERE member_id = ? AND month = ?",
                (row[0] + increment, member_id, month),
            )
        else:
            conn.execute(
                "INSERT INTO member_usage (member_id, month, sent_count) VALUES (?, ?, ?)",
                (member_id, month, increment),
            )


def extract_urls(value: str) -> list[str]:
    if not isinstance(value, str):
        return []
    return re.findall(r"https?://[^\s,;]+", value)


def explode_recipients(df: pd.DataFrame) -> pd.DataFrame:
    if not {"id", "url", "company"}.issubset(df.columns.str.lower()):
        df = df.rename(columns={col: col.lower() for col in df.columns})
    required = {"id", "url", "company"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"送信リストのCSVに必要な列が不足しています: {', '.join(sorted(missing))}")

    records = []
    for _, row in df.iterrows():
        urls = extract_urls(str(row["url"]))
        for url in urls:
            records.append(
                {
                    "recipient_id": str(row["id"]),
                    "company": str(row["company"]),
                    "url": url,
                }
            )
    return pd.DataFrame(records)


def load_variants(df: pd.DataFrame) -> list[Variant]:
    df = df.rename(columns={col: col.lower() for col in df.columns})
    required = {"variant_id", "subject", "body"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"A/BテストCSVに必要な列が不足しています: {', '.join(sorted(missing))}")
    variants = []
    for _, row in df.iterrows():
        variants.append(
            Variant(
                variant_id=str(row["variant_id"]),
                subject=str(row["subject"]),
                body=str(row["body"]),
            )
        )
    return variants


def assign_variant(variants: list[Variant], seed_key: str) -> Variant:
    digest = hashlib.sha256(seed_key.encode("utf-8")).hexdigest()
    index = int(digest, 16) % len(variants)
    return variants[index]


def build_tracking_url(base_domain: str, payload: dict[str, str]) -> str:
    token = hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()
    return f"{base_domain.rstrip('/')}/t/{token}"


def prepare_send_plan(
    recipients: pd.DataFrame,
    variants: list[Variant],
    tracking_domain: str,
) -> pd.DataFrame:
    plan_rows = []
    for _, row in recipients.iterrows():
        seed_key = f"{row['recipient_id']}::{row['url']}"
        variant = assign_variant(variants, seed_key)
        tracking_url = build_tracking_url(
            tracking_domain,
            {
                "recipient_id": row["recipient_id"],
                "company": row["company"],
                "url": row["url"],
                "variant_id": variant.variant_id,
            },
        )
        plan_rows.append(
            {
                "recipient_id": row["recipient_id"],
                "company": row["company"],
                "url": row["url"],
                "tracking_url": tracking_url,
                "variant_id": variant.variant_id,
                "subject": variant.subject,
                "body": variant.body,
            }
        )
    return pd.DataFrame(plan_rows)


init_db()

st.title("フォーム送信オートメーション")
st.caption("CSVで送信リストとA/Bテスト文面を管理し、送信計画とクリック追跡リンクを生成します。")

with st.sidebar:
    st.header("会員設定")
    member_id = st.text_input("会員ID", value="member-001")
    monthly_limit = st.number_input("月間送信上限", min_value=1, value=1000, step=100)
    current_usage = get_usage(member_id)
    st.metric("今月の送信数", f"{current_usage} 件")
    st.caption("毎月自動でリセットされます。")

    st.header("送信制御")
    test_mode = st.toggle("送信しないテストモード", value=True)
    schedule_date = st.date_input("配信開始日", value=dt.date.today())
    schedule_time = st.time_input("配信開始時刻", value=dt.datetime.now().time())
    schedule_at = dt.datetime.combine(schedule_date, schedule_time)
    st.write(f"予定日時: {schedule_at:%Y-%m-%d %H:%M}")

    st.header("操作")
    if "run_state" not in st.session_state:
        st.session_state.run_state = "停止中"
    col_a, col_b, col_c = st.columns(3)
    with col_a:
        if st.button("開始", use_container_width=True):
            st.session_state.run_state = "配信中"
    with col_b:
        if st.button("一時停止", use_container_width=True):
            st.session_state.run_state = "休止中"
    with col_c:
        if st.button("停止", use_container_width=True):
            st.session_state.run_state = "停止中"
    st.info(f"ステータス: {st.session_state.run_state}")

st.subheader("1. CSVアップロード")
col_list, col_mapping, col_variants = st.columns(3)

with col_list:
    list_file = st.file_uploader("送信リストCSV (id, url, company)", type=["csv"], key="send_list")

with col_mapping:
    mapping_file = st.file_uploader("フィールドマッピングCSV", type=["csv"], key="mapping")

with col_variants:
    variants_file = st.file_uploader("A/BテストCSV (variant_id, subject, body)", type=["csv"], key="variants")

st.divider()

tracking_domain = st.text_input("クリック測定用ドメイン", value=DEFAULT_TRACKING_DOMAIN)

send_plan_df = None
variants = []

if list_file and variants_file:
    try:
        send_list_df = load_csv(list_file)
        st.success("送信リストCSVを読み込みました")
        recipients_df = explode_recipients(send_list_df)
        st.write("送信対象 (URLを展開後)")
        st.dataframe(recipients_df, use_container_width=True, height=240)

        variants_df = load_csv(variants_file)
        variants = load_variants(variants_df)
        st.write("A/Bテスト文面")
        st.dataframe(variants_df, use_container_width=True, height=240)

        send_plan_df = prepare_send_plan(recipients_df, variants, tracking_domain)
        st.subheader("2. 送信計画")
        st.dataframe(send_plan_df, use_container_width=True, height=300)
        plan_csv = send_plan_df.to_csv(index=False).encode("utf-8")
        st.download_button(
            "送信計画をCSVでダウンロード",
            data=plan_csv,
            file_name="send_plan.csv",
            mime="text/csv",
        )
    except ValueError as exc:
        st.error(str(exc))

if mapping_file:
    mapping_df = load_csv(mapping_file)
    st.subheader("フィールドマッピング")
    st.dataframe(mapping_df, use_container_width=True, height=200)

st.divider()

st.subheader("3. 送信シミュレーション")
if send_plan_df is not None and variants:
    pending_count = len(send_plan_df)
    remaining = monthly_limit - current_usage

    if pending_count > remaining:
        st.warning("月間上限を超過するため、送信件数を調整してください。")
    else:
        st.success("月間上限内です。")

    if st.button("送信計画を確定", type="primary"):
        if test_mode:
            st.session_state.last_plan = send_plan_df
            st.warning("テストモードのため送信件数は加算されません。")
        else:
            update_usage(member_id, pending_count)
            st.session_state.last_plan = send_plan_df
            st.success("送信計画を確定しました。結果CSVをダウンロードできます。")

if "last_plan" in st.session_state:
    result_df = st.session_state.last_plan.copy()
    result_df["status"] = "準備完了" if not test_mode else "テストモード"
    result_df["scheduled_at"] = schedule_at.strftime("%Y-%m-%d %H:%M")
    result_df["run_state"] = st.session_state.run_state

    st.subheader("4. 送信結果")
    st.dataframe(result_df, use_container_width=True, height=320)

    csv_bytes = result_df.to_csv(index=False).encode("utf-8")
    st.download_button(
        "送信結果をCSVでダウンロード",
        data=csv_bytes,
        file_name="send_results.csv",
        mime="text/csv",
    )

    st.subheader("クリック測定ログ (サンプル)")
    click_log = result_df[["recipient_id", "company", "tracking_url", "variant_id"]].copy()
    click_log["clicked_at"] = "-"
    st.dataframe(click_log, use_container_width=True, height=200)
    click_csv = click_log.to_csv(index=False).encode("utf-8")
    st.download_button(
        "クリック測定ログをCSVでダウンロード",
        data=click_csv,
        file_name="click_log.csv",
        mime="text/csv",
    )

else:
    st.info("送信リストとA/BテストCSVをアップロードすると送信計画が生成されます。")
