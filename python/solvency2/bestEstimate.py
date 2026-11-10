"""
bestEstimate.py : ÉTAPE 2, provisions techniques Solvabilité II (best estimate) et passage depuis les comptes sociaux.

POURQUOI : en S2, les provisions techniques = BEST ESTIMATE (moyenne pondérée par les probabilités des flux
futurs, actualisée avec la courbe EIOPA + VA, sans prudence) + MARGE DE RISQUE (étape 4). Les provisions des
comptes sociaux sont prudentes (taux technique bas, marges) : l'écart alimente les fonds propres S2.

Segmentation (lignes d'activité S2) :
  * Santé NSLT « frais médicaux » (LoB 1) : frais de soins, individuel et collectif ;
  * Santé NSLT « perte de revenus » (LoB 2) : arrêts de travail futurs (période non échue) et arrêts survenus
    non déclarés (IBNR) ;
  * Santé SLT « rentes issues de contrats non-vie » (LoB 33) : incapacités et invalidités EN COURS ;
  * Vie « autres » (LoB 32) : décès, réassuré en quote-part 50 %.

Méthodes :
  * sinistres santé : Chain Ladder semestriel par segment (erreur de Mack), cadence de paiement, frais de gestion
    des sinistres 4 % ;
  * provision pour primes : limite des contrats au 31/12/2026 (renouvellement annuel, l'assureur peut résilier ou
    réviser le tarif) ; flux du second semestre : sinistres + frais - cotisations ;
  * rentes en cours : projection MENSUELLE des états (incapacité -> reprise, décès ou invalidité ; invalidité ->
    reprise, décès ou fin à 62 ans), frais de gestion 3 % des prestations, inflation des frais 2 % ;
  * IBNR prévoyance : Chain Ladder sur les nombres d'arrêts et de décès déclarés, coût moyen actualisé ;
  * réassurance : créances de réassurance best estimate, ajustement pour défaut du réassureur (Art. 61).
Le moteur accepte des CHOCS (mortalité, reprise, incidence, frais, révision, courbe) et une DATE DE DÉPART des
chocs : il sert aussi au SCR (étape 3) et à la marge de risque (étape 4), sans aucune approximation.
"""
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from . import config as C
from .actuarialTables import mortality, qx, incapacityExit, incapacityToInvalidShare, invalidityRecovery, newClaimCost, incidenceByAge
from .utils import log, banner, saveTable, saveFig

P = C.prevoyance
SEM = [f"{y}S{s}" for y in range(2019, 2027) for s in (1, 2)][:15]


# ----------------------------------------------------------------------------
# Actualisation
# ----------------------------------------------------------------------------
def discountFactors(rates, times):
    """rates : taux annuels 1..150 ans ; times en années (>0)."""
    t = np.asarray(times, float)
    r = np.interp(np.maximum(t, 1.0), np.arange(1, len(rates) + 1), rates)
    return (1 + r) ** -t


# ----------------------------------------------------------------------------
# Santé : Chain Ladder semestriel et Mack
# ----------------------------------------------------------------------------
def chainLadder(tri):
    cum = tri.pivot_table(index="survenance", columns="developpement", values="reglements", aggfunc="sum").reindex(SEM).cumsum(axis=1)
    n = cum.shape[1]
    f, sig2 = [], []
    for d in range(n - 1):
        ok = cum[d + 1].notna()
        fd = cum.loc[ok, d + 1].sum() / cum.loc[ok, d].sum()
        f.append(fd)
        res = cum.loc[ok, d] * (cum.loc[ok, d + 1] / cum.loc[ok, d] - fd) ** 2
        sig2.append(res.sum() / max(ok.sum() - 1, 1))
    sig2 = [s if s > 0 else 1e-9 for s in sig2]
    if len(sig2) > 1:
        sig2[-1] = min(sig2[-2] ** 2 / max(sig2[-3], 1e-12), min(sig2[-3], sig2[-2])) if len(sig2) > 2 else sig2[-2]
    rows = []
    for i, s in enumerate(SEM):
        last = n - 1 if i + n - 1 <= 14 else 14 - i
        c = cum.loc[s, last]
        ult, mse = c, 0.0
        for d in range(last, n - 1):
            mse = mse * f[d] ** 2 + sig2[d] * ult
            ult *= f[d]
        rows.append({"survenance": s, "paye": c, "developpementAtteint": last, "ultime": ult, "reserve": ult - c, "erreurMack": np.sqrt(mse)})
    return pd.DataFrame(rows), np.array(f)


def healthClaimsCashflows(cl, f):
    """Flux futurs de règlement par semestre calendaire (1 = second semestre 2026)."""
    n = len(f) + 1
    cumPat = np.concatenate([[1.0], np.cumprod(f[::-1])])[::-1]
    cumPat = 1 / cumPat                                   # proportion cumulée payée à chaque développement
    cf = np.zeros(n + 1)
    for _, r in cl.iterrows():
        d0 = int(r.developpementAtteint)
        for d in range(d0 + 1, n):
            cf[d - d0] += r.ultime * (cumPat[d] - cumPat[d - 1])
    return cf


def healthBe(tris, prem, rates, spShock=0.0, expenseMult=1.0, lapse=0.0):
    out, cfsAll = {}, {}
    for seg in C.health:
        cl, f = chainLadder(tris[tris.segment == seg])
        cf = healthClaimsCashflows(cl, f)
        t = (np.arange(len(cf)) - 0.5) / 2
        df = discountFactors(rates, np.maximum(t, 0.25))
        beClaims = float((cf * df).sum()) * (1 + C.healthUlae * expenseMult)
        # provision pour primes : second semestre 2026 (limite du contrat au 31/12/2026)
        p = prem[(prem.segment == seg)]
        premS2 = float(p[p.semestre == "2026S1"].cotisations.iloc[0]) * (1 - lapse)
        ulr = p[p.semestre.isin(C.healthBestEstimateSpYears)]
        spBe = float(cl[cl.survenance.isin(C.healthBestEstimateSpYears)].ultime.sum() / ulr.cotisations.sum()) + spShock
        pat = np.diff(np.concatenate([[0], 1 / np.concatenate([[1.0], np.cumprod(f[::-1])])[::-1]]))
        claimsCf = premS2 * spBe * pat
        tc = 0.25 + np.arange(len(claimsCf)) / 2
        bePremClaims = float((claimsCf * discountFactors(rates, tc)).sum()) * (1 + C.healthUlae * expenseMult)
        beExpenses = premS2 * C.health[seg]["fraisGestionPrimes"] * expenseMult * float(discountFactors(rates, [0.25])[0])
        bePremIn = premS2 * float(discountFactors(rates, [0.25])[0])
        out[seg] = {"beSinistres": beClaims, "bePrimes": bePremClaims + beExpenses - bePremIn, "reserveNonActualisee": cl.reserve.sum(),
                    "erreurMack": np.sqrt((cl.erreurMack ** 2).sum()), "spBestEstimate": spBe, "cotisationsS2": premS2,
                    "cotisations12Mois": float(p[p.semestre.isin(["2025S2", "2026S1"])].cotisations.sum())}
        cfsAll[seg] = (cf, cl, f)
    return out, cfsAll


# ----------------------------------------------------------------------------
# Prévoyance : projection mensuelle des sinistres en cours (SLT)
# ----------------------------------------------------------------------------
class Shock:
    def __init__(self, mort=1.0, recovery=1.0, incid1=1.0, incidAfter=1.0, expense=1.0, inflAdd=0.0, revision=0.0, start=0):
        self.mort, self.recovery, self.incid1, self.incidAfter = mort, recovery, incid1, incidAfter
        self.expense, self.inflAdd, self.revision, self.start = expense, inflAdd, revision, start


def monthly(pAnnual):
    return 1 - (1 - np.clip(pAnnual, 0, 1)) ** (1 / 12)


def projectInvalid(ages, sexes, amounts, weights, startMonth, th, tf, sh, horizon=C.horizonMonths):
    """Flux mensuels de rentes d'invalidité ; chaque ligne démarre à son propre mois startMonth (vectorisé)."""
    cf = np.zeros(horizon)
    n = len(np.atleast_1d(ages))
    s = np.asarray(weights, float).copy()
    age = np.asarray(ages, float).copy()
    start = np.broadcast_to(np.asarray(startMonth), (n,)).astype(int)
    amt = np.asarray(amounts, float) * (1 + sh.revision)
    isH = np.asarray(sexes) == "H"
    qH = lambda a: qx("H", a, th, tf, P["surmortaliteInvalides"])
    qF = lambda a: qx("F", a, th, tf, P["surmortaliteInvalides"])
    for m in range(int(start.min()), horizon):
        started = start <= m
        active = started & (age < P["ageFinRente"])
        if not (started.all() or active.any()):
            continue
        if started.all() and not active.any():
            break
        cf[m] += (s * active * amt).sum() / 12
        on = m >= sh.start
        rec = monthly(invalidityRecovery(age)) * (sh.recovery if on else 1.0)
        dth = monthly(np.where(isH, qH(age), qF(age)) * (sh.mort if on else 1.0))
        s = np.where(started, s * (1 - rec) * (1 - dth) * (age < P["ageFinRente"]), s)
        age = np.where(started, age + 1 / 12, age)
    return cf


def projectIncapacity(inc, th, tf, sh, horizon=C.horizonMonths):
    """Flux mensuels d'IJ, et entrées en invalidité (âge, sexe, rente, poids, mois d'entrée) pour les incapacités en cours."""
    cfIj = np.zeros(horizon)
    age = (inc.ageEntree + (inc.ancienneteMois - 3) / 12).values.astype(float)
    d = inc.ancienneteMois.values.astype(float)
    ij = inc.ijAnnuelle.values.astype(float)
    rente = P["renteInvPctSalaire"] * inc.salaire.values.astype(float)
    sexes = inc.sexe.values
    isH = sexes == "H"
    s = np.ones(len(inc))
    flows = []
    for m in range(0, 36):
        alive = d < P["dureeMaxIncapaciteMois"]
        if not alive.any():
            break
        cfIj[m] += (s * alive * ij / 12).sum()
        on = m >= sh.start
        incidMult = (sh.incid1 if m < sh.start + 12 else sh.incidAfter) if on else 1.0
        ex = incapacityExit(d, age)
        share = np.clip(incapacityToInvalidShare(d, age) * incidMult, 0, 1)
        pInv = ex * share
        pRec = ex * (1 - share) * (sh.recovery if on else 1.0)
        pDth = monthly(np.where(isH, qx("H", age, th, tf), qx("F", age, th, tf)) * (sh.mort if on else 1.0))
        last = (d + 1 >= P["dureeMaxIncapaciteMois"]) & alive
        toInv = np.where(last, s * (1 - pDth), s * pInv) * alive
        k = toInv > 0
        if k.any():
            flows.append((age[k] + 1 / 12, sexes[k], rente[k], toInv[k], np.full(k.sum(), m + 1)))
        s = np.where(last, 0.0, s * (1 - pInv - pRec - pDth)) * alive
        d = d + 1
        age = age + 1 / 12
    if flows:
        a, sx, r, w, st = (np.concatenate(z) for z in zip(*flows))
        cfInv = projectInvalid(a, sx, r, w, st, th, tf, sh, horizon)
    else:
        cfInv = np.zeros(horizon)
    return cfIj, cfInv


def sltBe(inc, inv, rates, th, tf, sh=Shock(), fromMonth=0):
    """BE des sinistres en cours (valeur en fromMonth des flux postérieurs)."""
    cfIj, cfInvInc = projectIncapacity(inc, th, tf, sh)
    cfInvStock = projectInvalid(inv.ageActuel.values, inv.sexe.values, inv.renteAnnuelle.values, np.ones(len(inv)), 0, th, tf, sh)
    months = np.arange(C.horizonMonths)
    benefits = cfIj + cfInvInc + cfInvStock
    infl = (1 + C.expenseInflation + sh.inflAdd) ** ((months + 0.5) / 12)
    expenses = benefits * P["fraisGestionPrestations"] * sh.expense * infl
    keep = months >= fromMonth
    t = (months[keep] + 0.5) / 12
    df = discountFactors(rates, t) / (float(discountFactors(rates, [fromMonth / 12])[0]) if fromMonth > 0 else 1.0)   # taux forward depuis fromMonth
    return {"beIncapaciteIj": float((cfIj[keep] * df).sum()), "beInvaliditeFutureDesIncapacites": float((cfInvInc[keep] * df).sum()),
            "beInvaliditeEnCours": float((cfInvStock[keep] * df).sum()), "beFrais": float((expenses[keep] * df).sum()),
            "total": float(((benefits + expenses)[keep] * df).sum()), "cashflows": benefits + expenses}


# ----------------------------------------------------------------------------
# Prévoyance NSLT (perte de revenus) et décès (vie)
# ----------------------------------------------------------------------------
def countIbnr(tri):
    t = tri.pivot_table(index="survenance", columns="developpement", values="nombre", aggfunc="sum").reindex(SEM)
    cum = t.cumsum(axis=1)
    n = cum.shape[1]
    f = [cum.loc[cum[d + 1].notna(), d + 1].sum() / cum.loc[cum[d + 1].notna(), d].sum() for d in range(n - 1)]
    ibnr = 0.0
    for i, s in enumerate(SEM):
        last = min(n - 1, 14 - i)
        c = cum.loc[s, last]
        ibnr += c * (np.prod(f[last:]) - 1)
    return ibnr, f


def prevoyanceNsltBe(pop, triInc, rates, th, tf, tarif, lapse=0.0):
    """Perte de revenus NSLT : provision pour primes (arrêts du 2nd semestre 2026) + IBNR arrêts."""
    ages = np.arange(20, 65)
    rateAvg = float(np.interp(8, np.arange(1, 151), rates))
    cost = {a: newClaimCost(a, 1.0, 1.0, th, tf, rateAvg) for a in ages}
    a = pop.age.clip(20, 64).astype(int)
    inc = incidenceByAge(pop.age)
    perClaim = a.map(lambda x: cost[x][0]) * P["ijPctSalaire"] * pop.salaire + a.map(lambda x: cost[x][1]) * P["renteInvPctSalaire"] * pop.salaire
    claimsS2 = float((inc * perClaim).sum() / 2) * (1 - lapse)
    premS2 = float(tarif[tarif.garantie.isin(["incapacite", "invalidite"])].cotisationAnnuelle.sum() / 2) * (1 - lapse)
    df = float(discountFactors(rates, [0.5])[0])
    bePrem = claimsS2 * (1 + P["fraisGestionPrestations"]) * df + premS2 * P["fraisGestionPrimes"] * float(discountFactors(rates, [0.25])[0]) \
        - premS2 * float(discountFactors(rates, [0.25])[0])
    nIbnr, _ = countIbnr(triInc)
    avgCost = float((inc * perClaim).sum() / inc.sum())
    beIbnr = nIbnr * avgCost * (1 + P["fraisGestionPrestations"]) * float(discountFactors(rates, [0.25])[0])
    return {"bePrimes": bePrem, "beSinistresIbnr": beIbnr, "nombreIbnr": nIbnr, "coutMoyenArret": avgCost,
            "sinistresAttendusS2": claimsS2, "cotisationsS2": premS2}


def decesBe(pop, triDec, rates, th, tf, tarif, mortMult=1.0, catAdd=0.0, expenseMult=1.0, lapse=0.0):
    q = np.array([qx(s, x, th, tf, P["abattementMortaliteActifs"]) for s, x in zip(pop.sexe, pop.age)])
    q = np.minimum(q * mortMult + catAdd, 1.0)
    cap = P["capitalDecesPctSalaire"] * pop.salaire.values
    claimsS2 = float((q * cap).sum() / 2) * (1 - lapse)
    premS2 = float(tarif[tarif.garantie == "deces"].cotisationAnnuelle.iloc[0] / 2) * (1 - lapse)
    df25 = float(discountFactors(rates, [0.25])[0])
    bePrem = claimsS2 * (1 + P["fraisGestionPrestations"] * expenseMult) * df25 + premS2 * P["fraisGestionPrimes"] * expenseMult * df25 - premS2 * df25
    nIbnr, _ = countIbnr(triDec)
    beIbnr = nIbnr * cap.mean() * (1 + P["fraisGestionPrestations"] * expenseMult) * df25
    qs = C.reinsuranceQuotaShareDeces
    recov = qs * (claimsS2 * df25 + nIbnr * cap.mean() * df25) - qs * premS2 * df25
    return {"bePrimes": bePrem, "beSinistresIbnr": beIbnr, "creanceReassurance": recov, "capitalSousRisque": float(cap.sum()),
            "sinistresAttendusS2": claimsS2, "cotisationsS2": premS2, "capitalMoyen": float(cap.mean())}


def counterpartyDefaultAdjustment(recov, pd_, duration=0.5):
    """Art. 61 : ajustement pour défaut de la contrepartie (perte en cas de défaut 50 %)."""
    return max(0.5 * pd_ / (1 - pd_) * duration * recov, 0.0)


# ----------------------------------------------------------------------------
# Chargement commun et calcul complet
# ----------------------------------------------------------------------------
def loadInputs():
    d = {"th_tf": mortality(), "curves": pd.read_pickle(C.dataProc / "courbes.pkl"),
         "tris": pd.read_csv(C.dataRaw / "santeTriangles.csv"), "prem": pd.read_csv(C.dataRaw / "santeCotisations.csv"),
         "pop": pd.read_csv(C.dataProc / "prevoyancePopulationPropre.csv"), "inc": pd.read_csv(C.dataProc / "prevoyanceIncapacitePropre.csv"),
         "inv": pd.read_csv(C.dataProc / "prevoyanceInvaliditePropre.csv"), "triInc": pd.read_csv(C.dataRaw / "prevoyanceTriangleArrets.csv"),
         "triDec": pd.read_csv(C.dataRaw / "prevoyanceTriangleDeces.csv"), "tarif": pd.read_csv(C.dataRaw / "prevoyanceTarif.csv")}
    return d


def computeAll(d, rates, sh=Shock(), spShock=0.0, healthLapse=0.0, prevLapse=0.0, mortMultDeces=1.0, catAdd=0.0, expenseMult=1.0):
    th, tf = d["th_tf"]
    h, cfs = healthBe(d["tris"], d["prem"], rates, spShock, expenseMult, healthLapse)
    slt = sltBe(d["inc"], d["inv"], rates, th, tf, sh)
    ip = prevoyanceNsltBe(d["pop"], d["triInc"], rates, th, tf, d["tarif"], prevLapse)
    dc = decesBe(d["pop"], d["triDec"], rates, th, tf, d["tarif"], mortMultDeces, catAdd, expenseMult, prevLapse)
    cda = counterpartyDefaultAdjustment(dc["creanceReassurance"], C.counterpartyPd[C.reinsurerCqs])
    lob = pd.DataFrame([
        {"lob": "Santé NSLT : frais médicaux", "segment": "individuel", "beSinistres": h["individuel"]["beSinistres"], "bePrimes": h["individuel"]["bePrimes"], "reassurance": 0.0},
        {"lob": "Santé NSLT : frais médicaux", "segment": "collectif", "beSinistres": h["collectif"]["beSinistres"], "bePrimes": h["collectif"]["bePrimes"], "reassurance": 0.0},
        {"lob": "Santé NSLT : perte de revenus", "segment": "prévoyance arrêts de travail", "beSinistres": ip["beSinistresIbnr"], "bePrimes": ip["bePrimes"], "reassurance": 0.0},
        {"lob": "Santé SLT : rentes en cours", "segment": "incapacités et invalidités en cours", "beSinistres": slt["total"], "bePrimes": 0.0, "reassurance": 0.0},
        {"lob": "Vie : autres (décès)", "segment": "prévoyance décès", "beSinistres": dc["beSinistresIbnr"], "bePrimes": dc["bePrimes"],
         "reassurance": dc["creanceReassurance"] - cda}])
    lob["beBrut"] = lob.beSinistres + lob.bePrimes
    lob["beNet"] = lob.beBrut - lob.reassurance
    return {"lob": lob, "health": h, "healthCf": cfs, "slt": slt, "ip": ip, "deces": dc, "cda": cda}


def statutory(d, res):
    """Provisions des comptes sociaux : santé non actualisée + marge ; prévoyance au taux technique de 1,5 %."""
    th, tf = d["th_tf"]
    flat = np.full(150, C.statutoryRate)
    sltStat = sltBe(d["inc"], d["inv"], flat, th, tf)["total"]
    ipStat = prevoyanceNsltBe(d["pop"], d["triInc"], flat, th, tf, d["tarif"])["beSinistresIbnr"]
    h = res["health"]
    psap = sum(h[s]["reserveNonActualisee"] for s in C.health) * (1 + C.statutoryPsapMargin) * (1 + C.healthUlae)
    dcIbnr = res["deces"]["beSinistresIbnr"] / float(discountFactors(res.get("rates", flat), [0.25])[0]) if "rates" in res else res["deces"]["beSinistresIbnr"]
    return pd.DataFrame([
        {"poste": "PSAP santé (frais de soins)", "social": psap, "s2BestEstimate": h["individuel"]["beSinistres"] + h["collectif"]["beSinistres"]},
        {"poste": "Provision pour primes santé", "social": 0.0, "s2BestEstimate": h["individuel"]["bePrimes"] + h["collectif"]["bePrimes"]},
        {"poste": "Provisions incapacité et invalidité en cours (PM)", "social": sltStat, "s2BestEstimate": res["slt"]["total"]},
        {"poste": "IBNR arrêts de travail", "social": ipStat, "s2BestEstimate": res["ip"]["beSinistresIbnr"]},
        {"poste": "Provision pour primes arrêts de travail", "social": 0.0, "s2BestEstimate": res["ip"]["bePrimes"]},
        {"poste": "PSAP décès (IBNR)", "social": dcIbnr, "s2BestEstimate": res["deces"]["beSinistresIbnr"]},
        {"poste": "Provision pour primes décès", "social": 0.0, "s2BestEstimate": res["deces"]["bePrimes"]},
        {"poste": "Provision d'égalisation", "social": C.equalisationProvision, "s2BestEstimate": 0.0}])


def run():
    banner("ÉTAPE 2 : PROVISIONS TECHNIQUES (BEST ESTIMATE) ET PASSAGE DES COMPTES SOCIAUX")
    d = loadInputs()
    rates = d["curves"].tauxAvecVa.values
    res = computeAll(d, rates)
    res["rates"] = rates
    lob = res["lob"]
    stat = statutory(d, res)
    stat["ecart"] = stat.s2BestEstimate - stat.social
    noVa = computeAll(d, d["curves"].tauxSansVa.values)["lob"].beNet.sum()
    undisc = computeAll(d, np.zeros(150))["lob"].beNet.sum()
    kpi = pd.DataFrame([{"indicateur": "BE net total (courbe avec VA)", "valeur": lob.beNet.sum()},
                        {"indicateur": "BE net total (courbe sans VA)", "valeur": noVa},
                        {"indicateur": "BE net non actualisé", "valeur": undisc},
                        {"indicateur": "effet de l'actualisation", "valeur": lob.beNet.sum() - undisc},
                        {"indicateur": "effet de la VA", "valeur": lob.beNet.sum() - noVa},
                        {"indicateur": "erreur de Mack sur les sinistres santé", "valeur": sum(res["health"][s]["erreurMack"] for s in C.health)},
                        {"indicateur": "S/P best estimate santé individuel", "valeur": res["health"]["individuel"]["spBestEstimate"]},
                        {"indicateur": "S/P best estimate santé collectif", "valeur": res["health"]["collectif"]["spBestEstimate"]},
                        {"indicateur": "nombre d'arrêts IBNR estimé", "valeur": res["ip"]["nombreIbnr"]},
                        {"indicateur": "ajustement pour défaut du réassureur", "valeur": res["cda"]}])
    sltDet = pd.DataFrame([{k: v for k, v in res["slt"].items() if k != "cashflows"}])
    clTabs = []
    for seg in C.health:
        _, cl, f = res["healthCf"][seg]
        cl.insert(0, "segment", seg); clTabs.append(cl)
    saveTable(lob, "e2BestEstimateParLob"); saveTable(stat, "e2PassageSocialS2"); saveTable(kpi, "e2IndicateursBe")
    saveTable(sltDet, "e2DetailSlt"); saveTable(pd.concat(clTabs), "e2ChainLadderSante")
    import pickle
    with open(C.dataProc / "etape2.pkl", "wb") as fh:
        pickle.dump({"lob": lob, "stat": stat, "health": res["health"], "ip": res["ip"], "deces": res["deces"], "slt": sltDet, "cda": res["cda"]}, fh)

    fig, axes = plt.subplots(1, 3, figsize=(17, 4.8))
    x = np.arange(len(lob))
    axes[0].barh(x, lob.beNet / 1e6, color="#1f3b73")
    axes[0].set_yticks(x); axes[0].set_yticklabels([f"{a}\n({b})" for a, b in zip(lob.lob, lob.segment)], fontsize=7)
    axes[0].set_title("Best estimate net de réassurance par ligne d'activité (M€)")
    cf = res["slt"]["cashflows"]
    yrs = np.arange(len(cf)) // 12
    ann = pd.Series(cf).groupby(yrs).sum()
    axes[1].bar(ann.index + 2026.5, ann.values / 1e6, color="#2a9d8f")
    axes[1].set_title("Prévoyance SLT : flux annuels projetés (M€)"); axes[1].set_xlim(2026, 2066)
    y = np.arange(len(stat))
    axes[2].barh(y - .2, stat.social / 1e6, height=.4, color="#6c757d", label="comptes sociaux")
    axes[2].barh(y + .2, stat.s2BestEstimate / 1e6, height=.4, color="#c8102e", label="best estimate S2")
    axes[2].set_yticks(y); axes[2].set_yticklabels(stat.poste, fontsize=7); axes[2].legend(fontsize=8)
    axes[2].set_title("Du bilan social au best estimate (M€)")
    saveFig(fig, "e2BestEstimate")
    log.info("\n%s\n%s\n%s\n%s", lob.round(0).to_string(index=False), stat.round(0).to_string(index=False), kpi.round(4).to_string(index=False),
             sltDet.round(0).to_string(index=False))
    return res
