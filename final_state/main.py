#!/usr/bin/env python3.11

# Copyright 2025, Gurobi Optimization, LLC

# Solve the classic diet model, showing how to add constraints
# to an existing model.

import json

import gurobipy as gp
import nextmv
from gurobipy import GRB
from nextmv import cloud
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# Nutrition guidelines, based on
# USDA Dietary Guidelines for Americans, 2005
# http://www.health.gov/DietaryGuidelines/dga2005/

# MODIFIED - load manifest and extract options to use in the execution
manifest = cloud.Manifest.from_yaml(".")
options = manifest.extract_options()


# Load data from JSON file
with open("diet_data.json", "r") as f:
    data = json.load(f)

# Extract categories and nutrition limits
categories = list(data["categories"].keys())
minNutrition = {}
maxNutrition = {}

for category in categories:
    minNutrition[category] = data["categories"][category]["min"]
    max_val = data["categories"][category]["max"]
    maxNutrition[category] = GRB.INFINITY if max_val is None else max_val

# Extract foods and costs
foods = list(data["foods"].keys())
cost = {}
for food in foods:
    cost[food] = data["foods"][food]["cost"]

# Extract nutrition values
nutritionValues = {}
for food in foods:
    for category in categories:
        nutritionValues[(food, category)] = data["foods"][food]["nutrition"][category]

# Model
m = gp.Model("diet")

# Create decision variables for the foods to buy
buy = m.addVars(foods, name="buy")


# The objective is to minimize the costs
m.setObjective(buy.prod(cost), GRB.MINIMIZE)


# Nutrition constraints
m.addConstrs(
    (
        gp.quicksum(nutritionValues[f, c] * buy[f] for f in foods)
        == [minNutrition[c], maxNutrition[c]]
        for c in categories
    ),
    "_",
)


def printSolution(filename="solution.txt", append=False):
    mode = "a" if append else "w"
    with open(filename, mode) as f:
        if m.status == GRB.OPTIMAL:
            result = f"\nCost: {m.ObjVal:g}\n"
            result += "\nBuy:\n"
            for food in foods:
                if buy[food].X > 0.0001:
                    result += f"{food} {buy[food].X:g}\n"

            # Print to console
            print(result.strip())
            # Write to file
            f.write(result)
        else:
            message = "No solution\n"
            print("No solution")
            f.write(message)


if options.limit_dairy:
    m.addConstr(buy.sum(["milk", "ice cream"]) <= options.dairy_level, "limit_dairy")

# Solve
m.optimize()
printSolution("solution.txt", append=True)


# MODIFIED - write statistics to statistics.json
statistics_file = "statistics.json"
with open(statistics_file, "w") as stats_f:
    statistics = nextmv.Statistics(
        result=nextmv.ResultStatistics(
            duration=m.Runtime,
            value=m.ObjVal,
            custom={
                "nvars": m.NumVars,
                "ncons": m.NumConstrs,
            },
        ),
    )
    stats_f.write(json.dumps({"statistics": statistics.to_dict()}))

print(f"Statistics written to {statistics_file}")

# Plotly visualization: quantities and nutrition by category
def plot_solution(m: gp.Model)  -> list[nextmv.Asset]:
    if m.status != GRB.OPTIMAL:
        return

    # Quantities bought
    quantities = {food: buy[food].X for food in foods}

    fig_q = go.Figure(
        data=[go.Bar(name="Amount",x=list(quantities.keys()), y=list(quantities.values()), marker_color="steelblue")]
    )
    fig_q.update_layout(title="Food purchase quantities", xaxis_title="Food", yaxis_title="Amount")

    # Nutrition totals vs min/max
    mins = []
    actuals = []
    maxs = []
    for c in categories:
        total = sum(nutritionValues[(f, c)] * quantities[f] for f in foods)
        actuals.append(total)
        mins.append(minNutrition[c])
        maxs.append(None if maxNutrition[c] == GRB.INFINITY else maxNutrition[c])

    # Actual as bars, Min and Max as marker dots
    fig_n = go.Figure()
    fig_n.add_trace(
        go.Bar(name="Actual", x=categories, y=actuals, marker_color="orange")
    )
    fig_n.add_trace(
        go.Scatter(
            name="Min",
            x=categories,
            y=mins,
            mode="markers",
            marker=dict(color="lightgreen", size=10, symbol="circle"),
        )
    )
    # only add max markers if at least one finite max exists
    if any(v is not None for v in maxs):
        fig_n.add_trace(
            go.Scatter(
                name="Max",
                x=categories,
                y=[(v if v is not None else None) for v in maxs],
                mode="markers",
                marker=dict(color="crimson", size=10, symbol="circle"),
            )
        )

    fig_n.update_layout(barmode="group", title="Nutrition by category", yaxis_title="Amount")

    # Combine into one HTML with two subplots
    fig = make_subplots(rows=2, cols=1, subplot_titles=("Food quantities", "Nutrition by category"), vertical_spacing=0.15)
    for t in fig_q.data:
        fig.add_trace(t, row=1, col=1)
    for t in fig_n.data:
        fig.add_trace(t, row=2, col=1)
    fig.update_layout(height=800, showlegend=True)

    assets = []
    assets.append(
        nextmv.Asset(
            name="Diet Results",
            content_type="json",
            visual=nextmv.Visual(
                visual_schema=nextmv.VisualSchema.PLOTLY,
                visual_type="custom-tab",
                label="Food Selection",
            ),
            content=[json.loads(fig.to_json())],
        )
    )
    return assets

# MODIFIED - write statistics to statistics.json
assets = plot_solution(m)
# Write assets to file
assets_file = "assets.json"
with open(assets_file, "w") as assets_f:
    assets_dict = {"assets": [asset.to_dict() for asset in assets]}
    assets_f.write(json.dumps(assets_dict, indent=2))
print(f"Assets written to {assets_file}")