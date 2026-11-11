SELECT g.*, CASE
    WHEN g.grain IN ('day', 'zone') AND g.pickup_day = DATE '2025-01-06'
        THEN CASE WHEN g.fee_cents IS NULL THEN NULL ELSE 0 END
    WHEN (g.grain = 'day' OR (g.grain = 'zone' AND g.zone = 161))
        AND g.pickup_day = DATE '2025-01-07' THEN g.fee_cents + moved.fee_cents
    ELSE g.fee_cents END AS reported_cents
FROM report_groups g
LEFT JOIN report_groups moved ON moved.grain = 'day' AND moved.pickup_day = DATE '2025-01-06'
    AND g.month_start = moved.month_start
