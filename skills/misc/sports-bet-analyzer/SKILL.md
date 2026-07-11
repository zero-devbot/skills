---
name: sports-bet-analyzer
description: >
  Analyze a screenshot of a bookmaker odds board, match card, or bet slip
  (tennis, soccer/football, and similar sports) and produce a probability
  assessment: implied probabilities with the vig removed, an independent
  estimate built from visible stats and recent news, value-bet detection,
  and Kelly-based stake sizing. Use when the user sends a screenshot of
  odds, a fixture, or a bet slip and asks who will win, what to bet on,
  or whether a bet is good value, or invokes /sports-bet-analyzer.
---

# Sports Bet Analyzer

Turn a screenshot of odds into an honest probability assessment. The edge this
skill hunts for is **value** — markets where the bookmaker's odds imply a lower
probability than the evidence supports — not "guaranteed winners", which do not
exist. Never present any bet as a sure thing.

## Workflow

### 1. Extract the screenshot

Read the image and list, as structured data: sport, competition, competitors,
kickoff/start time, every visible market and its odds, and any stats shown
(form, H2H, rankings, league position). Note the odds format (decimal,
fractional, American) and anything unreadable. If the screenshot is a bet slip,
also extract stake, selections, and whether it is a single or accumulator.

### 2. Compute market probabilities

Run `scripts/odds_math.mjs` with the odds for each market — do not do this
arithmetic by hand. It returns implied probabilities, the bookmaker's
overround (vig), and no-vig "true market" probabilities. The no-vig number is
the baseline any pick must beat.

### 3. Form an independent estimate

Work through the sport's factor checklist in [REFERENCE.md](./REFERENCE.md)
(tennis: surface, form, fatigue, H2H; soccer: xG trend, lineups, motivation,
home advantage). If WebSearch is available, check for news the screenshot
can't show — injuries, confirmed lineups, suspensions, retirements — since
this is where most real edges live. State every assumption. Express the result
as a probability per outcome, and adjust conservatively: stay within roughly
±10 percentage points of the no-vig market number unless you have concrete,
recent information the market may not have priced in.

### 4. Classify each market

Edge = your estimate − no-vig market probability.

- **VALUE** — edge ≥ +4pp and your reasoning is concrete. Candidate bet.
- **FAIR** — |edge| < 4pp. No reason to bet; the vig makes it -EV.
- **AVOID** — negative edge, or too little data to estimate confidently.

Confirm VALUE picks with the script's `--est` mode (EV and Kelly stake).

### 5. Recommend stakes

Quarter-Kelly, capped at 2% of bankroll per bet. If no bankroll was given,
express stakes in units (1u = 1% of bankroll). Never recommend chasing losses
or increasing stakes after a losing run.

## Output format

1. **What I can read** — the extracted data, so the user can correct OCR errors.
2. **Verdict table** — one row per market: odds, implied %, no-vig %, your
   estimate %, edge, verdict (VALUE / FAIR / AVOID).
3. **Reasoning** — a short paragraph per non-FAIR market citing the specific
   factors used.
4. **Stake advice** — for VALUE picks only.
5. **Confidence & caveats** — what you couldn't verify, and how stale the
   odds may be.

## Hard rules

- Never claim a bet will win or use language like "sure thing", "banker",
  "guaranteed". Report probabilities and expected value only.
- Accumulators/parlays compound the vig on every leg. Default advice: break
  them into singles; only ever endorse an accumulator if *every* leg is
  independently VALUE.
- Live/in-play odds go stale in seconds — say so, and don't recommend stakes
  on them unless the user confirms current odds.
- If the screenshot lacks stats and web access is unavailable, say the
  estimate is low-confidence and cap the verdict at FAIR.
- End every analysis with a one-line responsible-gambling note: this is
  probabilistic analysis, not financial advice; only stake money the user can
  afford to lose; even +EV bets lose often.

## Reference

Sport-specific factor checklists, market glossary, and the math behind vig
removal, EV, and Kelly: [REFERENCE.md](./REFERENCE.md).
