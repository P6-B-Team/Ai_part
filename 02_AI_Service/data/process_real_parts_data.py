"""
Runs the REAL parts_data.csv (provided by the team, not synthetic) through
the live reorder rule engine, and writes out the actual suggestions.

This is the first time the engine runs against real project data instead
of the synthetic generator.

Run:
    python -m data.process_real_parts_data
"""
import csv
from pathlib import Path

from app.rules.reorder import ReorderInput, evaluate_reorder

DATA_PATH = Path(__file__).parent / "parts_data.csv"
OUT_PATH = Path(__file__).parent / "reorder_suggestions_output.csv"

WEEKS_PER_MONTH = 4.345  # standard conversion, documented so it's not a magic number


def main():
    if not DATA_PATH.exists():
        raise SystemExit(f"No parts_data.csv at {DATA_PATH}")

    rows_out = []
    risk_counts = {"High": 0, "Medium": 0, "Low": 0}

    with open(DATA_PATH, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            weekly_consumption = float(row["monthly_usage"]) / WEEKS_PER_MONTH

            result = evaluate_reorder(ReorderInput(
                part_id=row["part_id"],
                part_name=f"{row['part_id']} ({row['category']})",
                current_stock=float(row["stock_quantity"]),
                reserved_quantity=float(row["reserved_quantity"]),
                min_stock=float(row["min_stock_level"]),
                max_stock=float(row["max_stock_level"]),
                open_po_quantity=0,  # not present in this dataset
                avg_weekly_consumption=weekly_consumption,
            ))

            risk_counts[result.risk] += 1
            rows_out.append({
                "part_id": result.part_id,
                "category": row["category"],
                "current_stock": row["stock_quantity"],
                "reserved_quantity": row["reserved_quantity"],
                "min_stock": row["min_stock_level"],
                "max_stock": row["max_stock_level"],
                "weekly_consumption_derived": round(weekly_consumption, 2),
                "available_stock": result.available_stock,
                "net_position": result.net_position,
                "suggested_quantity": result.suggested_quantity,
                "risk": result.risk,
                "reason": result.reason,
            })

    with open(OUT_PATH, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rows_out[0].keys())
        writer.writeheader()
        writer.writerows(rows_out)

    print(f"Processed {len(rows_out)} real parts from {DATA_PATH.name}")
    print(f"Risk breakdown: {risk_counts}")
    reorder_needed = [r for r in rows_out if float(r["suggested_quantity"]) > 0]
    print(f"Parts needing reorder: {len(reorder_needed)} / {len(rows_out)}")
    print(f"Wrote -> {OUT_PATH}")


if __name__ == "__main__":
    main()
