
import argparse
import csv
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


# Columns expected in the company's CSV
REQUIRED_COLUMNS = [
    "row_id", "event_id", "order_id", "event_type",
    "event_time", "received_at", "source_system", "metadata"
]

# Rules for which event can follow the current status
ALLOWED_TRANSITIONS = {
    "START": {"PLACED"},
    "PLACED": {"PAID", "CANCELLED"},
    "PAID": {"PACKED", "CANCELLED"},
    "PACKED": {"SHIPPED", "CANCELLED"},
    "SHIPPED": {"OUT_FOR_DELIVERY"},
    "OUT_FOR_DELIVERY": {"DELIVERED"},
    "DELIVERED": {"RETURN_REQUESTED"},
    "RETURN_REQUESTED": {"RETURNED"},
    "RETURNED": {"REFUNDED"},
    "CANCELLED": set(),
    "REFUNDED": set(),
}

VALID_EVENT_TYPES = set(ALLOWED_TRANSITIONS) - {"START"}

SUMMARY_FIELDS = [
    "order_id", "final_status", "valid_events", "anomaly_count",
    "first_valid_event_time", "last_valid_event_time"
]

ANOMALY_FIELDS = [
    "row_id", "order_id", "event_id", "anomaly_type", "details"
]


def clean(value):
    """Remove surrounding spaces. Treat missing values as empty strings."""
    return "" if value is None else str(value).strip()


def parse_event_time(value):
    """Accept only the three timestamp formats allowed by the assessment."""
    value = clean(value)

    if not value:
        return None

    patterns = [
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z",
        r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}",
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+00:00",
    ]

    if not any(re.fullmatch(pattern, value) for pattern in patterns):
        return None

    # Python understands +00:00, so convert the Z form first.
    candidate = value[:-1] + "+00:00" if value.endswith("Z") else value

    try:
        parsed = datetime.fromisoformat(candidate)

        # A timestamp without a timezone is treated as UTC.
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)

        return parsed.astimezone(timezone.utc)

    except (ValueError, OverflowError):
        # Examples: February 30 or an invalid hour.
        return None


def format_utc(timestamp):
    """Format a valid timestamp in the required UTC format."""
    if timestamp is None:
        return ""

    return timestamp.strftime("%Y-%m-%dT%H:%M:%SZ")


def load_rows(input_path):
    """Read the CSV and normalize the values."""
    rows = []

    with open(input_path, "r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)

        if reader.fieldnames is None:
            raise ValueError("The input CSV has no header.")

        missing = [
            column for column in REQUIRED_COLUMNS
            if column not in reader.fieldnames
        ]

        if missing:
            raise ValueError(
                "Missing required columns: " + ", ".join(missing)
            )

        for raw_row in reader:
            row = {
                column: clean(raw_row.get(column, ""))
                for column in REQUIRED_COLUMNS
            }

            row["event_type"] = row["event_type"].upper()
            rows.append(row)

    return rows


def reconstruct(rows):
    """Validate events and reconstruct each order's timeline."""

    # Normalize again so this function also works with direct test input.
    rows = [
        {key: clean(row.get(key, "")) for key in REQUIRED_COLUMNS}
        for row in rows
    ]

    for row in rows:
        row["event_type"] = row["event_type"].upper()

    # Include every nonempty order ID, even if its events are rejected.
    order_ids = sorted({
        row["order_id"] for row in rows if row["order_id"]
    })

    anomalies_by_row = {}

    def reject(row, anomaly_type, details):
        """Record one anomaly for a rejected row."""
        anomalies_by_row[row["row_id"]] = {
            "row_id": row["row_id"],
            "order_id": row["order_id"],
            "event_id": row["event_id"],
            "anomaly_type": anomaly_type,
            "details": details,
        }

    # STEP 1: Find repeated, nonempty event IDs.
    event_groups = defaultdict(list)

    for row in rows:
        if row["event_id"]:
            event_groups[row["event_id"]].append(row)

    rejected_row_ids = set()

    for event_id, group in event_groups.items():
        if len(group) < 2:
            continue

        # Lexicographically smallest row_id is the canonical row.
        group.sort(key=lambda row: row["row_id"])
        canonical = group[0]

        canonical_identity = (
            canonical["order_id"],
            canonical["event_type"],
            canonical["event_time"],
        )

        for row in group[1:]:
            rejected_row_ids.add(row["row_id"])

            identity = (
                row["order_id"],
                row["event_type"],
                row["event_time"],
            )

            if identity == canonical_identity:
                reject(
                    row,
                    "DUPLICATE_EVENT",
                    "Repeated event ID with matching event identity."
                )
            else:
                reject(
                    row,
                    "EVENT_ID_CONFLICT",
                    "Repeated event ID with differing event identity."
                )

    # STEP 2: Validate canonical rows in the required order.
    eligible_events = []

    for row in rows:
        # Duplicate/conflicting rows were already rejected.
        if row["row_id"] in rejected_row_ids:
            continue

        if not row["order_id"]:
            reject(row, "MISSING_ORDER_ID", "order_id is empty.")
            continue

        if not row["event_id"]:
            reject(row, "MISSING_EVENT_ID", "event_id is empty.")
            continue

        if not row["event_time"]:
            reject(row, "MISSING_TIMESTAMP", "event_time is empty.")
            continue

        timestamp = parse_event_time(row["event_time"])

        if timestamp is None:
            reject(
                row,
                "INVALID_TIMESTAMP",
                "event_time is not a valid supported UTC timestamp."
            )
            continue

        if row["event_type"] not in VALID_EVENT_TYPES:
            reject(
                row,
                "UNKNOWN_EVENT",
                "event_type is not in the supported vocabulary."
            )
            continue

        eligible_events.append((timestamp, row))

    # STEP 3: Sort by event time, event ID, and row ID.
    # Do not sort by CSV position or received_at.
    eligible_events.sort(
        key=lambda item: (
            item[0],
            item[1]["event_id"],
            item[1]["row_id"],
        )
    )

    events_by_order = defaultdict(list)

    for timestamp, row in eligible_events:
        events_by_order[row["order_id"]].append((timestamp, row))

    # STEP 4: Reconstruct each order's valid state transitions.
    summaries = []

    for order_id in order_ids:
        current_status = "START"
        accepted_times = []

        for timestamp, row in events_by_order[order_id]:
            event_type = row["event_type"]

            if event_type in ALLOWED_TRANSITIONS[current_status]:
                current_status = event_type
                accepted_times.append(timestamp)
            else:
                reject(
                    row,
                    "INVALID_TRANSITION",
                    f"{current_status} -> {event_type} is not allowed."
                )

        if current_status == "START":
            final_status = "UNKNOWN"
        else:
            final_status = current_status

        summaries.append({
            "order_id": order_id,
            "final_status": final_status,
            "valid_events": len(accepted_times),
            "anomaly_count": 0,
            "first_valid_event_time": (
                format_utc(accepted_times[0]) if accepted_times else ""
            ),
            "last_valid_event_time": (
                format_utc(accepted_times[-1]) if accepted_times else ""
            ),
        })

    # STEP 5: Count anomalies against their orders.
    anomaly_counts = defaultdict(int)

    for anomaly in anomalies_by_row.values():
        if anomaly["order_id"]:
            anomaly_counts[anomaly["order_id"]] += 1

    for summary in summaries:
        summary["anomaly_count"] = anomaly_counts[summary["order_id"]]

    anomalies = sorted(
        anomalies_by_row.values(),
        key=lambda anomaly: anomaly["row_id"]
    )

    return summaries, anomalies


def write_csv(path, fieldnames, rows):
    """Write a report CSV, creating its folder if necessary."""
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=fieldnames,
            lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(rows)


def run(input_path, output_dir):
    """Run the complete assessment pipeline."""
    rows = load_rows(input_path)
    summaries, anomalies = reconstruct(rows)

    output_dir = Path(output_dir)

    write_csv(
        output_dir / "order_summary.csv",
        SUMMARY_FIELDS,
        summaries
    )

    write_csv(
        output_dir / "anomalies.csv",
        ANOMALY_FIELDS,
        anomalies
    )

    return summaries, anomalies


def main():
    parser = argparse.ArgumentParser(
        description="Reconstruct order timelines from event logs."
    )

    parser.add_argument(
        "--input",
        required=True,
        help="Path to the input CSV file"
    )

    parser.add_argument(
        "--output-dir",
        required=True,
        help="Folder where output reports will be saved"
    )

    args = parser.parse_args()

    try:
        summaries, anomalies = run(args.input, args.output_dir)
    except (OSError, ValueError, csv.Error) as error:
        parser.error(str(error))

    print("Processing complete!")
    print(f"Orders summarized: {len(summaries)}")
    print(f"Anomalies reported: {len(anomalies)}")
    print(f"Output folder: {args.output_dir}")


if __name__ == "__main__":
    main()
