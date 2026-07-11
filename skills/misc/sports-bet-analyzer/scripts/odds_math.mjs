#!/usr/bin/env node
// Odds math for the sports-bet-analyzer skill.
//
// Usage:
//   node odds_math.mjs <odds> <odds> [...]
//     All outcomes of ONE market. Accepts decimal (2.50), fractional (6/4),
//     or American (+150 / -200). Prints implied %, overround, and no-vig %.
//
//   node odds_math.mjs --est <p> <odds> <odds> [...]
//     Additionally evaluates a bet on the FIRST listed outcome at your
//     estimated probability p (0..1): EV per unit, Kelly, quarter-Kelly.

function toDecimal(raw) {
  const s = String(raw).trim();
  if (/^[+-]\d+$/.test(s)) {
    const n = Number(s);
    return n > 0 ? n / 100 + 1 : 100 / -n + 1;
  }
  if (/^\d+(\.\d+)?\/\d+(\.\d+)?$/.test(s)) {
    const [num, den] = s.split("/").map(Number);
    return num / den + 1;
  }
  const d = Number(s);
  if (!Number.isFinite(d) || d <= 1) {
    throw new Error(`Cannot parse odds "${raw}" (decimal must be > 1)`);
  }
  return d;
}

const pct = (x) => `${(100 * x).toFixed(1)}%`;

const args = process.argv.slice(2);
let est = null;
const estIdx = args.indexOf("--est");
if (estIdx !== -1) {
  est = Number(args[estIdx + 1]);
  args.splice(estIdx, 2);
  if (!(est > 0 && est < 1)) {
    console.error("--est must be a probability strictly between 0 and 1");
    process.exit(1);
  }
}

if (args.length < 2) {
  console.error(
    "Usage: odds_math.mjs [--est p] <odds1> <odds2> [...oddsN]  (all outcomes of one market)",
  );
  process.exit(1);
}

let decimals;
try {
  decimals = args.map(toDecimal);
} catch (e) {
  console.error(e.message);
  process.exit(1);
}

const implied = decimals.map((d) => 1 / d);
const book = implied.reduce((a, b) => a + b, 0);
const noVig = implied.map((p) => p / book);

console.log("Outcome  Odds(dec)  Implied   No-vig");
decimals.forEach((d, i) => {
  console.log(
    `#${i + 1}`.padEnd(9) +
      d.toFixed(3).padEnd(11) +
      pct(implied[i]).padEnd(10) +
      pct(noVig[i]),
  );
});
console.log(`\nOverround (vig): ${pct(book - 1)}`);

if (est !== null) {
  const d = decimals[0];
  const ev = est * (d - 1) - (1 - est);
  const edge = est - noVig[0];
  const kelly = (est * d - 1) / (d - 1);
  const quarter = Math.min(Math.max(kelly / 4, 0), 0.02);
  console.log(`\nBet evaluation for outcome #1 at your estimate p=${pct(est)}:`);
  console.log(`  Edge vs no-vig market: ${(100 * edge).toFixed(1)}pp`);
  console.log(`  EV per unit staked:    ${(100 * ev).toFixed(1)}%`);
  if (ev <= 0) {
    console.log("  Verdict: -EV at your estimate. Do not bet.");
  } else {
    console.log(`  Full Kelly stake:      ${pct(kelly)} of bankroll`);
    console.log(
      `  Recommended (1/4 Kelly, 2% cap): ${pct(quarter)} of bankroll`,
    );
  }
}
