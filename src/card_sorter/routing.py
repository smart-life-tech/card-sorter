from typing import Dict, Set

from .models import AppConfig, CardRecognitionResult, RoutingDecision


class Router:
    def __init__(self, config: AppConfig, disabled_bins: Set[str] | None = None) -> None:
        self.config = config
        self.disabled_bins = disabled_bins or set()

    def route(self, card: CardRecognitionResult, price_usd: float | None, mode: str | None = None) -> RoutingDecision:
        mode = mode or self.config.mode
        flags = []

        # Disabled bins route
        disabled_route = self.config.routing_rules.get("disabled_bin_route", "combined_bin")

        # Handle disabled bin for price bin specifically
        price_bin_name = "price_bin"
        if price_bin_name in self.disabled_bins:
            price_bin_name = disabled_route
            flags.append("price_bin_disabled")

        combined_bin_name = "combined_bin"
        if combined_bin_name in self.disabled_bins:
            # If combined is disabled, fall back to price bin to avoid dead-end
            combined_bin_name = price_bin_name
            flags.append("combined_bin_disabled")

        # Low-confidence routing
        low_conf_route = self.config.routing_rules.get("low_confidence_route", combined_bin_name)
        if card.confidence < 0.5:
            return RoutingDecision(bin_name=low_conf_route, reason="low_confidence", flags=flags + ["low_confidence"])

        # Unrecognized routing
        if not card.name:
            route = self.config.routing_rules.get("unrecognized_route", combined_bin_name)
            return RoutingDecision(bin_name=route, reason="unrecognized", flags=flags + ["unrecognized"])

        # Mode-specific routing
        if mode == "price":
            if price_usd is None:
                route = self.config.routing_rules.get("unpriced_route", combined_bin_name)
                return RoutingDecision(bin_name=route, reason="unpriced", flags=flags + ["unpriced"])
            if price_usd >= self.config.price_threshold_usd:
                return RoutingDecision(bin_name=price_bin_name, reason="price_above_threshold", flags=flags)
            return RoutingDecision(bin_name=combined_bin_name, reason="price_below_threshold", flags=flags)

        # Color routing (use color identity when available)
        if mode == "color":
            return RoutingDecision(bin_name=self._route_color(card), reason="color_mode", flags=flags)

        # Mixed: high price overrides; else color
        if mode == "mixed":
            if price_usd is not None and price_usd >= self.config.price_threshold_usd:
                return RoutingDecision(bin_name=price_bin_name, reason="price_above_threshold", flags=flags)
            return RoutingDecision(bin_name=self._route_color(card), reason="color_mode", flags=flags)

        # Default fallback
        return RoutingDecision(bin_name=combined_bin_name, reason="default", flags=flags + ["fallback"])

    def _route_color(self, card: CardRecognitionResult) -> str:
        identity = card.color_identity or []
        if len(identity) != 1:
            return "combined_bin"
        single = identity[0]
        if single == "W" or single == "U":
            return "white_blue_bin"
        if single == "B":
            return "black_bin"
        if single == "R":
            return "red_bin"
        if single == "G":
            return "green_bin"
        return "combined_bin"
