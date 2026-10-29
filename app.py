import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go

# ==========================================
# 1. ตั้งค่าหน้าเว็บ (Page Configuration)
# ==========================================
st.set_page_config(
    page_title="โปรแกรมประเมินคาร์บอนเครดิตสำหรับฟาร์มปศุสัตว์",
    page_icon="🌱",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ==========================================
# 2. คลังข้อมูลพารามิเตอร์อ้างอิง (Backend Database)
# อ้างอิงตามบทที่ 2 และตารางที่ 3.2 ในเล่มปริญญานิพนธ์
# ==========================================
GWP_CH4 = 28.0      # IPCC AR5
GWP_N2O = 265.0     # IPCC AR5
EF_GRID = 0.4021    # kg CO2e / kWh (อบก. 2569)
EF_DIESEL = 2.70    # kg CO2e / Litre

# พารามิเตอร์จำแนกตามประเภทสัตว์
LIVESTOCK_PARAMS = {
    "โคนม (Dairy Cattle)": {
        "ef_enteric": 68.0,   # kg CH4/ตัว/ปี
        "vs": 3.80,           # kg VS/ตัว/วัน
        "b0": 0.24,           # m3 CH4/kg VS
        "n_ex": 105.0,        # kg N/ตัว/ปี
        "bw": 550             # kg
    },
    "โคเนื้อ (Beef Cattle)": {
        "ef_enteric": 54.0,   # kg CH4/ตัว/ปี
        "vs": 2.80,           # kg VS/ตัว/วัน
        "b0": 0.19,           # m3 CH4/kg VS
        "n_ex": 60.0,         # kg N/ตัว/ปี
        "bw": 400             # kg
    },
    "สุกร (Swine)": {
        "ef_enteric": 1.5,    # kg CH4/ตัว/ปี
        "vs": 0.35,           # kg VS/ตัว/วัน
        "b0": 0.48,           # m3 CH4/kg VS
        "n_ex": 16.0,         # kg N/ตัว/ปี
        "bw": 70              # kg
    },
    "สัตว์ปีก/ไก่ (Poultry)": {
        "ef_enteric": 0.0,    # ไม่มีค่า Enteric
        "vs": 0.08,           # kg VS/ตัว/วัน
        "b0": 0.36,           # m3 CH4/kg VS
        "n_ex": 0.6,          # kg N/ตัว/ปี
        "bw": 2.0             # kg
    }
}

# ปัจจัยการแปลงเป็นมีเทน (MCF) ตามระบบจัดการมูลสัตว์
MCF_VALUES = {
    "บ่อหมักไร้อากาศแบบเปิด (Open Lagoon)": 0.75,     # Baseline
    "กองมูลแห้งกลางแจ้ง (Dry Lot / Solid Storage)": 0.02, # Baseline
    "ระบบบ่อหมักก๊าซชีวภาพแบบปิด (Covered Biogas Lagoon - AMS-III.D)": 0.05, # Project physical leakage
    "ระบบทำปุ๋ยหมักแบบเติมอากาศ (Aerobic Composting - AMS-III.F)": 0.01      # Project
}

# ==========================================
# 3. จัดเก็บ State ข้อมูลของระบบ (Session State)
# ==========================================
if "farm_info" not in st.session_state:
    st.session_state.farm_info = {
        "farm_name": "มหาวิทยาลัยมหาสารคาม ฟาร์ม",
        "animal_type": "สุกร (Swine)",
        "animal_count": 2000,
        "baseline_system": "บ่อหมักไร้อากาศแบบเปิด (Open Lagoon)",
        "project_tech": "ระบบบ่อหมักก๊าซชีวภาพแบบปิด (Covered Biogas Lagoon - AMS-III.D)",
        "electricity_kwh": 120000.0,
        "diesel_litres": 3500.0,
        "leakage_km": 15.0,
        # ตัวแปรทางการเงิน
        "carbon_price": 500.0,
        "capex": 2500000.0,
        "opex": 120000.0,
        "energy_saving_thb": 350000.0,
        "discount_rate": 0.07,
        "project_years": 10
    }

# ==========================================
# 4. ฟังก์ชันคำนวณตามหลักวิชาการ (Engine Core)
# สมการอ้างอิงบทที่ 2.5.2 & 3.2.2
# ==========================================
def calculate_carbon_credits():
    info = st.session_state.farm_info
    p = LIVESTOCK_PARAMS[info["animal_type"]]
    N = info["animal_count"]
    
    # 4.1 การปล่อยกรณีฐาน (Baseline Emissions: BEy)
    # Enteric Fermentation
    BE_enteric_ch4 = (N * p["ef_enteric"]) / 1000.0 # tCH4
    BE_enteric_co2e = BE_enteric_ch4 * GWP_CH4
    
    # Manure CH4 (Baseline)
    mcf_base = MCF_VALUES.get(info["baseline_system"], 0.75)
    BE_manure_ch4 = (N * p["vs"] * p["b0"] * 0.67 * mcf_base * 365.0) / 1000.0 / 1000.0 # tCH4
    BE_manure_ch4_co2e = BE_manure_ch4 * GWP_CH4
    
    # Manure N2O (Baseline)
    ef3_direct = 0.005 if "เปิด" in info["baseline_system"] else 0.01
    BE_manure_n2o = (N * p["n_ex"] * ef3_direct * (44.0/28.0)) / 1000.0 # tN2O
    BE_manure_n2o_co2e = BE_manure_n2o * GWP_N2O
    
    # Energy Baseline
    BE_energy_co2e = ((info["electricity_kwh"] * EF_GRID) + (info["diesel_litres"] * EF_DIESEL)) / 1000.0
    
    BE_total = BE_enteric_co2e + BE_manure_ch4_co2e + BE_manure_n2o_co2e + BE_energy_co2e

    # 4.2 การปล่อยกรณีโครงการ (Project Emissions: PEy)
    mcf_proj = MCF_VALUES.get(info["project_tech"], 0.05)
    PE_manure_ch4 = (N * p["vs"] * p["b0"] * 0.67 * mcf_proj * 365.0) / 1000.0 / 1000.0 # tCH4
    PE_manure_ch4_co2e = PE_manure_ch4 * GWP_CH4
    
    # โครงการใช้ไฟฟ้า/พลังงานเพิ่มขึ้นเล็กน้อยในระบบบำบัดใหม่ (~15%)
    PE_energy_co2e = BE_energy_co2e * 0.85
    PE_total = BE_enteric_co2e + PE_manure_ch4_co2e + PE_energy_co2e

    # 4.3 การรั่วไหลนอกขอบเขต (Leakage Emissions: LEy)
    LE_transport_co2e = (info["leakage_km"] * 52 * 2.5 * EF_DIESEL) / 1000.0 # สมมติขนส่งสลัดจ์สัปดาห์ละ 1 เที่ยว
    
    # 4.4 คาร์บอนเครดิตสุทธิ (Net Carbon Credits: ERy = BEy - PEy - LEy)
    ER_total = max(0.0, BE_total - PE_total - LE_transport_co2e)
    
    return {
        "BE_total": BE_total,
        "BE_enteric": BE_enteric_co2e,
        "BE_manure_ch4": BE_manure_ch4_co2e,
        "BE_manure_n2o": BE_manure_n2o_co2e,
        "BE_energy": BE_energy_co2e,
        "PE_total": PE_total,
        "LE_total": LE_transport_co2e,
        "ER_total": ER_total
    }

# ==========================================
# 5. ส่วนแถบเมนูนำทาง 5 หน้าหลัก (Sidebar & Navigation)
# อ้างอิงสถาปัตยกรรม 5 Core Screens
# ==========================================
st.sidebar.title("🌱 ปศุสัตว์คาร์บอน")
st.sidebar.caption("ระบบประเมินคาร์บอนเครดิตฟาร์มปศุสัตว์")
st.sidebar.divider()

menu = st.sidebar.radio(
    "เลือกหน้าการทำงาน (Core Screens):",
    [
        "1. 📊 Dashboard (แดชบอร์ดภาพรวม)",
        "2. 📝 Data Input (ป้อนข้อมูลกิจกรรม)",
        "3. ⚙️ Methodology Engine (ประมวลผล & ระเบียบวิธี)",
        "4. 💰 Financial Simulator (วิเคราะห์ความคุ้มทุน)",
        "5. 📄 MRV Report (ออกรายงานและ PDD)"
    ]
)

st.sidebar.divider()
st.sidebar.info(f"**ฟาร์มปัจจุบัน:** {st.session_state.farm_info['farm_name']}")

results = calculate_carbon_credits()

# ==========================================
# SCREEN 1: MAIN DASHBOARD
# ==========================================
if menu == "1. 📊 Dashboard (แดชบอร์ดภาพรวม)":
    st.title("📊 Main Dashboard & Overview Screen")
    st.caption("ภาพรวมสรุปการปล่อยก๊าซเรือนกระจกและประเมินคาร์บอนเครดิตเบื้องต้น")
    
    # Summary KPI Cards
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Baseline Emissions", f"{results['BE_total']:,.2f} tCO₂e/ปี", "กรณีปกติเดิม")
    c2.metric("Project Emissions", f"{results['PE_total']:,.2f} tCO₂e/ปี", "หลังทำโครงการ", delta_color="inverse")
    c3.metric("Leakage Emissions", f"{results['LE_total']:,.2f} tCO₂e/ปี", "การรั่วไหลภายนอก")
    c4.metric("Estimated Carbon Credits", f"{results['ER_total']:,.2f} tCO₂e/ปี", "คาร์บอนเครดิตสุทธิ (ERy)", delta_color="normal")
    
    st.divider()
    
    col_chart1, col_chart2 = st.columns(2)
    
    with col_chart1:
        st.subheader("📊 เปรียบเทียบการปล่อยก๊าซ (Baseline vs Project)")
        df_comp = pd.DataFrame({
            "สถานะ": ["Baseline (กรณีปกติ)", "Project (ทำโครงการ)", "Net Carbon Credit"],
            "ปริมาณ (tCO₂e/ปี)": [results["BE_total"], results["PE_total"], results["ER_total"]]
        })
        fig_bar = px.bar(df_comp, x="สถานะ", y="ปริมาณ (tCO₂e/ปี)", color="สถานะ",
                         text_auto='.2f', color_discrete_sequence=['#ef553b', '#636efa', '#00cc96'])
        st.plotly_chart(fig_bar, use_container_width=True)
        
    with col_chart2:
        st.subheader("🍩 สัดส่วนแหล่งกำเนิดก๊าซเรือนกระจก (Baseline)")
        df_donut = pd.DataFrame({
            "แหล่งกำเนิด": ["การย่อยอาหาร (Enteric)", "มูลสัตว์ (CH₄)", "มูลสัตว์ (N₂O)", "การใช้พลังงาน (Energy)"],
            "ปริมาณ (tCO₂e/ปี)": [results["BE_enteric"], results["BE_manure_ch4"], results["BE_manure_n2o"], results["BE_energy"]]
        })
        fig_donut = px.pie(df_donut, values="ปริมาณ (tCO₂e/ปี)", names="แหล่งกำเนิด", hole=0.4,
                           color_discrete_sequence=px.colors.qualitative.Pastel)
        st.plotly_chart(fig_donut, use_container_width=True)

# ==========================================
# SCREEN 2: ACTIVITY DATA INPUT
# ==========================================
elif menu == "2. 📝 Data Input (ป้อนข้อมูลกิจกรรม)":
    st.title("📝 Activity Data Input / ป้อนข้อมูลกิจกรรมฟาร์ม")
    st.caption("กรอกข้อมูลกายภาพและกิจกรรมของฟาร์มตามขอบเขตการประเมิน (Scope 1 & Scope 2)")
    
    with st.form("input_form"):
        st.subheader("1. ข้อมูลทั่วไปและประชากรสัตว์")
        f_name = st.text_input("ชื่อฟาร์ม / โครงการ", value=st.session_state.farm_info["farm_name"])
        a_type = st.selectbox("ประเภทสัตว์ปศุสัตว์", list(LIVESTOCK_PARAMS.keys()), 
                              index=list(LIVESTOCK_PARAMS.keys()).index(st.session_state.farm_info["animal_type"]))
        a_count = st.number_input("จำนวนสัตว์เฉลี่ยในฟาร์ม (ตัว)", min_value=1, value=int(st.session_state.farm_info["animal_count"]))
        
        st.subheader("2. ระบบจัดการมูลสัตว์และเทคโนโลยี")
        base_sys = st.selectbox("ระบบจัดการมูลสัตว์เดิม (Baseline System)", 
                                [k for k in MCF_VALUES.keys() if "Baseline" in k or "เปิด" in k or "กลางแจ้ง" in k],
                                index=0)
        proj_tech = st.selectbox("เทคโนโลยีโครงการใหม่ (Project Technology)", 
                                 [k for k in MCF_VALUES.keys() if "Project" in k or "ปิด" in k or "เติมอากาศ" in k],
                                 index=0)
        
        st.subheader("3. การใช้พลังงานและการขนส่ง")
        c1, c2, c3 = st.columns(3)
        elec = c1.number_input("การใช้ไฟฟ้าประจำปี (kWh/ปี)", min_value=0.0, value=float(st.session_state.farm_info["electricity_kwh"]))
        diesel = c2.number_input("การใช้น้ำมันดีเซล (ลิตร/ปี)", min_value=0.0, value=float(st.session_state.farm_info["diesel_litres"]))
        leak_km = c3.number_input("ระยะทางขนส่งกากมูล/สลัดจ์ออกนอกฟาร์ม (กิโลเมตร/เที่ยว)", min_value=0.0, value=float(st.session_state.farm_info["leakage_km"]))
        
        submit = st.form_submit_button("💾 บันทึกข้อมูลและประมวลผลใหม่", type="primary")
        
        if submit:
            st.session_state.farm_info.update({
                "farm_name": f_name,
                "animal_type": a_type,
                "animal_count": a_count,
                "baseline_system": base_sys,
                "project_tech": proj_tech,
                "electricity_kwh": elec,
                "diesel_litres": diesel,
                "leakage_km": leak_km
            })
            st.success("บันทึกข้อมูลกิจกรรมเรียบร้อยแล้ว!")
            st.rerun()

# ==========================================
# SCREEN 3: METHODOLOGY ENGINE
# ==========================================
elif menu == "3. ⚙️ Methodology Engine (ประมวลผล & ระเบียบวิธี)":
    st.title("⚙️ Methodology Engine & Decision Matrix")
    st.caption("ระบบคัดเลือกระเบียบวิธีคำนวณอัตโนมัติ (T-VER / CDM) พร้อมตรวจสอบเงื่อนไขของคุณสมบัติ")
    
    col_check, col_calc = st.columns([1, 1], gap="large")
    
    with col_check:
        st.subheader("📋 Eligibility Checklist & Auto-Routing")
        
        selected_method = "CDM AMS-III.D / T-VER-METH-WM-08" if "Biogas" in st.session_state.farm_info["project_tech"] else "CDM AMS-III.F (Aerobic Composting)"
        
        st.info(f"💡 **ระเบียบวิธีที่ระบบเลือกให้อัตโนมัติ:**\n\n### `{selected_method}`")
        
        st.markdown("**การตรวจสอบคุณสมบัติขั้นต่ำ (Eligibility Criteria):**")
        st.checkbox("ขนาดโครงการผลิตการลดก๊าซไม่เกิน 60,000 tCO₂e/ปี (Type III Small-scale)", value=True, disabled=True)
        st.checkbox("ระบบเดิมมีระยะเวลาเก็บกักน้ำเสีย/มูลสัตว์ > 30 วัน", value=True, disabled=True)
        st.checkbox("ความลึกบ่อหมักเดิมเปิดมากกว่า 1.0 เมตร", value=True, disabled=True)
        st.checkbox("มีระบบดักจับก๊าซและอุปกรณ์เผาทำลายก๊าซส่วนเกิน (Flaring - TOOL06)", value=True, disabled=True)

    with col_calc:
        st.subheader("🔢 Real-time Calculation Breakdown")
        
        st.markdown(f"""
        | รายการประมวลผล | สมการอ้างอิง | ผลลัพธ์ (tCO₂e/ปี) |
        | :--- | :--- | :---: |
        | ** Baseline Emissions ($BE_y$)** | $BE_{{enteric}} + BE_{{manure}} + BE_{{energy}}$ | **{results['BE_total']:,.2f}** |
        | ** Project Emissions ($PE_y$)** | $PE_{{manure}} + PE_{{energy}}$ | **{results['PE_total']:,.2f}** |
        | ** Leakage Emissions ($LE_y$)** | $LE_{{transport}}$ | **{results['LE_total']:,.2f}** |
        | ** Net Carbon Credits ($ER_y$)** | **$BE_y - PE_y - LE_y$** | **{results['ER_total']:,.2f}** |
        """)
        
        st.success(f"🌱 **ปริมาณคาร์บอนเครดิตสุทธิที่ได้รับสุทธิ ($ER_y$): {results['ER_total']:,.2f} tCO₂e/ปี**")

# ==========================================
# SCREEN 4: FINANCIAL SIMULATOR
# ==========================================
elif menu == "4. 💰 Financial Simulator (วิเคราะห์ความคุ้มทุน)":
    st.title("💰 Financial Simulator & Sensitivity Analysis")
    st.caption("แบบจำลองประเมินความคุ้มทุนทางการเงินและระยะเวลาคืนทุนของโครงการ")
    
    col_fin_in, col_fin_out = st.columns([1, 2], gap="large")
    
    with col_fin_in:
        st.subheader("🛠️ ตัวแปรทางการเงิน (Inputs)")
        c_price = st.slider("ราคาคาร์บอนเครดิต (บาท / tCO₂e)", 100, 2000, int(st.session_state.farm_info["carbon_price"]), 50)
        capex = st.number_input("เงินลงทุนเริ่มต้น / CAPEX (บาท)", value=float(st.session_state.farm_info["capex"]), step=100000.0)
        opex = st.number_input("ค่าบำรุงรักษารายปี / OPEX (บาท/ปี)", value=float(st.session_state.farm_info["opex"]), step=10000.0)
        e_saving = st.number_input("มูลค่าพลังงานที่ประหยัดได้ (บาท/ปี)", value=float(st.session_state.farm_info["energy_saving_thb"]), step=10000.0)
        p_years = st.slider("ระยะเวลาโครงการ (ปี)", 5, 20, int(st.session_state.farm_info["project_years"]))
        
    with col_fin_out:
        st.subheader("📈 ผลการวิเคราะห์ทางการเงิน")
        
        annual_credit_revenue = results["ER_total"] * c_price
        total_annual_revenue = annual_credit_revenue + e_saving
        net_annual_cashflow = total_annual_revenue - opex
        
        payback_period = capex / net_annual_cashflow if net_annual_cashflow > 0 else 99.0
        
        m1, m2, m3 = st.columns(3)
        m1.metric("รายได้คาร์บอนเครดิต", f"{annual_credit_revenue:,.2f} บาท/ปี")
        m2.metric("กระแสเงินสดสุทธิรายปี", f"{net_annual_cashflow:,.2f} บาท/ปี")
        m3.metric("ระยะเวลาคืนทุน (Payback)", f"{payback_period:.1f} ปี" if payback_period < 50 else "ไม่คืนทุน")
        
        st.divider()
        
        years = list(range(0, p_years + 1))
        cashflows = [-capex] + [net_annual_cashflow] * p_years
        cum_cashflows = np.cumsum(cashflows)
        
        df_cf = pd.DataFrame({"ปีที่": years, "กระแสเงินสดสะสม (บาท)": cum_cashflows})
        fig_cf = px.line(df_cf, x="ปีที่", y="กระแสเงินสดสะสม (บาท)", markers=True,
                         title=f"การประมาณการกระแสเงินสดสะสมตลอดระยะเวลา {p_years} ปี")
        fig_cf.add_hline(y=0, line_dash="dash", line_color="red")
        st.plotly_chart(fig_cf, use_container_width=True)

# ==========================================
# SCREEN 5: MRV REPORT GENERATOR
# ==========================================
elif menu == "5. 📄 MRV Report (ออกรายงานและ PDD)":
    st.title("📄 Automated PDD & MRV Report Generator")
    st.caption("ระบบจัดทำเอกสารข้อเสนอโครงการ (PDD) และรายงานการติดตามผล (MRV) ฉบับร่าง")
    
    st.subheader("📝 ตัวอย่างเอกสารร่างข้อเสนอโครงการ (Project Design Document - PDD Summary)")
    
    report_text = f"""
    ================================================================================
    เอกสารข้อเสนอโครงการลดก๊าซเรือนกระจกภาคสมัครใจ (Draft PDD / MRV Report)
    มาตรฐานอ้างอิง: T-VER / CDM Standard
    วันเวลาที่ออกรายงาน: 2026-10-29
    ================================================================================
    
    1. ข้อมูลทั่วไปของโครงการ (Project Information)
       - ชื่อฟาร์ม/โครงการ: {st.session_state.farm_info['farm_name']}
       - ประเภทปศุสัตว์: {st.session_state.farm_info['animal_type']} (จำนวน {st.session_state.farm_info['animal_count']:,} ตัว)
       - ระบบจัดการเดิม (Baseline): {st.session_state.farm_info['baseline_system']}
       - เทคโนโลยีโครงการ (Project): {st.session_state.farm_info['project_tech']}
       
    2. สรุปผลการประเมินคาร์บอนเครดิตสุทธิ (Emission Reduction Summary)
       - การปล่อยกรณีฐาน (Baseline Emissions: BEy): {results['BE_total']:,.2f} tCO2e/ปี
       - การปล่อยกรณีโครงการ (Project Emissions: PEy): {results['PE_total']:,.2f} tCO2e/ปี
       - การรั่วไหลภายนอก (Leakage Emissions: LEy): {results['LE_total']:,.2f} tCO2e/ปี
       -----------------------------------------------------------------------------
       - คาร์บอนเครดิตสุทธิที่คาดว่าจะได้รับ (Net Carbon Credits: ERy): {results['ER_total']:,.2f} tCO2e/ปี
       -----------------------------------------------------------------------------
       
    3. การวิเคราะห์มูลค่าทางเศรษฐศาสตร์เบื้องต้น (Financial Summary)
       - ประเมินราคาขายคาร์บอนเครดิต: {st.session_state.farm_info['carbon_price']:,} บาท/tCO2e
       - รายได้คาร์บอนเครดิตคาดการณ์: {results['ER_total'] * st.session_state.farm_info['carbon_price']:,.2f} บาท/ปี
       - ระยะเวลาคืนทุนของโครงการ (Payback Period): {(st.session_state.farm_info['capex'] / ((results['ER_total'] * st.session_state.farm_info['carbon_price']) + st.session_state.farm_info['energy_saving_thb'] - st.session_state.farm_info['opex'])):.1f} ปี
    ================================================================================
    """
    
    st.code(report_text, language="text")
    
    c1, c2 = st.columns(2)
    
    df_mrv = pd.DataFrame([{
        "ชื่อฟาร์ม": st.session_state.farm_info['farm_name'],
        "ประเภทสัตว์": st.session_state.farm_info['animal_type'],
        "จำนวนสัตว์ (ตัว)": st.session_state.farm_info['animal_count'],
        "Baseline Emissions (tCO2e/yr)": round(results['BE_total'], 2),
        "Project Emissions (tCO2e/yr)": round(results['PE_total'], 2),
        "Leakage Emissions (tCO2e/yr)": round(results['LE_total'], 2),
        "Net Carbon Credits (tCO2e/yr)": round(results['ER_total'], 2)
    }])
    
    csv_bytes = df_mrv.to_csv(index=False).encode('utf-8-sig')
    
    c1.download_button(
        label="📥 ดาวน์โหลดรายงาน MRV Data Audit Trail (CSV)",
        data=csv_bytes,
        file_name=f"MRV_Report_{st.session_state.farm_info['farm_name']}.csv",
        mime="text/csv",
        type="primary"
    )
    
    c2.download_button(
        label="📄 ดาวน์โหลดร่างเอกสาร PDD (TXT)",
        data=report_text.encode('utf-8'),
        file_name=f"Draft_PDD_{st.session_state.farm_info['farm_name']}.txt",
        mime="text/plain"
    )