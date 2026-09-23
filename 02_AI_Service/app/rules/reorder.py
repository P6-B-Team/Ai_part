"""
Reorder Suggestion Engine — deterministic rule-based baseline (WST-FR-14).

Mirrors AI_Design_Document.docx section 2.2 exactly. No ML here — this is
the fallback / baseline every future model must be measured against.
"""
from dataclasses import dataclass

from app import config


@dataclass
class ReorderInput:
    part_id: str
    part_name: str
    current_stock: float
    reserved_quantity: float
    min_stock: float
    max_stock: float
    open_po_quantity: float
    avg_weekly_consumption: float


@dataclass
class ReorderResult:
    part_id: str
    part_name: str
    suggested_quantity: float
    risk: str
    reason: str
    available_stock: float
    net_position: float
    weeks_of_cover: float | None
    baseline_version: str


def evaluate_reorder(data: ReorderInput) -> ReorderResult:
    # Step 1 — Available stock
    available_stock = data.current_stock - data.reserved_quantity

    # Step 2 — Net position (accounts for stock already inbound)
    net_position = available_stock + data.open_po_quantity

    # Step 3 — Trigger condition
    needs_reorder = net_position < data.min_stock

    # Step 4 — Suggested quantity, never negative
    suggested_quantity = max(0.0, data.max_stock - net_position) if needs_reorder else 0.0

    # Step 5 — Risk classification by weeks of cover
    if data.avg_weekly_consumption <= 0:
        weeks_of_cover = None
        risk = "High"
        reason = "No consumption history available — treating as High risk until data accumulates"
    else:
        weeks_of_cover = available_stock / data.avg_weekly_consumption

        if available_stock < 0:
            # Real-data edge case (seen in parts_data.csv): reserved
            # quantity exceeds physical stock — the part is already
            # over-committed to open jobs, which is worse than simply
            # "low stock". Say that plainly instead of a confusing
            # negative week count.
            risk = "High"
            overcommitted_by = abs(available_stock)
            if needs_reorder:
                reason = (
                    f"Stock is over-reserved by {overcommitted_by:g} unit(s) "
                    f"(reserved exceeds on-hand quantity) — treat as High risk"
                )
            else:
                reason = (
                    f"Stock is over-reserved by {overcommitted_by:g} unit(s), "
                    f"but incoming purchase orders bring net position above minimum"
                )
        else:
            if weeks_of_cover < config.REORDER_WEEKS_OF_COVER_HIGH:
                risk = "High"
            elif weeks_of_cover < config.REORDER_WEEKS_OF_COVER_MEDIUM:
                risk = "Medium"
            else:
                risk = "Low"

            if needs_reorder:
                reason = (
                    f"Available stock covers {weeks_of_cover:.1f} week(s) of demand; "
                    f"net position ({net_position:g}) is below minimum ({data.min_stock:g})"
                )
            else:
                reason = (
                    f"Available stock covers {weeks_of_cover:.1f} week(s) of demand; "
                    f"net position is above minimum — no reorder needed"
                )

    return ReorderResult(
        part_id=data.part_id,
        part_name=data.part_name,
        suggested_quantity=round(suggested_quantity, 2),
        risk=risk,
        reason=reason,
        available_stock=round(available_stock, 2),
        net_position=round(net_position, 2),
        weeks_of_cover=round(weeks_of_cover, 2) if weeks_of_cover is not None else None,
        baseline_version=config.BASELINE_VERSION,
    )
