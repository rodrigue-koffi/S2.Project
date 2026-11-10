"""
marketScr.py : ÉTAPE 4, SCR de marché, de contrepartie, opérationnel, BSCR, ajustement pour impôts différés,
SCR, MCR et marge de risque.

  * MARCHÉ (Art. 164-188), en revalorisation complète de l'actif ET du passif :
      taux : courbes choquées à la hausse et à la baisse (table EIOPA), obligations repricées, best estimate
             recalculé, dette subordonnée revalorisée ; on retient le scénario le plus défavorable ;
      actions : type 1 39 % + ajustement symétrique, type 2 49 % + ajustement symétrique, corrélation 0,75 ;
      immobilier : 25 % ;
      spread : facteur selon l'échelon de qualité de crédit et la duration (Art. 176), exemption des
               obligations d'États de l'Union en euros ;
      change : 25 % sur les expositions en dollars ;
      concentration : excès au-delà des seuils par émetteur (3 % ou 1,5 % selon la notation, 10 % pour
               l'immobilier) x facteur g ;
      agrégation : matrice de l'Art. 164 avec A = 0 si le choc de hausse des taux est retenu, 0,5 sinon.
  * CONTREPARTIE (Art. 189-202) : type 1 (réassureur, banques : formule de variance), type 2 (créances :
    15 %, 90 % au-delà de 3 mois de retard), agrégation.
  * ACTIFS INCORPORELS (Art. 203) : 80 % de la valeur S2 (nulle ici : logiciel non cessible).
  * OPÉRATIONNEL (Art. 204) : max(primes, provisions) plafonné à 30 % du BSCR.
  * BSCR (Art. 87, matrice de l'Annexe IV), AJUSTEMENT pour impôts différés (Art. 207) limité aux impôts
    différés passifs nets du bilan (aucune reconnaissance sur profits futurs : choix prudent), SCR.
  * MCR (Art. 248-251) : formule linéaire, corridor 25 %-45 % du SCR, plancher absolu.
  * MARGE DE RISQUE (Art. 37-39) : coût du capital 6 % ; SCR de l'entreprise de référence RECALCULÉ À CHAQUE
    ANNÉE FUTURE (chocs SLT relancés à partir de chaque date sur le portefeuille en run-off, réserves santé
    en run-off), sans méthode simplifiée.
"""
import pickle
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from . import config as C
from .bestEstimate import loadInputs, computeAll, sltBe, Shock, discountFactors, healthClaimsCashflows
from .marketData import shockCurve
from .utils import log, banner, saveTable, saveFig, aggregate

S = C.sltShocks


# ----------------------------------------------------------------------------
# Actifs
# ----------------------------------------------------------------------------
def bondPrices(bonds, rfr):
    out = []
    for _, b in bonds.iterrows():
        t = np.arange(1, int(b.maturite) + 1)
        sp = C.sovereignSpreads.get(b.pays, 0.0) if b.type == "etat" else C.bondSpreads[int(b.cqs)]
        y = rfr[t - 1] + sp
        cf = np.full(len(t), b.coupon * b.nominal); cf[-1] += b.nominal
        out.append(float((cf / (1 + y) ** t).sum()))
    return np.array(out)


def subDebtValue(rfr):
    sd = C.subordinatedDebt
    t = np.arange(1, sd["maturite"] + 1)
    cf = np.full(len(t), sd["coupon"] * sd["nominal"]); cf[-1] += sd["nominal"]
    return float((cf / (1 + rfr[t - 1] + sd["spreadEmission"]) ** t).sum())


def spreadFactor(dur, cqs):
    tab = {0: [(0.009, 0), (0.045, 0.005), (0.07, 0.005), (0.095, 0.005), (0.12, 0.005)],
           1: [(0.011, 0), (0.055, 0.006), (0.084, 0.005), (0.109, 0.005), (0.134, 0.005)],
           2: [(0.014, 0), (0.07, 0.007), (0.105, 0.005), (0.13, 0.005), (0.155, 0.005)],
           3: [(0.025, 0), (0.125, 0.015), (0.2, 0.01), (0.25, 0.01), (0.3, 0.005)],
           4: [(0.045, 0), (0.225, 0.025), (0.35, 0.018), (0.44, 0.005), (0.465, 0.005)]}[int(cqs)]
    if dur <= 5:
        return tab[0][0] * dur
    for k, (lo, hi) in enumerate([(5, 10), (10, 15), (15, 20)], start=1):
        if dur <= hi:
            return tab[k][0] + tab[k][1] * (dur - lo)
    return min(tab[4][0] + tab[4][1] * (dur - 20), 1.0)


# ----------------------------------------------------------------------------
# Contrepartie type 1
# ----------------------------------------------------------------------------
def counterpartyType1(exposures):
    """exposures : liste (pd, lgd). Formule de variance de l'Art. 200."""
    pds = sorted({pd_ for pd_, _ in exposures})
    tl = {p: sum(l for q, l in exposures if q == p) for p in pds}
    sl = {p: sum(l ** 2 for q, l in exposures if q == p) for p in pds}
    g = C.counterpartyGamma
    vInter = sum(pj * (1 - pj) * pk * (1 - pk) / ((1 + g) * (pj + pk) - pj * pk) * tl[pj] * tl[pk] for pj in pds for pk in pds)
    vIntra = sum(1.5 * p * (1 - p) / (2.5 - p) * sl[p] for p in pds)
    sv, tot = np.sqrt(vInter + vIntra), sum(tl.values())
    if sv <= 0.07 * tot:
        return 3 * sv
    if sv <= 0.20 * tot:
        return 5 * sv
    return tot


# ----------------------------------------------------------------------------
# Marge de risque : SCR de l'entreprise de référence recalculé à chaque date future
# ----------------------------------------------------------------------------
def riskMargin(d, base, scrUw, defaultReins, opTab, rates):
    th, tf = d["th_tf"]
    shocks = {"mortalite": Shock(mort=1 + S["mortality"]), "longevite": Shock(mort=1 + S["longevity"]),
              "incapacite": Shock(incid1=1 + S["incidenceYear1"], incidAfter=1 + S["incidenceAfter"], recovery=1 + S["recovery"]),
              "frais": Shock(expense=1 + S["expense"], inflAdd=S["expenseInflation"]), "revision": Shock(revision=S["revision"])}
    healthCf = {s: base["healthCf"][s][0] for s in C.health}
    ipIbnr0 = base["ip"]["beSinistresIbnr"]
    rows = []
    T = 40
    for t in range(0, T + 1):
        fm = 12 * t
        b0 = sltBe(d["inc"], d["inv"], rates, th, tf, Shock(start=fm), fm)["total"]
        if b0 < 1e3:
            break
        sub = {}
        for k, sh in shocks.items():
            sh.start = fm
            sub[k] = max(sltBe(d["inc"], d["inv"], rates, th, tf, sh, fm)["total"] - b0, 0.0)
        sub["rachat"] = 0.0
        scrSlt = aggregate([sub[n] for n in C.sltCorrelation["names"]], C.sltCorrelation["matrix"])
        # réserves santé en run-off (flux semestriels), primes uniquement à t = 0 (limite des contrats)
        resMe = 0.0
        for s in C.health:
            cf = healthCf[s]
            k0 = 2 * t
            fut = cf[k0 + 1:] if k0 + 1 < len(cf) else np.array([])
            tt = (np.arange(len(fut)) + k0 + 0.5) / 2
            resMe += float((fut * discountFactors(rates, np.maximum(tt, 0.25)) / (discountFactors(rates, [max(t, 1e-9)])[0] if t > 0 else 1)).sum())
        ipRes = ipIbnr0 * (b0 / base["slt"]["total"]) if t > 0 else ipIbnr0      # les arrêts IBNR s'écoulent comme les sinistres en cours
        vPremMe = sum(base["health"][s]["cotisationsS2"] for s in C.health) if t == 0 else 0.0
        vPremIp = base["ip"]["cotisationsS2"] if t == 0 else 0.0
        sig, vol = [], []
        for lob, vp, vr in (("medicalExpense", vPremMe, resMe), ("incomeProtection", vPremIp, ipRes)):
            sp, sr = C.nslt[lob]["sigmaPrem"], C.nslt[lob]["sigmaRes"]
            v = vp + vr
            sig.append(np.sqrt((sp * vp) ** 2 + sp * vp * sr * vr + (sr * vr) ** 2) / v if v > 0 else 0); vol.append(v)
        sv = np.array(sig) * np.array(vol)
        scrNslt = float(np.sqrt(sv @ np.array([[1, 0.5], [0.5, 1]]) @ sv)) * 3
        if t == 0:
            scrNslt = np.sqrt(scrNslt ** 2 + scrUw["scrNsltLapse"] ** 2)
        scrCat = scrUw["scrCat"] if t == 0 else 0.0
        hm = C.healthModuleCorrelation
        scrHealth = aggregate([scrSlt, scrNslt, scrCat], [[1, hm["SLT-NSLT"], hm["SLT-CAT"]], [hm["SLT-NSLT"], 1, hm["NSLT-CAT"]], [hm["SLT-CAT"], hm["NSLT-CAT"], 1]])
        scrLife = scrUw["scrLife"] if t == 0 else 0.0
        dflt = defaultReins if t == 0 else 0.0
        bscr = aggregate([0, dflt, scrLife, scrHealth, 0], C.bscrCorrelation["matrix"])
        opProv = 0.0045 * b0 + 0.03 * (resMe + ipRes)
        opPrem = opTab["opPrimes"] if t == 0 else 0.0
        op = min(0.3 * bscr, max(opProv, opPrem))
        rows.append({"annee": t, "beSltRunOff": b0, "reservesSanteRunOff": resMe, "scrSlt": scrSlt, "scrNslt": scrNslt, "scrCat": scrCat,
                     "scrVie": scrLife, "scrContrepartieReassurance": dflt, "scrOperationnel": op, "scrReference": bscr + op})
    rm = pd.DataFrame(rows)
    rm["actualisation"] = discountFactors(rates, rm.annee + 1)
    rm["coutDuCapital"] = C.costOfCapital * rm.scrReference * rm.actualisation
    return rm, float(rm.coutDuCapital.sum())


def run():
    banner("ÉTAPE 4 : SCR MARCHÉ, CONTREPARTIE, OPÉRATIONNEL, BSCR, SCR, MCR ET MARGE DE RISQUE")
    d = loadInputs()
    cur = d["curves"]
    ratesVa, rfr = cur.tauxAvecVa.values, cur.tauxSansVa.values
    shocks = pd.read_pickle(C.dataProc / "chocsTaux.pkl")
    uw = pickle.load(open(C.dataProc / "etape3.pkl", "rb"))
    bonds = pd.read_csv(C.dataRaw / "actifsObligations.csv")
    other = pd.read_csv(C.dataRaw / "actifsAutres.csv")
    base = computeAll(d, ratesVa)
    beNet0 = base["lob"].beNet.sum()
    bondMv0 = bondPrices(bonds, rfr)
    sd0 = subDebtValue(rfr)

    # ---------------- taux ----------------
    rate = {}
    for direction in ("up", "down"):
        rfrS = shockCurve(rfr, shocks, direction)
        vaS = cur.tauxAvecVaChocHausse.values if direction == "up" else cur.tauxAvecVaChocBaisse.values
        dA = bondPrices(bonds, rfrS).sum() - bondMv0.sum()
        dL = computeAll(d, vaS)["lob"].beNet.sum() - beNet0
        dSd = subDebtValue(rfrS) - sd0
        rate[direction] = {"variationActifs": dA, "variationBestEstimate": dL, "variationDetteSubordonnee": dSd, "perteFondsPropres": -(dA - dL - dSd)}
    rateTab = pd.DataFrame(rate).T.reset_index().rename(columns={"index": "scenario"})
    scrRate = max(rate["up"]["perteFondsPropres"], rate["down"]["perteFondsPropres"], 0.0)
    A = 0.0 if rate["up"]["perteFondsPropres"] >= rate["down"]["perteFondsPropres"] else 0.5
    # ---------------- actions, immobilier, change ----------------
    eq1 = other[other.categorie == "action type 1"].valeurMarche.sum()
    eq2 = other[other.categorie == "action type 2"].valeurMarche.sum()
    s1, s2 = C.equityShock["type1"] + C.symmetricAdjustment, C.equityShock["type2"] + C.symmetricAdjustment
    scrEq = aggregate([s1 * eq1, s2 * eq2], [[1, C.equityCorrelation], [C.equityCorrelation, 1]])
    prop = other[other.categorie == "immobilier"].valeurMarche.sum()
    scrProp = C.propertyShock * prop
    usd = other[other.devise == "USD"].valeurMarche.sum()
    scrFx = C.currencyShock * usd
    # ---------------- spread ----------------
    bonds["valeurMarcheS2"] = bondMv0
    exempt = (bonds.type == "etat") & bonds.pays.isin(["FR", "DE", "IT"])
    bonds["facteurSpread"] = [0.0 if ex else spreadFactor(du, cq) for ex, du, cq in zip(exempt, bonds.duration, bonds.cqs)]
    bonds["scrSpread"] = bonds.facteurSpread * bonds.valeurMarcheS2
    scrSpread = bonds.scrSpread.sum()
    # ---------------- concentration ----------------
    totalAssets = bondMv0.sum() + other.valeurMarche.sum()
    conc = []
    for _, b in bonds[~exempt].iterrows():
        cqs = int(b.cqs)
        xs = max(0.0, b.valeurMarcheS2 - C.concentration["threshold"][cqs] * totalAssets)
        conc.append({"exposition": b.emetteur, "montant": b.valeurMarcheS2, "seuil": C.concentration["threshold"][cqs] * totalAssets, "exces": xs,
                     "scr": xs * C.concentration["g"][cqs]})
    for _, o in other[other.categorie == "immobilier"].iterrows():
        xs = max(0.0, o.valeurMarche - C.propertyConcentrationThreshold * totalAssets)
        conc.append({"exposition": o.emetteur, "montant": o.valeurMarche, "seuil": C.propertyConcentrationThreshold * totalAssets, "exces": xs,
                     "scr": xs * C.propertyConcentrationFactor})
    conc = pd.DataFrame(conc)
    scrConc = float(np.sqrt((conc.scr ** 2).sum()))
    Mm = np.array([[1, A, A, A, 0.25, 0], [A, 1, 0.75, 0.75, 0.25, 0], [A, 0.75, 1, 0.5, 0.25, 0],
                   [A, 0.75, 0.5, 1, 0.25, 0], [0.25, 0.25, 0.25, 0.25, 1, 0], [0, 0, 0, 0, 0, 1]])
    mk = [scrRate, scrEq, scrProp, scrSpread, scrFx, scrConc]
    scrMarket = aggregate(mk, Mm)
    # ---------------- contrepartie ----------------
    recov = float(base["lob"].reassurance.sum())
    rmEffect = uw["scrLife"] * C.reinsuranceQuotaShareDeces / (1 - C.reinsuranceQuotaShareDeces)
    lgdReins = max(0.5 * (recov + 0.5 * rmEffect), 0.0)
    banks = other[other.categorie == "dépôt bancaire"]
    exposures = [(C.counterpartyPd[C.reinsurerCqs], lgdReins)] + [(C.counterpartyPd[int(c)], v) for c, v in zip(banks.cqs, banks.valeurMarche)]
    scrDef1 = counterpartyType1(exposures)
    rec = other[other.categorie == "créances"].valeurMarche.sum()
    scrDef2 = C.receivablesFactor * rec * 0.9 + C.receivablesOverdueFactor * rec * 0.1
    scrDef = float(np.sqrt(scrDef1 ** 2 + 1.5 * scrDef1 * scrDef2 + scrDef2 ** 2))
    scrDefReinsOnly = counterpartyType1([(C.counterpartyPd[C.reinsurerCqs], lgdReins)])
    # ---------------- BSCR, opérationnel ----------------
    scrIntangible = 0.8 * other[other.categorie == "incorporel"].valeurMarche.sum()
    bscr = aggregate([scrMarket, scrDef, uw["scrLife"], uw["scrHealth"], 0.0], C.bscrCorrelation["matrix"]) + scrIntangible
    lob = base["lob"]
    earnLife = float(d["tarif"][d["tarif"].garantie == "deces"].cotisationAnnuelle.iloc[0])
    earnNl = sum(base["health"][s]["cotisations12Mois"] for s in C.health) + float(d["tarif"][d["tarif"].garantie != "deces"].cotisationAnnuelle.sum())
    tpLife = float(lob[lob.lob.str.startswith(("Santé SLT", "Vie"))].beBrut.sum())
    tpNl = float(lob[lob.lob.str.startswith("Santé NSLT")].beBrut.sum())
    opPrem, opProv = 0.04 * earnLife + 0.03 * earnNl, 0.0045 * max(tpLife, 0) + 0.03 * max(tpNl, 0)
    scrOp = min(0.3 * bscr, max(opPrem, opProv))
    opTab = {"opPrimes": opPrem, "opProvisions": opProv, "scrOperationnel": scrOp}
    # ---------------- marge de risque ----------------
    rmTab, rm = riskMargin(d, base, uw, scrDefReinsOnly, opTab, ratesVa)
    # ---------------- impôts différés et ajustement ----------------
    from .balanceSheet import buildBalanceSheets
    bs = buildBalanceSheets(base, rm, bondMv0, bonds, other, sd0, d)
    netDtl = bs["impotsDifferesNets"]
    adjDt = -min(C.taxRate * (bscr + scrOp), max(netDtl, 0.0))
    scr = bscr + scrOp + adjDt
    # ---------------- MCR ----------------
    h = base["health"]
    meBe = max(sum(h[s]["beSinistres"] + h[s]["bePrimes"] for s in C.health), 0)
    mePrem = sum(h[s]["cotisations12Mois"] for s in C.health)
    ipBe = max(base["ip"]["beSinistresIbnr"] + base["ip"]["bePrimes"], 0)
    ipPrem = float(d["tarif"][d["tarif"].garantie != "deces"].cotisationAnnuelle.sum())
    mcrNl = C.mcrFactors["medicalExpense"][0] * meBe + C.mcrFactors["medicalExpense"][1] * mePrem + C.mcrFactors["incomeProtection"][0] * ipBe + C.mcrFactors["incomeProtection"][1] * ipPrem
    lifeNetBe = float(lob[lob.lob.str.startswith(("Santé SLT", "Vie"))].beNet.sum())
    car = base["deces"]["capitalSousRisque"] * (1 - C.reinsuranceQuotaShareDeces)
    mcrL = C.mcrFactors["otherLifeHealth"] * lifeNetBe + C.mcrFactors["capitalAtRisk"] * car
    mcrLinear = mcrNl + mcrL
    mcrComb = min(max(mcrLinear, C.mcrCorridor[0] * scr), C.mcrCorridor[1] * scr)
    mcr = max(mcrComb, C.amcr)

    marketTab = pd.DataFrame({"sousModule": ["taux", "action", "immobilier", "spread", "change", "concentration"], "scr": mk})
    synth = pd.DataFrame([
        ("SCR marché", scrMarket), ("SCR contrepartie", scrDef), ("SCR vie", uw["scrLife"]), ("SCR santé", uw["scrHealth"]), ("SCR non-vie", 0.0),
        ("Somme des modules", scrMarket + scrDef + uw["scrLife"] + uw["scrHealth"]),
        ("Diversification entre modules", bscr - scrIntangible - (scrMarket + scrDef + uw["scrLife"] + uw["scrHealth"])),
        ("SCR actifs incorporels", scrIntangible), ("BSCR", bscr), ("SCR opérationnel", scrOp), ("Ajustement pour impôts différés", adjDt),
        ("SCR", scr), ("MCR linéaire", mcrLinear), ("MCR combiné (corridor 25 %-45 % du SCR)", mcrComb), ("MCR", mcr), ("Marge de risque", rm)],
        columns=["poste", "montant"])
    defTab = pd.DataFrame([{"contrepartie": "réassureur (quote-part décès)", "type": 1, "lgd": lgdReins},
                           *[{"contrepartie": n, "type": 1, "lgd": v} for n, v in zip(banks.emetteur, banks.valeurMarche)],
                           {"contrepartie": "créances sur assurés et intermédiaires", "type": 2, "lgd": rec},
                           {"contrepartie": "SCR type 1", "type": 1, "lgd": scrDef1}, {"contrepartie": "SCR type 2", "type": 2, "lgd": scrDef2}])
    saveTable(rateTab, "e4ScrTaux"); saveTable(marketTab, "e4ScrMarche"); saveTable(bonds, "e4SpreadParLigne"); saveTable(conc, "e4Concentration")
    saveTable(defTab, "e4Contrepartie"); saveTable(pd.DataFrame([opTab]), "e4Operationnel"); saveTable(rmTab, "e4MargeDeRisque")
    saveTable(synth, "e4SyntheseScr")
    with open(C.dataProc / "etape4.pkl", "wb") as fh:
        pickle.dump({"synth": synth, "scr": scr, "mcr": mcr, "rm": rm, "bscr": bscr, "scrOp": scrOp, "adjDt": adjDt, "scrMarket": scrMarket,
                     "scrDef": scrDef, "marketTab": marketTab, "bondMv": bondMv0, "subDebt": sd0, "A": A, "rateTab": rateTab,
                     "mcrLinear": mcrLinear, "opTab": opTab}, fh)

    fig, axes = plt.subplots(1, 3, figsize=(17, 4.8))
    axes[0].bar(marketTab.sousModule, marketTab.scr / 1e6, color="#1f3b73"); axes[0].set_title(f"SCR marché par sous-module (M€) ; agrégé {scrMarket / 1e6:.1f}")
    labels = ["Marché", "Contrepartie", "Vie", "Santé", "Diversif.", "BSCR", "Opérationnel", "Impôts diff.", "SCR"]
    vals = [scrMarket, scrDef, uw["scrLife"], uw["scrHealth"], bscr - scrIntangible - (scrMarket + scrDef + uw["scrLife"] + uw["scrHealth"]), bscr, scrOp, adjDt, scr]
    cols = ["#1f3b73", "#3e95cd", "#6c757d", "#2a9d8f", "#9fb3d9", "#1f3b73", "#e9a03b", "#9fb3d9", "#c8102e"]
    axes[1].bar(labels, np.array(vals) / 1e6, color=cols); axes[1].axhline(0, color="k", lw=.6); axes[1].tick_params(axis="x", rotation=40)
    axes[1].set_title("Du BSCR au SCR (M€)")
    axes[2].bar(rmTab.annee, rmTab.scrReference / 1e6, color="#2a9d8f", label="SCR de l'entreprise de référence")
    axes[2].set_title(f"Marge de risque = 6 % x somme actualisée : {rm / 1e6:.1f} M€"); axes[2].set_xlabel("année de run-off"); axes[2].legend(fontsize=8)
    saveFig(fig, "e4ScrMarcheEtAgregation")
    log.info("\n%s\n%s\n%s\n%s", rateTab.round(0).to_string(index=False), marketTab.round(0).to_string(index=False), synth.round(0).to_string(index=False),
             rmTab.head(8).round(0).to_string(index=False))
    return synth
