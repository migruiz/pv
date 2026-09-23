"""FCM push notifications via topics.

All devices subscribe to the "auto_discharge" topic. The API sends to
the topic — no token storage or registration needed.
"""

import logging
from pathlib import Path

logger = logging.getLogger("pv.notifications")

LOCAL_SA_KEY = Path(__file__).parent / "firebase-sa.json"
DOCKER_SA_KEY = Path("/data/firebase-sa.json")
TOPIC = "auto_discharge"

_initialized = False


def init_firebase():
    """Initialize Firebase Admin SDK. Call once at startup."""
    global _initialized
    if _initialized:
        return

    sa_path = LOCAL_SA_KEY if LOCAL_SA_KEY.exists() else DOCKER_SA_KEY
    if not sa_path.exists():
        logger.warning("Firebase SA key not found — push notifications disabled")
        return

    try:
        import firebase_admin
        from firebase_admin import credentials

        cred = credentials.Certificate(str(sa_path))
        # A push must finish or fail within seconds: the controller sends them one at a time, in order
        firebase_admin.initialize_app(cred, {"httpTimeout": 10})
        _initialized = True
        logger.info("Firebase Admin SDK initialized")
    except Exception as exc:
        logger.error("Firebase init failed: %s", exc)


def _send(data: dict[str, str]):
    """Send a data-only message to the auto_discharge topic."""
    if not _initialized:
        logger.debug("Firebase not initialized, skipping notification")
        return

    from firebase_admin import messaging

    message = messaging.Message(
        data=data,
        topic=TOPIC,
        android=messaging.AndroidConfig(priority="high"),
    )

    try:
        message_id = messaging.send(message)
        logger.info("FCM sent to topic %s: %s", TOPIC, message_id)
    except Exception as exc:
        logger.error("FCM send failed: %s", exc)


def notify_discharge_started(
    soc: float, power_kw: float, minutes_remaining: float, window_name: str | None = None,
):
    _send({
        "type": "auto_discharge_active",
        "soc": f"{soc:.1f}",
        "power_kw": f"{power_kw:.3f}",
        "minutes_remaining": f"{minutes_remaining:.0f}",
        "window_name": window_name or "",
    })


def notify_discharge_update(
    soc: float, power_kw: float, minutes_remaining: float, window_name: str | None = None,
):
    _send({
        "type": "auto_discharge_update",
        "soc": f"{soc:.1f}",
        "power_kw": f"{power_kw:.3f}",
        "minutes_remaining": f"{minutes_remaining:.0f}",
        "window_name": window_name or "",
    })


def notify_discharge_stopped(reason: str, window_name: str | None = None):
    _send({
        "type": "auto_discharge_stopped",
        "reason": reason,
        "window_name": window_name or "",
    })

