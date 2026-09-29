"""Рисует images/engines.svg - сравнение движков на трёх сценариях.

Цифры - замер 29.09.2026: OSRM (авто по дорогам), без запаса, «баланс» (F = 60),
OR-Tools 10 с с тёплым стартом от greedy. Перезапустить: python3 diagrams/engines.py
"""
from pathlib import Path

import matplotlib

matplotlib.use("svg")
import matplotlib.pyplot as plt

SCENARIOS = ["Обычный день\n59 заявок, 12 чел.", "Пик\n78 заявок, 12 чел.", "Некомплект\n59 заявок, 8 чел."]
ENGINES = ["baseline", "greedy", "OR-Tools"]
COLORS = ["#B8BCC4", "#F2B705", "#2F6FEB"]
ASSIGNED = [[33, 57, 57], [41, 73, 73], [24, 57, 57]]
ENGINEERS = [[12, 8, 7], [12, 10, 10], [8, 8, 8]]
KM = [[239.1, 209.0, 204.4], [287.9, 310.6, 289.9], [152.2, 238.1, 218.4]]

plt.rcParams.update({"font.family": "Helvetica", "font.size": 10})
fig, axes = plt.subplots(1, 3, figsize=(11, 3.4))
panels = [("Назначено заявок", ASSIGNED, "{:d}"), ("Инженеров вышло", ENGINEERS, "{:d}"),
          ("Пробег, км", KM, "{:.0f}")]
w = 0.26
for ax, (title, data, fmt) in zip(axes, panels):
    for j, (name, color) in enumerate(zip(ENGINES, COLORS)):
        xs = [i + (j - 1) * w for i in range(len(SCENARIOS))]
        vals = [row[j] for row in data]
        bars = ax.bar(xs, vals, w, color=color, label=name)
        for b, v in zip(bars, vals):
            ax.text(b.get_x() + b.get_width() / 2, b.get_height(), fmt.format(v),
                    ha="center", va="bottom", fontsize=8)
    ax.set_title(title, loc="left", fontsize=11)
    ax.set_xticks(range(len(SCENARIOS)), SCENARIOS, fontsize=8)
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.set_yticks([])
axes[0].legend(frameon=False, fontsize=8, loc="upper left", bbox_to_anchor=(0, -0.22), ncol=3)
fig.tight_layout()
fig.savefig(Path(__file__).resolve().parent.parent / "images" / "engines.svg")
