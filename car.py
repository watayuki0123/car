import streamlit as st
import numpy as np
import pandas as pd
import math
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import plotly.graph_objects as go

st.set_page_config(page_title="レンタカー最安値マップ", layout="wide")

GAS_PRICE, FUEL_EFFICIENCY = 160, 20
GRID_SIZE = 60
COMP_KEYS = ['times', 'mitsui_s', 'orix_s', 'orix_r', 'toyota_s', 'toyota_r', 'niconico', 'nippon', 'nissan', 'budget', 'uqey']

# ==========================================
# 0. 共通の割引抽出ヘルパー関数
# ==========================================
def get_discount_vals(comp_key, active_discounts):
    pct, yen = 0, 0
    refuel, wash, orix_15min = False, False, False
    for item in active_discounts:
        if item[0] == comp_key:
            if item[1] == 'pct': pct = item[2]
            elif item[1] == 'yen': yen = item[2]
            elif item[1] == 'refuel': refuel = item[2]
            elif item[1] == 'wash': wash = item[2]
            elif item[1] == '15min': orix_15min = item[2]
    return pct, yen, refuel, wash, orix_15min

# ==========================================
# 1. 状態保持（Session State）とコールバック関数
# ==========================================
if "current_page" not in st.session_state:
    st.session_state.current_page = "main"

if "discounts_initialized" not in st.session_state:
    for comp in COMP_KEYS:
        st.session_state[f"d_{comp}_yen"] = 0
        st.session_state[f"d_{comp}_pct"] = 0
        st.session_state[f"d_{comp}_refuel"] = False
        st.session_state[f"d_{comp}_wash"] = False
        st.session_state[f"d_{comp}_15min"] = False
    st.session_state.discounts_initialized = True

if "sync_init" not in st.session_state:
    now = datetime.now(ZoneInfo("Asia/Tokyo"))
    st.session_state.start_d = now.date()
    st.session_state.start_t = datetime.strptime("10:00", "%H:%M").time()
    st.session_state.max_h = 72
    e_dt = datetime.combine(st.session_state.start_d, st.session_state.start_t) + timedelta(hours=72)
    st.session_state.end_d = e_dt.date()
    st.session_state.end_t = e_dt.time()
    st.session_state.sync_init = True

def sync_dates(mode):
    s_dt = datetime.combine(st.session_state.start_d, st.session_state.start_t)
    if mode in ['start', 'hours']:
        e_dt = s_dt + timedelta(hours=st.session_state.max_h)
        st.session_state.end_d = e_dt.date()
        st.session_state.end_t = e_dt.time()
    elif mode == 'end':
        e_dt = datetime.combine(st.session_state.end_d, st.session_state.end_t)
        diff_hours = (e_dt - s_dt).total_seconds() / 3600.0
        diff_hours = max(12, min(720, diff_hours))
        e_dt = s_dt + timedelta(hours=diff_hours)
        st.session_state.end_d = e_dt.date()
        st.session_state.end_t = e_dt.time()
        st.session_state.max_h = int(diff_hours)

@st.cache_data(show_spinner=False)
def load_parameters(filepath="parameters.xlsx", pax=5):
    try:
        df = pd.read_excel(filepath)
        df = df[df['pax'] == pax]
        params = {}
        for _, r in df.iterrows():
            c, s = r['company'], r['season']
            if c not in params:
                params[c] = {}
            params[c][s] = r.to_dict()
        return params
    except Exception:
        return None

# ==========================================
# 2. 各社の料金計算関数
# ==========================================
def calc_times_car(h, d, start_dt, use_ins, params, consider_biz_hours, fuel_calc_mode, comp_disc, return_breakdown=False):
    p = params['times']['normal']
    end_dt = start_dt + timedelta(hours=float(h))
    th = math.ceil(h * 4) / 4
    if th <= 6: base = min(th * p['p_hr1'], p['p_6h'])
    elif th <= 12: base = min(p['p_6h'] + (th - 6) * p['p_hr1'], p['p_12h'])
    elif th <= 24: base = min(p['p_12h'] + (th - 12) * p['p_hr1'], p['p_24h'])
    elif th <= 36: base = min(p['p_24h'] + (th - 24) * p['p_hr1'], p['p_36h'])
    elif th <= 48: base = min(p['p_36h'] + (th - 36) * p['p_hr1'], p['p_48h'])
    elif th <= 72: base = min(p['p_48h'] + (th - 48) * p['p_hr1'], p['p_72h'])
    else: base = p['p_72h'] + ((th - 72) // 24) * p['p_ex_day'] + min(((th - 72) % 24) * p['p_hr1'], p['p_ex_day'])
    if (start_dt.hour >= 18 and end_dt.hour <= 9 and (end_dt.date() - start_dt.date()).days == 1) or ((start_dt.hour >= 18 or end_dt.hour <= 9) and (end_dt.date() - start_dt.date()).days == 0):
        base = min(base, p['p_night'])
    dist_charge = np.maximum(0, d - 20) * p['p_dist']
    ins_charge = p['p_ins'] if use_ins else 0
    
    discount = comp_disc['yen']
    if comp_disc['refuel']: discount += p['p_hr1'] / 2
    if comp_disc['wash']: discount += p['p_hr1'] / 2

    if return_breakdown:
        applied_discount = min(base + dist_charge + ins_charge, discount)
        total = base + dist_charge + ins_charge - applied_discount
        bd = f"・基本(時間): {int(base):,}円\n・距離料金: {int(dist_charge):,}円\n・補償料: {int(ins_charge):,}円\n"
        if applied_discount > 0: bd += f"・割引: -{int(applied_discount):,}円"
        return total, bd
    return np.maximum(0, base + dist_charge + ins_charge - discount)

def calc_orix_share(h, d, start_dt, use_ins, params, consider_biz_hours, fuel_calc_mode, comp_disc, return_breakdown=False):
    p = params['orix_s']['normal']
    end_dt = start_dt + timedelta(hours=float(h))
    th = math.ceil(h * 4) / 4
    days, remain_th = int(th // 24), th % 24
    if remain_th == 0: remain_base = 0
    elif remain_th <= 6: remain_base = min(remain_th * p['p_hr1'], p['p_6h'])
    elif remain_th <= 12: remain_base = min(p['p_6h'] + (remain_th - 6) * p['p_hr1'], p['p_12h'])
    else: remain_base = min(p['p_12h'] + (remain_th - 12) * p['p_hr1'], p['p_24h'])
    base = (days * p['p_24h']) + remain_base
    dist_charge = d * (0 if th <= 6 else p['p_dist'])
    is_night = (start_dt.hour >= 18 and end_dt.hour <= 9 and (end_dt.date() - start_dt.date()).days == 1) or ((start_dt.hour >= 18 or end_dt.hour <= 9) and (end_dt.date() - start_dt.date()).days == 0)
    ins_charge = math.ceil(th / 24) * p['p_ins'] if use_ins else 0
    
    discount = comp_disc['yen']
    if comp_disc['15min'] and th <= 6 and remain_th * p['p_hr1'] < p['p_6h']:
        discount += p['p_hr1'] / 4

    if return_breakdown:
        time_charge = p['p_night'] if (is_night and (base + dist_charge >= p['p_night'] + d * p['p_dist'])) else base
        dist_charge = d * p['p_dist'] if (is_night and (base + dist_charge >= p['p_night'] + d * p['p_dist'])) else dist_charge
        
        applied_discount = min(time_charge, discount)
        time_charge -= applied_discount

        bd = f"・基本(時間): {int(time_charge + applied_discount):,}円\n"
        if applied_discount > 0: bd += f"・割引: -{int(applied_discount):,}円\n"
        bd += f"・距離料金: {int(dist_charge):,}円\n・補償料: {int(ins_charge):,}円"
        return time_charge + dist_charge + ins_charge, bd
    else:
        total_before = np.minimum(base + dist_charge, p['p_night'] + d * p['p_dist']) if is_night else base + dist_charge
        time_charge = np.maximum(0, total_before - dist_charge - discount)
        return time_charge + dist_charge + ins_charge

def calc_toyota_share(h, d, start_dt, use_ins, params, consider_biz_hours, fuel_calc_mode, comp_disc, return_breakdown=False):
    p = params['toyota_s']['normal']
    th = math.ceil(h * 4) / 4
    if th <= 6:
        time_charge = np.minimum(th * p['p_hr1'], p['p_6h'] + d * p['p_dist'])
    else:
        days, rem = math.floor(th / 24), th % 24
        if days == 0:
            time_charge = min(p['p_6h'] + math.ceil(th - 6) * p['p_hr2'], p['p_12h'] + math.ceil(max(0, th - 12)) * p['p_hr2'], p['p_24h'])
        else:
            time_charge = p['p_24h'] + (days - 1) * p['p_ex_day'] + min(math.ceil(rem) * p['p_hr2'], p['p_ex_day'])
        time_charge += d * p['p_dist']
    ins_charge = (p['p_ins_short'] if th <= 6 else math.ceil(th / 24) * p['p_ins']) if use_ins else 0
    
    if return_breakdown:
        applied_discount = min(time_charge, comp_disc['yen'])
        time_charge -= applied_discount
        bd = f"・時間＋距離: {int(time_charge + applied_discount):,}円\n"
        if applied_discount > 0: bd += f"・割引: -{int(applied_discount):,}円\n"
        bd += f"・補償料: {int(ins_charge):,}円"
        return time_charge + ins_charge, bd
    return np.maximum(0, time_charge - comp_disc['yen']) + ins_charge

def calc_mitsui_share(h, d, start_dt, use_ins, params, consider_biz_hours, fuel_calc_mode, comp_disc, return_breakdown=False):
    p = params['mitsui_s']['normal']
    end_dt = start_dt + timedelta(hours=float(h))
    th = math.ceil(h * 6) / 6
    if th <= 6: time_charge = min(th * p['p_hr1'], p['p_6h'])
    elif th <= 12: time_charge = min(p['p_6h'] + (th - 6) * p['p_hr1'], p['p_12h'])
    elif th <= 24: time_charge = min(p['p_12h'] + (th - 12) * p['p_hr1'], p['p_24h'])
    else: time_charge = (math.floor(th / 24) * p['p_24h']) + min((th % 24) * p['p_hr1'], p['p_24h'])
    if (start_dt.hour >= 18 and end_dt.hour <= 9 and (end_dt.date() - start_dt.date()).days == 1) or ((start_dt.hour >= 18 or end_dt.hour <= 9) and (end_dt.date() - start_dt.date()).days == 0):
        time_charge = min(time_charge, p['p_night'])
    dist_charge = d * (p['p_dist'] if th > 6 else 0)
    ins_charge = math.ceil(th / 24) * p['p_ins'] if use_ins else 0
    
    discount = comp_disc['yen']
    if comp_disc['refuel']: discount += 400
    if comp_disc['wash']: discount += 500

    if return_breakdown:
        applied_discount = min(time_charge + dist_charge + ins_charge, discount)
        total = time_charge + dist_charge + ins_charge - applied_discount
        bd = f"・時間料金: {int(time_charge):,}円\n・距離料金: {int(dist_charge):,}円\n・補償料: {int(ins_charge):,}円\n"
        if applied_discount > 0: bd += f"・割引: -{int(applied_discount):,}円"
        return total, bd
    return np.maximum(0, time_charge + dist_charge + ins_charge - discount)

def calc_niconico(h, d, start_dt, use_ins, params, consider_biz_hours, fuel_calc_mode, comp_disc, return_breakdown=False):
    p = params['niconico']['normal']
    th, md = math.ceil(h), start_dt.month * 100 + start_dt.day
    days = math.ceil(th / 24)
    base = p['p_12h'] if h <= 12 else p['p_24h'] * days
    hs = 1 if (425 <= md <= 506) or (1225 <= md) or (105 <= md) else 2 if (701 <= md <= 831) or (918 <= md <= 927) else 0
    gas = (d / p['fuel_efficiency']) * GAS_PRICE if fuel_calc_mode==1 else (d / FUEL_EFFICIENCY) * GAS_PRICE
    ins = days * p['p_ins'] if use_ins else 0
    hs_charge = (hs - 1) * 1100 + p['p_hs_surcharge']
    end_dt = start_dt + timedelta(hours=float(h))
    
    if consider_biz_hours and ((start_dt.hour < p['open_time']) or (end_dt.hour > p['close_time']) or (end_dt.hour < p['open_time'])):
        if return_breakdown: return 9999999999, "営業時間外です。"
        return 9999999999

    if return_breakdown: 
        applied_discount = min(base, comp_disc['yen'])
        base -= applied_discount
        bd = f"・基本" + ("(ハイシーズン料金)" if hs != 0 else "") + f": {int(base + applied_discount):,}円\n"
        if applied_discount > 0: bd += f"・割引: -{int(applied_discount):,}円\n"
        bd += f"・ガソリン: {int(gas):,}円\n・補償料: {int(ins):,}円\n・割増: {int(hs_charge):,}円"
        return base + gas + ins + hs_charge, bd
    return np.maximum(0, base - comp_disc['yen']) + gas + ins + hs_charge

def calc_nippon_rent(h, d, start_dt, use_ins, params, consider_biz_hours, fuel_calc_mode, comp_disc, return_breakdown=False):
    th, md = math.ceil(h), start_dt.month * 100 + start_dt.day
    days = math.ceil(th / 24)
    if (918 <= md <= 922) or (1009 <= md <= 1011) or (1225 <= md <= 1231) or (101 <= md <= 102): s = 'hs1'
    elif 701 <= md <= 831: s = 'hs2'
    else: s = 'normal'
    p = params['nippon'][s]
    num = [p['p_6h'], p['p_12h'], p['p_24h'], p['p_ex_hr'], p['p_ex_day']]
    if th <= 6: base = num[0]
    elif th <= 12: base = num[1]
    elif th <= 24: base = num[2]
    else: base = num[2] + ((th // 24) - 1) * num[4] + min((th % 24) * num[3], num[4])
    base *= 0.83 # 三井カーシェア経由17%引
    gas = (d / p['fuel_efficiency']) * GAS_PRICE if fuel_calc_mode==1 else (d / FUEL_EFFICIENCY) * GAS_PRICE
    ins = days * p['p_ins'] if use_ins else 0
    end_dt = start_dt + timedelta(hours=float(h))
    
    if consider_biz_hours and ((start_dt.hour < p['open_time']) or (end_dt.hour > p['close_time']) or (end_dt.hour < p['open_time'])):
        if return_breakdown: return 9999999999, "営業時間外です。"
        return 9999999999

    if return_breakdown: 
        applied_discount = min(base, comp_disc['yen'])
        base -= applied_discount
        bd = f"・基本(期間含): {int(base + applied_discount):,}円\n"
        if applied_discount > 0: bd += f"・割引: -{int(applied_discount):,}円\n"
        bd += f"・ガソリン: {int(gas):,}円\n・補償料: {int(ins):,}円"
        return base + gas + ins, bd
    return np.maximum(0, base - comp_disc['yen']) + gas + ins

def calc_orix_rent(h, d, start_dt, use_ins, params, consider_biz_hours, fuel_calc_mode, comp_disc, return_breakdown=False):
    th, md = math.ceil(h), start_dt.month * 100 + start_dt.day
    days = math.ceil(th / 24)
    if (918 <= md <= 926) or (1225 <= md <= 1231) or (101 <= md <= 102) or (428 <= md <= 504): s = 'hs1'
    elif 701 <= md <= 831: s = 'hs2'
    else: s = 'normal'
    p = params['orix_r'][s]
    num = [p['p_6h'], p['p_12h'], p['p_24h'], p['p_ex_hr'], p['p_ex_day']]
    if th <= 6: base = num[0]
    elif th <= 12: base = num[1]
    elif th <= 24: base = num[2]
    else: base = num[2] + ((th // 24) - 1) * num[4] + min((th % 24) * num[3], num[4])
    base *= 0.8
    gas = (d / p['fuel_efficiency']) * GAS_PRICE if fuel_calc_mode==1 else (d / FUEL_EFFICIENCY) * GAS_PRICE
    ins = days * p['p_ins'] if use_ins else 0
    end_dt = start_dt + timedelta(hours=float(h))
    
    if consider_biz_hours and ((start_dt.hour < p['open_time']) or (end_dt.hour > p['close_time']) or (end_dt.hour < p['open_time'])):
        if return_breakdown: return 9999999999, "営業時間外です。"
        return 9999999999

    if return_breakdown:
        applied_discount = min(base, comp_disc['yen'])
        base -= applied_discount
        bd = f"・基本(期間含): {int(base + applied_discount):,}円\n"
        if applied_discount > 0: bd += f"・割引: -{int(applied_discount):,}円\n"
        bd += f"・ガソリン: {int(gas):,}円\n・補償料: {int(ins):,}円"
        return base + gas + ins, bd
    return np.maximum(0, base - comp_disc['yen']) + gas + ins

def calc_nissan_rent(h, d, start_dt, use_ins, params, consider_biz_hours, fuel_calc_mode, comp_disc, return_breakdown=False):
    th, md = math.ceil(h), start_dt.month * 100 + start_dt.day
    days = math.ceil(th / 24)
    if 701 <= md <= 831: s = 'summer'
    elif 1116 <= md or md <= 430: s = 'winter'
    else: s = 'normal'
    p = params['nissan'][s]
    num = [p['p_6h'], p['p_12h'], p['p_24h'], p['p_ex_day'], p['p_ex_hr']]
    if th <= 6: base = num[0]
    elif th <= 12: base = num[1]
    elif th <= 24: base = num[2]
    else: base = num[2] + ((th // 24) - 1) * num[4] + min((th % 24) * num[3], num[1])
    if (429 <= md <= 506) or (919 <= md <= 923) or (1010 <= md <= 1012) or (1121 <= md <= 1123) or (1228 <= md) or (md <= 105) or (109 <= md <= 111) or (320 <= md <= 322):
        base += days * p['p_hs_surcharge']
    base *= 0.8
    gas = (d / p['fuel_efficiency']) * GAS_PRICE if fuel_calc_mode==1 else (d / FUEL_EFFICIENCY) * GAS_PRICE
    ins = days * p['p_ins'] if use_ins else 0
    
    if return_breakdown: 
        applied_discount = min(base, comp_disc['yen'])
        base -= applied_discount
        bd = f"・基本(割増含): {int(base + applied_discount):,}円\n"
        if applied_discount > 0: bd += f"・割引: -{int(applied_discount):,}円\n"
        bd += f"・ガソリン: {int(gas):,}円\n・補償料: {int(ins):,}円"
        return base + gas + ins, bd
    return np.maximum(0, base - comp_disc['yen']) + gas + ins

def calc_budget_rent(h, d, start_dt, use_ins, params, consider_biz_hours, fuel_calc_mode, comp_disc, return_breakdown=False):
    th, md = math.ceil(h), start_dt.month * 100 + start_dt.day
    days = math.ceil(th / 24)
    if (701 <= md <= 831) or (918 <= md <= 922) or (1225 <= md) or (md <= 102): s = 'hs'
    else: s = 'normal'
    p = params['budget'][s]
    num = [p['p_6h'], p['p_12h'], p['p_24h'], p['p_ex_hr'], p['p_ex_day']]
    if th <= 6: base = num[0]
    elif th <= 12: base = num[1]
    elif th <= 24: base = num[2]
    else: base = num[2] + ((th // 24) - 1) * num[4] + min((th % 24) * num[3], num[4])
    gas = (d / p['fuel_efficiency']) * GAS_PRICE if fuel_calc_mode==1 else (d / FUEL_EFFICIENCY) * GAS_PRICE
    ins = days * p['p_ins'] if use_ins else 0
    end_dt = start_dt + timedelta(hours=float(h))
    
    if consider_biz_hours and ((start_dt.hour < p['open_time']) or (end_dt.hour > p['close_time']) or (end_dt.hour < p['open_time'])):
        if return_breakdown: return 9999999999, "営業時間外です。"
        return 9999999999

    if return_breakdown: 
        applied_discount = min(base, comp_disc['yen'])
        base -= applied_discount
        bd = f"・基本(期間含): {int(base + applied_discount):,}円\n"
        if applied_discount > 0: bd += f"・割引: -{int(applied_discount):,}円\n"
        bd += f"・ガソリン: {int(gas):,}円\n・補償料: {int(ins):,}円"
        return base + gas + ins, bd
    return np.maximum(0, base - comp_disc['yen']) + gas + ins

def calc_toyota_rent(h, d, start_dt, use_ins, params, consider_biz_hours, fuel_calc_mode, comp_disc, return_breakdown=False):
    th, md = math.ceil(h), start_dt.month * 100 + start_dt.day
    days = math.ceil(th / 24)
    if 701 <= md <= 831: s = 'summer'
    elif (1226 <= md) or (md <= 103) or (424 <= md <= 505) or (901 <= md <= 922) or (206 <= md <= 214): s = 'special'
    elif (1101 <= md <= 1225) or (104 <= md <= 205) or (215 <= md <= 423): s = 'winter'
    else: s = 'normal'
    p = params['toyota_r'][s]
    num = [p['p_3h'], p['p_6h'], p['p_12h'], p['p_24h'], p['p_ex_day'], p['p_ex_hr']]
    base, gas, ins = [0, 0], [0, 0], [0, 0]
    
    if th <= 3: base[0] = num[0]
    elif th <= 6: base[0] = num[1]
    elif th <= 12: base[0] = num[2]
    elif th <= 24: base[0] = num[3]
    else: base[0] = num[3] + ((th // 24) - 1) * num[4] + min((th % 24) * num[5], num[4])
    gas[0] = (d / p['fuel_efficiency']) * GAS_PRICE if fuel_calc_mode==1 else (d / FUEL_EFFICIENCY) * GAS_PRICE
    ins[0] = days * p['p_ins'] if use_ins else 0
    
    if th <= 12: base[1] = params['toyota_r']['student']['p_12h']
    elif th <= 24: base[1] = params['toyota_r']['student']['p_24h']
    else: base[1] = (((th-24)//24)+1)* params['toyota_r']['student']['p_ex_day']+params['toyota_r']['student']['p_24h']
    gas[1] = (d / params['toyota_r']['student']['fuel_efficiency']) * GAS_PRICE if fuel_calc_mode==1 else (d / FUEL_EFFICIENCY) * GAS_PRICE
    ins[1] = days * params['toyota_r']['student']['p_ins'] if use_ins else 0

    end_dt = start_dt + timedelta(hours=float(h))
    if consider_biz_hours and ((start_dt.hour < p['open_time']) or (end_dt.hour > p['close_time']) or (end_dt.hour < p['open_time'])):
        if return_breakdown: return 9999999999, "営業時間外です。"
        return 9999999999
        
    if return_breakdown: 
        total0, total1 = base[0] + gas[0] + ins[0], base[1] + gas[1] + ins[1]
        is_st = 1 if total0 > total1 else 0

        applied_discount = min(base[is_st], comp_disc['yen'])
        base[is_st] -= applied_discount
        bd = "・基本" + ("(ハイシーズン料金)" if s in ['special', 'winter'] else "")
        bd += "(通常料金より学割が安いです)" if is_st == 1 else "(学割より通常料金が安いです)"
        bd += f": {int(base[is_st] + applied_discount):,}円\n"
        if applied_discount > 0: bd += f"・割引: -{int(applied_discount):,}円\n"
        bd += f"・ガソリン: {int(gas[is_st]):,}円\n・補償料: {int(ins[is_st]):,}円"
        return (base[is_st] + gas[is_st] + ins[is_st]), bd
        
    else:
        return np.minimum(np.maximum(0, base[0] - comp_disc['yen']) + gas[0] + ins[0],
                          np.maximum(0, base[1] - comp_disc['yen']) + gas[1] + ins[1])

def calc_uqey(h, d, start_dt, use_ins, params, consider_biz_hours, fuel_calc_mode, comp_disc, return_breakdown=False):
    p = params['uqey']['normal']
    th = math.ceil(h)
    days = math.ceil(th / 24)
    if th <= 3: base = p['p_3h']
    elif th <= 6: base = p['p_6h']
    elif th <= 12: base = p['p_12h']
    elif th <= 24: base = p['p_24h']
    else: base = p['p_24h'] + (th // 24) * p['p_ex_day']
    gas = (d / p['fuel_efficiency']) * GAS_PRICE if fuel_calc_mode==1 else (d / FUEL_EFFICIENCY) * GAS_PRICE
    ins = days * p['p_ins'] if use_ins else 0
    
    if return_breakdown: 
        applied_discount = min(base, comp_disc['yen'])
        base -= applied_discount
        bd = f"・基本料金: {int(base + applied_discount):,}円\n"
        if applied_discount > 0: bd += f"・割引: -{int(applied_discount):,}円\n"
        bd += f"・ガソリン: {int(gas):,}円\n・補償料: {int(ins):,}円"
        return base + gas + ins, bd
    return np.maximum(0, base - comp_disc['yen']) + gas + ins

all_companies = {
    'times': {'func': calc_times_car, 'color': '#1f77b4', 'label': 'タイムズカー(青)'},
    'orix_s': {'func': calc_orix_share, 'color': '#17becf', 'label': 'オリックスシェア(水)'},
    'orix_r': {'func': calc_orix_rent, 'color': '#9467bd', 'label': 'オリックスレンタカー(紫)'},
    'toyota_s': {'func': calc_toyota_share, 'color': '#d62728', 'label': 'トヨタシェア(赤)'},
    'toyota_r': {'func': calc_toyota_rent, 'color': '#34495e', 'label': 'トヨタレンタカー(紺)'},
    'mitsui_s': {'func': calc_mitsui_share, 'color': '#2ca02c', 'label': '三井のシェア(緑)'},
    'niconico': {'func': calc_niconico, 'color': '#ff7f0e', 'label': 'ニコニコ(橙)'},
    'uqey': {'func': calc_uqey, 'color': '#e377c2', 'label': 'Uqey(桃)'},
    'nippon': {'func': calc_nippon_rent, 'color': '#8c564b', 'label': 'ニッポンレンタカー(茶)'},
    'nissan': {'func': calc_nissan_rent, 'color': '#bcbd22', 'label': '日産レンタカー(黄緑)'},
    'budget': {'func': calc_budget_rent, 'color': '#f1c40f', 'label': 'バジェット(黄)'}
}

@st.cache_data(show_spinner=False)
def compute_all_matrices(max_hours, max_dist, start_dt, use_ins, consider_biz_hours, fuel_calc_mode, pax, active_discounts):
    params = load_parameters("parameters.xlsx", pax)
    h_vec = np.linspace(1, max_hours, GRID_SIZE)
    d_vec = np.linspace(0, max_dist, GRID_SIZE)
    H, D = np.meshgrid(h_vec, d_vec)
    matrices = {}
    
    # 辞書化して関数ごとのパース処理を省き高速化
    disc_dict = {k: {'yen':0, 'refuel':False, 'wash':False, '15min':False} for k in COMP_KEYS}
    for item in active_discounts:
        comp, dtype, val = item
        disc_dict[comp][dtype] = val

    for comp_key, c in all_companies.items():
        matrices[comp_key] = np.column_stack([
            np.broadcast_to(c['func'](h, d_vec, start_dt, use_ins, params, consider_biz_hours, fuel_calc_mode, disc_dict[comp_key]), d_vec.shape) 
            for h in h_vec
        ]).astype(int)
    return H, D, matrices

@st.cache_data(show_spinner=False)
def generate_map_data(max_hours, max_dist, start_dt, use_ins, selected_comps_tuple, consider_biz_hours, fuel_calc_mode, pax, active_discounts):
    H, D, matrices = compute_all_matrices(max_hours, max_dist, start_dt, use_ins, consider_biz_hours, fuel_calc_mode, pax, active_discounts)
    Z_list = [matrices[k] for k in selected_comps_tuple]
    active_colors = [all_companies[k]['color'] for k in selected_comps_tuple]
    names_array = np.array([all_companies[k]['label'].split('(')[0] for k in selected_comps_tuple])

    stacked = np.stack(Z_list, axis=-1)
    Z_winner = np.argmin(stacked, axis=-1)
    indices = np.argsort(stacked, axis=-1)
    sorted_prices = np.take_along_axis(stacked, indices, axis=-1)
    sorted_names = names_array[indices]
    sorted_splits = sorted_prices // pax

    n_pts = H.size
    n_comps = len(selected_comps_tuple)
    sn_flat = sorted_names.reshape(n_pts, n_comps)
    sp_flat = sorted_prices.reshape(n_pts, n_comps)
    ss_flat = sorted_splits.reshape(n_pts, n_comps)

    col_lines = []
    for k in range(n_comps):
        prefix = "👑 <b>" if k == 0 else "  "
        suffix = "</b>" if k == 0 else ""
        col_lines.append([
            f"{prefix}{n}: {p:,}円{suffix} ({pax}人割勘:約{s:,}円)<br>"
            for n, p, s in zip(sn_flat[:, k], sp_flat[:, k], ss_flat[:, k])
        ])
    hover_flat = ["".join(rows) for rows in zip(*col_lines)]
    hover_text = np.array(hover_flat, dtype=object).reshape(H.shape)
    return H, D, Z_winner, hover_text, active_colors, names_array

# ==========================================
# 3. 全画面設定ページ
# ==========================================
if st.session_state.current_page == "settings":
    st.title("⚙️ 詳細設定")
    st.markdown("各社の割引金額を設定できます。（マップに戻るボタンを押すと設定が保存されます）")
    st.write("")

    st.markdown("""
    <style>
    div[data-testid="stContainer"] {
        border-radius: 12px !important;
        transition: transform 0.2s ease, border-color 0.2s ease;
        background-color: rgba(30, 30, 30, 0.4);
    }
    div[data-testid="stContainer"]:hover { transform: translateX(4px); border-color: #888888 !important; }
    </style>
    """, unsafe_allow_html=True)

    def draw_discount_card(comp_key, title, color, features):
        with st.container(border=True):
            st.markdown(f"""
            <div style="border-left: 6px solid {color}; padding-left: 16px; margin-bottom: 12px;">
                <div style="font-size: 1.1rem; font-weight: bold; margin-bottom: 2px;">{title}</div>
            </div>
            """, unsafe_allow_html=True)
            
            has_toggles = False
            if 'refuel' in features:
                st.toggle("⛽ 給油割引 (30分)", value=st.session_state.get(f"d_{comp_key}_refuel", False), key=f"_ui_d_{comp_key}_refuel")
                has_toggles = True
            if 'wash' in features:
                st.toggle("🧽 洗車割引 (30分)", value=st.session_state.get(f"d_{comp_key}_wash", False), key=f"_ui_d_{comp_key}_wash")
                has_toggles = True
            if '15min' in features:
                st.toggle("🕒 6時間以内の通常利用で15分無料", value=st.session_state.get(f"d_{comp_key}_15min", False), key=f"_ui_d_{comp_key}_15min")
                has_toggles = True
                
            if has_toggles:
                st.markdown("<hr style='margin: 8px 0; border: none; border-top: 1px solid #444;'>", unsafe_allow_html=True)
                
            st.number_input("割引額 (円)", min_value=0, step=1, value=st.session_state.get(f"d_{comp_key}_yen", 0), key=f"_ui_d_{comp_key}_yen")

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        draw_discount_card("times", "タイムズカー (青)", "#1f77b4", ['refuel', 'wash'])
        draw_discount_card("mitsui_s", "三井のシェア (緑)", "#2ca02c", ['refuel', 'wash'])
        draw_discount_card("orix_s", "オリックスシェア (水)", "#17becf", ['15min'])
        draw_discount_card("toyota_s", "トヨタシェア (赤)", "#d62728", [])
        draw_discount_card("orix_r", "オリックスレンタカー (紫)", "#9467bd", [])
        draw_discount_card("toyota_r", "トヨタレンタカー (紺)", "#34495e", [])
        draw_discount_card("budget", "バジェット (黄)", "#f1c40f", [])
        draw_discount_card("nippon", "ニッポンレンタカー (茶)", "#8c564b", [])
        draw_discount_card("nissan", "日産レンタカー (黄緑)", "#bcbd22", [])
        draw_discount_card("niconico", "ニコニコ (橙)", "#ff7f0e", [])
        draw_discount_card("uqey", "Uqey (桃)", "#e377c2", [])
        
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("◀ マップに戻る", type="primary", use_container_width=True):
            for comp in COMP_KEYS:
                for f in ['refuel', 'wash', '15min', 'yen']:
                    ui_key = f"_ui_d_{comp}_{f}"
                    if ui_key in st.session_state:
                        st.session_state[f"d_{comp}_{f}"] = st.session_state[ui_key]
            st.session_state.current_page = "main"
            st.rerun()

# ==========================================
# 4. メイン画面
# ==========================================
elif st.session_state.current_page == "main":
    st.title("北海道レンタカー・カーシェア最安値マップ")

    if st.button("⚙️ 全画面の詳細設定を開く"):
        st.session_state.current_page = "settings"
        st.rerun()

    st.markdown("サイドバーで条件変更。マップの任意の場所をクリックすると下部に各社の詳細な計算式と内訳が瞬時に表示されます。")

    discounts = []
    for comp in COMP_KEYS:
        if st.session_state.get(f"d_{comp}_refuel"): discounts.append((comp, 'refuel', True))
        if st.session_state.get(f"d_{comp}_wash"): discounts.append((comp, 'wash', True))
        if st.session_state.get(f"d_{comp}_15min"): discounts.append((comp, '15min', True))
        yen = st.session_state.get(f"d_{comp}_yen", 0)
        if yen > 0: discounts.append((comp, 'yen', yen))
    active_discounts = frozenset(discounts)

    with st.sidebar:
        st.header("⚙️条件")
        pax = st.selectbox("乗車人数", [2, 3, 4, 5, 6, 7, 8], index=3, key="pax")
        col1, col2 = st.columns(2)
        with col1: st.date_input("出発日", key="start_d", on_change=sync_dates, args=('start',))
        with col2: st.time_input("出発時刻", key="start_t", on_change=sync_dates, args=('start',))
        start_dt = datetime.combine(st.session_state.start_d, st.session_state.start_t)
        
        col3, col4 = st.columns(2)
        with col3: st.date_input("返却日", key="end_d", on_change=sync_dates, args=('end',))
        with col4: st.time_input("返却時刻", key="end_t", on_change=sync_dates, args=('end',))
        st.caption("返却時刻と最大時間は連動します。")
        
        max_hours = st.number_input("最大時間(h)", min_value=12, max_value=720, step=12, key="max_h", on_change=sync_dates, args=('hours',))
        use_ins = st.toggle("フルサポート保険", value=True, key="use_ins")
        consider_biz_hours = st.toggle("営業時間を考慮する", value=True, key="consider_biz_hours")
        fuel_calc_mode = st.radio("ガソリン代の計算方式", options=range(2), format_func=lambda x: ["固定燃費 (165円/L・20km/L)", "Excelの実燃費データに従う"][x], index=0, key="fuel_calc_mode")
        max_dist = st.number_input("最大距離(km)", 100, 5000, 1000, 100, key="max_dist")
        
        selected_comps = st.multiselect(
            "比較会社",
            options=list(all_companies.keys()),
            default=list(all_companies.keys()),
            format_func=lambda x: all_companies[x]['label'],
            key="selected_comps"
        )
    params = load_parameters("parameters.xlsx", pax)
    if not params:
        st.error("Excelエラー")
        st.stop()

    @st.fragment
    def render_map_and_details():
        if not selected_comps:
            st.warning("会社を選択してください")
            return

        H, D, Z_winner, hover_text, active_colors, names_array = generate_map_data(
            max_hours, max_dist, start_dt, use_ins, tuple(selected_comps), consider_biz_hours, fuel_calc_mode, pax, active_discounts
        )

        sel_h, sel_d = None, None
        if "map_chart" in st.session_state:
            pts = st.session_state["map_chart"].get("selection", {}).get("points", [])
            if pts: sel_h, sel_d = pts[0]["x"], pts[0]["y"]

        N = len(active_colors)
        colorscale = []
        for i, c in enumerate(active_colors):
            colorscale += [[i / N, c], [(i + 1) / N, c]]

        fig = go.Figure()
        fig.add_trace(go.Heatmap(
            x=H[0, :], y=D[:, 0], z=Z_winner,
            colorscale=colorscale, zmin=-0.5, zmax=N - 0.5, showscale=True,
            colorbar=dict(title="<b>最安値</b>", tickmode="array", tickvals=np.arange(N), ticktext=names_array),
            hoverinfo="skip", hovertemplate=None
        ))
        fig.add_trace(go.Scatter(
            x=H.flatten(), y=D.flatten(), mode='markers',
            marker=dict(color='rgba(0,0,0,0)', size=8),
            customdata=hover_text.flatten(),
            hovertemplate="<b>利用時間: %{x:.1f}h / 距離: %{y:.0f}km</b><br>---<br>%{customdata}<extra></extra>",
            showlegend=False
        ))
        if sel_h is not None and sel_d is not None:
            fig.add_trace(go.Scatter(
                x=[sel_h], y=[sel_d], mode='markers+text',
                marker=dict(color='#ff2b2b', size=16, line=dict(color='white', width=2)),
                text=['📍'], textfont=dict(size=36), textposition='top center',
                hoverinfo='skip', showlegend=False
            ))

        fig.update_layout(
            xaxis_title="利用時間(時間)", yaxis_title="想定距離(km)",
            height=650, margin=dict(l=40, r=10, t=40, b=40), clickmode="event+select"
        )
        st.plotly_chart(fig, use_container_width=True, on_select="rerun", selection_mode="points", key="map_chart", config={'displayModeBar': False})

        if sel_h is not None and sel_d is not None:
            st.markdown("---")
            st.subheader(f"📍 料金詳細 (利用時間: {sel_h:.1f}h / 距離: {sel_d:.0f}km)")
            
            disc_dict = {k: {'yen':0, 'refuel':False, 'wash':False, '15min':False} for k in COMP_KEYS}
            for item in active_discounts:
                comp, dtype, val = item
                disc_dict[comp][dtype] = val

            bds = []
            for c_key in selected_comps:
                c = all_companies[c_key]
                pr, tx = c['func'](sel_h, sel_d, start_dt, use_ins, params, consider_biz_hours, fuel_calc_mode, disc_dict[c_key], True)
                bds.append((pr, c['label'], tx, c['color']))
            bds.sort(key=lambda x: x[0])
            
            st.markdown("""
            <style>
            .price-card { background-color: #1e1e1e; border-radius: 12px; padding: 16px 24px; margin-bottom: 12px; display: flex; align-items: center; justify-content: space-between; box-shadow: 0 4px 6px rgba(0,0,0,0.3); border-left: 8px solid transparent; transition: transform 0.2s ease; }
            .price-card:hover { transform: translateX(4px); }
            .rank-winner { border-left-color: #ffd700; background: linear-gradient(90deg, rgba(255,215,0,0.1) 0%, rgba(30,30,30,1) 100%); }
            .card-left { flex: 1; }
            .card-right { text-align: right; min-width: 150px; }
            .comp-name { font-size: 1.2rem; font-weight: bold; color: #ffffff; margin-bottom: 4px; }
            .breakdown { font-size: 0.85rem; color: #aaaaaa; white-space: pre-wrap; }
            .total-price { font-size: 1.8rem; font-weight: 800; color: #ffffff; }
            .split-price { font-size: 0.9rem; color: #888888; }
            .rank-badge { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 0.8rem; font-weight: bold; margin-right: 8px; }
            </style>
            """, unsafe_allow_html=True)

            for i, (pr, lb, tx, color) in enumerate(bds):
                if pr >= 9999999999: pr_str, split_str = "利用不可", "営業時間外"
                else: pr_str, split_str = f"¥{int(pr):,}", f"1人あたり: ¥{int(pr) // pax:,}"

                winner_class = "rank-winner" if i == 0 else ""
                badge_bg, badge_text, rank_str = ("#ffd700", "#000000", "👑 1位") if i == 0 else ("#444444", "#ffffff", f"{i+1}位")

                card_html = f"""
                <div class="price-card {winner_class}" style="border-left-color: {color};">
                    <div class="card-left">
                        <div class="comp-name"><span class="rank-badge" style="background-color: {badge_bg}; color: {badge_text};">{rank_str}</span>{lb}</div>
                        <div class="breakdown">{tx.replace('\n', '<br>')}</div>
                    </div>
                    <div class="card-right"><div class="total-price">{pr_str}</div><div class="split-price">{split_str}</div></div>
                </div>
                """
                st.markdown(card_html, unsafe_allow_html=True)

    render_map_and_details()
