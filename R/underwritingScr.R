# =============================================================================
# underwritingScr.R : ETAPE 3, SCR de souscription sante (NSLT, SLT, CAT) et vie (miroir de underwritingScr.py)
# =============================================================================
sigmaLob <- function(sp, sr, vp, vr) if (vp + vr > 0) sqrt((sp * vp)^2 + sp * vp * sr * vr + (sr * vr)^2) / (vp + vr) else 0
nsltPR <- function(vpMe, vrMe, vpIp, vrIp) {
  s <- c(sigmaLob(nslt$medicalExpense[1], nslt$medicalExpense[2], vpMe, vrMe), sigmaLob(nslt$incomeProtection[1], nslt$incomeProtection[2], vpIp, vrIp))
  v <- c(vpMe + vrMe, vpIp + vrIp); sv <- s * v; 3 * sqrt(as.numeric(t(sv) %*% matrix(c(1, 0.5, 0.5, 1), 2) %*% sv))
}
healthCatR <- function(d) {
  pop <- d$pop; rente <- prev$renteInvPctSalaire * pop$salaire; ages <- pmin(pmax(pop$age, 20), 61)
  af <- sapply(20:61, function(a) invalidAnnuityFactor(a, 0.03)); perm <- rente * af[floor(ages) - 19]
  tenY <- rente * pmin(10, prev$ageFinRente - ages) * 0.88; tw <- prev$ijPctSalaire * pop$salaire * 0.75
  nH <- sum(sapply(health, `[[`, "assures")); hc <- healthCat
  E <- c(deces = 0, invaliditePermanente = sum(perm), incapacite10Ans = sum(tenY), incapacite12Mois = sum(tw), soins = nH * hc$coutSoinsAccident)
  ma <- hc$massAccidentFrance * sum(hc$events * E); avg <- E / c(rep(nrow(pop), 4), nH)
  ac <- hc$plusGrandeConcentration * sum(hc$events * avg)
  pan <- hc$pandemicIp * sum(perm) + hc$pandemicSymptoms * nH * (hc$hospitalisation * hc$coutHospitalisation + hc$consultation * hc$coutConsultation)
  c(ma = ma, ac = ac, pan = pan, cat = sqrt(ma^2 + ac^2 + pan^2))
}
sltShockList <- function(start = 0) list(mortalite = Shock(mort = 1 + sltShocks$mortality, start = start), longevite = Shock(mort = 1 + sltShocks$longevity, start = start),
  incapacite = Shock(incid1 = 1 + sltShocks$incidenceYear1, incidAfter = 1 + sltShocks$incidenceAfter, recovery = 1 + sltShocks$recovery, start = start),
  frais = Shock(expense = 1 + sltShocks$expense, inflAdd = sltShocks$expenseInflation, start = start), revision = Shock(revision = sltShocks$revision, start = start))
runUnderwriting <- function(d, curves, base) {
  banner("\u00c9TAPE 3 : SCR DE SOUSCRIPTION (R)")
  rates <- curves$tauxAvecVa; h <- base$health
  p12 <- sum(sapply(h, `[[`, "cotisations12Mois"))
  vpIp <- sum(d$tarif$cotisationAnnuelle[d$tarif$garantie %in% c("incapacite", "invalidite")])
  scrPr <- nsltPR(max(p12 * (1 + healthGrowth), p12), max(sum(sapply(h, `[[`, "beSinistres")), 0), vpIp, max(base$ip$beSinistresIbnr, 0))
  lapse <- sum(pmax(0, -nsltLapse * c(sapply(h, `[[`, "bePrimes"), base$ip$bePrimes)))
  scrNslt <- sqrt(scrPr^2 + lapse^2)
  be0 <- base$slt$total; sh <- sltShockList()
  slt <- sapply(sh, function(s) max(sltBe(d$inc, d$inv, rates, s)$total - be0, 0)); slt <- c(slt[1:3], rachat = 0, slt[4:5])
  scrSlt <- aggregateScr(slt[sltNames], sltMatrix)
  cat <- healthCatR(d); scrHealth <- aggregateScr(c(scrSlt, scrNslt, cat["cat"]), healthMatrix)
  net <- function(x) x$bePrimes + x$beSinistresIbnr - x$creanceReassurance; n0 <- net(base$deces)
  life <- c(mortalite = max(net(decesBe(d$pop, d$triDec, rates, d$tarif, mortMult = 1.15)) - n0, 0), longevite = 0, invalidite = 0,
            rachat = max(0, -sltShocks$massLapse * base$deces$bePrimes * (1 - reinsuranceQuotaShareDeces)),
            frais = max(net(decesBe(d$pop, d$triDec, rates, d$tarif, expenseMult = 1.1)) - n0, 0), revision = 0,
            catastrophe = max(net(decesBe(d$pop, d$triDec, rates, d$tarif, catAdd = lifeCatShock)) - n0, 0))
  scrLife <- aggregateScr(life, lifeMatrix)
  summ <- data.frame(sousModule = c("NSLT primes et r\u00e9serves", "NSLT rachat", "NSLT", "SLT", "catastrophe", "SCR sant\u00e9", "SCR vie"),
                     scr = c(scrPr, lapse, scrNslt, scrSlt, cat["cat"], scrHealth, scrLife))
  saveTable(data.frame(sousModule = names(slt), scr = slt), "e3SltChocs"); saveTable(summ, "e3SyntheseSouscription")
  p <- ggplot(data.frame(s = names(slt), v = slt / 1e6), aes(s, v)) + geom_col(fill = palette[1]) + labs(title = "Sant\u00e9 SLT : SCR par choc (M\u20ac)", x = NULL, y = "M\u20ac")
  saveFig(p, "e3ScrSouscription")
  print(summ, row.names = FALSE)
  list(scrHealth = scrHealth, scrLife = scrLife, scrSlt = scrSlt, scrNslt = scrNslt, scrCat = unname(cat["cat"]), scrPr = scrPr, lapse = lapse, slt = slt, life = life)
}
