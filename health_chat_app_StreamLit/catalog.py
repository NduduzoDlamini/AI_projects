"""Indicator catalog + prompt parsing (no external dependencies).

Keywords are whole words/phrases, comma separated. The FIRST row of a topic
is the default when the user gives no measure (e.g. just "malaria trends").
To add an indicator, add one row to CATALOG.
"""
import re

# (keywords, GHO_CODE, label)
CATALOG = [
    # ---- Malaria
    ("malaria,incidence,rate", "MALARIA_EST_INCIDENCE", "Estimated malaria incidence (per 1000 population at risk)"),
    ("malaria,mortality,death,deaths", "MALARIA_EST_MORTALITY", "Estimated malaria mortality rate (per 100 000 population)"),
    ("malaria,cases,total", "MALARIA_TOTAL_CASES", "Total number of malaria cases (presumed + confirmed)"),
    ("malaria,confirmed", "MALARIA_CONF_CASES", "Number of confirmed malaria cases"),
    ("malaria,imported", "MALARIA_IMPORTED", "Number of imported malaria cases"),
    ("malaria,indigenous,local", "MALARIA_INDIG", "Number of indigenous malaria cases"),

    # ---- NCD
    ("ncd,ncds,noncommunicable,non communicable,deaths,death,mortality", "NCD_DTH_TOT", "Total NCD deaths"),
    ("ncd,ncds,premature,under 70", "NCD_UNDER70", "Premature NCD deaths as a proportion of all NCD deaths"),
    ("ncd,ncds,probability,premature", "NCDMORT3070", "Probability (%) of dying between age 30 and 70 from CVD, cancer, diabetes or chronic respiratory disease"),
    ("diabetes,prevalence", "NCD_DIABETES_PREVALENCE_AGESTD", "Prevalence of diabetes, age-standardized"),
    ("diabetes,crude", "NCD_DIABETES_PREVALENCE_CRUDE", "Prevalence of diabetes, crude"),
    ("diabetes,treatment,coverage", "NCD_DIABETES_TREATMENT_AGESTD", "Diabetes treatment coverage, age-standardized"),
    ("obesity,obese,adults", "NCD_BMI_30A", "Obesity among adults, BMI >= 30 (age-standardized, %)"),
    ("obesity,obese,children,adolescents", "NCD_BMI_PLUS2C", "Obesity among children and adolescents (crude, %)"),
    ("overweight,adults", "NCD_BMI_25A", "Overweight among adults, BMI >= 25 (age-standardized, %)"),
    ("underweight,thinness", "NCD_BMI_18A", "Underweight among adults, BMI < 18.5 (age-standardized, %)"),
    ("physical activity,inactivity,insufficient", "NCD_PAA", "Insufficient physical activity among adults (age-standardized, %)"),
    ("cholesterol", "NCD_CHOL_MEANTOTALCHOL_A", "Mean total cholesterol, age-standardized"),
    ("cervical,screening,cancer", "NCD_CXCA_SCREENED_WITHIN_TIMEPERIOD", "Cervical cancer screening among women aged 30-49 (%)"),
    ("tobacco,smoking,smokers,use", "M_Est_tob_curr_std", "Current tobacco use prevalence (age-standardized, %)"),
    ("smoking,smokers,cigarette,smoke", "M_Est_smk_curr_std", "Current tobacco smoking prevalence (age-standardized, %)"),
    ("alcohol,drinking,consumption", "SA_0000001688", "Alcohol total per capita (15+) consumption, litres of pure alcohol"),
    ("suicide,suicides", "MH_12", "Age-standardized suicide rates (per 100 000 population)"),

    # ---- Tuberculosis
    ("tuberculosis,tb,incidence,rate", "MDG_0000000020", "Incidence of tuberculosis (per 100 000 population per year)"),
    ("tuberculosis,tb,cases,number,incident", "TB_e_inc_num", "Number of incident tuberculosis cases"),
    ("tuberculosis,tb,notified,new,relapse", "TB_c_newinc", "Tuberculosis new and relapse cases"),
    ("tuberculosis,tb,treatment,success", "TB_c_new_tsr", "Treatment success rate: new TB cases"),
    ("tuberculosis,tb,mdr,resistant", "TB_rr_mdr", "Confirmed cases of RR-/MDR-TB"),

    # ---- HIV
    ("hiv,aids,living,people", "HIV_0000000001", "Estimated number of people (all ages) living with HIV"),
    ("hiv,aids,prevalence,adults", "MDG_0000000029", "Prevalence of HIV among adults aged 15 to 49 (%)"),
    ("hiv,aids,new,infections,incidence", "HIV_0000000026", "Number of new HIV infections"),
    ("hiv,aids,deaths,death,mortality", "HIV_0000000006", "Number of people dying from HIV-related causes"),
    ("hiv,aids,art,antiretroviral,treatment,coverage", "HIV_ARTCOVERAGE", "Estimated antiretroviral therapy coverage among people living with HIV (%)"),

    # ---- Hepatitis
    ("hepatitis b,hbv,hepatitis,prevalence", "HEPATITIS_HBV_PREVALENCE_PER100", "Prevalence of chronic hepatitis B in the general population (%)"),
    ("hepatitis c,hcv,hepatitis,prevalence", "HEPATITIS_HCV_PREVALENCE_PER100", "Prevalence of chronic hepatitis C in the general population (%)"),
    ("hepatitis b,hbv,deaths,death,mortality", "HEPATITIS_HBV_DEATHS_NUM", "Deaths caused by chronic hepatitis B (number)"),

    # ---- Vaccine-preventable diseases (reported cases)
    ("measles,cases", "WHS3_62", "Measles - number of reported cases"),
    ("tetanus,cases", "WHS3_46", "Total tetanus - number of reported cases"),
    ("neonatal tetanus", "WHS3_56", "Neonatal tetanus - number of reported cases"),
    ("polio,poliomyelitis,cases", "WHS3_49", "Poliomyelitis - number of reported cases"),
    ("pertussis,whooping cough,cases", "WHS3_43", "Pertussis - number of reported cases"),
    ("diphtheria,cases", "WHS3_41", "Diphtheria - number of reported cases"),
    ("yellow fever,cases", "WHS3_50", "Yellow fever - number of reported cases"),
    ("mumps,cases", "WHS3_53", "Mumps - number of reported cases"),
    ("rubella,cases", "WHS3_57", "Rubella - number of reported cases"),

    # ---- Immunization coverage
    ("measles,mcv1,vaccine,vaccination,immunization,immunisation,coverage", "WHS8_110", "Measles first-dose (MCV1) immunization coverage among 1-year-olds (%)"),
    ("dtp,dtp1,diphtheria,vaccine,vaccination,immunization,immunisation,coverage", "VACCINECOVERAGE_DTP1", "DTP1 immunization coverage among 1-year-olds (%)"),
    ("bcg,vaccine,vaccination,immunization,immunisation,coverage", "WHS4_543", "BCG immunization coverage among 1-year-olds (%)"),
    ("polio,ipv,vaccine,vaccination,immunization,immunisation,coverage", "VACCINECOVERAGE_IPV1", "IPV1 immunization coverage among 1-year-olds (%)"),

    # ---- Mortality and life expectancy
    ("under five,under 5,u5mr,child,children,mortality,rate", "MDG_0000000007", "Under-five mortality rate (per 1000 live births)"),
    ("under five,under 5,child,children,deaths,number", "CM_01", "Number of under-five deaths"),
    ("infant,infants,mortality,rate", "MDG_0000000001", "Infant mortality rate (per 1000 live births)"),
    ("infant,infants,deaths,number", "CM_02", "Number of infant deaths"),
    ("neonatal,newborn,mortality,rate", "WHOSIS_000003", "Neonatal mortality rate (per 1000 live births)"),
    ("neonatal,newborn,deaths,number", "CM_03", "Number of neonatal deaths"),
    ("adult,mortality", "WHOSIS_000004", "Adult mortality rate (per 1000 population)"),
    ("stillbirth,stillbirths", "WHOSIS_000014", "Stillbirth rate (per 1000 total births)"),
    ("life expectancy,life,expectancy", "WHOSIS_000001", "Life expectancy at birth (years)"),
    ("healthy life expectancy,hale,healthy", "WHOSIS_000002", "Healthy life expectancy (HALE) at birth (years)"),
    ("low birth weight,lbw", "LBW_PREVALENCE", "Low birth weight prevalence (%)"),

    # ---- Maternal and reproductive
    ("antenatal,anc,pregnant,pregnancy", "WHS4_154", "Antenatal care coverage - at least four visits (%)"),
    ("skilled,birth,births,attended,delivery", "MDG_0000000025", "Births attended by skilled health personnel (%)"),
    ("caesarean,cesarean,c section", "WHS4_115", "Births by caesarean section (%)"),
    ("adolescent,birth,rate,teenage", "MDG_0000000003", "Adolescent birth rate (per 1000 women)"),

    # ---- Nutrition
    ("stunting,malnutrition,children", "NUTSTUNTINGPREV", "Stunting prevalence among children under 5 (%, model-based)"),
    ("wasting,malnutrition,children", "NUTRITION_WH_2", "Wasting prevalence among children under 5 (%)"),
    ("underweight,children,malnutrition", "NUTRITION_WA_2", "Underweight prevalence among children under 5 (%)"),
    ("anaemia,anemia,children", "NUTRITION_ANAEMIA_CHILDREN_PREV", "Prevalence of anaemia in children aged 6-59 months (%)"),
    ("anaemia,anemia,women", "NUTRITION_ANAEMIA_REPRODUCTIVEAGE_PREV", "Prevalence of anaemia in women of reproductive age (%)"),
    ("breastfeeding,exclusive,breastfed", "NUT_BF_EBF", "Exclusive breastfeeding under six months"),

    # ---- Health financing and system
    ("health expenditure,expenditure,spending,gdp", "GHED_CHEGDP_SHA2011", "Current health expenditure as % of GDP"),
    ("expenditure,spending,per capita", "GHED_CHE_pc_US_SHA2011", "Current health expenditure per capita in US$"),
    ("out of pocket,oop,expenditure,spending", "GHED_OOPSCHE_SHA2011", "Out-of-pocket expenditure as % of current health expenditure"),
    ("uhc,universal health coverage,service coverage index", "UHC_INDEX_REPORTED", "UHC Service Coverage Index (SDG 3.8.1)"),
    ("doctors,doctor,physicians,physician", "HWF_0001", "Medical doctors (per 10,000)"),
    ("nurses,nursing,midwives,midwifery", "HWF_0006", "Nursing and midwifery personnel (per 10,000)"),
    ("dentists,dentist", "HWF_0010", "Dentists (per 10,000)"),
    ("hospital beds,beds", "WHS6_102", "Hospital beds (per 10 000 population)"),

    # ---- Environment and WASH
    ("water,drinking", "WSH_WATER_BASIC", "Population using at least basic drinking-water services (%)"),
    ("sanitation,toilets", "WSH_SANITATION_BASIC", "Population using at least basic sanitation services (%)"),
    ("handwashing,hygiene", "WSH_HYGIENE_BASIC", "Population with basic handwashing facilities at home (%)"),
    ("diarrhoea,diarrhea,wash", "WSH_10", "Number of diarrhoea deaths from inadequate water, sanitation and hygiene"),
    ("air pollution,ambient,rate", "AIR_42", "Ambient air pollution attributable death rate (per 100 000, age-standardized)"),
    ("air pollution,ambient,deaths,death,number", "AIR_41", "Ambient air pollution attributable deaths"),
    ("air pollution,household,indoor", "AIR_52", "Household air pollution attributable death rate (per 100 000, age-standardized)"),
    ("clean fuels,cooking,clean", "PHE_HHAIR_PROP_POP_CLEAN_FUELS", "Proportion of population relying on clean fuels for cooking (%)"),
    ("oral,dental,caries,teeth", "ORALHEALTH_UNTREATEDCARIESPERMANENT", "Prevalence of untreated caries of permanent teeth (%)"),
]

CHART_WORDS = [
    ("pie", ["pie", "donut", "doughnut"]),
    ("bar", ["bar", "bars", "column", "columns", "histogram"]),
    ("area", ["area"]),
    ("scatter", ["scatter", "dots"]),
    ("table", ["table"]),
    ("line", ["line"]),
]
CHART_TYPES = ["line", "bar", "area", "pie", "scatter", "table"]

STOPWORDS = set("""
show me give display plot draw make create get see the a an of in on for to from and or with by
trend trends trending graph graphs chart charts over time please can you i want would like
line bar pie area scatter table donut column columns until till since before after between up
year years eswatini
""".split())


def _join(text: str) -> str:
    """Lowercase, keep only alphanumeric words, pad with spaces for whole-word matching."""
    return " " + " ".join(re.findall(r"[a-z0-9]+", text.lower())) + " "


def find_indicator(prompt: str):
    """Return {'code','label','score'} for the best catalog match, or None."""
    text = _join(prompt)
    best, best_score = None, 0
    for keywords, code, label in CATALOG:
        score = sum(1 for k in keywords.split(",") if _join(k) in text)
        if score > best_score:  # strict '>' keeps catalog order on ties
            best, best_score = {"code": code, "label": label, "score": score}, score
    return best


def explicit_code(prompt: str):
    """If the user typed a GHO_CODE (e.g. TB_e_inc_num), return it. Charset is SQL-safe."""
    m = re.search(r"\b[A-Za-z][A-Za-z0-9]*(?:_[A-Za-z0-9\-]+)+\b", prompt)
    return m.group(0) if m else None


def year_bounds(prompt: str):
    """Return (low, high); either may be None."""
    years = [int(y) for y in re.findall(r"(?<!\d)(?:19|20)\d{2}(?!\d)", prompt)]
    if len(years) >= 2:
        return min(years), max(years)
    if len(years) == 1:
        y, text = years[0], _join(prompt)
        if any(w in text for w in (" since ", " from ", " after ", " starting ")):
            return y, None
        if any(w in text for w in (" before ", " until ", " till ", " up to ", " by ")):
            return None, y
        return y, y
    return None, None


def detect_chart_type(prompt: str, default: str = "line") -> str:
    """Chart type named in the prompt, else `default` (the sidebar choice)."""
    text = _join(prompt)
    for ctype, words in CHART_WORDS:
        if any(f" {w} " in text for w in words):
            return ctype
    return default if default in CHART_TYPES else "line"


def topic_words(prompt: str):
    """Words left after removing stopwords/numbers, used for the discovery search."""
    words = re.findall(r"[a-z]+", prompt.lower())
    return [w for w in dict.fromkeys(words) if w not in STOPWORDS and len(w) > 2]
