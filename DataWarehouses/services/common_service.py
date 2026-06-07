from datetime import date


class CommonService:
    """Common service for asset and timeseries operations.

    This mirrors the responsibilities shown in the Java example: look up an asset
    and return timeseries for a given date range. The implementation delegates
    to injected repository objects so tests can mock those dependencies.
    """

    def __init__(self, asset_repository, timeseries_repository):
        self.asset_repository = asset_repository
        self.timeseries_repository = timeseries_repository

    def get_timeseries(self, asset_id: str, start: date, end: date):
        # Find asset by id; if not present, return None to mirror example behavior
        asset = self.asset_repository.find_by_id(asset_id)
        if asset is None:
            return None

        # If the caller accidentally passed start > end, swap them
        if start > end:
            start, end = end, start

        # Delegate to repository method expected by our unit tests
        return self.timeseries_repository.find_by_asset_id_and_business_date_between_order_by_version_desc(
            asset.get('id') if isinstance(asset, dict) else asset.id,
            start,
            end,
        )
