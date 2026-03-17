"""Tests for reset-dev CSV export defaults."""

import csv
from pathlib import Path

from ezrules import cli as cli_module


def test_default_reset_dev_labels_csv_path_points_to_repo_root():
    expected_path = Path(cli_module.__file__).resolve().parent.parent / "test_labels.csv"

    assert cli_module.DEFAULT_RESET_DEV_LABELS_CSV_PATH == expected_path


def test_export_labels_to_csv_writes_event_label_rows(tmp_path):
    output_path = tmp_path / "labels.csv"

    cli_module._export_labels_to_csv(
        [
            ("TestEvent_0001", "FRAUD"),
            ("TestEvent_0002", "CHARGEBACK"),
        ],
        str(output_path),
    )

    with output_path.open(newline="") as handle:
        rows = list(csv.reader(handle))

    assert rows == [
        ["TestEvent_0001", "FRAUD"],
        ["TestEvent_0002", "CHARGEBACK"],
    ]


def test_invoke_reset_dev_generation_exports_root_csv_path():
    invocations: list[tuple[object, dict]] = []

    class DummyContext:
        def invoke(self, command, **kwargs):
            invocations.append((command, kwargs))

    cli_module._invoke_reset_dev_generation(DummyContext(), n_rules=7, n_events=15)

    assert invocations == [
        (
            cli_module.generate_random_data,
            {
                "n_rules": 7,
                "n_events": 15,
                "label_ratio": 0.3,
                "export_csv": str(cli_module.DEFAULT_RESET_DEV_LABELS_CSV_PATH),
            },
        )
    ]
