"""
config.py : hypothèses centralisées du projet Solvabilité II (santé et prévoyance).

Deux familles de paramètres :
  * paramètres RÉGLEMENTAIRES (Directive 2009/138/CE, Règlement délégué (UE) 2015/35 modifié) :
    chocs, écarts-types, matrices de corrélation, facteurs du MCR ; ils ne se discutent pas ;
  * hypothèses de l'ORGANISME (portefeuilles, frais, sinistralité, actifs) : générées ou calées sur
    des données de place, toutes modifiables ici.
Convention : camelCase.
"""
from pathlib import Path

root = Path(__file__).resolve().parents[2]
dataRaw = root / "data" / "raw"
dataProc = root / "data" / "processed"
outFig = root / "outputs" / "python" / "figures"
outTab = root / "outputs" / "python" / "tables"
for p in (dataProc, outFig, outTab):
    p.mkdir(parents=True, exist_ok=True)
seed = 20260630

# ============================================================================
# 1. Données de marché (EIOPA)
# ============================================================================
valuationDate = "2026-06-30"
ufr = 0.0330                        # EIOPA, UFR 2026 de l'euro
llp = 20                            # dernier point liquide de l'euro
convergencePeriod = 40              # convergence vers l'UFR en LLP + 40 ans
convergenceTolerance = 0.0001       # 1 pb (critère EIOPA)
alphaMin = 0.05
maxMaturity = 150
symmetricAdjustment = 0.0           # ajustement symétrique action : à remplacer par la valeur EIOPA publiée au 30/06/2026

# ============================================================================
# 2. Portefeuilles (hypothèses de l'organisme, calées sur la place)
# ============================================================================
health = {  # frais de soins, contrats annuels renouvelés au 1er janvier
    "individuel": {"prime2025": 55e6, "sp": 0.73, "fraisGestionPrimes": 0.20, "assures": 60000},
    "collectif": {"prime2025": 75e6, "sp": 0.85, "fraisGestionPrimes": 0.12, "assures": 120000},
}
healthGrowth = 0.05                 # croissance annuelle des cotisations (DREES : +8 % en 2024)
healthDevPattern = [0.72, 0.95, 0.985, 0.995, 0.999, 1.0]   # cumul payé par semestre de développement
healthUlae = 0.04                   # frais de gestion des sinistres (en % des sinistres restant à payer)
firstAccidentSemester = "2019S1"

prevoyance = {"assures": 60000, "salaireMoyen": 38000, "franchiseMois": 3, "dureeMaxIncapaciteMois": 36,
              "ijPctSalaire": 0.25, "renteInvPctSalaire": 0.30, "capitalDecesPctSalaire": 2.0, "ageFinRente": 62,
              "incidenceArret90j": 0.012, "abattementMortaliteActifs": 0.60, "surmortaliteInvalides": 2.5,
              "fraisGestionPrimes": 0.08, "fraisGestionPrestations": 0.03, "ratioSinistresCibleTarif": 0.92,
              "tauxDeclarationTardive": 0.15}          # part des arrêts du dernier semestre non encore déclarés
reinsuranceQuotaShareDeces = 0.50   # quote-part décès, réassureur noté A
reinsurerCqs = 2                    # échelon de qualité de crédit (A)
statutoryRate = 0.015               # taux technique des provisions mathématiques en comptes sociaux
statutoryPsapMargin = 0.05          # prudence des provisions sociales santé (PSAP)
equalisationProvision = 2.0e6       # provision d'égalisation (comptes sociaux, non reconnue en S2)

# ============================================================================
# 3. Paramètres réglementaires : souscription santé et vie
# ============================================================================
nslt = {"medicalExpense": {"sigmaPrem": 0.05, "sigmaRes": 0.057},
        "incomeProtection": {"sigmaPrem": 0.085, "sigmaRes": 0.14}}
nsltLobCorrelation = 0.5            # Annexe XV : frais médicaux / perte de revenus
nsltLapse = 0.40
sltShocks = {"mortality": 0.15, "longevity": -0.20, "incidenceYear1": 0.35, "incidenceAfter": 0.25, "recovery": -0.20,
             "expense": 0.10, "expenseInflation": 0.01, "revision": 0.04, "lapseUp": 0.5, "lapseDown": -0.5, "massLapse": 0.40}
sltCorrelation = {  # santé SLT (Art. 151) : mortalité, longévité, incapacité, rachat, frais, révision
    "names": ["mortalite", "longevite", "incapacite", "rachat", "frais", "revision"],
    "matrix": [[1, -0.25, 0.25, 0, 0.25, 0], [-0.25, 1, 0, 0.25, 0.25, 0.25], [0.25, 0, 1, 0, 0.5, 0],
               [0, 0.25, 0, 1, 0.5, 0], [0.25, 0.25, 0.5, 0.5, 1, 0.5], [0, 0.25, 0, 0, 0.5, 1]]}
lifeCorrelation = {  # vie (Annexe IV) : mortalité, longévité, invalidité, rachat, frais, révision, catastrophe
    "names": ["mortalite", "longevite", "invalidite", "rachat", "frais", "revision", "catastrophe"],
    "matrix": [[1, -0.25, 0.25, 0, 0.25, 0, 0.25], [-0.25, 1, 0, 0.25, 0.25, 0.25, 0], [0.25, 0, 1, 0, 0.5, 0, 0.25],
               [0, 0.25, 0, 1, 0.5, 0, 0.25], [0.25, 0.25, 0.5, 0.5, 1, 0.5, 0.25], [0, 0.25, 0, 0, 0.5, 1, 0],
               [0.25, 0, 0.25, 0.25, 0.25, 0, 1]]}
lifeCatShock = 0.0015               # +0,15 point de mortalité sur 12 mois (Art. 143)
healthModuleCorrelation = {"SLT-NSLT": 0.5, "SLT-CAT": 0.25, "NSLT-CAT": 0.25}
healthCat = {"massAccidentFrance": 0.0005,                       # Annexe XVI
             "events": {"deces": 0.10, "invaliditePermanente": 0.015, "incapacite10Ans": 0.05, "incapacite12Mois": 0.135, "soins": 0.30},
             "pandemicIp": 0.000075, "pandemicSymptoms": 0.4, "hospitalisation": 0.01, "consultation": 0.20,
             "coutHospitalisation": 3500.0, "coutConsultation": 60.0, "coutSoinsAccident": 1500.0,
             "plusGrandeConcentration": 1000}                    # plus grand site assuré (clients collectifs)

# ============================================================================
# 4. Paramètres réglementaires : marché, contrepartie, opérationnel, agrégation
# ============================================================================
equityShock = {"type1": 0.39, "type2": 0.49}
equityCorrelation = 0.75
propertyShock = 0.25
currencyShock = 0.25
upShockMin = 0.01                   # hausse minimale de 1 point (Art. 166)
marketCorrelation = {"names": ["taux", "action", "immobilier", "spread", "change", "concentration"]}
concentration = {"threshold": {0: 0.03, 1: 0.03, 2: 0.03, 3: 0.015, 4: 0.015, 5: 0.015, 6: 0.015},
                 "g": {0: 0.12, 1: 0.12, 2: 0.21, 3: 0.27, 4: 0.73, 5: 0.73, 6: 0.73}}
counterpartyPd = {0: 0.00002, 1: 0.0001, 2: 0.0005, 3: 0.0024, 4: 0.012, 5: 0.042, 6: 0.042}   # Art. 199
receivablesFactor, receivablesOverdueFactor = 0.15, 0.90
counterpartyCorrelation = 0.75
bscrCorrelation = {"names": ["marche", "contrepartie", "vie", "sante", "nonVie"],
                   "matrix": [[1, 0.25, 0.25, 0.25, 0.25], [0.25, 1, 0.25, 0.25, 0.5], [0.25, 0.25, 1, 0, 0],
                              [0.25, 0.25, 0, 1, 0], [0.25, 0.5, 0, 0, 1]]}
taxRate = 0.2583                    # impôt sur les sociétés en France (25 % + contribution sociale)
costOfCapital = 0.06
mcrFactors = {"medicalExpense": (0.047, 0.047), "incomeProtection": (0.131, 0.085), "otherLifeHealth": 0.021, "capitalAtRisk": 0.0007}
mcrCorridor = (0.25, 0.45)
amcr = 4.0e6                        # plancher absolu du MCR (activité vie et santé, montants révisés)
tier2Limit = 0.50                   # Tier 2 + Tier 3 limités à 50 % du SCR
tier2LimitMcr = 0.20                # Tier 2 limité à 20 % du MCR

# ============================================================================
# 5. Bilan, sensibilités, ORSA
# ============================================================================
orsaYears = [2026, 2027, 2028, 2029]
orsaGrowth = 0.04
orsaInvestmentReturn = 0.030

# ============================================================================
# Hypothèses de best estimate
# ============================================================================
expenseInflation = 0.02             # inflation des frais (cible BCE)
horizonMonths = 540                 # 45 ans de projection mensuelle
healthBestEstimateSpYears = ["2024S1", "2024S2", "2025S1", "2025S2", "2026S1"]

# ============================================================================
# Actifs : spreads de valorisation et dette subordonnée
# ============================================================================
bondSpreads = {0: 0.0015, 1: 0.0060, 2: 0.0090, 3: 0.0150, 4: 0.0300}
sovereignSpreads = {"FR": 0.0, "DE": 0.0, "IT": 0.012}
subordinatedDebt = {"nominal": 8.0e6, "coupon": 0.05, "maturite": 10, "spreadEmission": 0.030}
propertyConcentrationThreshold, propertyConcentrationFactor = 0.10, 0.12
counterpartyGamma = 0.25
