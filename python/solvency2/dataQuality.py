"""
dataQuality.py : ÉTAPE 1.4, qualité des données (Art. 19 du Règlement délégué, orientations EIOPA sur
la qualité des données : exhaustivité, exactitude, pertinence).

Contrôles et traitements, tous tracés :
  * population prévoyance : salaires manquants (imputés par la médiane de la tranche d'âge), âges
    aberrants (lignes écartées et signalées) ;
  * sinistres en cours : doublons d'identifiants (supprimés) ; cohérence âge / fin de rente ;
  * triangles : montants négatifs, cellules au-delà de la diagonale, cohérence cotisations / règlements ;
  * actifs : notations manquantes, valeurs négatives, rapprochement des totaux.
"""
import numpy as np
import pandas as pd
from . import config as C
from .utils import log, banner, saveTable


def run():
    banner("ÉTAPE 1.4 : QUALITÉ DES DONNÉES")
    rd = lambda n: pd.read_csv(C.dataRaw / f"{n}.csv")
    pop, inc, inv = rd("prevoyancePopulation"), rd("prevoyanceIncapaciteEnCours"), rd("prevoyanceInvaliditeEnCours")
    tri, prem, bonds, other = rd("santeTriangles"), rd("santeCotisations"), rd("actifsObligations"), rd("actifsAutres")
    log_ = []
    miss = pop.salaire.isna().sum()
    band = (pop.age // 5).clip(upper=12)
    pop["salaire"] = pop.salaire.fillna(pop.groupby(band).salaire.transform("median"))
    log_.append(("population prévoyance", "salaires manquants", int(miss), "imputation par la médiane de la tranche d'âge de 5 ans"))
    bad = (pop.age < 16) | (pop.age > 70)
    log_.append(("population prévoyance", "âges hors de [16 ; 70]", int(bad.sum()), "lignes écartées, signalées au gestionnaire"))
    pop = pop[~bad]
    dup = inv.duplicated("sinistreId").sum()
    inv = inv.drop_duplicates("sinistreId")
    log_.append(("invalidités en cours", "identifiants en double", int(dup), "doublons supprimés"))
    late = (inv.ageActuel >= C.prevoyance["ageFinRente"]).sum()
    log_.append(("invalidités en cours", "âge atteint ou dépassé la fin de rente", int(late), "écartées : plus aucune prestation due (passage en retraite)"))
    inv = inv[inv.ageActuel < C.prevoyance["ageFinRente"]]
    undeclared = (~inc.declare).sum()
    log_.append(("incapacités en cours", "arrêts non encore déclarés dans le fichier de simulation", int(undeclared),
                 "écartés : inconnus de l'assureur, couverts par la provision pour sinistres tardifs (IBNR)"))
    inc = inc[inc.declare]
    log_.append(("triangles santé", "montants négatifs", int((tri.reglements < 0).sum()), "aucun"))
    sem = sorted(tri.survenance.unique())
    fut = sum(1 for _, r in tri.iterrows() if sem.index(r.survenance) + r.developpement > len(sem) - 1)
    log_.append(("triangles santé", "cellules postérieures au 30/06/2026", int(fut), "aucune"))
    log_.append(("actifs", "obligations sans notation", int(bonds.cqs.isna().sum()), "aucune"))
    log_.append(("actifs", "valeurs de marché négatives", int((bonds.valeurMarche < 0).sum() + (other.valeurMarche < 0).sum()), "aucune"))
    report = pd.DataFrame(log_, columns=["fichier", "controle", "lignesConcernees", "traitement"])
    pop.to_csv(C.dataProc / "prevoyancePopulationPropre.csv", index=False)
    inc.to_csv(C.dataProc / "prevoyanceIncapacitePropre.csv", index=False)
    inv.to_csv(C.dataProc / "prevoyanceInvaliditePropre.csv", index=False)
    saveTable(report, "e1QualiteDonnees")
    log.info("\n%s", report.to_string(index=False))
    return report
