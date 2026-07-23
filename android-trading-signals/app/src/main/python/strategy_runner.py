"""Runs user-supplied strategy code on-device (via Chaquopy) against candle data.

The Kotlin side calls run_user_strategy(user_code, candles_json) and gets back a JSON string.
User code must define a top-level function `strategy(candles)` where `candles` is a list of
dicts with keys: timestamp, open, high, low, close, volume (oldest first). It must return either
a dict {"action": "BUY"|"SELL"|"HOLD", "note": "..."} or a bare string action.
"""

import json


class StrategyError(Exception):
    pass


def run_user_strategy(user_code: str, candles_json: str) -> str:
    candles = json.loads(candles_json)

    namespace = {}
    try:
        exec(user_code, namespace)
    except Exception as exc:  # noqa: BLE001 - surface any user code error to the UI
        raise StrategyError(f"Strategy code failed to load: {exc}") from exc

    strategy_fn = namespace.get("strategy")
    if strategy_fn is None or not callable(strategy_fn):
        raise StrategyError("Strategy code must define a callable named 'strategy(candles)'.")

    try:
        result = strategy_fn(candles)
    except Exception as exc:  # noqa: BLE001
        raise StrategyError(f"Strategy raised an exception: {exc}") from exc

    if isinstance(result, dict):
        action = str(result.get("action", "HOLD")).upper()
        note = str(result.get("note", ""))
    else:
        action = str(result).upper()
        note = ""

    if action not in ("BUY", "SELL", "HOLD"):
        raise StrategyError(f"Strategy returned an invalid action: {action!r}")

    return json.dumps({"action": action, "note": note})
