# Trading Signals (Android)

A standalone Android app (Kotlin + Jetpack Compose) that runs a **Python trading strategy
on-device** against live market data and shows the resulting BUY/SELL/HOLD signals. It is not a
Claude Code skill and deliberately lives outside `skills/` — it doesn't fit the SKILL.md format
described in the repo's `CLAUDE.md`, so it has no entry in the top-level README or
`.claude-plugin/plugin.json`.

## What it does

- **Strategy tab** — edit a Python function `strategy(candles)` right on the phone (backed by
  [Chaquopy](https://chaquo.com/chaquopy/), which embeds a real CPython interpreter in the APK),
  fetch recent candles from whichever broker is active, and run the strategy against them.
- **Signals tab** — history of every signal produced, either from a manual "Run strategy now",
  a 15-minute background WorkManager job, or an inbound TradingView webhook.
- **Connections tab** — configure Bybit, MT5 (via MetaApi), and a local TradingView webhook
  receiver.

## Broker support — read this before wiring up MT5 or TradingView

Only **Bybit** has a genuine, documented, mobile-friendly API, so it's the fully worked example:
public REST endpoints for candles (no auth needed) and HMAC-signed order placement
(`app/src/main/java/com/tradingsignals/app/data/broker/BybitBroker.kt`).

**MT5** does not expose any API you can call from a phone — the terminal is a Windows desktop app
that only speaks its own protocol. The only real ways to reach an MT5 account remotely are (a) a
hosted bridge like [MetaApi.cloud](https://metaapi.cloud), which is what
`MetaApiBroker.kt` talks to, or (b) self-hosting the official `MetaTrader5` Python package on an
always-on Windows box running the MT5 terminal, and exposing your own HTTP API in front of it.
There is no way to skip having a bridge somewhere. To use the MetaApi path: create a MetaApi
account, deploy your MT5 login to it, and paste the resulting **account id** and **token** into
Connections.

**TradingView** doesn't offer a pull API for account/strategy data either — its integration point
is outbound webhooks from a TradingView alert to a URL you specify. `TradingViewWebhookServer.kt`
is a small embedded HTTP server (NanoHTTPD) that receives that webhook and turns it into a signal.
The catch: TradingView's servers need to reach your phone over the internet, which a phone
normally isn't reachable on. Two practical options:
1. Port-forward the phone (if you control the router/network it's on), or
2. Tunnel it — [Tailscale Funnel](https://tailscale.com/kb/1223/funnel), `ngrok`, or a Cloudflare
   Tunnel all work — and point the TradingView alert's webhook URL at the tunnel's public address.

Point the alert at your receiver with a JSON message body like:
```json
{"symbol": "BTCUSDT", "action": "buy", "price": 65000, "note": "MA cross alert"}
```

## Project layout

```
app/src/main/java/com/tradingsignals/app/
  data/model/        Candle, TradeSignal, BrokerType
  data/broker/        Broker interface + Bybit / MetaApi / TradingView implementations
  data/python/        Kotlin <-> Chaquopy bridge
  data/prefs/          EncryptedSharedPreferences-backed settings
  data/repo/           Signal history (in-memory + JSON file)
  service/             WorkManager periodic strategy runner
  ui/                  Compose screens, nav, view model
app/src/main/python/
  strategy_runner.py   Executes user-supplied strategy code safely and normalizes its result
  example_strategy.py  Reference strategy (5/20 SMA crossover) shown as the editor default
```

## Building

This was scaffolded without an Android SDK available in the sandbox that generated it, so it
has **not** been compiled or run yet. To build it:

1. Open the `android-trading-signals/` folder in Android Studio (Ladybug or newer), which will
   prompt to install any missing SDK/NDK components.
2. Or from the command line, with `ANDROID_HOME` set to a valid SDK:
   ```
   ./gradlew assembleDebug
   ```
3. First launch triggers a Chaquopy Python environment download — needs network access to
   `chaquo.com` and Google's Maven repo.

Dependency versions (AGP 8.6.0, Kotlin 2.0.20, Compose BOM 2024.09.00, Chaquopy 15.0.1) were
current as of early 2026 knowledge; bump them in the root `build.gradle.kts` / `app/build.gradle.kts`
if Android Studio flags newer stable releases.

## Security notes

- API keys/tokens are stored in `EncryptedSharedPreferences` (Android Keystore-backed), not plain
  prefs or a file.
- The Python strategy runs with `exec()` inside Chaquopy's sandboxed-per-app CPython — it has the
  same permissions as the rest of the app (network, storage), so only paste strategy code you
  trust. There is no additional sandboxing beyond what the Android app process itself has.
- Trading (`placeOrder`) is wired up for Bybit and MetaApi but is **not** called automatically by
  the background worker or the manual "Run strategy now" button — both only log/display signals.
  Wire up auto-trading yourself once you've validated a strategy's signals, so you don't wake up
  to unattended live orders from day one.
