# =============================================================================
# actuarialTables.R : ETAPE 1.2, tables biometriques (miroir de actuarialTables.py)
# =============================================================================
TH <- read.csv(file.path(dataRaw, "tableTH0002.csv")); TF <- read.csv(file.path(dataRaw, "tableTF0002.csv"))
qxF <- function(sex, age, factor = 1) { t <- if (sex == "H") TH else TF; pmin(approx(t$age, t$qx, xout = age, rule = 2)$y * factor, 1) }
qxV <- function(sexes, age, factor = 1) ifelse(sexes == "H", qxF("H", age, factor), qxF("F", age, factor))
incapacityExit <- function(d, age) pmin(pmax((0.10 * exp(-0.05 * (d - 3)) + 0.02) * exp(-0.02 * (age - 45)), 0.002), 0.5)
incapacityToInvalidShare <- function(d, age) pmin(pmax((0.02 + 0.012 * (d - 3)) * (1 + 0.02 * (age - 45)), 0), 0.8)
invalidityRecovery <- function(age) pmin(pmax(0.04 * exp(-0.05 * (age - 40)), 0.002), 0.2)
incidenceByAge <- function(age) prev$incidenceArret90j * exp(0.04 * (age - 43)) / 1.08
invalidAnnuityFactor <- function(age, rate = 0.025) {
  s <- 1; v <- 0; xs <- seq(floor(age), prev$ageFinRente - 1)
  if (floor(age) >= prev$ageFinRente) return(0)
  for (k in seq_along(xs)) { x <- xs[k]; pR <- invalidityRecovery(x); pD <- qxF("H", x, prev$surmortaliteInvalides)
    v <- v + s * (1 - 0.5 * (pR + pD)) * (1 + rate)^-(k - 1 + 0.5); s <- s * (1 - pR) * (1 - pD) }
  v
}
newClaimCost <- function(age, ijA, renteA, rate = 0.025) {
  s <- 1; cij <- 0; cinv <- 0
  for (d in 3:35) { cij <- cij + s * ijA / 12 * (1 + rate)^-(d / 12); ex <- incapacityExit(d, age)
    cinv <- cinv + s * ex * incapacityToInvalidShare(d, age) * renteA * invalidAnnuityFactor(age + d / 12, rate) * (1 + rate)^-(d / 12); s <- s * (1 - ex) }
  cinv <- cinv + s * renteA * invalidAnnuityFactor(age + 3, rate) * (1 + rate)^-3
  c(cij, cinv)
}
runTables <- function() {
  banner("\u00c9TAPE 1.2 : TABLES BIOM\u00c9TRIQUES (R)")
  inc <- do.call(rbind, lapply(c(30, 45, 55), function(a) { s <- 1; inv <- 0
    for (d in 3:35) { ex <- incapacityExit(d, a); inv <- inv + s * ex * incapacityToInvalidShare(d, a); s <- s * (1 - ex) }
    data.frame(ageEntree = a, maintien36Mois = s, probaInvaliditeTotale = inv + s) }))
  saveTable(inc, "e1TableIncapaciteSynthese"); print(inc); inc
}
