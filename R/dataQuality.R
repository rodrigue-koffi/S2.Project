# =============================================================================
# dataQuality.R : ETAPE 1.4, controles et traitements (miroir de dataQuality.py)
# Les portefeuilles sont generes par la version Python (donnees brutes communes) ; R refait tous les traitements.
# =============================================================================
runQuality <- function() {
  banner("\u00c9TAPE 1.4 : QUALIT\u00c9 DES DONN\u00c9ES (R)")
  pop <- read.csv(file.path(dataRaw, "prevoyancePopulation.csv")); inc <- read.csv(file.path(dataRaw, "prevoyanceIncapaciteEnCours.csv"))
  inv <- read.csv(file.path(dataRaw, "prevoyanceInvaliditeEnCours.csv"))
  miss <- sum(is.na(pop$salaire)); band <- pmin(pop$age %/% 5, 12)
  med <- tapply(pop$salaire, band, median, na.rm = TRUE); pop$salaire[is.na(pop$salaire)] <- med[as.character(band[is.na(pop$salaire)])]
  bad <- pop$age < 16 | pop$age > 70; pop <- pop[!bad, ]
  dup <- sum(duplicated(inv$sinistreId)); inv <- inv[!duplicated(inv$sinistreId), ]; late <- sum(inv$ageActuel >= prev$ageFinRente)
  inv <- inv[inv$ageActuel < prev$ageFinRente, ]
  inc$declare <- as.character(inc$declare) %in% c("True", "TRUE"); und <- sum(!inc$declare); inc <- inc[inc$declare, ]
  rep <- data.frame(controle = c("salaires manquants", "\u00e2ges aberrants", "doublons invalidit\u00e9", "invalides au-del\u00e0 de 62 ans", "arr\u00eats non d\u00e9clar\u00e9s"),
                    lignes = c(miss, sum(bad), dup, late, und))
  saveTable(rep, "e1QualiteDonnees"); print(rep)
  list(pop = pop, inc = inc, inv = inv)
}
