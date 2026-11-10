# =============================================================================
# utils.R : outils transverses
# =============================================================================
suppressPackageStartupMessages({ library(ggplot2); library(dplyr); library(tidyr) })
palette <- c("#1f3b73", "#c8102e", "#2a9d8f", "#e9a03b", "#6c757d", "#8e5ea2", "#3e95cd", "#5c946e")
theme_set(theme_minimal(base_size = 10) + theme(plot.title = element_text(face = "bold")))
banner <- function(txt) cat(strrep("=", 78), "\n", txt, "\n", strrep("=", 78), "\n", sep = "")
saveTable <- function(df, name) {
  con <- file(file.path(outTab, paste0(name, ".csv")), open = "w", encoding = "UTF-8")
  writeLines("\ufeff", con, sep = ""); write.table(df, con, sep = ";", dec = ",", row.names = FALSE); close(con)
  invisible(df)
}
saveFig <- function(p, name, w = 9, h = 5) ggsave(file.path(outFig, paste0(name, ".png")), p, width = w, height = h, dpi = 110)
readPyTable <- function(name) read.table(file.path(root, "outputs", "python", "tables", paste0(name, ".csv")), sep = ";", dec = ",",
                                         header = TRUE, quote = "\"", fileEncoding = "UTF-8-BOM", check.names = FALSE)
aggregateScr <- function(v, M) sqrt(as.numeric(t(v) %*% M %*% v))
reconcile <- function(name, labels, py, r) {
  d <- data.frame(controle = labels, python = py, R = r); d$ecartRelatif <- ifelse(abs(d$python) > 1e-9, d$R / d$python - 1, d$R - d$python)
  saveTable(d, name); cat("\nR\u00e9conciliation", name, ":\n"); print(d, row.names = FALSE); invisible(d)
}
