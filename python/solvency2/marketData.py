"""
marketData.py : ÉTAPE 1.1, courbe des taux sans risque EIOPA et chocs de taux de la formule standard.

POURQUOI : en Solvabilité II, TOUS les flux (prestations, frais, primes) s'actualisent avec la courbe
publiée chaque mois par l'EIOPA. Elle est construite par la méthode de SMITH-WILSON :
  * ajustement exact des taux de marché jusqu'au dernier point liquide (LLP = 20 ans pour l'euro) ;
  * extrapolation au-delà, convergence du taux forward vers l'UFR (3,30 % en 2026) en 40 ans ;
  * paramètre alpha (vitesse de convergence) : le plus petit alpha >= 0,05 tel que le forward à
    LLP + 40 = 60 ans soit à moins de 1 pb de l'UFR.
La correction pour volatilité (VA, 14 pb pour la France au 30/06/2026) est ajoutée aux taux liquides
avant extrapolation, comme le fait l'EIOPA.

Nous ne disposons pour 2026 que des points 1, 5, 10, 20 et 30 ans : la courbe complète est donc
RECONSTRUITE par Smith-Wilson à partir des points 1, 5, 10 et 20 ans. Deux validations :
  1. sur le fichier EIOPA complet du 31/12/2021 : même méthode appliquée aux points liquides publiés,
     comparée à la courbe officielle de 1 à 150 ans ;
  2. au 30/06/2026 : le point 30 ans (non utilisé dans l'ajustement) est comparé au 30 ans publié.
Chocs de taux (Art. 166 et 167) lus dans la table officielle de l'EIOPA ; leur application est validée
sur les courbes choquées publiées par l'EIOPA au 31/12/2021.
"""
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy.optimize import brentq
from . import config as C
from .utils import log, banner, saveTable, saveFig

mats = np.arange(1, C.maxMaturity + 1)


def wilson(t, u, alpha, omega):
    t, u = np.asarray(t, float)[:, None], np.asarray(u, float)[None, :]
    lo, hi = np.minimum(t, u), np.maximum(t, u)
    return np.exp(-omega * (t + u)) * (alpha * lo - 0.5 * np.exp(-alpha * hi) * (np.exp(alpha * lo) - np.exp(-alpha * lo)))


def smithWilson(liquidMat, liquidRates, ufr=C.ufr, alpha=None, out=mats):
    """Taux sans risque (composition annuelle) de 1 à 150 ans à partir de taux zéro-coupon liquides."""
    omega = np.log(1 + ufr)
    u = np.asarray(liquidMat, float)
    p = (1 + np.asarray(liquidRates, float)) ** -u

    def curve(a, t):
        zeta = np.linalg.solve(wilson(u, u, a, omega), p - np.exp(-omega * u))
        return np.exp(-omega * np.asarray(t, float)) + wilson(t, u, a, omega) @ zeta

    def gap(a):
        T = u.max() + C.convergencePeriod
        f = -(np.log(curve(a, [T + 0.001])[0]) - np.log(curve(a, [T - 0.001])[0])) / 0.002
        return abs(f - omega) - C.convergenceTolerance
    if alpha is None:
        alpha = C.alphaMin if gap(C.alphaMin) <= 0 else brentq(gap, C.alphaMin, 1.0)
    P = curve(alpha, out)
    return P ** (-1 / np.asarray(out, float)) - 1, alpha


def readEiopa2021():
    f = C.dataRaw / "eiopaRfr20211231TermStructures.xlsx"
    out = {}
    for sheet in ("RFR_spot_no_VA", "RFR_spot_with_VA", "Spot_WITH_VA_shock_UP", "Spot_WITH_VA_shock_DOWN"):
        d = pd.read_excel(f, sheet, header=None)
        col = [c for c in d.columns if str(d.iloc[1, c]).strip() == "Euro"][0]
        out[sheet] = d.iloc[10:160, col].astype(float).values
        if sheet == "RFR_spot_no_VA":
            out["alpha"] = float(d.iloc[7, col]); out["ufr"] = float(d.iloc[6, col]) / 100
    s = pd.read_excel(f, "Shocks", header=None)
    rows = s[pd.to_numeric(s.iloc[:, 1], errors="coerce").between(1, 90)]
    out["shocks"] = pd.DataFrame({"maturite": rows.iloc[:, 1].astype(int).values, "chocBaisse": rows.iloc[:, 3].astype(float).values,
                                  "chocHausse": rows.iloc[:, 4].astype(float).values})
    return out


def shockCurve(r, shocks, direction):
    s = shocks.set_index("maturite")
    fac = np.array([s.loc[m, "chocHausse" if direction == "up" else "chocBaisse"] if m <= 90 else 0.20 for m in mats[:len(r)]])
    if direction == "up":
        return r + np.maximum(r * fac, C.upShockMin)
    return np.where(r > 0, r * (1 - fac), r)


def run():
    banner("ÉTAPE 1.1 : COURBE EIOPA (SMITH-WILSON), VA ET CHOCS DE TAUX")
    e21 = readEiopa2021()
    liq = np.array([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 12, 15, 20])
    base21 = e21["RFR_spot_no_VA"]
    rOwn, aOwn = smithWilson(liq, base21[liq - 1], ufr=e21["ufr"])
    rPub, _ = smithWilson(liq, base21[liq - 1], ufr=e21["ufr"], alpha=e21["alpha"])
    rPillars, _ = smithWilson(np.array([1, 5, 10, 20]), base21[[0, 4, 9, 19]], ufr=e21["ufr"])
    val21 = pd.DataFrame([
        {"reconstruction": "points liquides EIOPA, alpha recalculé", "alpha": aOwn, "ecartMaxPb": np.abs(rOwn - base21).max() * 1e4, "ecartMoyenAbsPb": np.abs(rOwn - base21).mean() * 1e4},
        {"reconstruction": "points liquides EIOPA, alpha publié", "alpha": e21["alpha"], "ecartMaxPb": np.abs(rPub - base21).max() * 1e4, "ecartMoyenAbsPb": np.abs(rPub - base21).mean() * 1e4},
        {"reconstruction": "points 1, 5, 10, 20 ans seulement (comme en 2026)", "alpha": np.nan, "ecartMaxPb": np.abs(rPillars - base21).max() * 1e4, "ecartMoyenAbsPb": np.abs(rPillars - base21).mean() * 1e4}])
    shocks = e21["shocks"]
    pd.DataFrame({"maturite": mats, "tauxSansVa": base21, "tauxAvecVa": e21["RFR_spot_with_VA"], "chocHausseAvecVa": e21["Spot_WITH_VA_shock_UP"],
                  "chocBaisseAvecVa": e21["Spot_WITH_VA_shock_DOWN"]}).to_csv(C.dataRaw / "eiopaRfr20211231Euro.csv", index=False)   # extrait lisible sans Excel
    shocks.to_csv(C.dataRaw / "eiopaChocsTauxFormuleStandard.csv", index=False)
    pd.DataFrame([{"alpha": e21["alpha"], "ufr": e21["ufr"]}]).to_csv(C.dataRaw / "eiopaParametres20211231.csv", index=False)
    upOwn, dnOwn = shockCurve(e21["RFR_spot_with_VA"], shocks, "up"), shockCurve(e21["RFR_spot_with_VA"], shocks, "down")
    valShock = pd.DataFrame([{"courbe": "hausse (avec VA)", "ecartMaxPb": np.abs(upOwn - e21["Spot_WITH_VA_shock_UP"]).max() * 1e4},
                             {"courbe": "baisse (avec VA)", "ecartMaxPb": np.abs(dnOwn - e21["Spot_WITH_VA_shock_DOWN"]).max() * 1e4}])

    hist = pd.read_csv(C.dataRaw / "eiopaRfrFranceHistorique.csv", parse_dates=["reference_date"])
    row = hist[hist.reference_date == pd.Timestamp(C.valuationDate)].iloc[0]
    pil = np.array([1, 5, 10, 20]); pr = row[["rate_1y", "rate_5y", "rate_10y", "rate_20y"]].values.astype(float)
    rNoVa, a1 = smithWilson(pil, pr)
    rVa, a2 = smithWilson(pil, pr + row.va)
    curves = pd.DataFrame({"maturite": mats, "tauxSansVa": rNoVa, "tauxAvecVa": rVa,
                           "tauxAvecVaChocHausse": shockCurve(rVa, shocks, "up"), "tauxAvecVaChocBaisse": shockCurve(rVa, shocks, "down")})
    check26 = pd.DataFrame([{"date": C.valuationDate, "va": row.va, "alphaSansVa": a1, "alphaAvecVa": a2,
                             "taux30AnsPublie": row.rate_30y, "taux30AnsReconstruit": rNoVa[29], "ecart30AnsPb": (rNoVa[29] - row.rate_30y) * 1e4}])
    curves.to_pickle(C.dataProc / "courbes.pkl")
    shocks.to_pickle(C.dataProc / "chocsTaux.pkl")
    saveTable(val21, "e1ValidationSmithWilson2021"); saveTable(valShock, "e1ValidationChocsTaux2021")
    saveTable(check26, "e1Courbe20260630Controle"); saveTable(curves.round(6), "e1CourbesEiopa20260630"); saveTable(shocks, "e1TableChocsTaux")

    fig, axes = plt.subplots(1, 3, figsize=(17, 4.8))
    for c, col in (("rate_1y", "#2a9d8f"), ("rate_10y", "#1f3b73"), ("rate_30y", "#c8102e")):
        axes[0].plot(hist.reference_date, hist[c] * 100, color=col, label=c.replace("rate_", ""))
    axes[0].plot(hist.reference_date, hist.va * 100, "k:", label="VA")
    axes[0].axvline(pd.Timestamp(C.valuationDate), color="grey", ls="--"); axes[0].set_title("Courbe EIOPA France 2023-2026 (%)"); axes[0].legend(fontsize=8)
    axes[1].plot(mats, base21 * 100, color="k", lw=2, label="EIOPA publiée 31/12/2021")
    axes[1].plot(mats, rPillars * 100, "--", color="#c8102e", label="reconstruite (1, 5, 10, 20 ans)")
    axes[1].set_title("Validation de Smith-Wilson sur 2021"); axes[1].legend(fontsize=8); axes[1].set_xlabel("maturité")
    for c, lab, col in (("tauxAvecVa", "avec VA", "#1f3b73"), ("tauxSansVa", "sans VA", "#6c757d"),
                        ("tauxAvecVaChocHausse", "choc à la hausse", "#c8102e"), ("tauxAvecVaChocBaisse", "choc à la baisse", "#2a9d8f")):
        axes[2].plot(mats, curves[c] * 100, color=col, label=lab)
    axes[2].scatter([1, 5, 10, 20, 30], row[["rate_1y", "rate_5y", "rate_10y", "rate_20y", "rate_30y"]].values.astype(float) * 100, color="k", zorder=3, label="points publiés")
    axes[2].axhline(C.ufr * 100, color="k", ls=":", lw=.8); axes[2].set_xlim(0, 100)
    axes[2].set_title("Courbe au 30/06/2026 et chocs de la formule standard"); axes[2].legend(fontsize=7); axes[2].set_xlabel("maturité")
    saveFig(fig, "e1CourbeEiopa")
    log.info("\n%s\n%s\n%s", val21.round(3).to_string(index=False), valShock.round(4).to_string(index=False), check26.round(5).to_string(index=False))
    return curves
