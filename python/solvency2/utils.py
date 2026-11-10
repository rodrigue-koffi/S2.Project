"""utils.py : outils transverses (journalisation, sauvegardes, style graphique, export Excel)."""
import logging
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from . import config as C

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("solvency2")
palette = ["#1f3b73", "#c8102e", "#2a9d8f", "#e9a03b", "#6c757d", "#8e5ea2", "#3e95cd", "#5c946e"]
plt.rcParams.update({"figure.figsize": (9, 5), "figure.dpi": 110, "axes.grid": True, "grid.alpha": .3,
                     "axes.spines.top": False, "axes.spines.right": False, "font.size": 10,
                     "axes.prop_cycle": matplotlib.cycler(color=palette)})
tableStore = {}


def banner(title):
    log.info("=" * 78); log.info(title); log.info("=" * 78)


def saveTable(df, name, index=False):
    df.to_csv(C.outTab / f"{name}.csv", index=index, sep=";", decimal=",", encoding="utf-8-sig")
    tableStore[name] = df.reset_index() if index else df
    return df


def saveFig(fig, name):
    fig.tight_layout(); fig.savefig(C.outFig / f"{name}.png", bbox_inches="tight"); plt.close(fig)


def exportExcel(path):
    with pd.ExcelWriter(path, engine="openpyxl") as xw:
        for name, df in tableStore.items():
            df.to_excel(xw, sheet_name=name[:31], index=False)


def aggregate(values, matrix):
    """Agrégation par matrice de corrélation : racine(v' M v)."""
    import numpy as np
    v = np.asarray(values, float)
    return float(np.sqrt(v @ np.asarray(matrix, float) @ v))
