WITH pickups AS (
    {inputs}
), report_groups AS (
    SELECT
        CASE WHEN GROUPING(pickup_day) = 1 THEN 'month'
             WHEN GROUPING(zone) = 1 THEN 'day'
             ELSE 'zone' END AS grain,
        month_start,
        pickup_day,
        zone,
        COUNT(*) AS trips,
        COUNT(cents) AS present_fees,
        SUM(CASE WHEN has_fee = 1 AND cents IS NULL THEN 1 ELSE 0 END) AS null_fees,
        SUM(CASE WHEN cents < 0 THEN 1 ELSE 0 END) AS negative_fees,
        SUM(cents) AS fee_cents,
        SUM(clock_seconds) AS pickup_clock_sum,
        SUM(MOD(clock_seconds, 100003) * (COALESCE(zone, -1) + 3)
            * (MOD(COALESCE(cents, 7919), 997) + 1000)) AS projected_sum,
        MIN(clock_seconds) AS first_pickup,
        MAX(clock_seconds) AS last_pickup,
        MAX(input_id) AS input_id,
        MAX(has_fee) AS has_fee
    FROM pickups
    GROUP BY GROUPING SETS (
        (month_start), (month_start, pickup_day), (month_start, pickup_day, zone)
    )
)
{result}
