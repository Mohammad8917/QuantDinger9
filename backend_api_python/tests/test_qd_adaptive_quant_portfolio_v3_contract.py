"""Regression tests for the locked QD Adaptive Quant Portfolio 20 strategy.

These tests intentionally do not import or execute the strategy: its runtime API
is supplied by the QuantDinger strategy host. They verify the file is unchanged,
syntactically valid, and still declares its agreed safety/configuration contract.
"""

from __future__ import annotations

import ast
import hashlib
import re
from pathlib import Path

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
STRATEGY_PATH = (
    REPOSITORY_ROOT
    / "docs"
    / "strategies"
    / "QD_Adaptive_Quant_Portfolio_20_Risk_Controlled_V3.py"
)

# Git's blob SHA-1 for the approved strategy file at lock time. Any content
# change must be reviewed explicitly and the lock deliberately updated.
LOCKED_GIT_BLOB_SHA = "3cd1fbbcf3e57ad5031791b944ce764aad6151b1"

EXPECTED_SYMBOLS = [
    "Crypto:BTC/USDT@gate:swap",
    "Crypto:ETH/USDT@gate:swap",
    "Crypto:SOL/USDT@gate:swap",
    "Crypto:BNB/USDT@gate:swap",
    "Crypto:XRP/USDT@gate:swap",
    "Crypto:ADA/USDT@gate:swap",
    "Crypto:AVAX/USDT@gate:swap",
    "Crypto:DOT/USDT@gate:swap",
    "Crypto:LINK/USDT@gate:swap",
    "Crypto:POL/USDT@gate:swap",
    "Crypto:ATOM/USDT@gate:swap",
    "Crypto:NEAR/USDT@gate:swap",
    "Crypto:APT/USDT@gate:swap",
    "Crypto:ARB/USDT@gate:swap",
    "Crypto:OP/USDT@gate:swap",
    "Crypto:LTC/USDT@gate:swap",
    "Crypto:BCH/USDT@gate:swap",
    "Crypto:DOGE/USDT@gate:swap",
    "Crypto:UNI/USDT@gate:swap",
    "Crypto:ETC/USDT@gate:swap",
]


@pytest.fixture(scope="module")
def strategy_bytes() -> bytes:
    assert STRATEGY_PATH.is_file(), f"Locked strategy file missing: {STRATEGY_PATH}"
    return STRATEGY_PATH.read_bytes()


@pytest.fixture(scope="module")
def strategy_source(strategy_bytes: bytes) -> str:
    return strategy_bytes.decode("utf-8")


@pytest.fixture(scope="module")
def strategy_ast(strategy_source: str) -> ast.Module:
    return ast.parse(strategy_source, filename=str(STRATEGY_PATH))


def _git_blob_sha(content: bytes) -> str:
    header = f"blob {len(content)}\\0".encode("ascii")
    return hashlib.sha1(header + content).hexdigest()


def _function_names(tree: ast.Module) -> set[str]:
    return {
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def test_strategy_matches_approved_locked_content(strategy_bytes: bytes) -> None:
    """Fail closed if the locked strategy changes by even one byte."""
    assert _git_blob_sha(strategy_bytes) == LOCKED_GIT_BLOB_SHA


def test_strategy_is_valid_python(strategy_source: str) -> None:
    """Check compilation without importing host-specific trading APIs."""
    compile(strategy_source, str(STRATEGY_PATH), "exec")


def test_strategy_declares_exact_twenty_symbol_universe(
    strategy_ast: ast.Module,
) -> None:
    initialize = next(
        node
        for node in strategy_ast.body
        if isinstance(node, ast.FunctionDef) and node.name == "initialize"
    )
    symbols_assignment = next(
        node
        for node in ast.walk(initialize)
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Attribute)
            and isinstance(target.value, ast.Name)
            and target.value.id == "g"
            and target.attr == "symbols"
            for target in node.targets
        )
    )
    actual_symbols = ast.literal_eval(symbols_assignment.value)

    assert actual_symbols == EXPECTED_SYMBOLS
    assert len(actual_symbols) == 20
    assert len(set(actual_symbols)) == 20


@pytest.mark.parametrize(
    ("setting", "expected"),
    [
        ("max_positions", "5"),
        ("max_entries_day", "7"),
        ("risk_per_trade", "0.0025"),
        ("max_weight", "0.10"),
        ("max_gross_exposure", "0.80"),
        ("max_net_exposure", "0.40"),
        ("daily_drawdown_limit", "0.02"),
        ("portfolio_drawdown_limit", "0.08"),
        ("cooldown_bars", "4"),
        ("order_timeout_bars", "4"),
        ("max_stop_pct", "0.06"),
        ("time_stop_bars", "96"),
        ("portfolio_rearm", "false"),
    ],
)
def test_locked_risk_parameters_remain_declared(
    strategy_source: str,
    setting: str,
    expected: str,
) -> None:
    pattern = rf"^# @param {re.escape(setting)} \w+ {re.escape(expected)}(?:\s|$)"
    assert re.search(pattern, strategy_source, flags=re.MULTILINE), (
        f"Locked strategy parameter changed or missing: {setting}={expected}"
    )


def test_host_setup_contract_remains_present(strategy_source: str) -> None:
    assert "PERSIST_RUNTIME_STATE = True" in strategy_source
    assert 'frequency="15m"' in strategy_source
    assert 'frequency="1h"' in strategy_source
    assert "context.set_warmup(220)" in strategy_source
    assert 'context.set_metadata(direction_mode="one_way")' in strategy_source
    assert "context.allow_leverage(max_leverage=2)" in strategy_source


def test_risk_and_order_control_functions_remain_present(
    strategy_ast: ast.Module,
    strategy_source: str,
) -> None:
    names = _function_names(strategy_ast)
    expected_functions = {
        "_exposure",
        "_pending_reservations",
        "_pending_position_count",
        "_daily_drawdown",
        "_portfolio_drawdown",
        "_process_rearm",
        "_submit_target",
        "_consume_exit_events",
        "_sync_pending",
        "_close_all",
        "_risk_kill",
        "_signal_and_risk",
        "_target_weight",
        "_cooldown_active",
        "_time_stop_bars",
        "_time_stop_seconds",
        "handle_data",
    }
    assert expected_functions <= names

    required_guards = (
        "if g.daily_killed or g.portfolio_killed",
        "if gross + pending_gross + weight > max_gross",
        "if abs(net + pending_net + signed_weight) > max_net",
        'effective_risk = weight * candidate["stop"]',
        'risk_budget = _clamp(_num(context.params.get("risk_per_trade", 0.0025)), 0.001, 0.005)',
    )
    for guard in required_guards:
        assert guard in strategy_source, f"Required risk guard missing: {guard}"
