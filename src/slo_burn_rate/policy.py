"""Default alert policy as data.

Source: Google SRE Workbook, chapter 5 "Alerting on SLOs", approach 6, Multiwindow,
Multi-Burn-Rate Alerts. Checked 2026-11-05.

* 2% of a 30-day budget consumed in 1 hour is a burn rate of 14.4 (page).
* 5% of a 30-day budget consumed in 6 hours is a burn rate of 6 (page).
* 10% of a 30-day budget consumed in 3 days is a burn rate of 1 (ticket).

The short window is 1/12 of the long window.
"""

from __future__ import annotations

from datetime import timedelta

from .models import AlertRule

DEFAULT_POLICY: tuple[AlertRule, ...] = (
    AlertRule("page-fast", 14.4, timedelta(hours=1), timedelta(minutes=5), "page"),
    AlertRule("page-slow", 6.0, timedelta(hours=6), timedelta(minutes=30), "page"),
    AlertRule("ticket", 1.0, timedelta(days=3), timedelta(hours=6), "ticket"),
)
