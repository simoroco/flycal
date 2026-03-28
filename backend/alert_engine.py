"""
FlyCal Alert Engine — evaluates price alerts after each scan.

Logic:
  - Alerts within the same logic_group must ALL be true (AND).
  - If ANY group is fully satisfied, the overall condition is met (OR between groups).
  - Cooldown is checked per alert via AlertHistory.
"""

import logging
from datetime import datetime, timedelta

from database import (
    TrackedFlight, PriceAlert, AlertHistory, PriceTracker, Airline,
)

logger = logging.getLogger("flycal.alerts")


def check_alerts(db):
    """Check all enabled alerts against latest prices. Called after each scan."""

    tracks = db.query(TrackedFlight).all()
    if not tracks:
        return

    for track in tracks:
        alerts = (
            db.query(PriceAlert)
            .filter(PriceAlert.pinned_flight_id == track.id, PriceAlert.enabled == True)
            .all()
        )
        if not alerts:
            continue

        # Fetch recent price entries for this flight
        prices = (
            db.query(PriceTracker)
            .filter(
                PriceTracker.airline_id == track.airline_id,
                PriceTracker.direction == track.direction,
                PriceTracker.flight_date == track.flight_date,
                PriceTracker.departure_time == track.departure_time,
                PriceTracker.origin_airport == track.origin_airport,
                PriceTracker.destination_airport == track.destination_airport,
            )
            .order_by(PriceTracker.recorded_at.desc())
            .limit(10)
            .all()
        )

        if not prices:
            continue

        latest_price = prices[0].price
        previous_price = prices[1].price if len(prices) >= 2 else None

        # Get oldest for percent threshold
        oldest_price = prices[-1].price if prices else latest_price

        # Evaluate each alert
        alert_results = {}  # alert_id -> True/False
        for alert in alerts:
            alert_results[alert.id] = _evaluate_alert(
                alert, latest_price, previous_price, oldest_price, prices
            )

        # Group by logic_group: AND within group, OR between groups
        groups = {}
        for alert in alerts:
            g = alert.logic_group
            if g not in groups:
                groups[g] = []
            groups[g].append(alert)

        any_group_satisfied = False
        satisfied_alerts = []

        for group_id, group_alerts in groups.items():
            group_ok = all(alert_results.get(a.id, False) for a in group_alerts)
            if group_ok:
                any_group_satisfied = True
                satisfied_alerts.extend(group_alerts)

        if not any_group_satisfied:
            continue

        # Check cooldown for each satisfied alert and filter
        alerts_to_fire = []
        for alert in satisfied_alerts:
            if _cooldown_allows(alert, db):
                alerts_to_fire.append(alert)

        if not alerts_to_fire:
            continue

        # Record in history
        for alert in alerts_to_fire:
            db.add(AlertHistory(
                price_alert_id=alert.id,
                price_at_trigger=latest_price,
                message=_describe_alert(alert),
            ))
            # Disable once_only alerts
            if alert.cooldown == "once_only":
                alert.enabled = False

        db.commit()

        # Send email
        try:
            airline = db.query(Airline).filter(Airline.id == track.airline_id).first()
            from email_service import send_alert_email
            send_alert_email(
                pin=track,
                airline=airline,
                alerts_triggered=alerts_to_fire,
                current_price=latest_price,
                previous_price=previous_price,
            )
        except Exception as e:
            logger.error(f"Alert email failed for track {track.id}: {e}")


def _evaluate_alert(alert, latest, previous, oldest, prices):
    """Evaluate a single alert against price data."""

    if alert.alert_type == "threshold":
        compare_price = latest
        threshold = alert.value
        if alert.value_is_percent and oldest:
            # Value is a percentage change from oldest
            change_pct = abs(latest - oldest) / oldest * 100
            compare_price = change_pct
            threshold = alert.value

        if alert.operator == "lt":
            return compare_price < threshold
        elif alert.operator == "gt":
            return compare_price > threshold
        return False

    elif alert.alert_type == "variation":
        if previous is None:
            return False
        if previous == 0:
            return False
        change_pct = abs(latest - previous) / previous * 100
        return change_pct > (alert.value or 0)

    elif alert.alert_type == "trend_start":
        if len(prices) < 2:
            return False
        # Check last 2+ consecutive prices for trend
        recent = [p.price for p in reversed(prices[:3])]  # oldest first
        if len(recent) < 2:
            return False

        if alert.operator == "decrease":
            return all(recent[i] > recent[i + 1] for i in range(len(recent) - 1))
        elif alert.operator == "increase":
            return all(recent[i] < recent[i + 1] for i in range(len(recent) - 1))
        return False

    return False


def _cooldown_allows(alert, db):
    """Check if cooldown period has elapsed since last trigger."""

    last_trigger = (
        db.query(AlertHistory)
        .filter(AlertHistory.price_alert_id == alert.id)
        .order_by(AlertHistory.triggered_at.desc())
        .first()
    )

    if not last_trigger:
        return True  # Never triggered

    if alert.cooldown == "once_only":
        return False  # Already triggered once

    if alert.cooldown == "every_scan":
        return True

    now = datetime.utcnow()
    if alert.cooldown == "once_per_day":
        return (now - last_trigger.triggered_at) > timedelta(days=1)

    if alert.cooldown == "once_per_week":
        return (now - last_trigger.triggered_at) > timedelta(weeks=1)

    return True


def _describe_alert(alert):
    """Human-readable description of an alert."""
    if alert.alert_type == "threshold":
        op = "<" if alert.operator == "lt" else ">"
        unit = "%" if alert.value_is_percent else "€"
        return f"Price {op} {alert.value}{unit}"
    elif alert.alert_type == "variation":
        return f"Price changed by >{alert.value}%"
    elif alert.alert_type == "trend_start":
        direction = "decreasing" if alert.operator == "decrease" else "increasing"
        return f"Price started {direction}"
    return str(alert.alert_type)
