from app.rules.reorder import ReorderInput, evaluate_reorder


def test_below_minimum_triggers_suggestion():
    data = ReorderInput(
        part_id="P-1", part_name="Brake Pad",
        current_stock=5, reserved_quantity=0,
        min_stock=10, max_stock=40,
        open_po_quantity=0, avg_weekly_consumption=7,
    )
    result = evaluate_reorder(data)
    assert result.risk == "High"
    assert result.suggested_quantity == 35  # max_stock(40) - net_position(5)
    assert result.net_position == 5


def test_open_po_prevents_duplicate_order():
    data = ReorderInput(
        part_id="P-2", part_name="Oil Filter",
        current_stock=2, reserved_quantity=0,
        min_stock=10, max_stock=30,
        open_po_quantity=15, avg_weekly_consumption=3,
    )
    result = evaluate_reorder(data)
    # net_position = 2 + 15 = 17, still below min(10)? no, 17 > 10 -> no reorder
    assert result.net_position == 17
    assert result.suggested_quantity == 0


def test_reserved_quantity_reduces_available_stock():
    data = ReorderInput(
        part_id="P-3", part_name="Spark Plug",
        current_stock=20, reserved_quantity=15,
        min_stock=10, max_stock=50,
        open_po_quantity=0, avg_weekly_consumption=5,
    )
    result = evaluate_reorder(data)
    assert result.available_stock == 5
    assert result.net_position == 5
    assert result.suggested_quantity == 45


def test_zero_consumption_defaults_to_high_risk_without_crash():
    data = ReorderInput(
        part_id="P-4", part_name="Rare Sensor",
        current_stock=1, reserved_quantity=0,
        min_stock=2, max_stock=10,
        open_po_quantity=0, avg_weekly_consumption=0,
    )
    result = evaluate_reorder(data)
    assert result.risk == "High"
    assert result.weeks_of_cover is None


def test_healthy_stock_needs_no_reorder():
    data = ReorderInput(
        part_id="P-5", part_name="Wiper Blade",
        current_stock=40, reserved_quantity=0,
        min_stock=10, max_stock=50,
        open_po_quantity=0, avg_weekly_consumption=2,
    )
    result = evaluate_reorder(data)
    assert result.suggested_quantity == 0
    assert result.risk == "Low"


def test_over_reserved_stock_flagged_high_with_clear_reason():
    """
    Real-data edge case found in parts_data.csv: 7 of 100 parts have
    reserved_quantity > stock_quantity (already over-committed to open
    jobs). Must be High risk with a clear explanation, not a confusing
    negative "weeks of cover" number.
    """
    data = ReorderInput(
        part_id="PART_016", part_name="PART_016 (Brake)",
        current_stock=0, reserved_quantity=0,  # available_stock forced negative below
        min_stock=12, max_stock=116,
        open_po_quantity=0, avg_weekly_consumption=9,
    )
    # simulate reserved > on-hand directly, matching the real row
    data.reserved_quantity = 7
    result = evaluate_reorder(data)
    assert result.risk == "High"
    assert result.available_stock == -7
    assert "over-reserved" in result.reason
    assert "week(s)" not in result.reason  # no confusing negative-week phrasing
