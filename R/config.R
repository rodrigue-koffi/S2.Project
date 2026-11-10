# =============================================================================
# config.R : hypotheses centralisees (miroir de python/solvency2/config.py)
# =============================================================================
getRoot <- function() {
  args <- commandArgs(trailingOnly = FALSE); f <- sub("--file=", "", args[grep("--file=", args)])
  if (length(f) == 1) return(normalizePath(file.path(dirname(f), ".."))); normalizePath("..")
}
root <- getRoot()
dataRaw <- file.path(root, "data", "raw"); dataProc <- file.path(root, "data", "processed")
outFig <- file.path(root, "outputs", "R", "figures"); outTab <- file.path(root, "outputs", "R", "tables")
for (p in c(dataProc, outFig, outTab)) dir.create(p, recursive = TRUE, showWarnings = FALSE)
valuationDate <- as.Date("2026-06-30"); ufr <- 0.0330; convergencePeriod <- 40; convergenceTolerance <- 1e-4; alphaMin <- 0.05
maxMaturity <- 150; symmetricAdjustment <- 0; upShockMin <- 0.01
health <- list(individuel = list(fraisGestionPrimes = 0.20, assures = 60000), collectif = list(fraisGestionPrimes = 0.12, assures = 120000))
healthGrowth <- 0.05; healthUlae <- 0.04
healthBestEstimateSpYears <- c("2024S1", "2024S2", "2025S1", "2025S2", "2026S1")
SEM <- paste0(rep(2019:2026, each = 2), c("S1", "S2"))[1:15]
prev <- list(renteInvPctSalaire = 0.30, ijPctSalaire = 0.25, capitalDecesPctSalaire = 2.0, ageFinRente = 62, dureeMaxIncapaciteMois = 36,
             incidenceArret90j = 0.012, abattementMortaliteActifs = 0.60, surmortaliteInvalides = 2.5, fraisGestionPrimes = 0.08,
             fraisGestionPrestations = 0.03, ratioSinistresCibleTarif = 0.92)
reinsuranceQuotaShareDeces <- 0.50; reinsurerCqs <- 2; statutoryRate <- 0.015; statutoryPsapMargin <- 0.05; equalisationProvision <- 2e6
expenseInflation <- 0.02; horizonMonths <- 540
nslt <- list(medicalExpense = c(0.05, 0.057), incomeProtection = c(0.085, 0.14)); nsltLobCorrelation <- 0.5; nsltLapse <- 0.40
sltShocks <- list(mortality = 0.15, longevity = -0.20, incidenceYear1 = 0.35, incidenceAfter = 0.25, recovery = -0.20, expense = 0.10,
                  expenseInflation = 0.01, revision = 0.04, massLapse = 0.40)
sltNames <- c("mortalite", "longevite", "incapacite", "rachat", "frais", "revision")
sltMatrix <- matrix(c(1, -0.25, 0.25, 0, 0.25, 0, -0.25, 1, 0, 0.25, 0.25, 0.25, 0.25, 0, 1, 0, 0.5, 0, 0, 0.25, 0, 1, 0.5, 0,
                      0.25, 0.25, 0.5, 0.5, 1, 0.5, 0, 0.25, 0, 0, 0.5, 1), 6, byrow = TRUE)
lifeMatrix <- matrix(c(1, -0.25, 0.25, 0, 0.25, 0, 0.25, -0.25, 1, 0, 0.25, 0.25, 0.25, 0, 0.25, 0, 1, 0, 0.5, 0, 0.25,
                       0, 0.25, 0, 1, 0.5, 0, 0.25, 0.25, 0.25, 0.5, 0.5, 1, 0.5, 0.25, 0, 0.25, 0, 0, 0.5, 1, 0, 0.25, 0, 0.25, 0.25, 0.25, 0, 1), 7, byrow = TRUE)
lifeCatShock <- 0.0015
healthMatrix <- matrix(c(1, 0.5, 0.25, 0.5, 1, 0.25, 0.25, 0.25, 1), 3, byrow = TRUE)
healthCat <- list(massAccidentFrance = 0.0005, events = c(deces = 0.10, invaliditePermanente = 0.015, incapacite10Ans = 0.05, incapacite12Mois = 0.135, soins = 0.30),
                  pandemicIp = 0.000075, pandemicSymptoms = 0.4, hospitalisation = 0.01, consultation = 0.20, coutHospitalisation = 3500,
                  coutConsultation = 60, coutSoinsAccident = 1500, plusGrandeConcentration = 1000)
equityShock <- c(type1 = 0.39, type2 = 0.49); equityCorrelation <- 0.75; propertyShock <- 0.25; currencyShock <- 0.25
concThreshold <- c(0.03, 0.03, 0.03, 0.015, 0.015, 0.015, 0.015); concG <- c(0.12, 0.12, 0.21, 0.27, 0.73, 0.73, 0.73)   # indices cqs + 1
counterpartyPd <- c(0.00002, 0.0001, 0.0005, 0.0024, 0.012, 0.042, 0.042)
bscrMatrix <- matrix(c(1, 0.25, 0.25, 0.25, 0.25, 0.25, 1, 0.25, 0.25, 0.5, 0.25, 0.25, 1, 0, 0, 0.25, 0.25, 0, 1, 0, 0.25, 0.5, 0, 0, 1), 5, byrow = TRUE)
taxRate <- 0.2583; costOfCapital <- 0.06; amcr <- 4e6; tier2LimitMcr <- 0.20
bondSpreads <- c(0.0015, 0.0060, 0.0090, 0.0150, 0.0300); sovereignSpreads <- c(FR = 0, DE = 0, IT = 0.012)
subordinatedDebt <- list(nominal = 8e6, coupon = 0.05, maturite = 10, spreadEmission = 0.03)
propertyConcentrationThreshold <- 0.10; propertyConcentrationFactor <- 0.12; counterpartyGamma <- 0.25
otherLiabilities <- 4e6; establishmentFund <- 10e6
orsaYears <- 2026:2029; orsaGrowth <- 0.04; orsaInvestmentReturn <- 0.03
