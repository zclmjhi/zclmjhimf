from .google_alerts import GoogleAlertsSource
from .google_news import GoogleNewsSource

# Every source class registered here is polled by the monitoring loop.
# To add a new source: append its class to this list.
#
# GoogleNewsSource runs automatically — it derives its feed list from the
# client registry and active briefs, so no manual feed configuration is needed.
#
# GoogleAlertsSource is for manually-configured Google Alert feeds stored in
# the google_alert_feeds table. These are optional and additive.
REGISTERED_SOURCES = [
    GoogleNewsSource,
    GoogleAlertsSource,
]
