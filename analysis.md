# Event Timeline Reconstruction — Analysis

## Results

The application was run on the complete supplied main dataset.

- **Total orders:** [Fill from `order_summary.csv`]
- **Input events:** [Count data rows in the original CSV, excluding the header]
- **Accepted events:** [Sum the `valid_events` column]
- **Reported anomalies:** [Count data rows in `anomalies.csv`, excluding the header]

## Interesting Edge Cases

1. **Duplicate and conflicting event IDs:** Repeated event IDs are resolved using the lexicographically smallest `row_id` as the canonical record. Other records are classified based on whether their event identity matches.
2. **Out-of-order events:** Events are processed by event timestamp rather than CSV row order. Invalid transitions are rejected without changing the order's current state.
3. **Invalid or missing data:** Missing identifiers, unsupported timestamps, and unknown event types are reported as anomalies instead of crashing the application.

*Verify which of these cases actually occur in the supplied dataset before describing them as observed findings.*

## Engineering Tradeoff

The implementation prioritizes deterministic processing, clear validation rules, and auditability. Keeping records in memory and sorting them simplifies timeline reconstruction and reproducibility, but increases memory usage for large datasets. A streaming or external-sorting approach could improve scalability at the cost of additional complexity.
