import pytest

from app.data_sources.native_crypto import normalize_market_type as normalize_native_market_type
from app.services.market_context import normalize_market_type as normalize_context_market_type
from app.services.strategy_v2.live_execution import LiveOrderRequest, StrategyV2OrderGateway


def _order_request(market_type: str) -> LiveOrderRequest:
    return LiveOrderRequest(
        strategy_id=1,
        strategy_run_id=1,
        user_id=1,
        symbol="BTC/USDT:USDT",
        action="open_long",
        quantity=1.0,
        reference_price=100.0,
        signal_timestamp=1,
        market_type=market_type,
        execution_mode="signal",
    )


def test_crypto_data_source_defaults_to_futures():
    assert normalize_native_market_type(None) == "swap"
    assert normalize_context_market_type(None, market="Crypto") == "swap"


@pytest.mark.parametrize("market_type", ["spot", " Spot ", "SPOT"])
def test_crypto_spot_is_rejected_by_data_source(market_type):
    with pytest.raises(ValueError, match="Spot market is disabled"):
        normalize_native_market_type(market_type)


def test_crypto_market_context_rejects_spot():
    with pytest.raises(ValueError, match="Spot market is disabled"):
        normalize_context_market_type("spot", market="Crypto")


def test_live_order_gateway_rejects_spot_orders():
    with pytest.raises(ValueError, match="strategyV2.futuresOnlyMarketRequired"):
        StrategyV2OrderGateway._validate(_order_request("spot"))


@pytest.mark.parametrize("market_type", ["swap", "future", "futures", "perp", "perpetual", "linear"])
def test_live_order_gateway_accepts_futures_aliases_as_swap(market_type):
    validated = StrategyV2OrderGateway._validate(_order_request(market_type))
    assert validated.market_type == "swap"
