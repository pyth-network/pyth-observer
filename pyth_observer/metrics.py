import time
from contextlib import contextmanager
from typing import Any, Dict, Optional

from prometheus_client import (
    REGISTRY,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    Info,
)
from pythclient.pythaccounts import PythPriceStatus

from pyth_observer.check.price_feed import PriceFeedState


class PythObserverMetrics:
    def __init__(self, registry: CollectorRegistry = REGISTRY):
        self.registry = registry

        self.observer_info = Info(
            "pyth_observer_info",
            "Information about the Pyth Observer instance",
            registry=registry,
        )

        self.check_execution_duration = Histogram(
            "pyth_observer_check_execution_duration_seconds",
            "Time spent executing checks",
            ["check_type"],
            buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0],
            registry=registry,
        )

        self.loop_errors_total = Counter(
            "pyth_observer_loop_errors_total",
            "Total number of errors in observation loop",
            ["error_type"],
            registry=registry,
        )

        self.price_feeds_processed = Gauge(
            "pyth_observer_price_feeds_processed_total",
            "Total number of price feeds processed in last cycle",
            registry=registry,
        )

        self.price_feed_status = Gauge(
            "pyth_observer_price_feed_status",
            "Status of price feeds (1=trading, 0=not trading)",
            ["symbol", "asset_type"],
            registry=registry,
        )

        self.price_feed_staleness = Gauge(
            "pyth_observer_price_feed_staleness_slots",
            "Number of slots since last price update",
            ["symbol", "asset_type"],
            registry=registry,
        )

        self.price_feed_confidence_interval = Gauge(
            "pyth_observer_price_feed_confidence_interval",
            "Price feed confidence interval",
            ["symbol", "asset_type"],
            registry=registry,
        )

        self.check_success_rate = Gauge(
            "pyth_observer_check_success_rate",
            "Success rate of checks (0-1)",
            ["check_type", "symbol"],
            registry=registry,
        )

        self.price_deviation_from_coingecko = Gauge(
            "pyth_observer_price_deviation_from_coingecko_percent",
            "Price deviation from CoinGecko as percentage",
            ["symbol"],
            registry=registry,
        )

        self.coingecko_price_age = Gauge(
            "pyth_observer_coingecko_price_age_seconds",
            "Age of CoinGecko price data in seconds",
            ["symbol"],
            registry=registry,
        )

        self.publishers_active = Gauge(
            "pyth_observer_publishers_active_total",
            "Number of active publishers for a symbol",
            ["symbol", "asset_type"],
            registry=registry,
        )

        self.alerts_active = Gauge(
            "pyth_observer_alerts_active_total",
            "Number of currently active alerts",
            ["alert_type"],
            registry=registry,
        )

        self.alerts_sent_total = Counter(
            "pyth_observer_alerts_sent_total",
            "Total number of alerts sent",
            ["alert_type", "channel"],
            registry=registry,
        )

        self.api_request_duration = Histogram(
            "pyth_observer_api_request_duration_seconds",
            "Duration of external API requests",
            ["service", "endpoint"],
            buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0],
            registry=registry,
        )

        self.api_request_total = Counter(
            "pyth_observer_api_requests_total",
            "Total number of API requests",
            ["service", "endpoint", "status"],
            registry=registry,
        )

        self.api_rate_limit_hits = Counter(
            "pyth_observer_api_rate_limit_hits_total",
            "Number of times rate limits were hit",
            ["service"],
            registry=registry,
        )

        self.crosschain_price_age = Gauge(
            "pyth_observer_crosschain_price_age_seconds",
            "Age of cross-chain price data in seconds",
            ["symbol"],
            registry=registry,
        )

        self.latest_block_slot = Gauge(
            "pyth_observer_latest_block_slot",
            "Latest Solana block slot observed",
            registry=registry,
        )

        self.network_connection_status = Gauge(
            "pyth_observer_network_connection_status",
            "Network connection status (1=connected, 0=disconnected)",
            ["network", "endpoint_type"],
            registry=registry,
        )

    def set_observer_info(self, network: str, config: Dict[str, Any]):
        """Set static information about the observer instance."""
        self.observer_info.info(
            {
                "network": network,
                "checks_enabled": str(
                    len(
                        [
                            c
                            for c in config.get("checks", {}).get("global", {})
                            if config["checks"]["global"][c].get("enable", False)
                        ]
                    )
                ),
                "event_handlers": ",".join(config.get("events", [])),
            }
        )

    @contextmanager
    def time_operation(self, metric: Histogram, **labels):
        start_time = time.time()
        try:
            yield
        finally:
            duration = time.time() - start_time
            metric.labels(**labels).observe(duration)

    def update_price_feed_metrics(self, state: PriceFeedState) -> None:
        labels = {"symbol": state.symbol, "asset_type": state.asset_type}

        status_value = 1 if state.status == PythPriceStatus.TRADING else 0
        self.price_feed_status.labels(**labels).set(status_value)

        staleness = state.latest_block_slot - state.latest_trading_slot
        self.price_feed_staleness.labels(**labels).set(staleness)

        self.price_feed_confidence_interval.labels(**labels).set(
            state.confidence_interval_aggregate
        )

        if state.coingecko_price:
            deviation = (
                abs(state.price_aggregate - state.coingecko_price)
                / state.coingecko_price
                * 100
            )
            self.price_deviation_from_coingecko.labels(symbol=state.symbol).set(
                deviation
            )

            if state.coingecko_update:
                age = time.time() - state.coingecko_update
                self.coingecko_price_age.labels(symbol=state.symbol).set(age)

        if state.crosschain_price and state.crosschain_price.get("publish_time"):
            age = (
                state.crosschain_price["snapshot_time"]
                - state.crosschain_price["publish_time"]
            )
            self.crosschain_price_age.labels(symbol=state.symbol).set(age)

        self.latest_block_slot.set(state.latest_block_slot)

    def record_api_request(
        self,
        service: str,
        endpoint: str,
        duration: float,
        status_code: int,
        rate_limited: bool = False,
    ):
        status = "success" if 200 <= status_code < 300 else "error"

        self.api_request_duration.labels(service=service, endpoint=endpoint).observe(
            duration
        )
        self.api_request_total.labels(
            service=service, endpoint=endpoint, status=status
        ).inc()

        if rate_limited:
            self.api_rate_limit_hits.labels(service=service).inc()

    def update_alert_metrics(
        self, active_alerts: Dict[str, Any], sent_alert: Optional[str] = None
    ):
        alert_counts = {}
        for alert_id, alert_info in active_alerts.items():
            alert_type = alert_info.get("type", "unknown")
            alert_counts[alert_type] = alert_counts.get(alert_type, 0) + 1

        for alert_type, count in alert_counts.items():
            self.alerts_active.labels(alert_type=alert_type).set(count)

        if sent_alert:
            alert_type = sent_alert.split("-")[0]
            self.alerts_sent_total.labels(
                alert_type=alert_type, channel="configured"
            ).inc()

    def set_network_status(self, network: str, endpoint_type: str, connected: bool):
        status = 1 if connected else 0
        self.network_connection_status.labels(
            network=network, endpoint_type=endpoint_type
        ).set(status)


metrics = PythObserverMetrics()
