"""
underwritingScr.py : ÉTAPE 3, SCR de souscription santé et vie (formule standard, Règlement délégué 2015/35).

POURQUOI : le SCR est la perte de fonds propres de base dans un scénario bicentenaire (quantile 99,5 % à
un an). Pour la souscription, la formule standard impose soit des CHOCS à appliquer au best estimate
(on recalcule entièrement les provisions choquées), soit des FACTEURS appliqués à des volumes.

Arbre calculé (voir schéma du projet) :
  Santé
    NSLT : primes et réserves (écarts-types réglementaires x volumes, Art. 146-148, Annexe XV), rachat de
           masse de 40 % (Art. 150)
    SLT  : mortalité +15 %, longévité -20 %, incapacité-invalidité (incidence +35 % la 1re année, +25 %
           ensuite, reprises -20 %), rachat, frais (+10 %, inflation +1 point), révision (+4 % des rentes)
           (Art. 151-159), agrégés par la matrice de l'Art. 151
    CAT  : accident de masse (France : 0,05 % de la population assurée), concentration d'accidents, pandémie
           (Art. 160-163, Annexe XVI)
    agrégation : corrélation SLT/NSLT 0,5, SLT/CAT 0,25, NSLT/CAT 0,25 (Art. 144)
  Vie (décès) : mortalité +15 %, rachat (hausse, baisse, masse 40 %), frais, catastrophe (+0,15 point de
                mortalité), agrégés par la matrice de l'Annexe IV.
Tous les SCR sont NETS de réassurance (perte de fonds propres après réassurance).
"""
import pickle
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from . import config as C
from .bestEstimate import loadInputs, computeAll, sltBe, decesBe, Shock, discountFactors
from .actuarialTables import invalidAnnuityFactor
from .utils import log, banner, saveTable, saveFig, aggregate

S = C.sltShocks


def nsltPremiumReserve(res, d):
    h, ip = res["health"], res["ip"]
    vPremMe = max(sum(h[s]["cotisations12Mois"] for s in C.health) * (1 + C.healthGrowth), sum(h[s]["cotisations12Mois"] for s in C.health))
    vResMe = max(sum(h[s]["beSinistres"] for s in C.health), 0)
    vPremIp = float(d["tarif"][d["tarif"].garantie.isin(["incapacite", "invalidite"])].cotisationAnnuelle.sum())
    vResIp = max(ip["beSinistresIbnr"], 0)
    rows, sig, vol = [], [], []
    for lob, vp, vr in (("medicalExpense", vPremMe, vResMe), ("incomeProtection", vPremIp, vResIp)):
        sp, sr = C.nslt[lob]["sigmaPrem"], C.nslt[lob]["sigmaRes"]
        s = np.sqrt((sp * vp) ** 2 + sp * vp * sr * vr + (sr * vr) ** 2) / (vp + vr)          # corrélation primes / réserves 0,5
        rows.append({"lob": lob, "volumePrimes": vp, "volumeReserves": vr, "sigmaPrimes": sp, "sigmaReserves": sr, "sigmaCombine": s, "volume": vp + vr})
        sig.append(s); vol.append(vp + vr)
    V = sum(vol)
    M = np.array([[1, C.nsltLobCorrelation], [C.nsltLobCorrelation, 1]])
    sigma = np.sqrt(np.array(sig) * vol @ M @ (np.array(sig) * vol)) / V
    return pd.DataFrame(rows), 3 * sigma * V, sigma


def healthCat(d, res, rates):
    th, tf = d["th_tf"]
    pop = d["pop"]
    P = C.prevoyance
    hc = C.healthCat
    rente = P["renteInvPctSalaire"] * pop.salaire.values
    ages = pop.age.clip(20, 61).values
    af = {a: invalidAnnuityFactor(a, th, tf, 0.03) for a in range(20, 62)}
    perm = rente * np.array([af[int(a)] for a in ages])
    tenY = rente * np.minimum(10, P["ageFinRente"] - ages) * 0.88
    twelveM = P["ijPctSalaire"] * pop.salaire.values * 0.75             # 12 mois d'arrêt : 9 mois indemnisés après franchise
    nHealth = sum(C.health[s]["assures"] for s in C.health)
    E = {"deces": 0.0, "invaliditePermanente": perm.sum(), "incapacite10Ans": tenY.sum(), "incapacite12Mois": twelveM.sum(),
         "soins": nHealth * hc["coutSoinsAccident"]}
    lossMa = hc["massAccidentFrance"] * sum(hc["events"][e] * E[e] for e in E)
    nPrev = len(pop)
    avg = {e: E[e] / (nPrev if e != "soins" else nHealth) for e in E}
    lossAc = hc["plusGrandeConcentration"] * sum(hc["events"][e] * avg[e] for e in E)
    lossPan = hc["pandemicIp"] * perm.sum() + hc["pandemicSymptoms"] * nHealth * (hc["hospitalisation"] * hc["coutHospitalisation"] + hc["consultation"] * hc["coutConsultation"])
    cat = np.sqrt(lossMa ** 2 + lossAc ** 2 + lossPan ** 2)
    det = pd.DataFrame([{"sousModule": "accident de masse", "scr": lossMa}, {"sousModule": "concentration d'accidents", "scr": lossAc},
                        {"sousModule": "pandémie", "scr": lossPan}, {"sousModule": "catastrophe santé (agrégé)", "scr": cat}])
    expo = pd.DataFrame([{"evenement": e, "tauxPersonnesTouchees": hc["events"][e], "sommesAssureesTotales": E[e]} for e in E])
    return cat, det, expo


def run():
    banner("ÉTAPE 3 : SCR DE SOUSCRIPTION SANTÉ (NSLT, SLT, CAT) ET VIE")
    d = loadInputs()
    rates = d["curves"].tauxAvecVa.values
    th, tf = d["th_tf"]
    base = computeAll(d, rates)
    # ---------------- santé NSLT ----------------
    prTab, scrPr, sigma = nsltPremiumReserve(base, d)
    lapseParts = [max(0.0, -C.nsltLapse * base["health"][s]["bePrimes"]) for s in C.health] + [max(0.0, -C.nsltLapse * base["ip"]["bePrimes"])]
    scrNsltLapse = sum(lapseParts)
    scrNslt = np.sqrt(scrPr ** 2 + scrNsltLapse ** 2)
    # ---------------- santé SLT ----------------
    be0 = sltBe(d["inc"], d["inv"], rates, th, tf)["total"]
    shocks = {"mortalite": Shock(mort=1 + S["mortality"]), "longevite": Shock(mort=1 + S["longevity"]),
              "incapacite": Shock(incid1=1 + S["incidenceYear1"], incidAfter=1 + S["incidenceAfter"], recovery=1 + S["recovery"]),
              "frais": Shock(expense=1 + S["expense"], inflAdd=S["expenseInflation"]), "revision": Shock(revision=S["revision"])}
    sltRows = []
    for k, sh in shocks.items():
        b = sltBe(d["inc"], d["inv"], rates, th, tf, sh)["total"]
        sltRows.append({"sousModule": k, "beChoque": b, "scr": max(b - be0, 0.0)})
    sltRows.insert(3, {"sousModule": "rachat", "beChoque": be0, "scr": 0.0})
    slt = pd.DataFrame(sltRows)
    scrSlt = aggregate(slt.set_index("sousModule").loc[C.sltCorrelation["names"], "scr"].values, C.sltCorrelation["matrix"])
    # ---------------- santé CAT ----------------
    scrCat, catDet, catExpo = healthCat(d, base, rates)
    hm = C.healthModuleCorrelation
    Mh = np.array([[1, hm["SLT-NSLT"], hm["SLT-CAT"]], [hm["SLT-NSLT"], 1, hm["NSLT-CAT"]], [hm["SLT-CAT"], hm["NSLT-CAT"], 1]])
    scrHealth = aggregate([scrSlt, scrNslt, scrCat], Mh)
    # ---------------- vie (décès) ----------------
    dc0 = decesBe(d["pop"], d["triDec"], rates, th, tf, d["tarif"])
    net = lambda x: x["bePrimes"] + x["beSinistresIbnr"] - x["creanceReassurance"]
    n0 = net(dc0)
    lifeRows = [
        {"sousModule": "mortalite", "scr": max(net(decesBe(d["pop"], d["triDec"], rates, th, tf, d["tarif"], mortMult=1 + S["mortality"])) - n0, 0)},
        {"sousModule": "longevite", "scr": 0.0}, {"sousModule": "invalidite", "scr": 0.0},
        {"sousModule": "rachat", "scr": max(0.0, -C.sltShocks["massLapse"] * (dc0["bePrimes"] * (1 - C.reinsuranceQuotaShareDeces)))},
        {"sousModule": "frais", "scr": max(net(decesBe(d["pop"], d["triDec"], rates, th, tf, d["tarif"], expenseMult=1 + S["expense"])) - n0, 0)},
        {"sousModule": "revision", "scr": 0.0},
        {"sousModule": "catastrophe", "scr": max(net(decesBe(d["pop"], d["triDec"], rates, th, tf, d["tarif"], catAdd=C.lifeCatShock)) - n0, 0)}]
    life = pd.DataFrame(lifeRows)
    scrLife = aggregate(life.scr.values, C.lifeCorrelation["matrix"])

    summary = pd.DataFrame([
        {"module": "Santé", "sousModule": "NSLT primes et réserves", "scr": scrPr}, {"module": "Santé", "sousModule": "NSLT rachat", "scr": scrNsltLapse},
        {"module": "Santé", "sousModule": "NSLT (agrégé)", "scr": scrNslt}, {"module": "Santé", "sousModule": "SLT (agrégé)", "scr": scrSlt},
        {"module": "Santé", "sousModule": "catastrophe (agrégé)", "scr": scrCat}, {"module": "Santé", "sousModule": "SCR santé", "scr": scrHealth},
        {"module": "Vie", "sousModule": "SCR vie", "scr": scrLife}])
    divHealth = pd.DataFrame([{"module": "santé", "sommeDesSousModules": scrSlt + scrNslt + scrCat, "apresDiversification": scrHealth,
                               "diversification": scrHealth - (scrSlt + scrNslt + scrCat)}])
    saveTable(prTab, "e3NsltPrimesReserves"); saveTable(slt, "e3SltChocs"); saveTable(catDet, "e3CatastropheSante")
    saveTable(catExpo, "e3CatastropheExpositions"); saveTable(life, "e3VieChocs"); saveTable(summary, "e3SyntheseSouscription"); saveTable(divHealth, "e3DiversificationSante")
    with open(C.dataProc / "etape3.pkl", "wb") as fh:
        pickle.dump({"scrHealth": scrHealth, "scrLife": scrLife, "scrSlt": scrSlt, "scrNslt": scrNslt, "scrCat": scrCat, "sigmaNslt": sigma,
                     "scrPr": scrPr, "scrNsltLapse": scrNsltLapse, "slt": slt, "life": life}, fh)

    fig, axes = plt.subplots(1, 3, figsize=(17, 4.8))
    axes[0].bar(slt.sousModule, slt.scr / 1e6, color="#1f3b73"); axes[0].set_title(f"Santé SLT : SCR par choc (M€) ; agrégé {scrSlt / 1e6:.1f}")
    axes[0].tick_params(axis="x", rotation=30)
    parts = ["SLT", "NSLT", "CAT"]
    vals = [scrSlt, scrNslt, scrCat]
    axes[1].bar(parts + ["diversif.", "Santé"], [v / 1e6 for v in vals] + [(scrHealth - sum(vals)) / 1e6, scrHealth / 1e6],
                color=["#1f3b73", "#3e95cd", "#e9a03b", "#2a9d8f", "#c8102e"])
    axes[1].axhline(0, color="k", lw=.6); axes[1].set_title("Agrégation du SCR santé (M€)")
    axes[2].bar(life.sousModule, life.scr / 1e3, color="#6c757d"); axes[2].set_title(f"Vie (décès) : SCR par choc (k€) ; agrégé {scrLife / 1e3:.0f} k€")
    axes[2].tick_params(axis="x", rotation=30)
    saveFig(fig, "e3ScrSouscription")
    log.info("\n%s\n%s\n%s\n%s\n%s", prTab.round(4).to_string(index=False), slt.round(0).to_string(index=False), catDet.round(0).to_string(index=False),
             life.round(0).to_string(index=False), summary.round(0).to_string(index=False))
    return summary
