# Projet Solvabilité II : santé et prévoyance

Chaîne complète de calcul prudentiel d'un organisme d'assurance portant un portefeuille **santé** (frais de soins, individuel et collectif) et un portefeuille **prévoyance collective** (incapacité, invalidité, décès), en **Python** et en **R** (double implémentation réconciliée), jusqu'au **bilan Solvabilité II**, aux ratios, aux états réglementaires et à l'ORSA.

## Les 5 étapes

| Étape | Contenu | Résultats clés au 30/06/2026 |
|---|---|---|
| 1. Fondations | Courbe EIOPA par Smith-Wilson (validée sur le fichier officiel 2021), VA, chocs de taux officiels ; tables TH/TF 00-02 et tables de maintien ; portefeuilles ; actifs ; qualité des données | Reconstruction à 0,34 pb de la courbe officielle |
| 2. Best estimate | Chain Ladder et Mack (santé), provisions pour primes (limite des contrats), projection mensuelle des rentes d'incapacité et d'invalidité, IBNR, réassurance ; passage des comptes sociaux | BE net 110,8 M€ |
| 3. SCR de souscription | Santé NSLT (primes et réserves, rachat), santé SLT (mortalité, longévité, incapacité, rachat, frais, révision), catastrophe santé (accident de masse, concentration, pandémie), vie (mortalité, rachat, frais, catastrophe) | SCR santé 34,3 M€ ; vie 1,9 M€ |
| 4. Marché et agrégation | Taux, actions, immobilier, spread, change, concentration ; contrepartie ; incorporels ; opérationnel ; BSCR ; impôts différés ; SCR ; MCR ; marge de risque recalculée année par année | SCR 50,4 M€ ; MCR 12,6 M€ ; marge de risque 3,2 M€ |
| 5. Bilan et pilotage | Bilan S2, passage des fonds propres sociaux, tiering, ratios, sensibilités, états au format QRT, ORSA 2026-2029 | Ratio SCR 210 % ; ratio MCR 798 % |

## Lancer le projet

```bash
pip install -r requirements.txt
cd python && python main.py        # étapes 1 à 5 
cd .. && Rscript R/main.R          # version R + réconciliation avec Python (environ 10 minutes)
```

## Organisation

- `python/solvency2/` : package Python (un module par bloc), `python/main.py` : orchestrateur.
- `R/` : version R ; tables de réconciliation dans `outputs/R/tables/*Reconciliation*`.
- `data/raw/` : données brutes et leur provenance (`sourcesDonnees.md`).
- `docs/notesMethodologiques/` : une note par étape ; `docs/fichesRevisionWord/` : une fiche Word par étape et la compilation des 5.
- `outputs/` : graphes, tables, classeur Excel des résultats.

## Données

- **Réelles :** courbe EIOPA France 2023-2026 et VA, fichier EIOPA complet du 31/12/2021 (courbes, chocs), UFR 2026, tables TH/TF 00-02, paramètres de l'Annexe XVI, ratios de place DREES 2025.
- **Générées :** portefeuilles, actifs, tables de maintien (les tables du BCAC ne sont pas en données ouvertes). Les portefeuilles sont générés par Python ; R refait tous les calculs à partir des mêmes données brutes.

## Limites

Portefeuilles générés ; tables de maintien paramétriques ; courbe 2026 reconstruite à partir de 4 points liquides ; ajustement symétrique action à 0 (à remplacer par la valeur EIOPA du 30/06/2026) ; sensibilités à SCR constant ; ORSA par inducteurs de volume ; paramètres antérieurs à la révision de la Directive applicable en 2027.
