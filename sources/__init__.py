from .google_alerts import GoogleAlertsSource

# Every source class registered here is polled by the monitoring loop.
# To add a new source: append its class to this list.
REGISTERED_SOURCES = [
    GoogleAlertsSource,
]
