# Example strategy: 5/20 simple moving average crossover.
# This is the code shown by default in the app's Strategy editor -- replace it with your own.
# `candles` is a list of dicts (oldest first), each with: timestamp, open, high, low, close, volume.
# Return {"action": "BUY" | "SELL" | "HOLD", "note": "..."}.


def strategy(candles):
    closes = [c["close"] for c in candles]
    if len(closes) < 20:
        return {"action": "HOLD", "note": "not enough candles yet (need 20)"}

    fast = sum(closes[-5:]) / 5
    slow = sum(closes[-20:]) / 20

    if fast > slow:
        return {"action": "BUY", "note": f"fast MA {fast:.4f} > slow MA {slow:.4f}"}
    if fast < slow:
        return {"action": "SELL", "note": f"fast MA {fast:.4f} < slow MA {slow:.4f}"}
    return {"action": "HOLD", "note": "fast MA == slow MA"}
