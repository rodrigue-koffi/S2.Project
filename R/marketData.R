# =============================================================================
# marketData.R : ETAPE 1.1, courbe EIOPA par Smith-Wilson, VA, chocs de taux (miroir de marketData.py)
# =============================================================================
mats <- 1:maxMaturity
wilsonM <- function(t, u, a, w) { outer(t, u, function(x, y) { lo <- pmin(x, y); hi <- pmax(x, y)
  exp(-w * (x + y)) * (a * lo - 0.5 * exp(-a * hi) * (exp(a * lo) - exp(-a * lo))) }) }
smithWilson <- function(liqMat, liqRates, u = ufr, alpha = NULL, out = mats) {
  w <- log(1 + u); p <- (1 + liqRates)^-liqMat
  curveF <- function(a, t) { z <- solve(wilsonM(liqMat, liqMat, a, w), p - exp(-w * liqMat)); exp(-w * t) + as.numeric(wilsonM(t, liqMat, a, w) %*% z) }
  gap <- function(a) { T <- max(liqMat) + convergencePeriod; f <- -(log(curveF(a, T + 0.001)) - log(curveF(a, T - 0.001))) / 0.002; abs(f - w) - convergenceTolerance }
  if (is.null(alpha)) alpha <- if (gap(alphaMin) <= 0) alphaMin else uniroot(gap, c(alphaMin, 1), tol = 1e-12)$root
  list(rates = curveF(alpha, out)^(-1 / out) - 1, alpha = alpha)
}
shockCurve <- function(r, shocks, direction) {
  fac <- sapply(seq_along(r), function(m) if (m <= 90) shocks[[if (direction == "up") "chocHausse" else "chocBaisse"]][shocks$maturite == m] else 0.20)
  if (direction == "up") r + pmax(r * fac, upShockMin) else ifelse(r > 0, r * (1 - fac), r)
}
runMarketData <- function() {
  banner("\u00c9TAPE 1.1 : COURBE EIOPA (R)")
  e21 <- read.csv(file.path(dataRaw, "eiopaRfr20211231Euro.csv")); par21 <- read.csv(file.path(dataRaw, "eiopaParametres20211231.csv"))
  shocks <- read.csv(file.path(dataRaw, "eiopaChocsTauxFormuleStandard.csv"))
  liq <- c(1:10, 12, 15, 20)
  own <- smithWilson(liq, e21$tauxSansVa[liq], par21$ufr); pil <- smithWilson(c(1, 5, 10, 20), e21$tauxSansVa[c(1, 5, 10, 20)], par21$ufr)
  val21 <- data.frame(reconstruction = c("points liquides EIOPA, alpha recalcul\u00e9", "points 1, 5, 10, 20 ans"), alpha = c(own$alpha, pil$alpha),
                      ecartMaxPb = c(max(abs(own$rates - e21$tauxSansVa)), max(abs(pil$rates - e21$tauxSansVa))) * 1e4)
  valShock <- data.frame(courbe = c("hausse", "baisse"), ecartMaxPb = c(max(abs(shockCurve(e21$tauxAvecVa, shocks, "up") - e21$chocHausseAvecVa)),
                                                                      max(abs(shockCurve(e21$tauxAvecVa, shocks, "down") - e21$chocBaisseAvecVa))) * 1e4)
  h <- read.csv(file.path(dataRaw, "eiopaRfrFranceHistorique.csv")); row <- h[h$reference_date == "2026-06-30", ]
  pr <- as.numeric(row[, c("rate_1y", "rate_5y", "rate_10y", "rate_20y")])
  nv <- smithWilson(c(1, 5, 10, 20), pr); wv <- smithWilson(c(1, 5, 10, 20), pr + row$va)
  curves <- data.frame(maturite = mats, tauxSansVa = nv$rates, tauxAvecVa = wv$rates)
  curves$tauxAvecVaChocHausse <- shockCurve(curves$tauxAvecVa, shocks, "up"); curves$tauxAvecVaChocBaisse <- shockCurve(curves$tauxAvecVa, shocks, "down")
  saveTable(val21, "e1ValidationSmithWilson2021"); saveTable(valShock, "e1ValidationChocsTaux2021"); saveTable(curves, "e1CourbesEiopa20260630")
  cl <- curves %>% pivot_longer(-maturite)
  p <- ggplot(cl[cl$maturite <= 100, ], aes(maturite, value * 100, colour = name)) + geom_line() + labs(title = "Courbe EIOPA au 30/06/2026 et chocs", x = "maturit\u00e9", y = "%", colour = NULL)
  saveFig(p, "e1CourbeEiopa")
  print(val21); print(valShock); cat("alpha sans VA :", nv$alpha, " avec VA :", wv$alpha, "\n")
  list(curves = curves, shocks = shocks, alphaNoVa = nv$alpha)
}
