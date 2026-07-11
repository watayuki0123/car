import streamlit as st
import numpy as np
import math
from datetime import datetime, timedelta
import plotly.graph_objects as go

st.set_page_config(page_title="レンタカー最安値マップ", layout="wide")
st.title("🚗 北海道 レンタカー・カーシェア 動的最安値マップ")
st.markdown(
    "サイドバーの条件を変更すると、マップがリアルタイムで再計算されます。グラフ上の色付きエリアにマウスを乗せると、**全社の具体的な金額と、3人で割り勘した場合の1人あたりの目安金額**がポップアップで一覧表示されます。")
GAS_PRICE = 170
FUEL_EFFICIENCY = 15


def calc_times_car(h, d, start_dt, use_ins):
    end_dt = start_dt + timedelta(hours=float(h))
    th = math.ceil(h * 4) / 4
    if th <= 6:
        base = min(th * 880, 4290)
    elif th <= 12:
        base = min(4290 + (th - 6) * 880, 5500)
    elif th <= 24:
        base = min(5500 + (th - 12) * 880, 6600)
    elif th <= 36:
        base = min(6600 + (th - 24) * 880, 8800)
    elif th <= 48:
        base = min(8800 + (th - 36) * 880, 9900)
    elif th <= 72:
        base = min(9900 + (th - 48) * 880, 14300)
    else:
        base = 14300 + ((th - 72) // 24) * 5500 + min(((th - 72) % 24) * 880, 5500)
    if start_dt.hour >= 18 and end_dt.hour <= 9 and (end_dt.date() - start_dt.date()).days <= 1: base = min(base, 2640)
    return base + max(0, d - 20) * 20 + (550 if use_ins else 0)


def calc_orix_share(h, d, start_dt, use_ins):
    end_dt = start_dt + timedelta(hours=float(h))
    th = math.ceil(h * 4) / 4
    days, remain_th = int(th // 24), th % 24
    if remain_th == 0:
        remain_base = 0
    elif remain_th <= 6:
        remain_base = min(remain_th * 960, 4190)
    elif remain_th <= 12:
        remain_base = min(4190 + (remain_th - 6) * 960, 5390)
    else:
        remain_base = min(5390 + (remain_th - 12) * 960, 7890)
    base = (days * 7890) + remain_base
    if start_dt.hour >= 20 and end_dt.hour <= 9 and (end_dt.date() - start_dt.date()).days <= 1: base = min(base, 3480)
    return base + (0 if th <= 6 else d * 20) + (math.ceil(th / 24) * 660 if use_ins else 0)


def calc_toyota_share(h, d, start_dt, use_ins):
    th = math.ceil(h * 4) / 4
    if th <= 6:
        time_charge = min(th * 880, 5610 + d * 16)
    else:
        days, rem = math.floor(th / 24), th % 24
        if days == 0:
            time_charge = min(5610 + math.ceil(th - 6) * 1210, 5940 + math.ceil(max(0, th - 12)) * 1210, 7810)
        else:
            time_charge = 7810 + (days - 1) * 6600 + min(math.ceil(rem) * 1210, 6600)
        time_charge += d * 16
    ins_charge = (330 if th <= 6 else math.ceil(th / 24) * 1650) if use_ins else 0
    return time_charge + ins_charge


def calc_mitsui_share(h, d, start_dt, use_ins):
    end_dt = start_dt + timedelta(hours=float(h))
    th = math.ceil(h * 6) / 6
    if th <= 6:
        time_charge = min(th * 900, 4280)
    elif th <= 12:
        time_charge = min(4280 + (th - 6) * 900, 5700)
    elif th <= 24:
        time_charge = min(5700 + (th - 12) * 900, 7300)
    else:
        time_charge = (math.floor(th / 24) * 7300) + min((th % 24) * 900, 7300)
    if start_dt.hour >= 18 and end_dt.hour <= 9 and (end_dt.date() - start_dt.date()).days <= 1: time_charge = min(
        time_charge, 3200)
    return time_charge + (d * (21 if th > 6 else 0)) + (math.ceil(th / 24) * 550 if use_ins else 0)


def calc_niconico(h, d, start_dt, use_ins):
    th, md = math.ceil(h), start_dt.month * 100 + start_dt.day
    days = math.ceil(th / 24)
    base = 2525 if h <= 12 else 5060 * days
    hs = 1 if (425 <= md <= 506) or (1225 <= md) or (105 <= md) else 2 if (701 <= md <= 831) or (
                918 <= md <= 927) else 0
    return base + (d / FUEL_EFFICIENCY) * GAS_PRICE + (days * 2200 if use_ins else 0) + hs * 1100


def calc_nippon_rent(h, d, start_dt, use_ins):
    th, md = math.ceil(h), start_dt.month * 100 + start_dt.day
    days = math.ceil(th / 24)
    if (918 <= md <= 922) or (1009 <= md <= 1011) or (1225 <= md <= 1231) or (101 <= md <= 102):
        num = [7480, 8140, 10010, 1320]
    elif 701 <= md <= 831:
        num = [9350, 10120, 12430, 1650]
    else:
        num = [7150, 7810, 9570, 1320]
    if th <= 6:
        base = num[0]
    elif th <= 12:
        base = num[1]
    elif th <= 24:
        base = num[2]
    else:
        base = num[2] + ((th // 24) - 1) * num[1] + min((th % 24) * num[3], num[1])
    return base + (d / FUEL_EFFICIENCY) * GAS_PRICE + (days * 2200 if use_ins else 0)


def calc_orix_rent(h, d, start_dt, use_ins):
    th, md = math.ceil(h), start_dt.month * 100 + start_dt.day
    days = math.ceil(th / 24)
    if (918 <= md <= 926) or (1225 <= md <= 1231) or (101 <= md <= 102) or (428 <= md <= 504):
        num = [8580, 9570, 11880, 1650]
    elif 701 <= md <= 831:
        num = [10010, 11110, 13860, 1870]
    else:
        num = [7150, 7920, 9900, 1320]
    if th <= 6:
        base = num[0]
    elif th <= 12:
        base = num[1]
    elif th <= 24:
        base = num[2]
    else:
        base = num[2] + ((th // 24) - 1) * num[1] + min((th % 24) * num[3], num[1])
    return base + (d / FUEL_EFFICIENCY) * GAS_PRICE + (days * 1100 if use_ins else 0)


def calc_nissan_rent(h, d, start_dt, use_ins):
    th, md = math.ceil(h), start_dt.month * 100 + start_dt.day
    days = math.ceil(th / 24)
    if 701 <= md <= 831:
        num = [10032, 10763, 12435, 9405, 1881]
    elif 1116 <= md or md <= 430:
        num = [7733, 8464, 10136, 8151, 1358]
    else:
        num = [6897, 7628, 9300, 7315, 1358]
    if th <= 6:
        base = num[0]
    elif th <= 12:
        base = num[1]
    elif th <= 24:
        base = num[2]
    else:
        base = num[2] + ((th // 24) - 1) * num[1] + min((th % 24) * num[3], num[1])
    if (429 <= md <= 506) or (919 <= md <= 923) or (1010 <= md <= 1012) or (1121 <= md <= 1123) or (1228 <= md) or (
            md <= 105) or (109 <= md <= 111) or (320 <= md <= 322): base += days * 1650
    return base + (d / FUEL_EFFICIENCY) * GAS_PRICE + (days * 2200 if use_ins else 0)


def calc_budget_rent(h, d, start_dt, use_ins):
    th, md = math.ceil(h), start_dt.month * 100 + start_dt.day
    days = math.ceil(th / 24)
    if (701 <= md <= 831) or (918 <= md <= 922) or (1225 <= md) or (md <= 102):
        num = [9009, 9900, 11286, 1485]
    else:
        num = [5940, 6336, 7722, 990]
    if th <= 6:
        base = num[0]
    elif th <= 12:
        base = num[1]
    elif th <= 24:
        base = num[2]
    else:
        base = num[2] + ((th // 24) - 1) * num[1] + min((th % 24) * num[3], num[1])
    return base + (d / FUEL_EFFICIENCY) * GAS_PRICE + (days * 1430 if use_ins else 0)


def calc_toyota_rent(h, d, start_dt, use_ins):
    th, md = math.ceil(h), start_dt.month * 100 + start_dt.day
    days = math.ceil(th / 24)
    if 701 <= md <= 831:
        num = [8624, 8624, 9240, 12012, 10164, 1848]
    elif (1226 <= md) or (md <= 103) or (424 <= md <= 505) or (901 <= md <= 922) or (206 <= md <= 214):
        num = [7392, 7392, 7920, 10296, 8712, 1584]
    elif (1101 <= md <= 1225) or (104 <= md <= 205) or (215 <= md <= 423):
        num = [6776, 6776, 7260, 9438, 7986, 1452]
    else:
        num = [4312, 6160, 6600, 8580, 7260, 1320]
    if th <= 3:
        base = num[0]
    elif th <= 6:
        base = num[1]
    elif th <= 12:
        base = num[2]
    elif th <= 24:
        base = num[3]
    else:
        base = num[3] + ((th // 24) - 1) * num[4] + min((th % 24) * num[5], num[4])
    return base + (d / FUEL_EFFICIENCY) * GAS_PRICE + (days * 1650 if use_ins else 0)


def calc_uqey(h, d, start_dt, use_ins):
    th = math.ceil(h)
    days = math.ceil(th / 24)
    if th <= 3:
        base = 4400
    elif th <= 6:
        base = 6600
    elif th <= 12:
        base = 7700
    elif th <= 24:
        base = 11000
    else:
        base = 11000 + (th // 24) * 9350
    return base + (d / FUEL_EFFICIENCY) * GAS_PRICE + (days * 3300 if use_ins else 0)


all_companies = {
    'times': {'func': calc_times_car, 'color': '#1f77b4', 'label': 'タイムズカー (青)'},
    'orix_s': {'func': calc_orix_share, 'color': '#17becf', 'label': 'オリックスシェア (水色)'},
    'orix_r': {'func': calc_orix_rent, 'color': '#9467bd', 'label': 'オリックスレンタカー (紫)'},
    'toyota_s': {'func': calc_toyota_share, 'color': '#d62728', 'label': 'トヨタシェア (赤)'},
    'toyota_r': {'func': calc_toyota_rent, 'color': '#34495e', 'label': 'トヨタレンタカー (紺・グレー)'},
    'mitsui_s': {'func': calc_mitsui_share, 'color': '#2ca02c', 'label': '三井のシェア (緑)'},
    'niconico': {'func': calc_niconico, 'color': '#ff7f0e', 'label': 'ニコニコ (オレンジ)'},
    'uqey': {'func': calc_uqey, 'color': '#e377c2', 'label': 'Uqey (ピンク)'},
    'nippon': {'func': calc_nippon_rent, 'color': '#8c564b', 'label': 'ニッポンレンタカー (茶)'},
    'nissan': {'func': calc_nissan_rent, 'color': '#bcbd22', 'label': '日産レンタカー (オリーブ)'},
    'budget': {'func': calc_budget_rent, 'color': '#f1c40f', 'label': 'バジェット (黄)'}
}

with st.sidebar:
    st.header("⚙️ シミュレーション条件")
    st.subheader("予約日時")
    start_dt = datetime.combine(st.date_input("出発日", value=datetime(2026, 8, 10)),
                                st.time_input("出発時刻", value=datetime.strptime("10:00", "%H:%M").time()))
    use_insurance_flag = st.checkbox("フルサポート保険に加入する", value=True)
    st.markdown("---")
    st.subheader("マップの描画上限")
    max_hours = st.number_input("最大利用時間 (時間)", min_value=12, max_value=720, value=72, step=12)
    max_dist = st.number_input("最大走行距離 (km)", min_value=100, max_value=5000, value=1000, step=100)
    st.markdown("---")
    st.subheader("比較する会社")
    selected_comps = st.multiselect("会社を選択", options=list(all_companies.keys()),
                                    default=list(all_companies.keys()), format_func=lambda x: all_companies[x]['label'])

if not selected_comps:
    st.warning("👈 左側のパネルから、比較する会社を1つ以上選択してください。")
else:
    with st.spinner("マップを計算中..."):
        hours_range = np.linspace(1, max_hours, 150)
        distance_range = np.linspace(0, max_dist, 150)
        H, D = np.meshgrid(hours_range, distance_range)
        Z_list, active_colors, active_labels = [], [], []
        for comp_key in selected_comps:
            c = all_companies[comp_key]
            Z_list.append(np.vectorize(lambda h, d, f=c['func']: f(h, d, start_dt, use_insurance_flag))(H, D))
            active_colors.append(c['color'])
            active_labels.append(c['label'])
        stacked = np.stack(Z_list, axis=-1).astype(int)
        Z_winner = np.argmin(stacked, axis=-1)
        indices = np.argsort(stacked, axis=-1)
        sorted_prices = np.take_along_axis(stacked, indices, axis=-1)
        names_array = np.array([lbl.split(' ')[0] for lbl in active_labels])
        sorted_names = names_array[indices]
        sorted_splits = sorted_prices // 3
        hover_text = np.full(H.shape, "", dtype=object)
        for k in range(len(active_colors)):
            n_flat, p_flat, s_flat = sorted_names[:, :, k].flat, sorted_prices[:, :, k].flat, sorted_splits[:, :,
                                                                                              k].flat
            prefix = "👑 <b>" if k == 0 else "  "
            suffix = "</b>" if k == 0 else ""
            lines = [f"{prefix}{n}: {p:,}円{suffix} (3人割勘: 約{s:,}円/人)<br>" for n, p, s in
                     zip(n_flat, p_flat, s_flat)]
            hover_text += np.array(lines).reshape(H.shape)
        N = len(active_colors)
        colorscale = []
        for i, c in enumerate(active_colors): colorscale += [[i / N, c], [(i + 1) / N, c]]

        fig = go.Figure(
            data=go.Heatmap(x=hours_range, y=distance_range, z=Z_winner, colorscale=colorscale, zmin=-0.5, zmax=N - 0.5,
                            showscale=True,
                            colorbar=dict(title="<b>最安値の会社</b>", tickmode="array", tickvals=np.arange(N),
                                          ticktext=names_array, len=1.0), customdata=hover_text,
                            hovertemplate="<b>利用時間: %{x:.1f}時間 / 走行距離: %{y:.0f}km</b><br>-----------------------------<br>%{customdata}<extra></extra>"))
        fig.update_layout(xaxis_title="利用時間 (時間)", yaxis_title="想定走行距離 (km)", height=700,
                          margin=dict(l=60, r=60, t=40, b=60))
        st.plotly_chart(fig, use_container_width=True)
