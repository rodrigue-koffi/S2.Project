"""
portfolios.py : ÉTAPE 1.3, portefeuilles santé et prévoyance, actifs et bilan social.

Les données de portefeuille d'un assureur ne sont pas publiques : elles sont GÉNÉRÉES, avec des ordres de
grandeur calés sur la place (DREES 2025 : prestations / cotisations de 73 % en individuel et 85 % en
collectif ; charges de gestion de l'ordre de 12 à 20 % des cotisations).

  * SANTÉ (frais de soins, contrats annuels renouvelés au 1er janvier) : individuel et collectif,
    cotisations et triangles de règlements par semestre de survenance 2019S1-2026S1 (effet COVID 2020S1
    inclus : baisse du recours aux soins).
  * PRÉVOYANCE COLLECTIVE (60 000 salariés) : incapacité (indemnités journalières après 90 jours de
    franchise, 36 mois maximum), invalidité (rente jusqu'à 62 ans), décès (capital de 200 % du salaire,
    réassuré en quote-part 50 %). Sinistres en cours au 30/06/2026 obtenus en SIMULANT les arrêts
    survenus dans le passé avec les tables de maintien : le stock est ainsi cohérent avec les tables.
    Cotisations calculées pour un ratio sinistres / cotisations cible de 92 %.
  * ACTIFS : obligations d'État et d'entreprises (prix de marché sur la courbe EIOPA + spread de crédit
    selon la notation), actions de type 1 (dont 20 % en dollars) et de type 2, immobilier, dépôts bancaires,
    créances, immobilisation incorporelle ; dette subordonnée émise.
  * BILAN SOCIAL (normes françaises) : actifs au coût amorti, provisions techniques prudentes (taux
    technique 1,5 %, marge de prudence), provision d'égalisation.
"""
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from . import config as C
from .actuarialTables import mortality, qx, incapacityExit, incapacityToInvalidShare, invalidityRecovery, incidenceByAge, newClaimCost
from .utils import log, banner, saveTable, saveFig

P = C.prevoyance
val = pd.Timestamp(C.valuationDate)


def semesters():
    return pd.period_range("2019Q1", "2026Q1", freq="2Q").strftime("%Y") + np.tile(["S1", "S2"], 8)[:15]


def healthPortfolio(rng):
    sem = [f"{y}S{s}" for y in range(2019, 2027) for s in (1, 2)][:15]
    rows, tri = [], []
    for seg, h in C.health.items():
        for i, s in enumerate(sem):
            yrs = (i - 12) / 2                                                  # 2025S1 = référence
            prem = h["prime2025"] / 2 * (1 + C.healthGrowth) ** yrs
            sp = h["sp"] + rng.normal(0, 0.02) + (-0.12 if s == "2020S1" else 0) + (0.04 if s == "2020S2" else 0)
            ult = prem * sp
            cum = np.array(C.healthDevPattern) * ult * np.exp(rng.normal(0, 0.01, len(C.healthDevPattern)))
            cum = np.maximum.accumulate(cum)
            inc = np.diff(np.concatenate([[0], cum]))
            for d, amt in enumerate(inc):
                if i + d <= 14:
                    tri.append({"segment": seg, "survenance": s, "developpement": d, "reglements": amt})
            rows.append({"segment": seg, "semestre": s, "cotisations": prem, "spVrai": sp, "chargeUltimeVraie": ult})
    return pd.DataFrame(rows), pd.DataFrame(tri)


def insuredPopulation(rng, th, tf):
    n = P["assures"]
    age = np.clip(rng.normal(43, 10.5, n), 20, 64).round(1)
    sex = np.where(rng.random(n) < 0.55, "H", "F")
    sal = P["salaireMoyen"] * np.exp(rng.normal(-0.08, 0.4, n)) * (1 + 0.01 * (age - 43))
    pop = pd.DataFrame({"assureId": np.arange(1, n + 1), "age": age, "sexe": sex, "salaire": sal.round(0)})
    # coûts attendus -> cotisations (taux sur la masse salariale)
    ages = np.arange(20, 65)
    cij, cinv = zip(*[newClaimCost(a, 1.0, 1.0, th, tf) for a in ages])
    fIj, fInv = dict(zip(ages, cij)), dict(zip(ages, cinv))
    a = pop.age.astype(int)
    inc = incidenceByAge(pop.age)
    costInc = (inc * a.map(fIj) * P["ijPctSalaire"] * pop.salaire).sum()
    costInv = (inc * a.map(fInv) * P["renteInvPctSalaire"] * pop.salaire).sum()
    q = np.array([qx(s, x, th, tf, P["abattementMortaliteActifs"]) for s, x in zip(pop.sexe, pop.age)])
    costDec = (q * P["capitalDecesPctSalaire"] * pop.salaire).sum()
    payroll = pop.salaire.sum()
    prem = {k: v / P["ratioSinistresCibleTarif"] for k, v in (("incapacite", costInc), ("invalidite", costInv), ("deces", costDec))}
    tarif = pd.DataFrame([{"garantie": k, "coutAnnuelAttendu": v * P["ratioSinistresCibleTarif"], "cotisationAnnuelle": v,
                           "tauxSurMasseSalariale": v / payroll} for k, v in prem.items()])
    return pop, tarif


def simulateIncapacityStock(rng, pop, th, tf):
    """Arrêts ayant atteint la fin de la franchise au cours des 36 derniers mois, suivis jusqu'au 30/06/2026."""
    rows, invRows = [], []
    w = np.asarray(incidenceByAge(pop.age)); w = w / w.sum()
    perMonth = P["incidenceArret90j"] * P["assures"] / 12
    cid = 0
    for m in range(1, 37):                                     # m = mois écoulés depuis la fin de franchise
        k = rng.poisson(perMonth)
        idx = rng.choice(len(pop), k, p=w)
        for j in idx:
            cid += 1
            p0 = pop.iloc[j]
            age0 = p0.age - m / 12
            state, d = "incapacite", 3
            for step in range(m):
                d = 3 + step
                ex = incapacityExit(d, age0 + step / 12)
                if rng.random() < ex:
                    state = "invalidite" if rng.random() < incapacityToInvalidShare(d, age0 + step / 12) else "sorti"
                    break
                if d == 35:
                    state = "invalidite"
                    break
            start = val - pd.DateOffset(months=m)
            if state == "incapacite":
                rows.append({"sinistreId": f"INC{cid:05d}", "sexe": p0.sexe, "ageEntree": round(age0, 2), "ancienneteMois": 3 + m,
                             "salaire": p0.salaire, "ijAnnuelle": P["ijPctSalaire"] * p0.salaire, "dateFinFranchise": start.date(),
                             "declare": not (m <= 6 and rng.random() < P["tauxDeclarationTardive"])})
            elif state == "invalidite":
                invRows.append({"sexe": p0.sexe, "ageEntree": age0 + (d - 3) / 12 + 0.25, "anneeEntree": (start + pd.DateOffset(months=d - 3)).year,
                                "salaire": p0.salaire})
    return pd.DataFrame(rows), pd.DataFrame(invRows)


def simulateInvalidityStock(rng, recent, th, tf):
    """Stock d'invalides : entrées de 1996 à 2023 (hors fenêtre de 36 mois) plus entrées récentes, suivies jusqu'à 2026."""
    rows = []
    perYear = P["incidenceArret90j"] * P["assures"] * 0.19
    for y in range(1996, 2024):
        k = rng.poisson(perYear * (0.8 + 0.2 * (y - 1996) / 27))
        for _ in range(k):
            rows.append({"sexe": "H" if rng.random() < 0.55 else "F", "ageEntree": float(np.clip(rng.normal(50, 7), 25, 61)),
                         "anneeEntree": y, "salaire": P["salaireMoyen"] * np.exp(rng.normal(-0.05, 0.35)) * 0.98 ** (2026 - y)})
    allInv = pd.concat([pd.DataFrame(rows), recent], ignore_index=True)
    keep = []
    for _, r in allInv.iterrows():
        age, alive = r.ageEntree, True
        for _ in range(2026 - int(r.anneeEntree)):
            if age >= P["ageFinRente"] or rng.random() < invalidityRecovery(age) or rng.random() < qx(r.sexe, age, th, tf, P["surmortaliteInvalides"]):
                alive = False
                break
            age += 1
        if alive and age < P["ageFinRente"]:
            keep.append({"sexe": r.sexe, "ageActuel": round(age, 2), "anneeEntree": int(r.anneeEntree),
                         "renteAnnuelle": round(P["renteInvPctSalaire"] * r.salaire, 2)})
    inv = pd.DataFrame(keep)
    inv.insert(0, "sinistreId", [f"INV{i:05d}" for i in range(1, len(inv) + 1)])
    return inv


def countTriangle(rng, perSemester, pattern, label):
    sem = [f"{y}S{s}" for y in range(2019, 2027) for s in (1, 2)][:15]
    rows = []
    for i, s in enumerate(sem):
        n = rng.poisson(perSemester * (1 + 0.01 * i))
        split = rng.multinomial(n, pattern)
        for d, v in enumerate(split):
            if i + d <= 14:
                rows.append({"garantie": label, "survenance": s, "developpement": d, "nombre": int(v)})
    return pd.DataFrame(rows)


def assetPortfolio(rng, curves):
    r = curves.set_index("maturite").tauxSansVa
    spreads = {0: 0.0015, 1: 0.0060, 2: 0.0090, 3: 0.0150, 4: 0.0300}
    bonds = []
    specs = ([("OAT", "etat", "FR", 1, 30e6 / 6)] * 6 + [("Bund", "etat", "DE", 0, 8e6 / 2)] * 2 + [("BTP", "etat", "IT", 3, 6e6 / 2)] * 2 +
             [(f"Entreprise AAA {i}", "entreprise", "EU", 0, 2e6) for i in range(3)] + [(f"Entreprise AA {i}", "entreprise", "EU", 1, 3e6) for i in range(5)] +
             [(f"Entreprise A {i}", "entreprise", "EU", 2, 3.5e6) for i in range(8)] + [(f"Entreprise BBB {i}", "entreprise", "EU", 3, 3e6) for i in range(7)] +
             [(f"Entreprise BB {i}", "entreprise", "EU", 4, 1.5e6) for i in range(2)])
    for k, (name, typ, country, cqs, nominal) in enumerate(specs):
        nominal *= 1.6
        mat = int(rng.integers(2, 16)); cpn = round(float(rng.uniform(0.005, 0.04)), 4)
        t = np.arange(1, mat + 1)
        y = np.array([r[m] for m in t]) + (0.0 if typ == "etat" and country in ("FR", "DE") else spreads[cqs] if typ == "entreprise" else 0.012)
        cf = np.full(mat, cpn * nominal); cf[-1] += nominal
        mv = float((cf / (1 + y) ** t).sum())
        bookYield = cpn + rng.normal(0, 0.002)
        book = float((cf / (1 + bookYield) ** t).sum())
        bonds.append({"ligne": f"OBL{k + 1:03d}", "emetteur": name, "type": typ, "pays": country, "cqs": cqs, "nominal": nominal, "coupon": cpn,
                      "maturite": mat, "valeurMarche": mv, "valeurComptable": book, "duration": float((t * cf / (1 + y) ** t).sum() / mv / (1 + y.mean()))})
    bonds = pd.DataFrame(bonds)
    other = pd.DataFrame([
        {"ligne": "ACT001", "categorie": "action type 1", "emetteur": "ETF actions zone euro", "devise": "EUR", "cqs": None, "valeurMarche": 9.0e6, "valeurComptable": 7.5e6},
        {"ligne": "ACT002", "categorie": "action type 1", "emetteur": "Actions françaises en direct (10 lignes)", "devise": "EUR", "cqs": None, "valeurMarche": 5.0e6, "valeurComptable": 4.6e6},
        {"ligne": "ACT003", "categorie": "action type 1", "emetteur": "ETF actions américaines", "devise": "USD", "cqs": None, "valeurMarche": 3.5e6, "valeurComptable": 2.6e6},
        {"ligne": "ACT004", "categorie": "action type 2", "emetteur": "Fonds de capital-investissement", "devise": "EUR", "cqs": None, "valeurMarche": 3.0e6, "valeurComptable": 2.8e6},
        {"ligne": "IMM001", "categorie": "immobilier", "emetteur": "Immeuble de placement (Paris)", "devise": "EUR", "cqs": None, "valeurMarche": 9.0e6, "valeurComptable": 6.0e6},
        {"ligne": "IMM002", "categorie": "immobilier", "emetteur": "OPCI diversifié", "devise": "EUR", "cqs": None, "valeurMarche": 4.0e6, "valeurComptable": 3.8e6},
        {"ligne": "DEP001", "categorie": "dépôt bancaire", "emetteur": "Banque A (notée A+)", "devise": "EUR", "cqs": 2, "valeurMarche": 7.0e6, "valeurComptable": 7.0e6},
        {"ligne": "DEP002", "categorie": "dépôt bancaire", "emetteur": "Banque B (notée A)", "devise": "EUR", "cqs": 2, "valeurMarche": 4.0e6, "valeurComptable": 4.0e6},
        {"ligne": "CRE001", "categorie": "créances", "emetteur": "Cotisations à recevoir", "devise": "EUR", "cqs": None, "valeurMarche": 6.0e6, "valeurComptable": 6.0e6},
        {"ligne": "INC001", "categorie": "incorporel", "emetteur": "Logiciel de gestion", "devise": "EUR", "cqs": None, "valeurMarche": 0.0, "valeurComptable": 1.5e6}])
    return bonds, other


def run(curves):
    banner("ÉTAPE 1.3 : PORTEFEUILLES SANTÉ ET PRÉVOYANCE, ACTIFS, BILAN SOCIAL")
    rng = np.random.default_rng(C.seed)
    th, tf = mortality()
    hPrem, hTri = healthPortfolio(rng)
    pop, tarif = insuredPopulation(rng, th, tf)
    inc, recentInv = simulateIncapacityStock(rng, pop, th, tf)
    inv = simulateInvalidityStock(rng, recentInv, th, tf)
    triInc = countTriangle(rng, P["incidenceArret90j"] * P["assures"] / 2, [0.85, 0.13, 0.02], "incapacite")
    qMean = np.mean([qx(s, a, th, tf, P["abattementMortaliteActifs"]) for s, a in zip(pop.sexe, pop.age)])
    triDec = countTriangle(rng, qMean * P["assures"] / 2, [0.80, 0.17, 0.03], "deces")
    bonds, other = assetPortfolio(rng, curves)
    # anomalies de données injectées (contrôlées à l'étape 1.4)
    pop.loc[rng.choice(len(pop), 120, replace=False), "salaire"] = np.nan
    pop.loc[rng.choice(len(pop), 15, replace=False), "age"] = 99
    dup = inv.sample(4, random_state=1)
    inv = pd.concat([inv, dup], ignore_index=True)
    for name, df in (("santeCotisations", hPrem), ("santeTriangles", hTri), ("prevoyancePopulation", pop), ("prevoyanceTarif", tarif),
                     ("prevoyanceIncapaciteEnCours", inc), ("prevoyanceInvaliditeEnCours", inv), ("prevoyanceTriangleArrets", triInc),
                     ("prevoyanceTriangleDeces", triDec), ("actifsObligations", bonds), ("actifsAutres", other)):
        df.to_csv(C.dataRaw / f"{name}.csv", index=False)
    summ = pd.DataFrame([
        {"portefeuille": "Santé individuel", "indicateur": "cotisations 2025", "valeur": hPrem[(hPrem.segment == "individuel") & hPrem.semestre.str.startswith("2025")].cotisations.sum()},
        {"portefeuille": "Santé collectif", "indicateur": "cotisations 2025", "valeur": hPrem[(hPrem.segment == "collectif") & hPrem.semestre.str.startswith("2025")].cotisations.sum()},
        {"portefeuille": "Prévoyance", "indicateur": "assurés", "valeur": len(pop)},
        {"portefeuille": "Prévoyance", "indicateur": "cotisations annuelles", "valeur": tarif.cotisationAnnuelle.sum()},
        {"portefeuille": "Prévoyance", "indicateur": "incapacités en cours déclarées", "valeur": int(inc.declare.sum())},
        {"portefeuille": "Prévoyance", "indicateur": "incapacités en cours non déclarées (inconnues de l'assureur)", "valeur": int((~inc.declare).sum())},
        {"portefeuille": "Prévoyance", "indicateur": "invalidités en cours", "valeur": len(inv)},
        {"portefeuille": "Actifs", "indicateur": "obligations (valeur de marché)", "valeur": bonds.valeurMarche.sum()},
        {"portefeuille": "Actifs", "indicateur": "autres actifs (valeur de marché)", "valeur": other.valeurMarche.sum()}])
    saveTable(summ, "e1Portefeuilles"); saveTable(tarif, "e1TarifPrevoyance")
    fig, axes = plt.subplots(1, 3, figsize=(17, 4.8))
    for seg, g in hPrem.groupby("segment"):
        axes[0].plot(g.semestre, g.spVrai * 100, "o-", label=seg)
    axes[0].set_title("Santé : ratio sinistres / cotisations par semestre (%)"); axes[0].tick_params(axis="x", rotation=60, labelsize=7); axes[0].legend()
    axes[1].hist(inv.ageActuel, bins=30, color="#1f3b73", alpha=.7, label="invalides en cours")
    axes[1].hist(inc.ageEntree + inc.ancienneteMois / 12, bins=30, color="#c8102e", alpha=.6, label="incapacités en cours")
    axes[1].set_title("Prévoyance : âge des sinistrés en cours"); axes[1].legend()
    lab = ["État", "Entreprises", "Actions", "Immobilier", "Dépôts", "Créances"]
    vals = [bonds[bonds.type == "etat"].valeurMarche.sum(), bonds[bonds.type == "entreprise"].valeurMarche.sum(),
            other[other.categorie.str.startswith("action")].valeurMarche.sum(), other[other.categorie == "immobilier"].valeurMarche.sum(),
            other[other.categorie == "dépôt bancaire"].valeurMarche.sum(), other[other.categorie == "créances"].valeurMarche.sum()]
    axes[2].pie(vals, labels=lab, autopct="%1.0f%%", colors=["#1f3b73", "#3e95cd", "#c8102e", "#e9a03b", "#2a9d8f", "#6c757d"])
    axes[2].set_title(f"Actifs en valeur de marché : {sum(vals) / 1e6:.0f} M€")
    saveFig(fig, "e1Portefeuilles")
    log.info("\n%s\n%s", summ.to_string(index=False), tarif.round(4).to_string(index=False))
