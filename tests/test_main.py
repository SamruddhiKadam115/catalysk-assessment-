
import unittest

from main import reconstruct, REQUIRED_COLUMNS


def make_event(
    row_id,
    event_id,
    order_id,
    event_type,
    event_time="2026-01-01T10:00:00Z",
):
    """Create a test event using the expected input CSV schema."""
    return {
        "row_id": row_id,
        "event_id": event_id,
        "order_id": order_id,
        "event_type": event_type,
        "event_time": event_time,
        "received_at": "2026-01-01T10:01:00Z",
        "source_system": "test",
        "metadata": "",
    }


class TestTimelineReconstruction(unittest.TestCase):

    def test_duplicate_event_is_rejected(self):
        """Repeated identical event IDs should count as duplicates."""
        rows = [
            make_event("R001", "E001", "O100", "PLACED"),
            make_event("R002", "E001", "O100", "PLACED"),
        ]

        summaries, anomalies = reconstruct(rows)

        self.assertEqual(len(anomalies), 1)
        self.assertEqual(anomalies[0]["anomaly_type"], "DUPLICATE_EVENT")
        self.assertEqual(anomalies[0]["row_id"], "R002")
        self.assertEqual(summaries[0]["valid_events"], 1)

    def test_events_are_sorted_by_event_time(self):
        """Earlier events must be processed before later events."""
        rows = [
            make_event(
                "R002", "E002", "O100", "PAID",
                "2026-01-01T10:05:00Z",
            ),
            make_event(
                "R001", "E001", "O100", "PLACED",
                "2026-01-01T10:00:00Z",
            ),
        ]

        summaries, anomalies = reconstruct(rows)

        self.assertEqual(summaries[0]["final_status"], "PAID")
        self.assertEqual(summaries[0]["valid_events"], 2)
        self.assertEqual(len(anomalies), 0)

    def test_invalid_transition_does_not_change_status(self):
        """SHIPPED cannot follow PLACED directly."""
        rows = [
            make_event("R001", "E001", "O100", "PLACED"),
            make_event(
                "R002", "E002", "O100", "SHIPPED",
                "2026-01-01T10:05:00Z",
            ),
        ]

        summaries, anomalies = reconstruct(rows)

        self.assertEqual(summaries[0]["final_status"], "PLACED")
        self.assertEqual(summaries[0]["valid_events"], 1)
        self.assertEqual(len(anomalies), 1)
        self.assertEqual(anomalies[0]["anomaly_type"], "INVALID_TRANSITION")

    def test_missing_and_unknown_values(self):
        """Missing fields and unsupported event types are reported."""
        rows = [
            make_event("R001", "E001", "O100", "PLACED", ""),
            make_event("R002", "E002", "O101", "ALIEN"),
            make_event("R003", "E003", "", "PLACED"),
            make_event("R004", "", "O103", "PLACED"),
        ]

        summaries, anomalies = reconstruct(rows)

        anomaly_types = {
            anomaly["anomaly_type"] for anomaly in anomalies
        }

        self.assertIn("MISSING_TIMESTAMP", anomaly_types)
        self.assertIn("UNKNOWN_EVENT", anomaly_types)
        self.assertIn("MISSING_ORDER_ID", anomaly_types)
        self.assertIn("MISSING_EVENT_ID", anomaly_types)

        # Orders with IDs are summarized even if their events are rejected.
        self.assertEqual(len(summaries), 3)

    def test_conflicting_event_id_is_rejected(self):
        """Reusing an event ID for a different order is a conflict."""
        rows = [
            make_event("R001", "E001", "O100", "PLACED"),
            make_event("R002", "E001", "O200", "PLACED"),
        ]

        summaries, anomalies = reconstruct(rows)

        self.assertEqual(len(anomalies), 1)
        self.assertEqual(anomalies[0]["anomaly_type"], "EVENT_ID_CONFLICT")
        self.assertEqual(anomalies[0]["row_id"], "R002")
        self.assertEqual(summaries[0]["valid_events"], 1)

    def test_equal_timestamps_are_deterministic(self):
        """Ties are resolved by event ID, not input row order."""
        rows = [
            make_event("R002", "E002", "O100", "PAID"),
            make_event("R001", "E001", "O100", "PLACED"),
        ]

        summaries_a, anomalies_a = reconstruct(rows)
        summaries_b, anomalies_b = reconstruct(list(reversed(rows)))

        self.assertEqual(summaries_a, summaries_b)
        self.assertEqual(anomalies_a, anomalies_b)
        self.assertEqual(summaries_a[0]["final_status"], "PAID")
        self.assertEqual(summaries_a[0]["valid_events"], 2)

    def test_every_test_event_has_required_columns(self):
        """The test helper matches the application's expected schema."""
        event = make_event("R001", "E001", "O100", "PLACED")

        self.assertEqual(set(event.keys()), set(REQUIRED_COLUMNS))


if __name__ == "__main__":
    unittest.main()
