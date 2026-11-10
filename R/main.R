# =============================================================================
invisible(Sys.setlocale("LC_ALL", "C.UTF-8"))
# main.R : version R du projet Solvabilite II sante et prevoyance (miroir de python/main.py)
# Usage : Rscript R/main.R [etape]  (depuis la racine du projet)
# Les portefeuilles sont generes par la version Python (data/raw) ; R refait tous les calculs et se reconcilie
# avec les tables Python.
# =============================================================================
suppressPackageStartupMessages({ library(ggplot2); library(dplyr); library(tidyr) })
args <- commandArgs(trailingOnly = TRUE); etape <- if (length(args)) as.integer(args[1]) else 5
.f <- sub("--file=", "", commandArgs(FALSE)[grep("--file=", commandArgs(FALSE))]); .dir <- if (length(.f)) dirname(normalizePath(.f)) else "R"
for (f in c("config.R", "utils.R", "marketData.R", "actuarialTables.R", "dataQuality.R", "bestEstimate.R", "underwritingScr.R", "marketScr.R", "balanceSheet.R"))
  source(file.path(.dir, f), encoding = "UTF-8")
pyTab <- function(n) read.table(file.path(root, "outputs", "python", "tables", paste0(n, ".csv")), sep = ";", dec = ",", header = TRUE, fileEncoding = "UTF-8-BOM", quote = "\"")
hasPy <- file.exists(file.path(root, "outputs", "python", "tables", "e4SyntheseScr.csv"))

md <- runMarketData(); runTables(); q <- runQuality(); d <- loadInputsR(q)
if (hasPy) { py <- pyTab("e1CourbesEiopa20260630")
  reconcile("e1ReconciliationPythonR", c("taux 1 an avec VA", "taux 10 ans avec VA", "taux 30 ans avec VA", "taux 60 ans avec VA", "taux 10 ans choc hausse"),
            c(py$tauxAvecVa[c(1, 10, 30, 60)], py$tauxAvecVaChocHausse[10]), c(md$curves$tauxAvecVa[c(1, 10, 30, 60)], md$curves$tauxAvecVaChocHausse[10])) }
if (etape >= 2) { base <- runBestEstimate(d, md$curves)
  if (hasPy) { p <- pyTab("e2BestEstimateParLob"); s <- pyTab("e2PassageSocialS2")
    reconcile("e2ReconciliationPythonR", c(paste("BE net", p$lob, p$segment), "provisions sociales totales"), c(p$beNet, sum(s$social)), c(base$lob$beNet, sum(base$stat$social))) } }
if (etape >= 3) { uw <- runUnderwriting(d, md$curves, base)
  if (hasPy) { p <- pyTab("e3SyntheseSouscription")
    reconcile("e3ReconciliationPythonR", p$sousModule, p$scr, c(uw$scrPr, uw$lapse, uw$scrNslt, uw$scrSlt, uw$scrCat, uw$scrHealth, uw$scrLife)) } }
if (etape >= 4) { mr <- runMarket(d, md$curves, md$shocks, base, uw)
  if (hasPy) { p <- pyTab("e4SyntheseScr"); m <- pyTab("e4ScrMarche"); g <- function(x) p$montant[p$poste == x]
    reconcile("e4ReconciliationPythonR", c(paste("march\u00e9,", m$sousModule), "SCR march\u00e9", "SCR contrepartie", "BSCR", "SCR op\u00e9rationnel", "SCR", "MCR", "marge de risque"),
              c(m$scr, g("SCR march\u00e9"), g("SCR contrepartie"), g("BSCR"), g("SCR op\u00e9rationnel"), g("SCR"), g("MCR"), g("Marge de risque")),
              c(mr$mk, mr$scrMarket, mr$scrDef, mr$bscr, mr$scrOp, mr$scr, mr$mcr, mr$rm)) } }
if (etape >= 5) { bl <- runBalance(d, md$curves, base, uw, mr)
  if (hasPy) { r <- pyTab("e5Ratios"); s <- pyTab("e5Sensibilites"); g <- function(x) r$valeur[r$indicateur == x]
    reconcile("e5ReconciliationPythonR", c("fonds propres \u00e9ligibles SCR", "ratio SCR", "ratio MCR", paste("sensibilit\u00e9 (points),", s$sensibilite)),
              c(g("eligiblesScr"), g("ratioScr"), g("ratioMcr"), s$variationRatioPoints), c(bl$of$eligScr, bl$of$ratioScr, bl$of$ratioMcr, bl$sens$variationRatioPoints)) } }
