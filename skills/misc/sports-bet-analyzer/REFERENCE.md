# Sports Bet Analyzer — Reference

## Odds formats

| Format | Example | Decimal equivalent |
| --- | --- | --- |
| Decimal | 2.50 | 2.50 |
| Fractional | 6/4 | 6/4 + 1 = 2.50 |
| American positive | +150 | 150/100 + 1 = 2.50 |
| American negative | -200 | 100/200 + 1 = 1.50 |

Implied probability of decimal odds `d` is `1/d`. Summed across all outcomes
of one market this exceeds 100% — the excess is the **overround (vig)**, the
bookmaker's margin (typically 2–8%). `scripts/odds_math.mjs` removes it
proportionally to give the no-vig market probability.

Known bias: markets systematically *overprice* longshots and slightly
underprice heavy favourites (favourite-longshot bias). Be extra skeptical of
apparent value on outcomes priced above ~4.00.

## Tennis factor checklist

Work through these when forming the independent estimate:

- **Surface** — the single biggest factor. A clay specialist vs a fast-court
  player can invert the H2H. Weight surface-specific results far above
  overall ranking.
- **Recent form** — last 5–10 matches, quality of opposition, and whether wins
  were competitive or blowouts.
- **Fatigue and schedule** — a three-set grinder yesterday, back-to-back
  tournaments, long travel, or a deep run the previous week all matter,
  especially in best-of-5.
- **Head-to-head** — useful only on the same surface and within ~3 years;
  stylistic matchups (big server vs elite returner) persist longer than form.
- **Injury/retirement news** — search for it. A niggle announced in press is
  the most common source of stale odds.
- **Format** — best-of-5 favours the stronger player (fewer upsets); best-of-3
  and fast indoor courts favour big servers and underdogs.
- **Conditions** — altitude, heat, indoor/outdoor, ball type.

Useful markets: moneyline (winner), games handicap (fits close matchups where
the favourite wins more games than sets), total games (driven by serve
dominance — two big servers pushes totals up), set betting (high variance,
usually AVOID).

## Soccer factor checklist

- **xG trend vs results** — a team winning while being out-created (xG) is due
  to regress; a team losing despite dominating xG is underpriced. Prefer the
  last ~6–10 matches of xG over the league table.
- **Lineups, injuries, suspensions** — search for confirmed team news. One
  missing keeper or striker moves true probability more than a month of form.
- **Motivation and rotation** — cup ties, dead rubbers, a Champions League
  fixture three days later, relegation/title stakes. Rotation announcements
  are a classic edge over slow markets.
- **Home advantage** — worth roughly 0.3–0.4 goals; smaller in empty or
  neutral stadiums.
- **Schedule congestion and travel** — midweek continental away trips depress
  weekend performance.
- **Goal environment** — league and team pace for over/under and BTTS
  markets; derbies and relegation scraps trend under.
- **Manager change** — short-term bounce is real but small and fades within
  ~5 matches.
- **Draw structure** — draws land 24–28% of the time in most leagues, more
  often between evenly-matched defensive sides. 1X2 estimates must include a
  serious draw probability; if two outcomes sum past ~80% for a balanced
  fixture, the estimate is wrong.

Useful markets: 1X2, double chance and draw-no-bet (lower variance ways to
back a side), Asian handicap (removes the draw; quarter-lines split the
stake), over/under goals, BTTS.

## Value, EV, and staking math

For decimal odds `d` and your estimated win probability `p`:

- **Expected value per unit staked**: `EV = p·(d − 1) − (1 − p)`.
  A bet is +EV only when `p > 1/d`.
- **Full Kelly fraction**: `f = (p·d − 1) / (d − 1)`.
- **Quarter Kelly** (`f/4`, capped at 2% of bankroll) is the default because
  the estimate of `p` is itself uncertain — full Kelly on a mis-estimated
  probability overbets catastrophically.

Even a genuinely +EV bettor loses 40–55% of individual bets and endures long
losing streaks; the edge only shows over hundreds of bets. Say this when the
user expects "high probability wins".

## Common traps to warn about

- **Accumulators** — the vig compounds per leg; a 5-leg acca at 5% margin per
  leg gives the book a ~23% edge.
- **Odds boosts and cash-out** — boosts are marketing on already-bad prices;
  cash-out is repriced with fresh vig against the user.
- **Betting after the news** — if the injury/lineup story is hours old, it is
  already in the price; the edge existed only in the minutes after the news.
- **Results-based confidence** — a won bet was not necessarily a good bet.
  Judge past picks by closing-line value, not outcome.
