# =============================================================================
# bestEstimate.R : ETAPE 2, best estimate sante, prevoyance, deces (miroir de bestEstimate.py)
# =============================================================================
DF <- function(rates, t) { r <- approx(1:length(rates), rates, xout = pmax(t, 1), rule = 2)$y; (1 + r)^-t }
monthlyP <- function(p) 1 - (1 - pmin(pmax(p, 0), 1))^(1 / 12)
Shock <- function(mort = 1, recovery = 1, incid1 = 1, incidAfter = 1, expense = 1, inflAdd = 0, revision = 0, start = 0)
  list(mort = mort, recovery = recovery, incid1 = incid1, incidAfter = incidAfter, expense = expense, inflAdd = inflAdd, revision = revision, start = start)

chainLadder <- function(tri) {
  w <- tapply(tri$reglements, list(factor(tri$survenance, levels = SEM), tri$developpement), sum)
  cum <- t(apply(w, 1, cumsum)); n <- ncol(cum); f <- c(); sig2 <- c()
  for (d in 1:(n - 1)) { ok <- !is.na(cum[, d + 1]); fd <- sum(cum[ok, d + 1]) / sum(cum[ok, d]); f <- c(f, fd)
    res <- cum[ok, d] * (cum[ok, d + 1] / cum[ok, d] - fd)^2; sig2 <- c(sig2, sum(res) / max(sum(ok) - 1, 1)) }
  sig2[sig2 <= 0] <- 1e-9
  k <- length(sig2); if (k > 2) sig2[k] <- min(sig2[k - 1]^2 / max(sig2[k - 2], 1e-12), min(sig2[k - 2], sig2[k - 1])) else if (k > 1) sig2[k] <- sig2[k - 1]
  rows <- lapply(seq_along(SEM), function(i) { last <- if (i - 1 + n - 1 <= 14) n - 1 else 14 - (i - 1); c0 <- cum[i, last + 1]; ult <- c0; mse <- 0
    if (last < n - 1) for (d in (last + 1):(n - 1)) { mse <- mse * f[d]^2 + sig2[d] * ult; ult <- ult * f[d] }
    data.frame(survenance = SEM[i], paye = c0, developpementAtteint = last, ultime = ult, reserve = ult - c0, erreurMack = sqrt(mse)) })
  list(cl = do.call(rbind, rows), f = f)
}
cumPattern <- function(f) 1 / rev(c(1, cumprod(rev(f))))
healthClaimsCashflows <- function(cl, f) {
  n <- length(f) + 1; cp <- cumPattern(f); cf <- numeric(n + 1)
  for (i in seq_len(nrow(cl))) { d0 <- cl$developpementAtteint[i]; if (d0 + 1 <= n - 1) for (d in (d0 + 1):(n - 1)) cf[d - d0 + 1] <- cf[d - d0 + 1] + cl$ultime[i] * (cp[d + 1] - cp[d]) }
  cf
}
healthBe <- function(tris, prem, rates, spShock = 0, expenseMult = 1, lapse = 0) {
  out <- list(); cfs <- list()
  for (seg in names(health)) {
    x <- chainLadder(tris[tris$segment == seg, ]); cl <- x$cl; f <- x$f; cf <- healthClaimsCashflows(cl, f)
    t <- (seq_along(cf) - 1 - 0.5) / 2; beClaims <- sum(cf * DF(rates, pmax(t, 0.25))) * (1 + healthUlae * expenseMult)
    p <- prem[prem$segment == seg, ]; premS2 <- p$cotisations[p$semestre == "2026S1"] * (1 - lapse)
    sel <- p$semestre %in% healthBestEstimateSpYears
    spBe <- sum(cl$ultime[cl$survenance %in% healthBestEstimateSpYears]) / sum(p$cotisations[sel]) + spShock
    pat <- diff(c(0, cumPattern(f))); claimsCf <- premS2 * spBe * pat; tc <- 0.25 + (seq_along(claimsCf) - 1) / 2
    bePremClaims <- sum(claimsCf * DF(rates, tc)) * (1 + healthUlae * expenseMult)
    d25 <- DF(rates, 0.25)
    out[[seg]] <- list(beSinistres = beClaims, bePrimes = bePremClaims + premS2 * health[[seg]]$fraisGestionPrimes * expenseMult * d25 - premS2 * d25,
                       reserveNonActualisee = sum(cl$reserve), erreurMack = sqrt(sum(cl$erreurMack^2)), spBestEstimate = spBe, cotisationsS2 = premS2,
                       cotisations12Mois = sum(p$cotisations[p$semestre %in% c("2025S2", "2026S1")]))
    cfs[[seg]] <- cf
  }
  list(h = out, cfs = cfs)
}
projectInvalid <- function(ages, sexes, amounts, weights, startMonth, sh, horizon = horizonMonths) {
  # version vectorisee sans ifelse (memes calculs que la version Python)
  cf <- numeric(horizon); s <- weights; age <- ages; start <- rep_len(startMonth, length(ages)); amt <- amounts * (1 + sh$revision)
  isH <- sexes == "H"; fH <- prev$surmortaliteInvalides
  for (m in min(start):(horizon - 1)) {
    started <- start <= m; activeAge <- age < prev$ageFinRente; active <- started & activeAge
    if (!(all(started) || any(active))) next
    if (all(started) && !any(active)) break
    cf[m + 1] <- cf[m + 1] + sum(s * active * amt) / 12
    on <- m >= sh$start
    rec <- (1 - (1 - invalidityRecovery(age))^(1 / 12)) * (if (on) sh$recovery else 1)
    q <- isH * pmin(approx(TH$age, TH$qx, xout = age, rule = 2)$y * fH, 1) + (!isH) * pmin(approx(TF$age, TF$qx, xout = age, rule = 2)$y * fH, 1)
    dth <- 1 - (1 - pmin(q * (if (on) sh$mort else 1), 1))^(1 / 12)
    s <- started * (s * (1 - rec) * (1 - dth) * activeAge) + (!started) * s; age <- age + started / 12
  }
  cf
}
projectIncapacity <- function(inc, sh, horizon = horizonMonths) {
  cfIj <- numeric(horizon); age <- inc$ageEntree + (inc$ancienneteMois - 3) / 12; d <- inc$ancienneteMois
  ij <- inc$ijAnnuelle; rente <- prev$renteInvPctSalaire * inc$salaire; sx <- inc$sexe; s <- rep(1, nrow(inc)); fl <- list()
  for (m in 0:35) {
    alive <- d < prev$dureeMaxIncapaciteMois; if (!any(alive)) break
    cfIj[m + 1] <- cfIj[m + 1] + sum(s * alive * ij / 12); on <- m >= sh$start
    im <- if (on) (if (m < sh$start + 12) sh$incid1 else sh$incidAfter) else 1
    ex <- incapacityExit(d, age); share <- pmin(pmax(incapacityToInvalidShare(d, age) * im, 0), 1)
    pInv <- ex * share; pRec <- ex * (1 - share) * (if (on) sh$recovery else 1); pDth <- monthlyP(qxV(sx, age) * (if (on) sh$mort else 1))
    last <- (d + 1 >= prev$dureeMaxIncapaciteMois) & alive
    toInv <- ifelse(last, s * (1 - pDth), s * pInv) * alive; k <- toInv > 0
    if (any(k)) fl[[length(fl) + 1]] <- data.frame(a = age[k] + 1 / 12, sx = sx[k], r = rente[k], w = toInv[k], st = m + 1)
    s <- ifelse(last, 0, s * (1 - pInv - pRec - pDth)) * alive; d <- d + 1; age <- age + 1 / 12
  }
  f <- do.call(rbind, fl)
  list(ij = cfIj, inv = if (is.null(f)) numeric(horizon) else projectInvalid(f$a, f$sx, f$r, f$w, f$st, sh, horizon))
}
sltBe <- function(inc, inv, rates, sh = Shock(), fromMonth = 0) {
  pi <- projectIncapacity(inc, sh); stock <- projectInvalid(inv$ageActuel, inv$sexe, inv$renteAnnuelle, rep(1, nrow(inv)), 0, sh)
  months <- 0:(horizonMonths - 1); ben <- pi$ij + pi$inv + stock
  exps <- ben * prev$fraisGestionPrestations * sh$expense * (1 + expenseInflation + sh$inflAdd)^((months + 0.5) / 12)
  keep <- months >= fromMonth; df <- DF(rates, (months[keep] + 0.5) / 12) / (if (fromMonth > 0) DF(rates, fromMonth / 12) else 1)
  list(ij = sum(pi$ij[keep] * df), invFut = sum(pi$inv[keep] * df), invStock = sum(stock[keep] * df), frais = sum(exps[keep] * df),
       total = sum((ben + exps)[keep] * df), cashflows = ben + exps)
}
countIbnr <- function(tri) {
  w <- tapply(tri$nombre, list(factor(tri$survenance, levels = SEM), tri$developpement), sum); cum <- t(apply(w, 1, cumsum)); n <- ncol(cum)
  f <- sapply(1:(n - 1), function(d) { ok <- !is.na(cum[, d + 1]); sum(cum[ok, d + 1]) / sum(cum[ok, d]) })
  ib <- 0; for (i in seq_along(SEM)) { last <- min(n - 1, 14 - (i - 1)); c0 <- cum[i, last + 1]; ib <- ib + c0 * (prod(if (last < n - 1) f[(last + 1):(n - 1)] else 1) - 1) }
  ib
}
costTable <- NULL
prevoyanceNsltBe <- function(pop, triInc, rates, tarif, lapse = 0) {
  rateAvg <- rates[8]; ages <- 20:64
  cost <- t(sapply(ages, function(a) newClaimCost(a, 1, 1, rateAvg)))
  a <- floor(pmin(pmax(pop$age, 20), 64)); idx <- a - 19; inc <- incidenceByAge(pop$age)
  perClaim <- cost[idx, 1] * prev$ijPctSalaire * pop$salaire + cost[idx, 2] * prev$renteInvPctSalaire * pop$salaire
  claimsS2 <- sum(inc * perClaim) / 2 * (1 - lapse); premS2 <- sum(tarif$cotisationAnnuelle[tarif$garantie %in% c("incapacite", "invalidite")]) / 2 * (1 - lapse)
  d25 <- DF(rates, 0.25)
  bePrem <- claimsS2 * (1 + prev$fraisGestionPrestations) * DF(rates, 0.5) + premS2 * prev$fraisGestionPrimes * d25 - premS2 * d25
  nIbnr <- countIbnr(triInc); avgCost <- sum(inc * perClaim) / sum(inc)
  list(bePrimes = bePrem, beSinistresIbnr = nIbnr * avgCost * (1 + prev$fraisGestionPrestations) * d25, nombreIbnr = nIbnr, cotisationsS2 = premS2)
}
decesBe <- function(pop, triDec, rates, tarif, mortMult = 1, catAdd = 0, expenseMult = 1, lapse = 0) {
  q <- pmin(qxV(pop$sexe, pop$age, prev$abattementMortaliteActifs) * mortMult + catAdd, 1); cap <- prev$capitalDecesPctSalaire * pop$salaire
  claimsS2 <- sum(q * cap) / 2 * (1 - lapse); premS2 <- tarif$cotisationAnnuelle[tarif$garantie == "deces"] / 2 * (1 - lapse); d25 <- DF(rates, 0.25)
  nIbnr <- countIbnr(triDec); qs <- reinsuranceQuotaShareDeces
  list(bePrimes = claimsS2 * (1 + prev$fraisGestionPrestations * expenseMult) * d25 + premS2 * prev$fraisGestionPrimes * expenseMult * d25 - premS2 * d25,
       beSinistresIbnr = nIbnr * mean(cap) * (1 + prev$fraisGestionPrestations * expenseMult) * d25,
       creanceReassurance = qs * (claimsS2 * d25 + nIbnr * mean(cap) * d25) - qs * premS2 * d25, capitalSousRisque = sum(cap))
}
loadInputsR <- function(q) list(tris = read.csv(file.path(dataRaw, "santeTriangles.csv")), prem = read.csv(file.path(dataRaw, "santeCotisations.csv")),
  pop = q$pop, inc = q$inc, inv = q$inv, triInc = read.csv(file.path(dataRaw, "prevoyanceTriangleArrets.csv")),
  triDec = read.csv(file.path(dataRaw, "prevoyanceTriangleDeces.csv")), tarif = read.csv(file.path(dataRaw, "prevoyanceTarif.csv")))
computeAll <- function(d, rates, sh = Shock(), spShock = 0) {
  hb <- healthBe(d$tris, d$prem, rates, spShock); h <- hb$h; slt <- sltBe(d$inc, d$inv, rates, sh)
  ip <- prevoyanceNsltBe(d$pop, d$triInc, rates, d$tarif); dc <- decesBe(d$pop, d$triDec, rates, d$tarif)
  cda <- max(0.5 * counterpartyPd[reinsurerCqs + 1] / (1 - counterpartyPd[reinsurerCqs + 1]) * 0.5 * dc$creanceReassurance, 0)
  lob <- data.frame(lob = c("Sant\u00e9 NSLT : frais m\u00e9dicaux", "Sant\u00e9 NSLT : frais m\u00e9dicaux", "Sant\u00e9 NSLT : perte de revenus", "Sant\u00e9 SLT : rentes en cours", "Vie : autres (d\u00e9c\u00e8s)"),
                    segment = c("individuel", "collectif", "arr\u00eats de travail", "en cours", "d\u00e9c\u00e8s"),
                    beSinistres = c(h$individuel$beSinistres, h$collectif$beSinistres, ip$beSinistresIbnr, slt$total, dc$beSinistresIbnr),
                    bePrimes = c(h$individuel$bePrimes, h$collectif$bePrimes, ip$bePrimes, 0, dc$bePrimes), reassurance = c(0, 0, 0, 0, dc$creanceReassurance - cda))
  lob$beBrut <- lob$beSinistres + lob$bePrimes; lob$beNet <- lob$beBrut - lob$reassurance
  list(lob = lob, health = h, healthCf = hb$cfs, slt = slt, ip = ip, deces = dc, cda = cda)
}
runBestEstimate <- function(d, curves) {
  banner("\u00c9TAPE 2 : BEST ESTIMATE (R)")
  res <- computeAll(d, curves$tauxAvecVa); flat <- rep(statutoryRate, 150)
  sltStat <- sltBe(d$inc, d$inv, flat)$total; ipStat <- prevoyanceNsltBe(d$pop, d$triInc, flat, d$tarif)$beSinistresIbnr
  psap <- sum(sapply(res$health, `[[`, "reserveNonActualisee")) * (1 + statutoryPsapMargin) * (1 + healthUlae)
  dcStat <- res$deces$beSinistresIbnr / DF(curves$tauxAvecVa, 0.25)
  stat <- data.frame(poste = c("PSAP sant\u00e9", "Provision pour primes sant\u00e9", "PM incapacit\u00e9 et invalidit\u00e9", "IBNR arr\u00eats", "Provision pour primes arr\u00eats", "PSAP d\u00e9c\u00e8s", "Provision pour primes d\u00e9c\u00e8s", "Provision d'\u00e9galisation"),
                     social = c(psap, 0, sltStat, ipStat, 0, dcStat, 0, equalisationProvision),
                     s2BestEstimate = c(res$health$individuel$beSinistres + res$health$collectif$beSinistres, res$health$individuel$bePrimes + res$health$collectif$bePrimes,
                                        res$slt$total, res$ip$beSinistresIbnr, res$ip$bePrimes, res$deces$beSinistresIbnr, res$deces$bePrimes, 0))
  saveTable(res$lob, "e2BestEstimateParLob"); saveTable(stat, "e2PassageSocialS2")
  p <- ggplot(res$lob, aes(paste(lob, segment), beNet / 1e6)) + geom_col(fill = palette[1]) + coord_flip() + labs(title = "Best estimate net par ligne d'activit\u00e9 (M\u20ac)", x = NULL, y = "M\u20ac")
  saveFig(p, "e2BestEstimate")
  print(res$lob[, c("lob", "segment", "beBrut", "beNet")]); res$stat <- stat; res
}
