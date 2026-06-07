from dataclasses import dataclass
from datetime import date
from typing import Optional, Callable


@dataclass
class TrendAnalysisDto:
    asset_id: str


class ChatService:
    """Chat-facing helper that can summarize analytics results for humans.

    The service accepts either a direct `analytics_service` (callable
    `analyze_asset(asset_id, start, end)`) or a `tool_runner` callable that
    accepts `(tool_name, params)` and returns tool outputs. This keeps the
    service testable and decoupled from the data layer.
    """

    def __init__(self, common_service=None, analytics_service=None, tool_runner: Optional[Callable] = None):
        self.common_service = common_service
        self.analytics_service = analytics_service
        self.tool_runner = tool_runner

    def analyze_asset_performance(self, asset_id: str, start_date_str: str, end_date_str: str) -> Optional[TrendAnalysisDto]:
        start = date.fromisoformat(start_date_str)
        end = date.fromisoformat(end_date_str)
        if self.analytics_service:
            return self.analytics_service.analyze_asset(asset_id, start, end)
        # If no analytics service, try tool runner
        if self.tool_runner:
            resp = self.tool_runner("get_asset_analytics", {"assetId": asset_id})
            # Try to return a lightweight DTO if possible
            data = resp.get("data") if isinstance(resp, dict) else None
            if data and data.get("asset_id"):
                return TrendAnalysisDto(asset_id=data.get("asset_id"))
        return None

    def summarize_asset_performance(self, asset_id: str, start_date_str: str, end_date_str: str) -> dict:
        """Return a human-friendly summary and raw payload suitable for the UI.

        Uses the tool runner when available, otherwise falls back to the
        analytics_service. The returned dict contains `summary` (string) and
        `payload` (original data) keys.
        """
        # prefer tool runner for platform data
        payload = None
        if self.tool_runner:
            resp = self.tool_runner("get_asset_analytics", {"assetId": asset_id})
            if isinstance(resp, dict) and resp.get("status") == "success":
                payload = resp.get("data")
        elif self.analytics_service:
            # analytics_service may return a DTO or dict
            payload = self.analytics_service.analyze_asset(asset_id, date.fromisoformat(start_date_str), date.fromisoformat(end_date_str))

        if not payload:
            return {"summary": f"No analytics available for {asset_id}.", "payload": None}

        # Build a concise text summary
        lines = [f"Asset: {asset_id}"]
        # Yearly summaries
        yearly = payload.get("yearly_summaries") if isinstance(payload, dict) else None
        if yearly:
            last = yearly[-1] if len(yearly) else None
            if last:
                lines.append(f"Latest year ({last.get('business_date_year')}): avg {last.get('average_close_price')}, min {last.get('min_close_price')}, max {last.get('max_close_price')}")

        preds = payload.get("predictions") if isinstance(payload, dict) else None
        if preds and len(preds):
            p = preds[0]
            lines.append(f"Prediction: next close {p.get('predicted_next_close_price')} (r² {p.get('r_squared')})")

        if not yearly and not preds:
            lines.append("No yearly summaries or predictions available.")

        summary_text = "\n".join(lines)
        return {"summary": summary_text, "payload": payload}
