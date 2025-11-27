"""
Utility functions for alert identification and management.
"""

from pyth_observer.check import Check
from pyth_observer.check.publisher import PublisherState


def generate_alert_identifier(check: Check) -> str:
    """
    Generate a unique alert identifier for a check.
    This is a shared function to ensure consistency across the codebase.
    """
    alert_identifier = f"{check.__class__.__name__}-{check.state().symbol}"
    state = check.state()
    if isinstance(state, PublisherState):
        alert_identifier += f"-{state.publisher_name}"
    return alert_identifier
