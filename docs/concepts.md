# Concepts

Plain-language notes, added the first time a concept appears in the project.

## Stage 0

**Market maker, bid, ask, spread.** A market maker posts a price at which it buys (bid) and a
higher price at which it sells (ask). The difference is the spread. If a buyer and a seller
both trade with it while the price stands still, it keeps the spread; that is its income.

**Noise traders and informed traders.** A noise trader trades for reasons unrelated to where
the price is going (it needs cash, it rebalances). An informed trader trades because it knows
something about the future price. The market maker cannot tell them apart when they arrive.

**Adverse selection.** The market maker's losses from trading with people who know more than
it does. An informed trader buys only when the price is about to rise, so the market maker has
sold just before a rise. The spread earned from noise traders has to pay for these losses.

**Markout.** How a fill looks some time later: the price move after the fill, measured in the
market maker's favour (positive) or against it (negative), at a horizon of `h` steps. Negative
markouts mean the flow was "toxic", that is, informed.

**Fill intensity.** In the model, noise orders hit a quote at a rate `A·exp(−k·δ)`, where `δ` is
the quote's distance from the mid price. A quote further away is filled less often. Over a
step of length `dt` the fill probability is `1 − exp(−rate·dt)`.

**Martingale.** A price process whose expected future value equals its current value: no
predictable drift. On a martingale price, holding inventory earns zero on average, so against
noise traders alone all expected profit comes from the spread.

**Common random numbers.** Running two strategies on the same random numbers (same price path,
same arriving traders). The difference between them is then not blurred by luck that differs
between runs, so a paired comparison needs far fewer episodes to detect it.

**Pre-registration.** Writing the hypothesis, the parameters and the pass/fail numbers before
running an experiment. A simulator can be rerun until it tells a nice story; a written
prediction that the code checks against a config hash prevents that.

**Config hash.** A short fingerprint of every parameter that can change results. It is written
into every output, so any number can be traced to the exact configuration that produced it.

## Stage A

**Spread capture.** The edge at the moment of a fill: how far the fill price is from the true
value, in the market maker's favour. Selling at 100.75 when the value is 100 captures 0.75.
It is what the market maker is paid for providing liquidity.

**Inventory and inventory risk.** Inventory is the position the market maker is left with when
buys and sells do not match. While it holds inventory, every move of the value changes its
P&L. On a random-walk value this adds no profit on average, only variance, and here it is the
largest part of the P&L's standard deviation.

**P&L decomposition.** Total P&L split per fill into spread capture, the short-term move
after the fill (negative when the flow was informed) and the later holding P&L. It shows
where the money came from: a market maker can have a positive total while losing on every
fill's short-term move.

**Mark-to-market and liquidated P&L.** Mark-to-market values the final inventory at the true
value. Liquidated P&L also charges the cost of closing that inventory. A strategy that ends
with large positions looks better marked to market than it would be in practice.

**Monte Carlo, standard error, confidence interval.** One episode is one random draw, so a
single P&L says little. Running many independent episodes gives a mean; its standard error is
the std divided by the square root of the number of episodes, and the 95% confidence interval
is about two standard errors each side. A difference smaller than that is noise.

**Sharpe ratio (per episode).** Mean P&L divided by its std across episodes. Here it is not
annualised, because the model's time unit is arbitrary; it only compares strategies inside
the same scenario.

**Expected shortfall.** The average P&L in the worst 5% of episodes. It describes how bad the
bad cases are, which the std alone does not.

**Certainty equivalent (CARA).** The sure amount a risk-averse trader would accept instead of
the random P&L: `CE = −(1/γ)·ln E[exp(−γ·P&L)]`. It is below the mean, and further below the
riskier the P&L. Avellaneda–Stoikov maximise exactly this kind of objective, so it is the fair
way to compare a risk-reducing strategy with a risk-neutral one.

**Latency and stale quotes.** If the market maker requotes only every few steps, its quotes
stay where they were while the price moves. A stale quote on the wrong side of the new price
is a free option for whoever is faster.

**Tick size and outward rounding.** Prices live on a grid. Rounding the bid down and the ask
up means the quoted spread is never narrower than the strategy intended.

## Stage B

**Toxic flow and the markout curve.** Flow is toxic when the price moves against the market
maker after it trades. The markout curve shows it: the average edge of a fill measured at
longer and longer horizons. For noise fills it stays at the half-spread; for informed fills it
starts at the half-spread and falls below zero. Real desks watch this curve per client or
venue, because they cannot see who is informed either.

**Break-even spread.** The spread at which income from noise traders exactly pays for losses
to informed traders. The more informed traders there are, or the more they know, the wider it
must be. This is why spreads widen before news.

**Selection in who you trade with.** A quote is not hit at random. Informed traders take it
exactly when it is wrong, so conditional on being filled the price is more likely to move
against you. The same logic runs the other way: if an informed trader passed on your quote,
that is mild good news about it.

**Bayes' rule and the posterior.** The market maker starts with a prior probability that the
value is high and updates it after every trade: a buy is more likely if the value is high, so
a buy raises the probability. The updated number is the posterior.

**Glosten–Milgrom quotes.** Set the ask to the expected value given that the next trade is a
buy, and the bid given a sell. Then no trade is regretted on average: expected profit is zero
(competition between market makers would force this). The spread exists purely because of
adverse selection, even with no costs and no risk aversion, and it equals the informed share
times the size of what the informed know.

**Price discovery.** As trades arrive, the posterior moves toward the truth and the quotes
converge on the true value. Informed traders lose their edge by trading on it: their orders
are how the information gets into the price.

**Look-ahead bias and a negative control.** A simulated strategy that accidentally uses future
data looks brilliant and is worthless. The future-scramble test changes the future and checks
that past quotes do not change. A strategy that cheats on purpose (`clairvoyant`) must fail
the test; otherwise the test proves nothing.
