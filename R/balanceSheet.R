# =============================================================================
# balanceSheet.R : ETAPE 5, bilan S2, fonds propres, ratios, sensibilites, ORSA (miroir de balanceSheet.py)
# =============================================================================
buildBalanceSheets <- function(base, rm, mv, bonds, other, sdV, stat) {
  lob <- base$lob; rec <- sum(lob$reassurance)
  be <- c(sum(lob$beBrut[grepl("^Sant\u00e9 NSLT", lob$lob)]), sum(lob$beBrut[grepl("^Sant\u00e9 SLT", lob$lob)]), sum(lob$beBrut[grepl("^Vie", lob$lob)]))
  cm <- function(c) sum(other$valeurMarche[other$categorie == c]); cb <- function(c) sum(other$valeurComptable[other$categorie == c])
  aS2 <- c(incorporel = 0, immobilier = cm("immobilier"), actions = cm("action type 1") + cm("action type 2"), etat = sum(mv[bonds$type == "etat"]),
           entreprises = sum(mv[bonds$type == "entreprise"]), depots = cm("d\u00e9p\u00f4t bancaire"), reassurance = rec, creances = cm("cr\u00e9ances"))
  reinsSoc <- reinsuranceQuotaShareDeces * sum(stat$social[grepl("d\u00e9c\u00e8s", stat$poste)])
  aSoc <- c(incorporel = cb("incorporel"), immobilier = cb("immobilier"), actions = cb("action type 1") + cb("action type 2"),
            etat = sum(bonds$valeurComptable[bonds$type == "etat"]), entreprises = sum(bonds$valeurComptable[bonds$type == "entreprise"]),
            depots = cb("d\u00e9p\u00f4t bancaire"), reassurance = reinsSoc, creances = cb("cr\u00e9ances"))
  navSoc <- sum(aSoc) - sum(stat$social) - subordinatedDebt$nominal - otherLiabilities
  navPre <- sum(aS2) - sum(be) - rm - sdV - otherLiabilities; dt <- taxRate * (navPre - navSoc)
  list(aS2 = aS2, aSoc = aSoc, navSocial = navSoc, navS2 = navPre - dt, netDt = dt, be = be, rec = rec)
}
ownFundsR <- function(bs, scr, mcr, sdV) {
  dta <- max(-bs$netDt, 0); t1 <- bs$navS2 - dta; elig <- t1 + min(sdV + min(dta, 0.15 * scr), 0.5 * scr); eligM <- t1 + min(sdV, tier2LimitMcr * mcr)
  list(t1 = t1, t2 = sdV, t3 = dta, eligScr = elig, eligMcr = eligM, ratioScr = elig / scr, ratioMcr = eligM / mcr)
}
runBalance <- function(d, curves, base, uw, mr) {
  banner("\u00c9TAPE 5 : BILAN S2, FONDS PROPRES, RATIOS, SENSIBILIT\u00c9S, ORSA (R)")
  bs <- mr$bs; of <- ownFundsR(bs, mr$scr, mr$mcr, mr$sd0)
  bil <- data.frame(poste = names(bs$aS2), social = bs$aSoc, solvabilite2 = bs$aS2)
  rat <- data.frame(indicateur = c("excedent d'actif S2", "fonds propres sociaux", "SCR", "MCR", "fonds propres eligibles SCR", "ratio SCR", "ratio MCR"),
                    valeur = c(bs$navS2, bs$navSocial, mr$scr, mr$mcr, of$eligScr, of$ratioScr, of$ratioMcr))
  rfr <- curves$tauxSansVa; va <- curves$tauxAvecVa
  navUnder <- function(rS, vS, eq = 1, spr = 0, sp = 0, invM = 1) {
    mv <- bondPrices(mr$bonds, rS); if (spr) mv <- ifelse(mr$bonds$type == "entreprise", mv * (1 - mr$bonds$duration * spr), mv)
    oth <- mr$other; oth$valeurMarche[grepl("^action", oth$categorie)] <- oth$valeurMarche[grepl("^action", oth$categorie)] * eq
    if (invM != 1) { orig <- invalidityRecovery; invalidityRecovery <<- function(a) orig(a) * invM; on.exit(invalidityRecovery <<- orig) }
    bb <- computeAll(d, vS, spShock = sp); bb$stat <- base$stat
    buildBalanceSheets(bb, mr$rm, mv, mr$bonds, oth, subDebtValue(rS), base$stat)$navS2
  }
  cases <- list(list("Baisse des taux de 50 pb", rfr - 0.005, va - 0.005), list("Hausse des taux de 50 pb", rfr + 0.005, va + 0.005),
                list("Baisse des actions de 25 %", rfr, va, eq = 0.75), list("Hausse des spreads de 50 pb", rfr, va, spr = 0.005),
                list("Sinistralit\u00e9 sant\u00e9 +5 points", rfr, va, sp = 0.05), list("Reprises des invalides -20 %", rfr, va, invM = 0.8),
                list("Sans correction pour volatilit\u00e9", rfr, rfr))
  sens <- do.call(rbind, lapply(cases, function(k) { args <- k[-(1:3)]
    nav <- do.call(navUnder, c(list(k[[2]], k[[3]]), args)); dN <- nav - bs$navS2
    data.frame(sensibilite = k[[1]], variationFondsPropres = dN, variationRatioPoints = ((of$eligScr + dN) / mr$scr - of$ratioScr) * 100) }))
  saveTable(bil, "e5BilanActif"); saveTable(rat, "e5Ratios"); saveTable(sens, "e5Sensibilites")
  p <- ggplot(sens, aes(sensibilite, variationRatioPoints)) + geom_col(fill = palette[2]) + coord_flip() + labs(title = "Sensibilit\u00e9s du ratio de solvabilit\u00e9 (points)", x = NULL, y = "points")
  saveFig(p, "e5BilanEtRatios")
  print(rat, row.names = FALSE); print(sens, row.names = FALSE)
  list(of = of, bs = bs, sens = sens)
}
