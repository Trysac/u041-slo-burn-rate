"""SLO error budget math and multi-window, multi-burn-rate alert evaluation."""

from __future__ import annotations

import logging

from .core import burn_rate, evaluate
from .errors import SLOError
from .models import SLO, AlertResult, AlertRule, Evaluation, Sample
from .policy import DEFAULT_POLICY

logging.getLogger(__name__).addHandler(logging.NullHandler())

__all__ = [
    "DEFAULT_POLICY",
    "SLO",
    "AlertResult",
    "AlertRule",
    "Evaluation",
    "SLOError",
    "Sample",
    "__version__",
    "burn_rate",
    "evaluate",
]

__version__ = "0.1.0"
