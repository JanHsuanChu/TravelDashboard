# Mirrors TravelFriendliness-repo/06_travel_friendliness_caucasus.py indicator set.

INDICATOR_IDS = [
    "EN.ATM.PM25.MC.M3",
    "SH.H2O.SMDW.ZS",
    "SH.STA.SMSS.ZS",
    "PV.EST",
    "RL.EST",
    "IC.WBL.DFRN.XQ",
    "SL.TLF.CACT.FE.ZS",
    "VA.EST",
    "ST.INT.RCPT.XP.ZS",
    "ST.INT.RCPT.CD",
    "PA.NUS.FCRF",
    "FP.CPI.TOTL.ZG",
]

CRITERIA_MAP = {
    "Air Quality": ["EN.ATM.PM25.MC.M3"],
    "Water Quality": ["SH.H2O.SMDW.ZS", "SH.STA.SMSS.ZS"],
    "Security": ["PV.EST", "RL.EST"],
    "Female Friendliness": ["IC.WBL.DFRN.XQ", "SL.TLF.CACT.FE.ZS"],
    "Human Rights": ["VA.EST"],
    "Tourism Strength": ["ST.INT.RCPT.XP.ZS", "ST.INT.RCPT.CD"],
    "Currency Affordability": ["PA.NUS.FCRF", "FP.CPI.TOTL.ZG"],
}

LOWER_IS_BETTER = {
    "EN.ATM.PM25.MC.M3",
    "PA.NUS.FCRF",
    "FP.CPI.TOTL.ZG",
}

CRITERIA_LABELS_SHORT = list(CRITERIA_MAP.keys())
