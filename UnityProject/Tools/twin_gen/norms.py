"""Design norms and cost assumptions of the demo model. Every number is an orientation value ("модель"),
with the source it was taken from or calibrated to. Shown in the UI under «Почему?»."""

M2_PER_RESIDENT = 30.0          # QTwin build-out scenario assumption (housing GFA per resident)
# m² of GFA per job; calibrated so that 2050 ≈ 1 mln jobs (official target: "1,8 млн жителей и ~1 млн рабочих мест к 2050", inform.kz)
M2_PER_JOB = {"business": 90.0, "social": 50.0, "industry": 100.0, "leisure": 120.0}

# Electricity: coincident peak W per m² of GFA (orientation by СП РК 4.04-106-2013; calibrated to ≈1 kW per resident city peak)
ELEC_W_M2 = {"housing": 10.0, "business": 12.0, "social": 15.0, "industry": 30.0, "leisure": 12.0, "energy": 0.0}
# Water (СП РК 4.01-101-2012 / СНиП 2.04.02-84): l per resident per day with centralized hot water; irrigation; max-day factor
WATER_L_RES = 230.0
WATER_L_IRR = 50.0
WATER_L_JOB = 25.0
WATER_L_BED = 250.0
M2_PER_BED = 40.0               # hotels / resorts: GFA per bed
WATER_L_M2_IND = 3.0            # industry: l per m² per day
K_MAX_DAY = 1.2
SEWER_SHARE = 0.95              # of water without irrigation
# Heat: Gcal/h per 1000 m² at the design outdoor temperature −20 °C (heating + DHW, energy-efficient new stock)
HEAT_GCAL_1000M2 = {"housing": 0.045, "business": 0.035, "social": 0.040, "industry": 0.020, "leisure": 0.040, "energy": 0.0}
GAS_M3H_PER_GCALH = 136.0       # gas boilers: η 0.92, 8 000 kcal/m³
# Social infrastructure (СП РК 3.01-101-2013 orientation)
SCHOOL_SEATS_PER_1000 = 120.0
KG_PLACES_PER_1000 = 60.0
BEDS_PER_1000 = 5.0
CLINIC_VISITS_PER_1000 = 25.0   # visits per shift
EDU_SPLIT = {"school": 0.60, "kindergarten": 0.25, "university": 0.15}
M2_PER_SCHOOL_SEAT = 12.0
M2_PER_KG_PLACE = 15.0
HEALTH_SPLIT = {"hospital": 0.6, "clinic": 0.4}
M2_PER_BED_HOSP = 100.0
M2_PER_CLINIC_VISIT = 30.0

# Utility facility units (one stage = one unit of firm capacity)
UNIT = {
    "power_hv": 125.0,  # MW firm per stage of a 220/110 kV feeding substation (2×250 MVA at N-1 ≈ 2 stages)
    "power": 50.0,      # MW firm per stage of a 110/10 kV substation (2 stages = 2×63 MVA, N-1)
    "heat": 200.0,      # Gcal/h per boiler-house stage
    "gas": 100000.0,    # m³/h per AGRS stage
    "water": 60000.0,   # m³/day per water-intake stage (max day)
    "sewer": 50000.0,   # m³/day per treatment-plant stage
}
RESERVE = 1.10

# Construction duration (years before completion) by building kind
BUILD_YEARS = {"house": 1, "res_mid": 2, "residential": 2, "res_high": 3, "tower": 3, "mixed": 3, "podium": 2, "public": 2,
               "education": 2, "health": 3, "culture": 2, "retail": 1, "business": 2, "other": 1, "industry": 2, "utility": 1,
               "hotel": 2, "resort": 2, "solar": 1, "existing": 0}

# Unit construction cost, tenge per m² of GFA, 2026 prices (orientation for Almaty region)
COST_TG_M2 = {"housing": 300000, "business": 380000, "social": 400000, "industry": 250000, "leisure": 420000, "energy": 0}
# Infrastructure costs, bln tenge (calibrated: 11 substations ≈ 162 bln ₸ — Alatau road map, kapital.kz)
COST_BLN = {"power_hv_stage": 22.0, "power_stage": 7.4, "heat_stage": 9.0, "gas_stage": 12.0, "water_stage": 14.0, "sewer_stage": 16.0,
            "road_km": {"street": 1.1, "main": 1.8, "highway": 3.5, "ring": 3.5},
            "pipe_km": {"water": 0.35, "sewer": 0.45, "power": 0.30, "heat": 0.55, "gas": 0.25, "telecom": 0.04},
            "lrt_km": 9.0}
# Funding shares by use: budget / private / PPP / quasi-state
FUNDING = {"housing": (0.15, 0.85, 0.0, 0.0), "business": (0.0, 0.90, 0.10, 0.0), "social": (0.60, 0.0, 0.40, 0.0),
           "industry": (0.0, 1.0, 0.0, 0.0), "leisure": (0.0, 1.0, 0.0, 0.0), "infra": (0.60, 0.0, 0.10, 0.30)}
FUNDING_KEYS = ["budget", "private", "ppp", "quasi"]

SOURCES = [
    "Генплан Алатау: постановление Правительства РК № 388 от 17.05.2024 (зоны, улицы, объекты)",
    "Сценарий застройки QTwin (годы ввода, 30 м² жилья на человека)",
    "СП РК 4.01-101-2012, СНиП 2.04.02-84 (водопотребление), СП РК 4.04-106-2013 (электрические нагрузки), СП РК 3.01-101-2013 (социальные нормы) — ориентиры",
    "Ориентиры из СМИ: 1,8 млн жителей и ~1 млн рабочих мест к 2050 (inform.kz); 1-й этап 2026–2028: 21 проект на 365,1 млрд ₸, "
    "2-й этап 2028–2030: 9 проектов на 312,5 млрд ₸, 11 подстанций ≈ 162 млрд ₸ (kapital.kz)",
]
