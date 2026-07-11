import streamlit as st
import pandas as pd
import plotly.express as px
import math
from datetime import datetime, timedelta


# ==========================================
# 1. タイムラインに基づくハイシーズン判定エンジン (改善手段1)
# ==========================================
def count_high_season_days(start_dt, end_dt, comp_key):
    """
    利用期間（start_dt 〜 end_dt）を1日ごとにループし、
    ハイシーズンに該当する日数を正確にカウントする（日またぎ・月またぎ完全対応）
    """
    current = start_dt
    hs_days = 0

    # カーシェアはハイシーズン割増なし
    if comp_key in ['times', 'orix_s']:
        return 0

    while current < end_dt:
        md = current.month * 100 + current.day
        is_hs = False

        if comp_key == 'orix_r':
            is_hs = (424 <= md <= 505) or (701 <= md <= 831) or (918 <= md <= 926) or (1225 <= md <= 1231) or (
                        101 <= md <= 102)
        elif comp_key in ['nippon', 'nissan', 'toyota_r']:
            is_hs = (428 <= md <= 505) or (701 <= md <= 831) or (1228 <= md <= 1231) or (101 <= md <= 103)
        elif comp_key == 'niconico':
            is_hs = (429 <= md <= 505) or (715 <= md <= 816) or (1229 <= md <= 1231) or (101 <= md <= 103)

        if is_hs:
            hs_days += 1

        # 翌日へ進める
        current += timedelta(days=1)

    # もし24時間以内の利用でも、期間が少しでも被っていれば最低1日分とする
    if hs_days == 0 and start_dt.date() == end_dt.date():
        # 日帰りかつ、その日がハイシーズンの場合
        md = start_dt.month * 100 + start_dt.day
        if comp_key == 'niconico' and ((429 <= md <= 505) or (715 <= md <= 816)):
            hs_days = 1
        elif comp_key == 'nippon' and ((428 <= md <= 505) or (701 <= md <= 831)):
            hs_days = 1

    return max(1, hs_days) if hs_days > 0 else 0


# ==========================================
# 2. 各社の料金計算ロジック（実時刻ベース対応）
# ==========================================
GAS_PRICE = 170
FUEL_EFFICIENCY = 15


def calc_times_car(start_dt, end_dt, distance_km, use_insurance):
    total_hours = math.ceil((end_dt - start_dt).total_seconds() / 3600)
    if total_hours <= 0: return 0

    # 通常料金の計算
    if total_hours <= 6:
        base = min(total_hours * 880, 4290)
    elif total_hours <= 12:
        base = min(4290 + (total_hours - 6) * 880, 5500)
    elif total_hours <= 24:
        base = min(5500 + (total_hours - 12) * 880, 6600)
    else:
        base = 6600 + ((total_hours - 24) // 24) * 5500 + min(((total_hours - 24) % 24) * 880, 5500)

    # 🌙 【改善手段2】ナイトパックの自動適用ロジック
    # 18:00〜翌09:00の間に収まる利用であれば、自動的に定額(2,640円)を適用して比較
    is_night_eligible = start_dt.hour >= 18 and end_dt.hour <= 9 and (end_dt - start_dt).days <= 1
    if is_night_eligible:
        base = min(base, 2640)

    dist = max(0, distance_km - 20) * 20
    ins = 550 if use_insurance else 0
    return base + dist + ins


def calc_orix_share(start_dt, end_dt, distance_km, use_insurance):
    total_hours = math.ceil((end_dt - start_dt).total_seconds() / 3600)
    if total_hours <= 0: return 0

    if total_hours <= 6:
        base = min(total_hours * 960, 4190)
    elif total_hours <= 12:
        base = min(4190 + (total_hours - 6) * 960, 5390)
    elif total_hours <= 24:
        base = min(5390 + (total_hours - 12) * 960, 7890)
    else:
        base = 7890 + ((total_hours - 24) // 24) * 4190 + min(((total_hours - 24) % 24) * 960, 4190)

    # 🌙 ナイトパック (20:00〜翌09:00 / 2,800円)
    if start_dt.hour >= 20 and end_dt.hour <= 9 and (end_dt - start_dt).days <= 1:
        base = min(base, 2800)

    dist = 0 if total_hours <= 6 else distance_km * 20
    ins = math.ceil(total_hours / 24) * 660 if use_insurance else 0
    return base + dist + ins


def calc_niconico(start_dt, end_dt, distance_km, use_insurance, hs_days):
    total_hours = math.ceil((end_dt - start_dt).total_seconds() / 3600)
    if total_hours <= 0: return 0
    days = math.ceil(total_hours / 24)

    base = (total_hours // 24) * 5060 + (
        2525 if 0 < (total_hours % 24) <= 12 else (5060 if (total_hours % 24) > 12 else 0))
    gas = (distance_km / FUEL_EFFICIENCY) * GAS_PRICE
    ins = days * 1100 if use_insurance else 0
    hs_surcharge = hs_days * 550
    return base + gas + ins + hs_surcharge


def calc_nippon_rent(start_dt, end_dt, distance_km, use_insurance, hs_days):
    total_hours = math.ceil((end_dt - start_dt).total_seconds() / 3600)
    if total_hours <= 0: return 0
    days = math.ceil(total_hours / 24)

    if total_hours <= 6:
        base = 6490
    elif total_hours <= 12:
        base = 7150
    elif total_hours <= 24:
        base = 8910
    else:
        base = 8910 + ((total_hours // 24) - 1) * 7150 + min((total_hours % 24) * 1210, 7150)

    gas = (distance_km / FUEL_EFFICIENCY) * GAS_PRICE
    ins = days * 1540 if use_insurance else 0
    hs_surcharge = hs_days * 1100
    return base + gas + ins + hs_surcharge


# ==========================================
# 3. Streamlit UI (改善手段3)
# ==========================================
st.set_page_config(page_title="北海道レンタカー最安値シミュレーター", layout="wide")
st.title("🚗 北海道レンタカー・カーシェア 動的見積もりシミュレーター")

st.markdown("""
このシミュレーターは、利用期間と実時刻を入力することで、**日跨ぎのハイシーズン料金**や、カーシェアの**夜間ナイトパック割引**を自動計算し、1円単位で正確な料金を比較します。
""")

# サイドバーに入力フォームを配置
with st.sidebar:
    st.header("📋 予約条件")
    start_d = st.date_input("出発日", value=datetime(2026, 8, 31))
    start_t = st.time_input("出発時刻", value=datetime.strptime("18:00", "%H:%M").time())

    end_d = st.date_input("返却日", value=datetime(2026, 9, 2))
    end_t = st.time_input("返却時刻", value=datetime.strptime("09:00", "%H:%M").time())

    distance = st.slider("想定走行距離 (km)", 0, 500, 150, step=10)
    use_insurance = st.checkbox("フルサポート保険に加入する", value=True)

start_dt = datetime.combine(start_d, start_t)
end_dt = datetime.combine(end_d, end_t)

if start_dt >= end_dt:
    st.error("エラー: 返却日時は出発日時より後に設定してください。")
else:
    total_hours_real = (end_dt - start_dt).total_seconds() / 3600
    st.success(f"総利用時間: **{total_hours_real:.1f} 時間** (走行距離: {distance}km)")

    # 各社のハイシーズン日数を計算
    nico_hs = count_high_season_days(start_dt, end_dt, 'niconico')
    nippon_hs = count_high_season_days(start_dt, end_dt, 'nippon')

    # 料金計算
    costs = {
        "タイムズカー": calc_times_car(start_dt, end_dt, distance, use_insurance),
        "オリックスカーシェア": calc_orix_share(start_dt, end_dt, distance, use_insurance),
        "ニコニコレンタカー": calc_niconico(start_dt, end_dt, distance, use_insurance, nico_hs),
        "ニッポンレンタカー": calc_nippon_rent(start_dt, end_dt, distance, use_insurance, nippon_hs)
    }

    # データフレーム化
    df = pd.DataFrame(list(costs.items()), columns=["会社名", "合計金額 (円)"])
    df = df.sort_values(by="合計金額 (円)")

    # 🏆 最安値の強調表示
    winner = df.iloc[0]
    st.info(f"💡 現在の条件での最安値は **{winner['会社名']}** (約 {int(winner['合計金額 (円)'])}円) です！")

    # Plotlyによるインタラクティブな棒グラフ
    fig = px.bar(
        df,
        x="会社名",
        y="合計金額 (円)",
        color="会社名",
        text="合計金額 (円)",
        title="各社の総額比較 (マウスポインタを合わせると詳細表示)",
        color_discrete_map={
            "タイムズカー": "#1f77b4",
            "オリックスカーシェア": "#17becf",
            "ニコニコレンタカー": "#ff7f0e",
            "ニッポンレンタカー": "#8c564b"
        }
    )
    fig.update_traces(texttemplate='%{text:,.0f} 円', textposition='outside')
    fig.update_layout(yaxis=dict(title='合計金額 (円)'), showlegend=False)

    # グラフの表示
    st.plotly_chart(fig, use_container_width=True)

    # 詳細ステータスの表示（デバッグ・確認用）
    with st.expander("📊 計算の詳細ステータスを確認"):
        st.write(f"- **ニコニコレンタカー ハイシーズン適用日数**: {nico_hs}日")
        st.write(f"- **ニッポンレンタカー ハイシーズン適用日数**: {nippon_hs}日")
        if start_t.hour >= 18 and end_t.hour <= 9 and (end_d - start_d).days <= 1:
            st.write(
                "- 🌙 **ナイトパック判定**: タイムズカー、オリックスカーシェアにおいて条件を満たしたため、ナイトパック料金が自動適用されています。")