"""
actuarialTables.py : ÉTAPE 1.2, tables biométriques.

  * Mortalité : tables réglementaires TH 00-02 et TF 00-02 (données réelles). Pour une population de
    salariés actifs, abattement de 40 % (les actifs meurent moins que la population générale) ; pour les
    invalides, surmortalité de 150 %. Ces deux ajustements sont des hypothèses d'expérience, à justifier
    en pratique par un suivi du portefeuille.
  * Maintien en incapacité et en invalidité : les tables du BCAC utilisées en France ne sont pas publiées
    en données ouvertes. Des tables PARAMÉTRIQUES sont générées, avec les propriétés qualitatives connues :
      - incapacité (mensuelle, de la fin de la franchise de 3 mois jusqu'à 36 mois) : taux de sortie élevé
        au début et décroissant avec l'ancienneté, sorties plus lentes avec l'âge ; part des sorties vers
        l'invalidité croissante avec l'ancienneté et l'âge ; à 36 mois, les arrêts restants passent en
        invalidité (durée maximale légale des indemnités journalières) ;
      - invalidité (annuelle) : reprise d'activité rare et décroissante avec l'âge, mortalité des invalides,
        fin de la rente à 62 ans (départ en retraite).
    En production, elles seraient remplacées par les tables BCAC ou par des tables d'expérience certifiées.
"""
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from . import config as C
from .utils import log, banner, saveTable, saveFig

P = C.prevoyance


def mortality():
    th = pd.read_csv(C.dataRaw / "tableTH0002.csv").set_index("age").qx
    tf = pd.read_csv(C.dataRaw / "tableTF0002.csv").set_index("age").qx
    return th, tf


def qx(sex, age, th, tf, factor=1.0):
    t = th if sex == "H" else tf
    return np.minimum(np.interp(age, t.index.values, t.values) * factor, 1.0)


def incapacityExit(d, age):
    """Probabilité mensuelle de sortie de l'incapacité (d = mois d'ancienneté de l'arrêt, >= 3)."""
    base = 0.10 * np.exp(-0.05 * (d - 3)) + 0.02
    return np.clip(base * np.exp(-0.02 * (age - 45)), 0.002, 0.5)


def incapacityToInvalidShare(d, age):
    """Part des sorties d'incapacité qui sont des passages en invalidité."""
    return np.clip((0.02 + 0.012 * (d - 3)) * (1 + 0.02 * (age - 45)), 0.0, 0.8)


def invalidityRecovery(age):
    return np.clip(0.04 * np.exp(-0.05 * (age - 40)), 0.002, 0.2)


def run():
    banner("ÉTAPE 1.2 : TABLES BIOMÉTRIQUES (TH/TF 00-02, MAINTIEN EN INCAPACITÉ ET EN INVALIDITÉ)")
    th, tf = mortality()
    ages = np.arange(20, 63)
    rows = []
    for a in (30, 45, 55):
        s, inv = 1.0, 0.0
        for d in range(3, 36):
            ex = incapacityExit(d, a)
            inv += s * ex * incapacityToInvalidShare(d, a)
            s *= 1 - ex
        rows.append({"ageEntree": a, "maintien12Mois": np.prod([1 - incapacityExit(d, a) for d in range(3, 12)]),
                     "maintien36Mois": s, "probaInvaliditeAvant36Mois": inv, "probaInvaliditeTotale": inv + s})
    incSummary = pd.DataFrame(rows)
    invRows = []
    for a in (35, 45, 55):
        s, e = 1.0, 0.0
        for x in range(a, C.prevoyance["ageFinRente"]):
            e += s
            s *= (1 - invalidityRecovery(x)) * (1 - qx("H", x, th, tf, P["surmortaliteInvalides"]))
        invRows.append({"ageEntree": a, "dureeMoyenneRenteAnnees": e})
    invSummary = pd.DataFrame(invRows)
    mortTab = pd.DataFrame({"age": ages, "qxTH0002": qx("H", ages, th, tf), "qxTF0002": qx("F", ages, th, tf),
                            "qxActifsHommes": qx("H", ages, th, tf, P["abattementMortaliteActifs"]),
                            "qxInvalidesHommes": qx("H", ages, th, tf, P["surmortaliteInvalides"])})
    saveTable(incSummary, "e1TableIncapaciteSynthese"); saveTable(invSummary, "e1TableInvaliditeSynthese"); saveTable(mortTab, "e1TablesMortalite")

    fig, axes = plt.subplots(1, 3, figsize=(17, 4.8))
    for a, col in zip((30, 45, 55), ("#2a9d8f", "#1f3b73", "#c8102e")):
        s = [1.0]
        for d in range(3, 36):
            s.append(s[-1] * (1 - incapacityExit(d, a)))
        axes[0].plot(range(3, 37), s, color=col, label=f"entrée à {a} ans")
    axes[0].set_title("Maintien en incapacité après la franchise"); axes[0].set_xlabel("mois d'arrêt"); axes[0].legend(fontsize=8)
    axes[1].plot(ages, invalidityRecovery(ages) * 100, color="#1f3b73", label="reprise d'activité")
    axes[1].plot(ages, qx("H", ages, th, tf, P["surmortaliteInvalides"]) * 100, color="#c8102e", label="décès (invalides, hommes)")
    axes[1].set_title("Sorties annuelles de l'invalidité (%)"); axes[1].legend(fontsize=8)
    axes[2].semilogy(ages, qx("H", ages, th, tf), color="#1f3b73", label="TH 00-02")
    axes[2].semilogy(ages, qx("F", ages, th, tf), color="#c8102e", label="TF 00-02")
    axes[2].semilogy(ages, qx("H", ages, th, tf, P["abattementMortaliteActifs"]), "--", color="#1f3b73", label="actifs hommes (60 %)")
    axes[2].set_title("Mortalité réglementaire (qx, échelle log)"); axes[2].legend(fontsize=8)
    saveFig(fig, "e1TablesBiometriques")
    log.info("\n%s\n%s", incSummary.round(3).to_string(index=False), invSummary.round(2).to_string(index=False))
    return th, tf


def incidenceByAge(age):
    """Incidence annuelle d'arrêts de plus de 90 jours, croissante avec l'âge, moyenne calée à 1,2 %."""
    return C.prevoyance["incidenceArret90j"] * np.exp(0.04 * (np.asarray(age, float) - 43)) / 1.08


def invalidAnnuityFactor(age, th, tf, rate=0.025, sex="H", recoveryMult=1.0, mortMult=1.0):
    """Valeur actuelle d'une rente d'invalidité de 1 par an (paiement mensuel approché en milieu d'année)."""
    s, v = 1.0, 0.0
    for k, x in enumerate(range(int(age), C.prevoyance["ageFinRente"])):
        pRec = invalidityRecovery(x) * recoveryMult
        pDeath = qx(sex, x, th, tf, C.prevoyance["surmortaliteInvalides"] * mortMult)
        v += s * (1 - 0.5 * (pRec + pDeath)) * (1 + rate) ** -(k + 0.5)
        s *= (1 - pRec) * (1 - pDeath)
    return v


def newClaimCost(age, ijAnnual, renteAnnual, th, tf, rate=0.025):
    """Coût actuel attendu d'un arrêt de travail atteignant la fin de la franchise : IJ puis éventuelle rente."""
    s, cij, cinv = 1.0, 0.0, 0.0
    for d in range(3, 36):
        cij += s * ijAnnual / 12 * (1 + rate) ** -(d / 12)
        ex = incapacityExit(d, age)
        cinv += s * ex * incapacityToInvalidShare(d, age) * renteAnnual * invalidAnnuityFactor(age + d / 12, th, tf, rate) * (1 + rate) ** -(d / 12)
        s *= 1 - ex
    cinv += s * renteAnnual * invalidAnnuityFactor(age + 3, th, tf, rate) * (1 + rate) ** -3
    return cij, cinv
