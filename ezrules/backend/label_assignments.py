"""Canonical event-version label assignment helpers."""

from __future__ import annotations

import datetime
from typing import Any

from ezrules.models.backend_core import EvaluationDecision, EventVersion, EventVersionLabel, Label


def get_labelable_event_version(
    db: Any,
    *,
    o_id: int,
    event_id: str,
    event_version: int | None = None,
) -> EventVersion | None:
    """Return the canonical event version to label.

    When no version is specified, the latest served decision for the business
    event is labeled. That keeps CSV uploads ergonomic while still attaching
    labels to an explicit event version.
    """
    query = (
        db.query(EventVersion)
        .join(EvaluationDecision, EvaluationDecision.ev_id == EventVersion.ev_id)
        .filter(
            EventVersion.o_id == o_id,
            EventVersion.event_id == event_id,
            EvaluationDecision.o_id == o_id,
            EvaluationDecision.served.is_(True),
            EvaluationDecision.decision_type == "served",
        )
    )
    if event_version is not None:
        query = query.filter(EventVersion.event_version == event_version)
    else:
        query = query.order_by(EventVersion.event_version.desc(), EventVersion.ev_id.desc())
    return query.first()


def assign_event_version_label(
    db: Any,
    *,
    o_id: int,
    event_version: EventVersion,
    label: Label,
    assigned_by: str | None,
) -> EventVersionLabel:
    assignment = (
        db.query(EventVersionLabel)
        .filter(EventVersionLabel.o_id == o_id, EventVersionLabel.ev_id == event_version.ev_id)
        .first()
    )
    if assignment is None:
        assignment = EventVersionLabel(
            o_id=o_id,
            ev_id=int(event_version.ev_id),
            el_id=int(label.el_id),
            assigned_by=assigned_by,
        )
        db.add(assignment)
    else:
        assignment.el_id = int(label.el_id)
        assignment.assigned_by = assigned_by
        assignment.assigned_at = datetime.datetime.now(datetime.UTC)
    return assignment
