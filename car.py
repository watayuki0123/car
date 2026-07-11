import streamlit as st
import numpy as np
import pandas as pd
import math
from datetime import datetime,timedelta
import plotly.graph_objects as go
st.set_page_config(page_title="レンタカー最安値マップ",layout="wide")
st.title("北海道レンタカー・カーシェア最安値マップ")
st.markdown("サイドバーで条件変更。マップの任意の場所をクリックすると下部に各社の詳細な計算式と内訳が瞬時に表示されます。このマップは北大周辺に居住し、大学生である人に向けて作ったものです。車代の情報は2026/7/11のもので2027/3以降は正常に動作しません。")
GAS_PRICE,FUEL_EFFICIENCY=170,15
@st.cache_data(show_spinner=False)
def load_parameters(filepath="parameters.xlsx",pax=5):
    try:
        df=pd.read_excel(filepath);df=df[df['pax']==pax];params={}
        for _,r in df.iterrows():
            c,s=r['company'],r['season']
            if c not in params:params[c]={}
            params[c][s]=r.to_dict()
        return params
    except:return None
def calc_times_car(h,d,start_dt,use_ins,params,return_breakdown=False):
    p=params['times']['normal'];end_dt=start_dt+timedelta(hours=float(h));th=math.ceil(h*4)/4
    if th<=6:base=min(th*p['p_hr1'],p['p_6h'])
    elif th<=12:base=min(p['p_6h']+(th-6)*p['p_hr1'],p['p_12h'])
    elif th<=24:base=min(p['p_12h']+(th-12)*p['p_hr1'],p['p_24h'])
    elif th<=36:base=min(p['p_24h']+(th-24)*p['p_hr1'],p['p_36h'])
    elif th<=48:base=min(p['p_36h']+(th-36)*p['p_hr1'],p['p_48h'])
    elif th<=72:base=min(p['p_48h']+(th-48)*p['p_hr1'],p['p_72h'])
    else:base=p['p_72h']+((th-72)//24)*p['p_ex_day']+min(((th-72)%24)*p['p_hr1'],p['p_ex_day'])
    if start_dt.hour>=18 and end_dt.hour<=9 and(end_dt.date()-start_dt.date()).days<=1:base=min(base,p['p_night'])
    dist_charge=max(0,d-20)*p['p_dist'];ins_charge=p['p_ins']if use_ins else 0;total=base+dist_charge+ins_charge
    if return_breakdown:return total,f"・基本(時間): {int(base):,}円\n・距離料金: {int(dist_charge):,}円\n・補償料: {int(ins_charge):,}円"
    return total
def calc_orix_share(h,d,start_dt,use_ins,params,return_breakdown=False):
    p=params['orix_s']['normal'];end_dt=start_dt+timedelta(hours=float(h));th=math.ceil(h*4)/4;days,remain_th=int(th//24),th%24
    if remain_th==0:remain_base=0
    elif remain_th<=6:remain_base=min(remain_th*p['p_hr1'],p['p_6h'])
    elif remain_th<=12:remain_base=min(p['p_6h']+(remain_th-6)*p['p_hr1'],p['p_12h'])
    else:remain_base=min(p['p_12h']+(remain_th-12)*p['p_hr1'],p['p_24h'])
    base=(days*p['p_24h'])+remain_base
    if start_dt.hour>=20 and end_dt.hour<=9 and(end_dt.date()-start_dt.date()).days<=1:base=min(base,p['p_night'])
    dist_charge=0 if th<=6 else d*p['p_dist'];ins_charge=math.ceil(th/24)*p['p_ins']if use_ins else 0;total=base+dist_charge+ins_charge
    if return_breakdown:return total,f"・基本(時間): {int(base):,}円\n・距離料金: {int(dist_charge):,}円\n・補償料: {int(ins_charge):,}円"
    return total
def calc_toyota_share(h,d,start_dt,use_ins,params,return_breakdown=False):
    p=params['toyota_s']['normal'];th=math.ceil(h*4)/4
    if th<=6:time_charge=min(th*p['p_hr1'],p['p_6h']+d*p['p_dist'])
    else:
        days,rem=math.floor(th/24),th%24
        if days==0:time_charge=min(p['p_6h']+math.ceil(th-6)*p['p_hr2'],p['p_12h']+math.ceil(max(0,th-12))*p['p_hr2'],p['p_24h'])
        else:time_charge=p['p_24h']+(days-1)*p['p_ex_day']+min(math.ceil(rem)*p['p_hr2'],p['p_ex_day'])
        time_charge+=d*p['p_dist']
    ins_charge=(p['p_ins_short']if th<=6 else math.ceil(th/24)*p['p_ins'])if use_ins else 0;total=time_charge+ins_charge
    if return_breakdown:return total,f"・時間＋距離: {int(time_charge):,}円\n・補償料: {int(ins_charge):,}円"
    return total
def calc_mitsui_share(h,d,start_dt,use_ins,params,return_breakdown=False):
    p=params['mitsui_s']['normal'];end_dt=start_dt+timedelta(hours=float(h));th=math.ceil(h*6)/6
    if th<=6:time_charge=min(th*p['p_hr1'],p['p_6h'])
    elif th<=12:time_charge=min(p['p_6h']+(th-6)*p['p_hr1'],p['p_12h'])
    elif th<=24:time_charge=min(p['p_12h']+(th-12)*p['p_hr1'],p['p_24h'])
    else:time_charge=(math.floor(th/24)*p['p_24h'])+min((th%24)*p['p_hr1'],p['p_24h'])
    if start_dt.hour>=18 and end_dt.hour<=9 and(end_dt.date()-start_dt.date()).days<=1:time_charge=min(time_charge,p['p_night'])
    dist_charge=d*(p['p_dist']if th>6 else 0);ins_charge=math.ceil(th/24)*p['p_ins']if use_ins else 0;total=time_charge+dist_charge+ins_charge
    if return_breakdown:return total,f"・時間料金: {int(time_charge):,}円\n・距離料金: {int(dist_charge):,}円\n・補償料: {int(ins_charge):,}円"
    return total
def calc_niconico(h,d,start_dt,use_ins,params,return_breakdown=False):
    p=params['niconico']['normal'];th,md=math.ceil(h),start_dt.month*100+start_dt.day;days=math.ceil(th/24)
    base=p['p_12h']if h<=12 else p['p_24h']*days
    hs=1 if(425<=md<=506)or(1225<=md)or(105<=md)else 2 if(701<=md<=831)or(918<=md<=927)else 0
    gas=(d/FUEL_EFFICIENCY)*GAS_PRICE;ins=days*p['p_ins']if use_ins else 0;hs_charge=(hs-1)*1100+p['p_hs_surcharge'];total=base+gas+ins+hs_charge
    if return_breakdown:return total,f"・基本: {int(base):,}円\n・ガソリン: {int(gas):,}円\n・補償料: {int(ins):,}円\n・割増: {int(hs_charge):,}円"
    return total
def calc_nippon_rent(h,d,start_dt,use_ins,params,return_breakdown=False):
    th,md=math.ceil(h),start_dt.month*100+start_dt.day;days=math.ceil(th/24)
    if(918<=md<=922)or(1009<=md<=1011)or(1225<=md<=1231)or(101<=md<=102):s='hs1'
    elif 701<=md<=831:s='hs2'
    else:s='normal'
    p=params['nippon'][s];num=[p['p_6h'],p['p_12h'],p['p_24h'],p['p_ex_hr'],p['p_ex_day']]
    if th<=6:base=num[0]
    elif th<=12:base=num[1]
    elif th<=24:base=num[2]
    else:base=num[2]+((th//24)-1)*num[4]+min((th%24)*num[3],num[4])
    gas=(d/FUEL_EFFICIENCY)*GAS_PRICE;ins=days*p['p_ins']if use_ins else 0;total=base+gas+ins
    if return_breakdown:return total,f"・基本(期間含): {int(base):,}円\n・ガソリン: {int(gas):,}円\n・補償料: {int(ins):,}円"
    return total
def calc_orix_rent(h,d,start_dt,use_ins,params,return_breakdown=False):
    th,md=math.ceil(h),start_dt.month*100+start_dt.day;days=math.ceil(th/24)
    if(918<=md<=926)or(1225<=md<=1231)or(101<=md<=102)or(428<=md<=504):s='hs1'
    elif 701<=md<=831:s='hs2'
    else:s='normal'
    p=params['orix_r'][s];num=[p['p_6h'],p['p_12h'],p['p_24h'],p['p_ex_hr'],p['p_ex_day']]
    if th<=6:base=num[0]
    elif th<=12:base=num[1]
    elif th<=24:base=num[2]
    else:base=num[2]+((th//24)-1)*num[4]+min((th%24)*num[3],num[4])
    gas=(d/FUEL_EFFICIENCY)*GAS_PRICE;ins=days*p['p_ins']if use_ins else 0;total=base+gas+ins
    if return_breakdown:return total,f"・基本(期間含): {int(base):,}円\n・ガソリン: {int(gas):,}円\n・補償料: {int(ins):,}円"
    return total
def calc_nissan_rent(h,d,start_dt,use_ins,params,return_breakdown=False):
    th,md=math.ceil(h),start_dt.month*100+start_dt.day;days=math.ceil(th/24)
    if 701<=md<=831:s='summer'
    elif 1116<=md or md<=430:s='winter'
    else:s='normal'
    p=params['nissan'][s];num=[p['p_6h'],p['p_12h'],p['p_24h'],p['p_ex_day'],p['p_ex_hr']]
    if th<=6:base=num[0]
    elif th<=12:base=num[1]
    elif th<=24:base=num[2]
    else:base=num[2]+((th//24)-1)*num[1]+min((th%24)*num[3],num[1])
    if(429<=md<=506)or(919<=md<=923)or(1010<=md<=1012)or(1121<=md<=1123)or(1228<=md)or(md<=105)or(109<=md<=111)or(320<=md<=322):base+=days*p['p_hs_surcharge']
    gas=(d/FUEL_EFFICIENCY)*GAS_PRICE;ins=days*p['p_ins']if use_ins else 0;total=base+gas+ins
    if return_breakdown:return total,f"・基本(割増含): {int(base):,}円\n・ガソリン: {int(gas):,}円\n・補償料: {int(ins):,}円"
    return total
def calc_budget_rent(h,d,start_dt,use_ins,params,return_breakdown=False):
    th,md=math.ceil(h),start_dt.month*100+start_dt.day;days=math.ceil(th/24)
    if(701<=md<=831)or(918<=md<=922)or(1225<=md)or(md<=102):s='hs'
    else:s='normal'
    p=params['budget'][s];num=[p['p_6h'],p['p_12h'],p['p_24h'],p['p_ex_hr'],p['p_ex_day']]
    if th<=6:base=num[0]
    elif th<=12:base=num[1]
    elif th<=24:base=num[2]
    else:base=num[2]+((th//24)-1)*num[4]+min((th%24)*num[3],num[4])
    gas=(d/FUEL_EFFICIENCY)*GAS_PRICE;ins=days*p['p_ins']if use_ins else 0;total=base+gas+ins
    if return_breakdown:return total,f"・基本(期間含): {int(base):,}円\n・ガソリン: {int(gas):,}円\n・補償料: {int(ins):,}円"
    return total
def calc_toyota_rent(h,d,start_dt,use_ins,params,return_breakdown=False):
    th,md=math.ceil(h),start_dt.month*100+start_dt.day;days=math.ceil(th/24)
    if 701<=md<=831:s='summer'
    elif(1226<=md)or(md<=103)or(424<=md<=505)or(901<=md<=922)or(206<=md<=214):s='special'
    elif(1101<=md<=1225)or(104<=md<=205)or(215<=md<=423):s='winter'
    else:s='normal'
    p=params['toyota_r'][s];num=[p['p_3h'],p['p_6h'],p['p_12h'],p['p_24h'],p['p_ex_day'],p['p_ex_hr']]
    if th<=3:base=num[0]
    elif th<=6:base=num[1]
    elif th<=12:base=num[2]
    elif th<=24:base=num[3]
    else:base=num[3]+((th//24)-1)*num[4]+min((th%24)*num[5],num[4])
    gas=(d/FUEL_EFFICIENCY)*GAS_PRICE;ins=days*p['p_ins']if use_ins else 0;total=base+gas+ins
    if return_breakdown:return total,f"・基本(期間含): {int(base):,}円\n・ガソリン: {int(gas):,}円\n・補償料: {int(ins):,}円"
    return total
def calc_uqey(h,d,start_dt,use_ins,params,return_breakdown=False):
    p=params['uqey']['normal'];th=math.ceil(h);days=math.ceil(th/24)
    if th<=3:base=p['p_3h']
    elif th<=6:base=p['p_6h']
    elif th<=12:base=p['p_12h']
    elif th<=24:base=p['p_24h']
    else:base=p['p_24h']+(th//24)*p['p_ex_day']
    gas=(d/FUEL_EFFICIENCY)*GAS_PRICE;ins=days*p['p_ins']if use_ins else 0;total=base+gas+ins
    if return_breakdown:return total,f"・基本料金: {int(base):,}円\n・ガソリン: {int(gas):,}円\n・補償料: {int(ins):,}円"
    return total
all_companies={'times':{'func':calc_times_car,'color':'#1f77b4','label':'タイムズカー(青)'},'orix_s':{'func':calc_orix_share,'color':'#17becf','label':'オリックスシェア(水)'},'orix_r':{'func':calc_orix_rent,'color':'#9467bd','label':'オリックスレンタカー(紫)'},'toyota_s':{'func':calc_toyota_share,'color':'#d62728','label':'トヨタシェア(赤)'},'toyota_r':{'func':calc_toyota_rent,'color':'#34495e','label':'トヨタレンタカー(紺)'},'mitsui_s':{'func':calc_mitsui_share,'color':'#2ca02c','label':'三井のシェア(緑)'},'niconico':{'func':calc_niconico,'color':'#ff7f0e','label':'ニコニコ(橙)'},'uqey':{'func':calc_uqey,'color':'#e377c2','label':'Uqey(桃)'},'nippon':{'func':calc_nippon_rent,'color':'#8c564b','label':'ニッポンレンタカー(茶)'},'nissan':{'func':calc_nissan_rent,'color':'#bcbd22','label':'日産レンタカー(黄緑)'},'budget':{'func':calc_budget_rent,'color':'#f1c40f','label':'バジェット(黄)'}}
@st.cache_data(show_spinner=False)
def generate_map_data(max_hours,max_dist,start_dt,use_insurance_flag,selected_comps_tuple,pax,params):
    H,D=np.meshgrid(np.linspace(1,max_hours,100),np.linspace(0,max_dist,100));Z_list,active_colors,active_labels=[],[],[]
    for comp_key in selected_comps_tuple:
        c=all_companies[comp_key]
        Z_list.append(np.vectorize(lambda h,d,f=c['func']:f(h,d,start_dt,use_insurance_flag,params))(H,D))
        active_colors.append(c['color']);active_labels.append(c['label'])
    stacked=np.stack(Z_list,axis=-1).astype(int);Z_winner=np.argmin(stacked,axis=-1);indices=np.argsort(stacked,axis=-1)
    sorted_prices=np.take_along_axis(stacked,indices,axis=-1);names_array=np.array([l.split('(')[0]for l in active_labels]);sorted_names=names_array[indices];sorted_splits=sorted_prices//pax;hover_text=np.full(H.shape,"",dtype=object)
    for k in range(len(active_colors)):
        n_flat,p_flat,s_flat=sorted_names[:,:,k].flat,sorted_prices[:,:,k].flat,sorted_splits[:,:,k].flat
        lines=[f"{'👑 <b>'if k==0 else'  '}{n}: {p:,}円{'</b>'if k==0 else''} ({pax}人割勘:約{s:,}円)<br>"for n,p,s in zip(n_flat,p_flat,s_flat)]
        hover_text+=np.array(lines).reshape(H.shape)
    return H,D,Z_winner,hover_text,active_colors,names_array
with st.sidebar:
    st.header("⚙️条件");pax=st.selectbox("乗車人数",[2,3,4,5,6,7,8],index=3)
    start_dt=datetime.combine(st.date_input("出発日",value=datetime(2026,8,10)),st.time_input("出発時刻",value=datetime.strptime("10:00","%H:%M").time()))
    use_ins=st.checkbox("フルサポート保険",value=True)
    max_hours=st.number_input("最大時間(h)",12,720,72,12);max_dist=st.number_input("最大距離(km)",100,5000,1000,100)
    selected_comps=st.multiselect("比較会社",options=list(all_companies.keys()),default=list(all_companies.keys()),format_func=lambda x:all_companies[x]['label'])
params=load_parameters("parameters.xlsx",pax)
if not params:st.error("Excelエラー");st.stop()
if not selected_comps:st.warning("会社を選択してください")
else:
    with st.spinner("計算中..."):
        H,D,Z_winner,hover_text,active_colors,names_array=generate_map_data(max_hours,max_dist,start_dt,use_ins,tuple(selected_comps),pax,params)
        sel_h,sel_d=None,None
        if "map_chart" in st.session_state:
            pts=st.session_state["map_chart"].get("selection",{}).get("points",[])
            if pts:sel_h,sel_d=pts[0]["x"],pts[0]["y"]
        N=len(active_colors);colorscale=[]
        for i,c in enumerate(active_colors):colorscale+=[[i/N,c],[(i+1)/N,c]]
        fig=go.Figure()
        fig.add_trace(go.Heatmap(x=H[0,:],y=D[:,0],z=Z_winner,colorscale=colorscale,zmin=-0.5,zmax=N-0.5,showscale=True,colorbar=dict(title="<b>最安値</b>",tickmode="array",tickvals=np.arange(N),ticktext=names_array),hoverinfo="skip",hovertemplate=None))
        fig.add_trace(go.Scatter(x=H.flatten(),y=D.flatten(),mode='markers',marker=dict(color='rgba(0,0,0,0)',size=6),customdata=hover_text.flatten(),hovertemplate="<b>利用時間: %{x:.1f}h / 距離: %{y:.0f}km</b><br>---<br>%{customdata}<extra></extra>",showlegend=False))
        if sel_h and sel_d:fig.add_trace(go.Scatter(x=[sel_h],y=[sel_d],mode='markers+text',marker=dict(color='#ff2b2b',size=16,line=dict(color='white',width=2)),text=['📍'],textfont=dict(size=36),textposition='top center',hoverinfo='skip',showlegend=False))
        fig.update_layout(xaxis_title="利用時間(時間)",yaxis_title="想定距離(km)",height=650,margin=dict(l=40,r=10,t=40,b=40),clickmode="event+select")
        event=st.plotly_chart(fig,use_container_width=True,on_select="rerun",selection_mode="points",key="map_chart",config={'displayModeBar':False})
    if sel_h and sel_d:
        st.markdown("---");st.subheader(f"📍 料金詳細 (利用時間: {sel_h:.1f}h / 距離: {sel_d:.0f}km)")
        bds=[]
        for c_key in selected_comps:
            c=all_companies[c_key];pr,tx=c['func'](sel_h,sel_d,start_dt,use_ins,params,True);bds.append((pr,c['label'],tx))
        bds.sort(key=lambda x:x[0]);cols=st.columns(3)
        for i,(pr,lb,tx) in enumerate(bds):
            with cols[i%3]:
                if i==0:st.success(f"👑 **{lb}**\n\n**計: {int(pr):,}円** ({pax}人割勘:約{int(pr)//pax:,}円)\n\n{tx}")
                else:st.info(f"**{lb}**\n\n**計: {int(pr):,}円** ({pax}人割勘:約{int(pr)//pax:,}円)\n\n{tx}")
