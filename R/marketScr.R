# =============================================================================
# marketScr.R : ETAPE 4, marche, contrepartie, operationnel, BSCR, SCR, MCR, marge de risque (miroir de marketScr.py)
# =============================================================================
bondPrices <- function(b, rfr) sapply(seq_len(nrow(b)), function(i) { t <- 1:b$maturite[i]
  sp <- if (b$type[i] == "etat") sovereignSpreads[[b$pays[i]]] else bondSpreads[b$cqs[i] + 1]
  cf <- rep(b$coupon[i] * b$nominal[i], length(t)); cf[length(t)] <- cf[length(t)] + b$nominal[i]; sum(cf / (1 + rfr[t] + sp)^t) })
subDebtValue <- function(rfr) { sd <- subordinatedDebt; t <- 1:sd$maturite; cf <- rep(sd$coupon * sd$nominal, length(t)); cf[length(t)] <- cf[length(t)] + sd$nominal
  sum(cf / (1 + rfr[t] + sd$spreadEmission)^t) }
spreadFactor <- function(dur, cqs) {
  tab <- list(rbind(c(0.009, 0), c(0.045, 0.005), c(0.07, 0.005), c(0.095, 0.005), c(0.12, 0.005)), rbind(c(0.011, 0), c(0.055, 0.006), c(0.084, 0.005), c(0.109, 0.005), c(0.134, 0.005)),
              rbind(c(0.014, 0), c(0.07, 0.007), c(0.105, 0.005), c(0.13, 0.005), c(0.155, 0.005)), rbind(c(0.025, 0), c(0.125, 0.015), c(0.2, 0.01), c(0.25, 0.01), c(0.3, 0.005)),
              rbind(c(0.045, 0), c(0.225, 0.025), c(0.35, 0.018), c(0.44, 0.005), c(0.465, 0.005)))[[cqs + 1]]
  if (dur <= 5) return(tab[1, 1] * dur); if (dur <= 10) return(tab[2, 1] + tab[2, 2] * (dur - 5)); if (dur <= 15) return(tab[3, 1] + tab[3, 2] * (dur - 10))
  if (dur <= 20) return(tab[4, 1] + tab[4, 2] * (dur - 15)); min(tab[5, 1] + tab[5, 2] * (dur - 20), 1)
}
counterpartyType1 <- function(pd_, lgd) {
  u <- sort(unique(pd_)); tl <- sapply(u, function(p) sum(lgd[pd_ == p])); sl <- sapply(u, function(p) sum(lgd[pd_ == p]^2)); g <- counterpartyGamma
  vI <- sum(outer(seq_along(u), seq_along(u), Vectorize(function(j, k) { pj <- u[j]; pk <- u[k]; pj * (1 - pj) * pk * (1 - pk) / ((1 + g) * (pj + pk) - pj * pk) * tl[j] * tl[k] })))
  vA <- sum(1.5 * u * (1 - u) / (2.5 - u) * sl); sv <- sqrt(vI + vA); tot <- sum(tl)
  if (sv <= 0.07 * tot) 3 * sv else if (sv <= 0.2 * tot) 5 * sv else tot
}
riskMarginR <- function(d, base, uw, defReins, opPrem, rates) {
  rows <- list()
  for (t in 0:40) {
    fm <- 12 * t; b0 <- sltBe(d$inc, d$inv, rates, Shock(start = fm), fm)$total; if (b0 < 1e3) break
    sub <- sapply(sltShockList(fm), function(s) max(sltBe(d$inc, d$inv, rates, s, fm)$total - b0, 0)); sub <- c(sub[1:3], rachat = 0, sub[4:5])
    scrSlt <- aggregateScr(sub[sltNames], sltMatrix)
    resMe <- sum(sapply(names(health), function(s) { cf <- base$healthCf[[s]]; k0 <- 2 * t
      if (k0 + 2 > length(cf)) return(0); fut <- cf[(k0 + 2):length(cf)]; tt <- (seq_along(fut) - 1 + k0 + 0.5) / 2
      sum(fut * DF(rates, pmax(tt, 0.25)) / (if (t > 0) DF(rates, t) else 1)) }))
    ipRes <- if (t > 0) base$ip$beSinistresIbnr * b0 / base$slt$total else base$ip$beSinistresIbnr
    vpMe <- if (t == 0) sum(sapply(base$health, `[[`, "cotisationsS2")) else 0; vpIp <- if (t == 0) base$ip$cotisationsS2 else 0
    scrN <- nsltPR(vpMe, resMe, vpIp, ipRes); if (t == 0) scrN <- sqrt(scrN^2 + uw$lapse^2)
    scrH <- aggregateScr(c(scrSlt, scrN, if (t == 0) uw$scrCat else 0), healthMatrix)
    bscr <- aggregateScr(c(0, if (t == 0) defReins else 0, if (t == 0) uw$scrLife else 0, scrH, 0), bscrMatrix)
    op <- min(0.3 * bscr, max(0.0045 * b0 + 0.03 * (resMe + ipRes), if (t == 0) opPrem else 0))
    rows[[length(rows) + 1]] <- data.frame(annee = t, beSltRunOff = b0, scrReference = bscr + op)
  }
  rm <- do.call(rbind, rows); rm$coutDuCapital <- costOfCapital * rm$scrReference * DF(rates, rm$annee + 1)
  list(tab = rm, rm = sum(rm$coutDuCapital))
}
runMarket <- function(d, curves, shocks, base, uw) {
  banner("\u00c9TAPE 4 : SCR MARCH\u00c9, CONTREPARTIE, OP\u00c9RATIONNEL, SCR, MCR, MARGE DE RISQUE (R)")
  rfr <- curves$tauxSansVa; va <- curves$tauxAvecVa
  bonds <- read.csv(file.path(dataRaw, "actifsObligations.csv")); other <- read.csv(file.path(dataRaw, "actifsAutres.csv"))
  mv0 <- bondPrices(bonds, rfr); sd0 <- subDebtValue(rfr); be0 <- sum(base$lob$beNet)
  loss <- sapply(c("up", "down"), function(dir) { rS <- shockCurve(rfr, shocks, dir); vS <- if (dir == "up") curves$tauxAvecVaChocHausse else curves$tauxAvecVaChocBaisse
    dA <- sum(bondPrices(bonds, rS)) - sum(mv0); dL <- sum(computeAll(d, vS)$lob$beNet) - be0; -(dA - dL - (subDebtValue(rS) - sd0)) })
  scrRate <- max(loss, 0); A <- if (loss["up"] >= loss["down"]) 0 else 0.5
  cat_ <- function(c) sum(other$valeurMarche[other$categorie == c])
  scrEq <- aggregateScr(c((equityShock[1] + symmetricAdjustment) * cat_("action type 1"), (equityShock[2] + symmetricAdjustment) * cat_("action type 2")), matrix(c(1, 0.75, 0.75, 1), 2))
  scrProp <- propertyShock * cat_("immobilier"); scrFx <- currencyShock * sum(other$valeurMarche[other$devise == "USD"])
  exempt <- bonds$type == "etat" & bonds$pays %in% c("FR", "DE", "IT")
  scrSpread <- sum(ifelse(exempt, 0, mapply(spreadFactor, bonds$duration, bonds$cqs)) * mv0)
  totA <- sum(mv0) + sum(other$valeurMarche)
  xs <- c((pmax(0, mv0 - concThreshold[bonds$cqs + 1] * totA) * concG[bonds$cqs + 1])[!exempt],
          pmax(0, other$valeurMarche[other$categorie == "immobilier"] - propertyConcentrationThreshold * totA) * propertyConcentrationFactor)
  scrConc <- sqrt(sum(xs^2))
  Mm <- matrix(c(1, A, A, A, 0.25, 0, A, 1, 0.75, 0.75, 0.25, 0, A, 0.75, 1, 0.5, 0.25, 0, A, 0.75, 0.5, 1, 0.25, 0, 0.25, 0.25, 0.25, 0.25, 1, 0, 0, 0, 0, 0, 0, 1), 6, byrow = TRUE)
  mk <- c(taux = scrRate, action = scrEq, immobilier = scrProp, spread = scrSpread, change = scrFx, concentration = scrConc); scrMarket <- aggregateScr(mk, Mm)
  recov <- sum(base$lob$reassurance); lgdR <- max(0.5 * (recov + 0.5 * uw$scrLife * reinsuranceQuotaShareDeces / (1 - reinsuranceQuotaShareDeces)), 0)
  banks <- other[other$categorie == "d\u00e9p\u00f4t bancaire", ]
  d1 <- counterpartyType1(c(counterpartyPd[reinsurerCqs + 1], counterpartyPd[banks$cqs + 1]), c(lgdR, banks$valeurMarche))
  rec <- cat_("cr\u00e9ances"); d2 <- 0.15 * rec * 0.9 + 0.9 * rec * 0.1; scrDef <- sqrt(d1^2 + 1.5 * d1 * d2 + d2^2)
  dR <- counterpartyType1(counterpartyPd[reinsurerCqs + 1], lgdR)
  bscr <- aggregateScr(c(scrMarket, scrDef, uw$scrLife, uw$scrHealth, 0), bscrMatrix)
  lob <- base$lob; earnLife <- d$tarif$cotisationAnnuelle[d$tarif$garantie == "deces"]
  earnNl <- sum(sapply(base$health, `[[`, "cotisations12Mois")) + sum(d$tarif$cotisationAnnuelle[d$tarif$garantie != "deces"])
  tpL <- sum(lob$beBrut[grepl("^Sant\u00e9 SLT|^Vie", lob$lob)]); tpN <- sum(lob$beBrut[grepl("^Sant\u00e9 NSLT", lob$lob)])
  opPrem <- 0.04 * earnLife + 0.03 * earnNl; scrOp <- min(0.3 * bscr, max(opPrem, 0.0045 * max(tpL, 0) + 0.03 * max(tpN, 0)))
  rmr <- riskMarginR(d, base, uw, dR, opPrem, va)
  bs <- buildBalanceSheets(base, rmr$rm, mv0, bonds, other, sd0, base$stat)
  adj <- -min(taxRate * (bscr + scrOp), max(bs$netDt, 0)); scr <- bscr + scrOp + adj
  h <- base$health; meBe <- max(sum(sapply(h, function(x) x$beSinistres + x$bePrimes)), 0); mePrem <- sum(sapply(h, `[[`, "cotisations12Mois"))
  ipBe <- max(base$ip$beSinistresIbnr + base$ip$bePrimes, 0); ipPrem <- sum(d$tarif$cotisationAnnuelle[d$tarif$garantie != "deces"])
  mcrLin <- 0.047 * meBe + 0.047 * mePrem + 0.131 * ipBe + 0.085 * ipPrem + 0.021 * sum(lob$beNet[grepl("^Sant\u00e9 SLT|^Vie", lob$lob)]) +
    0.0007 * base$deces$capitalSousRisque * (1 - reinsuranceQuotaShareDeces)
  mcr <- max(min(max(mcrLin, 0.25 * scr), 0.45 * scr), amcr)
  synth <- data.frame(poste = c("SCR march\u00e9", "SCR contrepartie", "SCR vie", "SCR sant\u00e9", "BSCR", "SCR op\u00e9rationnel", "Ajustement imp\u00f4ts diff\u00e9r\u00e9s", "SCR", "MCR", "Marge de risque"),
                      montant = c(scrMarket, scrDef, uw$scrLife, uw$scrHealth, bscr, scrOp, adj, scr, mcr, rmr$rm))
  saveTable(data.frame(sousModule = names(mk), scr = mk), "e4ScrMarche"); saveTable(rmr$tab, "e4MargeDeRisque"); saveTable(synth, "e4SyntheseScr")
  p <- ggplot(data.frame(s = names(mk), v = mk / 1e6), aes(s, v)) + geom_col(fill = palette[1]) + labs(title = "SCR march\u00e9 par sous-module (M\u20ac)", x = NULL, y = "M\u20ac")
  saveFig(p, "e4ScrMarcheEtAgregation")
  print(synth, row.names = FALSE)
  list(synth = synth, mk = mk, scr = scr, mcr = mcr, rm = rmr$rm, bscr = bscr, scrOp = scrOp, scrMarket = scrMarket, scrDef = scrDef,
       mv0 = mv0, sd0 = sd0, bonds = bonds, other = other, bs = bs)
}
