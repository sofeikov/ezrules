"""Analytics utilities for time-based data aggregation.

This module provides shared configuration and helper functions for analytics endpoints
that aggregate data over different time periods (1h, 6h, 12h, 24h, 30d).
"""

import datetime

import sqlalchemy

# Shared aggregation configuration for analytics endpoints
AGGREGATION_CONFIG = {
    "1h": {
        "delta": datetime.timedelta(hours=1),
        "bucket_seconds": 300,  # 5 minutes
        "label_format": "%H:%M",
        "use_date_trunc": False,
    },
    "6h": {
        "delta": datetime.timedelta(hours=6),
        "bucket_seconds": 1800,  # 30 minutes
        "label_format": "%m-%d %H:%M",
        "use_date_trunc": False,
    },
    "12h": {
        "delta": datetime.timedelta(hours=12),
        "bucket_seconds": 3600,  # 1 hour
        "label_format": "%m-%d %H:%M",
        "use_date_trunc": False,
    },
    "24h": {
        "delta": datetime.timedelta(hours=24),
        "bucket_seconds": 7200,  # 2 hours
        "label_format": "%m-%d %H:%M",
        "use_date_trunc": False,
    },
    "30d": {
        "delta": datetime.timedelta(days=30),
        "bucket_seconds": None,  # Uses date_trunc instead
        "label_format": "%Y-%m-%d",
        "use_date_trunc": True,
    },
}


def get_bucket_expression(config, timestamp_column):
    """Generate SQLAlchemy bucket expression for time-based aggregation.

    For most time periods, this uses epoch-based bucketing with fixed-size buckets.
    For day-level aggregation (30d), it uses PostgreSQL's date_trunc for cleaner
    calendar-aligned buckets.

    Args:
        config: Configuration dict with 'use_date_trunc' and 'bucket_seconds' keys
        timestamp_column: SQLAlchemy column to bucket (e.g., TestingRecordLog.created_at)

    Returns:
        SQLAlchemy expression for time bucketing that can be used in queries

    Example:
        >>> config = AGGREGATION_CONFIG["1h"]
        >>> bucket_expr = get_bucket_expression(config, TestingRecordLog.created_at)
        >>> query = db_session.query(bucket_expr.label("bucket"), func.count(...))
    """
    if config["use_date_trunc"]:
        # Use PostgreSQL's date_trunc for day-level aggregation
        return sqlalchemy.func.date_trunc("day", timestamp_column)
    else:
        # Use epoch-based bucketing for sub-day intervals
        return sqlalchemy.cast(
            sqlalchemy.func.floor(sqlalchemy.func.extract("epoch", timestamp_column) / config["bucket_seconds"])
            * config["bucket_seconds"],
            sqlalchemy.Integer,
        )
