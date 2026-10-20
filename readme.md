# Event Timeline Reconstruction Engine

## Overview

A Python command-line tool that validates order event records, reconstructs order timelines, and generates reports summarizing order statuses and data anomalies.

Events are processed using their event timestamps, not CSV row order or received timestamps.

## Requirements

- Python 3.10+
- No external dependencies required.

## Setup

Clone the repository and enter the project directory:

```bash
git clone YOUR_GITHUB_REPOSITORY_URL
cd "catalysk assessment"
```

Keep the supplied main dataset in `data/` locally. The large original CSV is not included in the repository.

## Run the Application

Process the complete supplied dataset:

```bash
python main.py --input data/order_events.csv --output-dir output
```

For testing with the sample CSV:

```bash
python main.py --input test_data/test_events.csv --output-dir test_data/output
```

Update the input path if your dataset has a different filename.

## Run Unit Tests

```bash
python -m unittest discover -s tests -v
```

The tests should cover duplicate events, timestamp ordering, invalid transitions, missing or unknown values, and deterministic results.

## Output Files

### `output/order_summary.csv`

One row per order, containing:

- `order_id`: Order identifier.
- `final_status`: Last accepted status, or `UNKNOWN` if no event was accepted.
- `valid_events`: Number of accepted state transitions.
- `anomaly_count`: Number of anomalies associated with the order.
- `first_valid_event_time`: First accepted event timestamp.
- `last_valid_event_time`: Last accepted event timestamp.

### `output/anomalies.csv`

Contains rejected or problematic records, including their row ID, order ID, event ID, anomaly type, and details.

Supported anomaly types:

`DUPLICATE_EVENT`, `EVENT_ID_CONFLICT`, `MISSING_ORDER_ID`, `MISSING_EVENT_ID`, `MISSING_TIMESTAMP`, `INVALID_TIMESTAMP`, `UNKNOWN_EVENT`, `INVALID_TRANSITION`.

## Design Decisions

1. **Normalization:** Trim whitespace and convert event types to uppercase. IDs remain case-sensitive.
2. **Duplicate detection:** For repeated nonempty event IDs, select the lexicographically smallest `row_id` as canonical. Classify the other records as duplicates or conflicts.
3. **Timestamp validation:** Accept only the specified formats and normalize valid timestamps to UTC.
4. **Event ordering:** Sort eligible events by `(event_time, event_id, row_id)` to ensure deterministic tie-breaking.
5. **State validation:** Apply predefined order lifecycle transitions. Reject invalid transitions without changing the current status.
6. **Reproducibility:** Sort summary records by `order_id` and anomaly records by `row_id`.

## Complexity Considerations

Let `n` be the number of input records and `k` the number of eligible events.

- **Time:** Approximately `O(n log n)` because events are grouped and sorted.
- **Space:** `O(n)` because input records, intermediate structures, summaries, and anomalies are stored in memory.

This approach favors clarity, auditability, and deterministic results over minimum memory usage.

## Limitations

- Only supported event types, timestamp formats, and state transitions are accepted.
- Invalid records are reported rather than automatically repaired.
- The implementation stores records in memory, which may limit scalability for very large datasets.
- Missing events and order states are never invented.
