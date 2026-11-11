SELECT g.*, CASE WHEN g.grain = 'zone'
    AND g.pickup_day = DATE '2025-01-06' AND g.zone IN (161, 162)
    THEN other.fee_cents ELSE g.fee_cents END AS reported_cents
FROM report_groups g
LEFT JOIN report_groups other ON g.grain = 'zone' AND other.grain = 'zone'
    AND g.month_start = other.month_start AND g.pickup_day = other.pickup_day
    AND g.pickup_day = DATE '2025-01-06' AND g.zone IN (161, 162)
    AND other.zone = 323 - g.zone
