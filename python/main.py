"""
main.py : orchestrateur du projet Solvabilité II (santé et prévoyance).

Usage :  cd python && python main.py [--etape N]

  1. Fondations : courbe EIOPA (Smith-Wilson, VA, chocs), tables biométriques, portefeuilles, actifs, qualité des données
  2. Provisions techniques : best estimate santé (primes, sinistres), prévoyance (incapacité, invalidité, IBNR), décès ;
     réassurance ; passage des provisions sociales au best estimate
  3. SCR de souscription : santé NSLT (primes et réserves, rachat), santé SLT (mortalité, longévité, incapacité,
     rachat, frais, révision), catastrophe santé, vie (mortalité, rachat, frais, catastrophe)
  4. SCR marché, contrepartie, opérationnel, actifs incorporels, BSCR, ajustement pour impôts différés, SCR, MCR, marge de risque
  5. Bilan prudentiel, fonds propres et tiering, ratios de solvabilité, sensibilités, états réglementaires, projection ORSA
"""
import argparse
from solvency2 import config as C
from solvency2.utils import banner, exportExcel
from solvency2 import marketData, actuarialTables, portfolios, dataQuality
from solvency2 import bestEstimate, underwritingScr, marketScr, balanceSheet


def etape1():
    banner("GRANDE ÉTAPE 1 : FONDATIONS")
    curves = marketData.run()
    actuarialTables.run()
    portfolios.run(curves)
    dataQuality.run()


def etape2():
    banner("GRANDE ÉTAPE 2 : PROVISIONS TECHNIQUES (BEST ESTIMATE)")
    bestEstimate.run()


def etape3():
    banner("GRANDE ÉTAPE 3 : SCR DE SOUSCRIPTION SANTÉ ET VIE")
    underwritingScr.run()


def etape4():
    banner("GRANDE ÉTAPE 4 : SCR MARCHÉ, CONTREPARTIE, OPÉRATIONNEL, SCR, MCR, MARGE DE RISQUE")
    marketScr.run()


def etape5():
    banner("GRANDE ÉTAPE 5 : BILAN S2, FONDS PROPRES, RATIOS, SENSIBILITÉS, QRT, ORSA")
    balanceSheet.run()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--etape", type=int, default=5)
    a = ap.parse_args()
    etape1()
    for k, f in ((2, etape2), (3, etape3), (4, etape4), (5, etape5)):
        if a.etape >= k:
            f()
    exportExcel(C.root / "outputs" / "python" / f"resultatsEtapes1a{a.etape}.xlsx")
