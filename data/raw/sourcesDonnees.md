# Sources des données

| Fichier | Contenu | Source officielle | Copie utilisée |
|---|---|---|---|
| `eiopaRfrFranceHistorique.csv` | Courbe des taux sans risque EIOPA pour la France (euro), points 1, 5, 10, 20 et 30 ans, et correction pour volatilité (VA), fin de mois de janvier 2023 à juillet 2026 | EIOPA, Risk-free interest rate term structures (publication mensuelle) | github.com/SlimSaanouni/EIOPA_MONITORING (data/historical.csv) |
| `eiopaRfr20211231TermStructures.xlsx` | Fichier EIOPA complet au 31/12/2021 : courbes sans et avec VA de 1 à 150 ans, courbes choquées à la hausse et à la baisse, table des chocs de taux de la formule standard, paramètres Smith-Wilson | EIOPA (EIOPA_RFR_20211231_Term_Structures.xlsx) | github.com/994Simone/eiopa-ir-curves |
| `tableTH0002.csv`, `tableTF0002.csv` | Tables de mortalité réglementaires TH 00-02 et TF 00-02 (arrêté du 20 décembre 2005) | INSEE / réglementation française | github.com/mehdijac/mortables |

Paramètres de place repris de publications officielles :
- UFR 2026 de l'euro : 3,30 % (EIOPA, 31 mars 2025).
- Ratios prestations / cotisations en complémentaire santé en 2024 : 85 % pour les contrats collectifs, 73 % pour les contrats individuels ; charges de gestion de l'ordre de 19 % des cotisations (DREES, rapport 2025 sur la situation financière des organismes complémentaires).
- Paramètres du risque de catastrophe santé : Annexe XVI du Règlement délégué (UE) 2015/35 (France : 0,05 % de personnes touchées par un accident de masse).

Données générées (non disponibles en données ouvertes) : portefeuilles santé et prévoyance, tables de maintien en incapacité et en invalidité (les tables du BCAC ne sont pas publiées en open data), portefeuille d'actifs, bilan social. Voir la note de l'étape 1.
