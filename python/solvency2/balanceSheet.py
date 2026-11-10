"""
balanceSheet.py : ÉTAPE 5, bilan prudentiel, fonds propres, ratios de solvabilité, sensibilités, états
réglementaires et projection ORSA.

  * BILAN S2 (Art. 75 de la Directive) : actifs en valeur de marché, provisions techniques = best estimate +
    marge de risque, créances de réassurance, dette subordonnée en valeur de marché (hors variation du
    risque de crédit propre), impôts différés sur les écarts de valorisation entre le bilan S2 et le bilan
    social (taux de 25,83 %).
  * FONDS PROPRES (Art. 69-82 du Règlement délégué) : fonds d'établissement et réserve de réconciliation
    (Tier 1 non restreint), dette subordonnée (Tier 2), impôts différés actifs nets (Tier 3). Éligibilité :
    Tier 2 + Tier 3 au plus 50 % du SCR, Tier 3 au plus 15 % du SCR ; pour le MCR, Tier 2 au plus 20 % du MCR.
  * RATIOS de couverture du SCR et du MCR.
  * SENSIBILITÉS : fonds propres entièrement revalorisés (actifs, best estimate, dette subordonnée, impôts
    différés) sous chaque hypothèse ; SCR maintenu à son niveau central (lecture « impact sur les fonds propres »).
  * ÉTATS RÉGLEMENTAIRES au format des QRT : S.02.01 (bilan), S.12.01 (provisions vie et santé SLT), S.17.01
    (provisions non-vie et santé NSLT), S.23.01 (fonds propres), S.25.01 (SCR), S.28.02 (MCR).
  * PROJECTION ORSA 2026-2029 : scénario central et scénario adverse ; fonds propres projetés par le compte de
    résultat, SCR projeté module par module avec des inducteurs de volume (méthode usuelle en ORSA).
"""
import pickle
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from . import config as C
from .utils import log, banner, saveTable, saveFig

otherLiabilities = 4.0e6        # dettes diverses (identiques en social et en S2)
establishmentFund = 10.0e6      # fonds d'établissement


def buildBalanceSheets(base, rm, bondMv, bonds, other, sdValue, d, stat=None):
    lob = base["lob"]
    if stat is None:
        stat = pickle.load(open(C.dataProc / "etape2.pkl", "rb"))["stat"]
    rec = float(lob.reassurance.sum())
    beNslt = float(lob[lob.lob.str.startswith("Santé NSLT")].beBrut.sum())
    beSlt = float(lob[lob.lob.str.startswith("Santé SLT")].beBrut.sum())
    beLife = float(lob[lob.lob.str.startswith("Vie")].beBrut.sum())
    tot = beNslt + beSlt + beLife
    rmN, rmS, rmL = rm * beNslt / tot, rm * beSlt / tot, rm * beLife / tot
    cat = lambda c: float(other[other.categorie == c].valeurMarche.sum())
    catB = lambda c: float(other[other.categorie == c].valeurComptable.sum())
    gov = float(bondMv[bonds.type.values == "etat"].sum()); corp = float(bondMv[bonds.type.values == "entreprise"].sum())
    assetsS2 = {"Immobilisations incorporelles": 0.0, "Immobilier (hors usage propre)": cat("immobilier"),
                "Actions": cat("action type 1") + cat("action type 2"), "Obligations d'État": gov, "Obligations d'entreprises": corp,
                "Dépôts": cat("dépôt bancaire"), "Créances de réassurance (provisions cédées)": rec, "Créances nées d'opérations d'assurance": cat("créances")}
    socialStatTot = float(stat.social.sum())
    reinsSocial = C.reinsuranceQuotaShareDeces * float(stat[stat.poste.str.contains("décès", case=False)].social.sum())
    assetsSoc = {"Immobilisations incorporelles": catB("incorporel"), "Immobilier (hors usage propre)": catB("immobilier"),
                 "Actions": catB("action type 1") + catB("action type 2"), "Obligations d'État": float(bonds[bonds.type == "etat"].valeurComptable.sum()),
                 "Obligations d'entreprises": float(bonds[bonds.type == "entreprise"].valeurComptable.sum()), "Dépôts": catB("dépôt bancaire"),
                 "Créances de réassurance (provisions cédées)": reinsSocial, "Créances nées d'opérations d'assurance": catB("créances")}
    liabS2 = {"Provisions techniques santé NSLT (best estimate)": beNslt, "Provisions techniques santé NSLT (marge de risque)": rmN,
              "Provisions techniques santé SLT (best estimate)": beSlt, "Provisions techniques santé SLT (marge de risque)": rmS,
              "Provisions techniques vie (best estimate)": beLife, "Provisions techniques vie (marge de risque)": rmL,
              "Dettes subordonnées": sdValue, "Autres dettes": otherLiabilities}
    liabSoc = {"Provisions techniques (normes françaises)": socialStatTot, "Dettes subordonnées": C.subordinatedDebt["nominal"], "Autres dettes": otherLiabilities}
    navSoc = sum(assetsSoc.values()) - sum(liabSoc.values())
    navS2PreTax = sum(assetsS2.values()) - sum(liabS2.values())
    dt = C.taxRate * (navS2PreTax - navSoc)
    if dt >= 0:
        liabS2["Impôts différés passifs"] = dt; assetsS2["Impôts différés actifs"] = 0.0
    else:
        assetsS2["Impôts différés actifs"] = -dt; liabS2["Impôts différés passifs"] = 0.0
    navS2 = sum(assetsS2.values()) - sum(liabS2.values())
    return {"assetsS2": assetsS2, "liabS2": liabS2, "assetsSoc": assetsSoc, "liabSoc": liabSoc, "navSocial": navSoc, "navS2": navS2,
            "impotsDifferesNets": dt, "rmSplit": (rmN, rmS, rmL), "be": (beNslt, beSlt, beLife), "recov": rec}


def ownFunds(bs, scr, mcr, sdValue):
    nav = bs["navS2"]
    dta = bs["assetsS2"].get("Impôts différés actifs", 0.0)
    t1 = nav - dta
    rows = [("Fonds d'établissement", "Tier 1 non restreint", establishmentFund),
            ("Réserve de réconciliation", "Tier 1 non restreint", t1 - establishmentFund),
            ("Dette subordonnée", "Tier 2", sdValue), ("Impôts différés actifs nets", "Tier 3", dta)]
    of = pd.DataFrame(rows, columns=["element", "tier", "montant"])
    t2, t3 = sdValue, dta
    t3Elig = min(t3, 0.15 * scr)
    t23Elig = min(t2 + t3Elig, 0.5 * scr)
    eligScr = t1 + t23Elig
    eligMcr = t1 + min(t2, C.tier2LimitMcr * mcr)
    return of, {"fondsPropresDeBase": t1 + t2 + t3, "eligiblesScr": eligScr, "eligiblesMcr": eligMcr,
                "ratioScr": eligScr / scr, "ratioMcr": eligMcr / mcr, "tier1": t1, "tier2": t2, "tier3": t3}


def run():
    banner("ÉTAPE 5 : BILAN PRUDENTIEL, FONDS PROPRES, RATIOS, SENSIBILITÉS, ÉTATS RÉGLEMENTAIRES, ORSA")
    from .bestEstimate import loadInputs, computeAll
    from .marketScr import bondPrices, subDebtValue
    e2 = pickle.load(open(C.dataProc / "etape2.pkl", "rb"))
    e3 = pickle.load(open(C.dataProc / "etape3.pkl", "rb"))
    e4 = pickle.load(open(C.dataProc / "etape4.pkl", "rb"))
    d = loadInputs()
    cur = d["curves"]
    bonds = pd.read_csv(C.dataRaw / "actifsObligations.csv"); other = pd.read_csv(C.dataRaw / "actifsAutres.csv")
    base = computeAll(d, cur.tauxAvecVa.values)
    bs = buildBalanceSheets(base, e4["rm"], e4["bondMv"], bonds, other, e4["subDebt"], d, e2["stat"])
    scr, mcr = e4["scr"], e4["mcr"]
    of, ratios = ownFunds(bs, scr, mcr, e4["subDebt"])

    # ---------------- bilans ----------------
    keysA = list(bs["assetsS2"].keys())
    bilanA = pd.DataFrame({"actif": keysA, "social": [bs["assetsSoc"].get(k, 0.0) for k in keysA], "solvabilite2": [bs["assetsS2"][k] for k in keysA]})
    bilanA.loc[len(bilanA)] = ["Total actif", bilanA.social.sum(), bilanA.solvabilite2.sum()]
    bilanL = pd.DataFrame({"passif": list(bs["liabS2"].keys()), "solvabilite2": list(bs["liabS2"].values())})
    bilanL.loc[len(bilanL)] = ["Total passif (hors fonds propres)", bilanL.solvabilite2.sum()]
    bilanL.loc[len(bilanL)] = ["Excédent d'actif sur passif", bs["navS2"]]
    passage = pd.DataFrame([
        ("Fonds propres sociaux (actif net comptable)", bs["navSocial"]),
        ("Plus ou moins-values latentes sur placements", (bilanA.solvabilite2.iloc[1:6].sum() - bilanA.social.iloc[1:6].sum())),
        ("Annulation de l'immobilisation incorporelle", -bs["assetsSoc"]["Immobilisations incorporelles"]),
        ("Provisions techniques : social -> best estimate (net de réassurance)", float(e2["stat"].social.sum()) - (sum(bs["be"])) - (bs["assetsSoc"]["Créances de réassurance (provisions cédées)"] - bs["recov"])),
        ("Marge de risque", -e4["rm"]),
        ("Dette subordonnée en valeur de marché", C.subordinatedDebt["nominal"] - e4["subDebt"]),
        ("Impôts différés", -bs["impotsDifferesNets"]),
        ("Excédent d'actif sur passif S2", bs["navS2"])], columns=["etape", "montant"])
    ratioTab = pd.DataFrame([{"indicateur": k, "valeur": v} for k, v in
                             {"SCR": scr, "MCR": mcr, **ratios}.items()])

    # ---------------- états réglementaires ----------------
    h, ip, dc = base["health"], base["ip"], base["deces"]
    rmN, rmS, rmL = bs["rmSplit"]
    s1701 = pd.DataFrame([
        {"ligne": "Provision pour primes brute (BE)", "fraisMedicaux": sum(h[s]["bePrimes"] for s in C.health), "perteDeRevenus": ip["bePrimes"]},
        {"ligne": "Provision pour sinistres brute (BE)", "fraisMedicaux": sum(h[s]["beSinistres"] for s in C.health), "perteDeRevenus": ip["beSinistresIbnr"]},
        {"ligne": "Marge de risque", "fraisMedicaux": rmN * (bs["be"][0] - ip["bePrimes"] - ip["beSinistresIbnr"]) / bs["be"][0],
         "perteDeRevenus": rmN * (ip["bePrimes"] + ip["beSinistresIbnr"]) / bs["be"][0]}])
    s1701.loc[len(s1701)] = ["Provisions techniques totales", s1701.fraisMedicaux.sum(), s1701.perteDeRevenus.sum()]
    s1201 = pd.DataFrame([
        {"ligne": "Best estimate brut", "santeSlt": bs["be"][1], "vieAutres": bs["be"][2]},
        {"ligne": "Créances de réassurance", "santeSlt": 0.0, "vieAutres": bs["recov"]},
        {"ligne": "Best estimate net", "santeSlt": bs["be"][1], "vieAutres": bs["be"][2] - bs["recov"]},
        {"ligne": "Marge de risque", "santeSlt": rmS, "vieAutres": rmL}])
    s1201.loc[len(s1201)] = ["Provisions techniques totales (brutes)", bs["be"][1] + rmS, bs["be"][2] + rmL]
    s2501 = e4["synth"].copy()
    s2302 = of.copy()
    s2302.loc[len(s2302)] = ["Fonds propres éligibles pour le SCR", "", ratios["eligiblesScr"]]
    s2302.loc[len(s2302)] = ["Fonds propres éligibles pour le MCR", "", ratios["eligiblesMcr"]]
    s2802 = pd.DataFrame([("MCR linéaire", e4["mcrLinear"]), ("SCR", scr), ("Plafond du MCR (45 % du SCR)", 0.45 * scr),
                          ("Plancher du MCR (25 % du SCR)", 0.25 * scr), ("Plancher absolu (AMCR)", C.amcr), ("MCR", mcr)], columns=["ligne", "montant"])

    # ---------------- sensibilités (revalorisation complète) ----------------
    from .marketData import shockCurve
    from .marketScr import bondPrices as bp
    rfr, va = cur.tauxSansVa.values, cur.tauxAvecVa.values
    sens = []
    beNet0 = base["lob"].beNet.sum()

    def navUnder(rfrS, vaS, eqMult=1.0, spreadAdd=0.0, spShock=0.0, useInv=1.0):
        b = bonds.copy()
        mv = bp(b, rfrS)
        if spreadAdd:                                   # choc de spread : variation de prix = - duration x choc
            mv = np.array([m * (1 - du * spreadAdd) if t == "entreprise" else m for m, du, t in zip(mv, b.duration, b.type)])
        oth = other.copy()
        oth.loc[oth.categorie.str.startswith("action"), "valeurMarche"] *= eqMult
        if useInv != 1.0:
            import solvency2.bestEstimate as B
            import solvency2.actuarialTables as AT
            orig = AT.invalidityRecovery
            shocked = lambda a: orig(a) * useInv                  # choc appliqué aux invalides en cours ET aux invalidités futures
            B.invalidityRecovery = AT.invalidityRecovery = shocked
            try:
                bb = computeAll(d, vaS, spShock=spShock)
            finally:
                B.invalidityRecovery = AT.invalidityRecovery = orig
        else:
            bb = computeAll(d, vaS, spShock=spShock)
        bs2 = buildBalanceSheets(bb, e4["rm"], mv, b, oth, subDebtValue(rfrS), d, e2["stat"])
        return bs2["navS2"], bb["lob"].beNet.sum()

    cases = [("Baisse des taux de 50 pb", rfr - 0.005, va - 0.005, {}),
             ("Hausse des taux de 50 pb", rfr + 0.005, va + 0.005, {}),
             ("Baisse des actions de 25 %", rfr, va, {"eqMult": 0.75}),
             ("Hausse des spreads d'entreprises de 50 pb", rfr, va, {"spreadAdd": 0.005}),
             ("Sinistralité santé +5 points de S/P", rfr, va, {"spShock": 0.05}),
             ("Reprises d'activité des invalides -20 %", rfr, va, {"useInv": 0.8}),
             ("Sans correction pour volatilité", rfr, rfr * 0 + cur.tauxSansVa.values, {})]
    for lab, rS, vS, kw in cases:
        nav, beN = navUnder(rS, vS, **kw)
        dNav = nav - bs["navS2"]
        elig = ratios["eligiblesScr"] + dNav
        sens.append({"sensibilite": lab, "variationFondsPropres": dNav, "variationBestEstimateNet": beN - beNet0,
                     "ratioScrApres": elig / scr, "variationRatioPoints": (elig / scr - ratios["ratioScr"]) * 100})
    sens = pd.DataFrame(sens)

    # ---------------- ORSA 2026-2029 ----------------
    orsa = []
    for scen in ("central", "adverse"):
        ofv, scrv = ratios["eligiblesScr"], scr
        premH = sum(h[s]["cotisations12Mois"] for s in C.health); premP = float(d["tarif"].cotisationAnnuelle.sum())
        prem = premH + premP
        lossRatio = (sum(h[s]["cotisations12Mois"] * h[s]["spBestEstimate"] for s in C.health) + premP * C.prevoyance["ratioSinistresCibleTarif"]) / prem
        expRatio = (sum(h[s]["cotisations12Mois"] * C.health[s]["fraisGestionPrimes"] for s in C.health) +
                    premP * (C.prevoyance["fraisGestionPrimes"] + C.prevoyance["fraisGestionPrestations"])) / prem
        assets = sum(bs["assetsS2"].values())
        mod = {"marche": e4["scrMarket"], "contrepartie": e4["scrDef"], "vie": e3["scrLife"], "sante": e3["scrHealth"]}
        for i, y in enumerate(C.orsaYears):
            if i > 0:
                g = C.orsaGrowth
                sp = 0.05 if (scen == "adverse" and i == 1) else 0.0
                mkt = -0.25 * float(other[other.categorie.str.startswith("action")].valeurMarche.sum()) if (scen == "adverse" and i == 1) else 0.0
                uwResult = prem * (1 - lossRatio - sp - expRatio)
                fin = assets * C.orsaInvestmentReturn + mkt
                res = (uwResult + fin) * (1 - C.taxRate)
                prem *= 1 + g
                assets += res + prem * 0.0
                ofv += res
                mod = {k: v * (1 + g) for k, v in mod.items()}
                if scen == "adverse" and i == 1:
                    mod["marche"] *= 0.9
                bscrP = float(np.sqrt(np.array(list(mod.values())) @ np.array(C.bscrCorrelation["matrix"])[:4, :4] @ np.array(list(mod.values()))))
                scrv = bscrP * (scr / (e4["bscr"])) if e4["bscr"] else bscrP
            orsa.append({"scenario": scen, "annee": y, "fondsPropresEligibles": ofv, "scr": scrv, "ratio": ofv / scrv})
    orsa = pd.DataFrame(orsa)

    for name, df in (("e5BilanActif", bilanA), ("e5BilanPassif", bilanL), ("e5PassageSocialS2", passage), ("e5FondsPropres", of),
                     ("e5Ratios", ratioTab), ("e5QrtS0201Actif", bilanA), ("e5QrtS1201", s1201), ("e5QrtS1701", s1701),
                     ("e5QrtS2302", s2302), ("e5QrtS2501", s2501), ("e5QrtS2802", s2802), ("e5Sensibilites", sens), ("e5Orsa", orsa)):
        saveTable(df, name)

    fig, axes = plt.subplots(2, 2, figsize=(15, 10))
    ax = axes[0, 0]
    aS2 = sum(bs["assetsS2"].values())
    parts = [("BE", sum(bs["be"]) - bs["recov"]), ("Marge de risque", e4["rm"]), ("Dette subordonnée", e4["subDebt"]),
             ("Impôts différés", max(bs["impotsDifferesNets"], 0)), ("Autres dettes", otherLiabilities), ("Fonds propres", bs["navS2"])]
    bottom = 0
    for (lab, v), col in zip(parts, ["#1f3b73", "#3e95cd", "#e9a03b", "#9fb3d9", "#6c757d", "#2a9d8f"]):
        ax.bar(1, v / 1e6, bottom=bottom / 1e6, color=col, label=lab); bottom += v
    ax.bar(0, (aS2 - bs["recov"]) / 1e6, color="#c8102e", label="Actifs (nets des créances de réassurance)")
    ax.set_xticks([0, 1]); ax.set_xticklabels(["Actif", "Passif"]); ax.set_xlim(-0.6, 2.8); ax.legend(fontsize=7, loc="center right"); ax.set_title("Bilan Solvabilité II au 30/06/2026 (M€)")
    ax = axes[0, 1]
    ax.bar(passage.etape.str.slice(0, 28), passage.montant / 1e6, color=["#6c757d"] + ["#9fb3d9"] * 6 + ["#2a9d8f"])
    ax.tick_params(axis="x", rotation=60, labelsize=7); ax.axhline(0, color="k", lw=.6); ax.set_title("Du fonds propres social à l'excédent S2 (M€)")
    ax = axes[1, 0]
    ax.barh(sens.sensibilite, sens.variationRatioPoints, color=np.where(sens.variationRatioPoints < 0, "#c8102e", "#2a9d8f"))
    ax.set_title(f"Sensibilités du ratio de solvabilité ({ratios['ratioScr']:.0%}), en points"); ax.tick_params(axis="y", labelsize=8)
    ax = axes[1, 1]
    for scen, col in (("central", "#1f3b73"), ("adverse", "#c8102e")):
        g = orsa[orsa.scenario == scen]
        ax.plot(g.annee, g.ratio * 100, "o-", color=col, label=scen)
    ax.axhline(100, color="k", ls="--", lw=.8); ax.set_xticks(C.orsaYears); ax.set_ylim(0, None)
    ax.set_title("Projection ORSA du ratio de solvabilité (%)"); ax.legend()
    saveFig(fig, "e5BilanEtRatios")
    log.info("\n%s\n%s\n%s\n%s\n%s\n%s", bilanA.round(0).to_string(index=False), bilanL.round(0).to_string(index=False), passage.round(0).to_string(index=False),
             of.round(0).to_string(index=False), ratioTab.round(4).to_string(index=False), sens.round(3).to_string(index=False) + "\n" + orsa.round(3).to_string(index=False))
    return ratios
