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

## Stage C

**Quote skew.** Moving both quotes against the position: when long, quote lower, so selling
becomes more likely and buying less likely. The market maker pays a little edge to get rid of
inventory. It is the simplest form of inventory management.

**Reservation price.** The price at which a risk-averse market maker is indifferent between
holding its inventory and not holding it. Long inventory is a risk, so it values the asset
below the mid and centres its quotes there; the more inventory, the more risk aversion, the
more volatility and the more time left, the further from the mid.

**Avellaneda–Stoikov.** A model that derives quotes for a market maker with CARA utility:
quote around the reservation price `s − q·γ·σ²·(T − t)` with a spread that has a risk part and
a part set by how fill probability decays with distance. The quotes in the paper are an
approximation.

**Risk aversion (γ).** How much expected profit the trader gives up to reduce variance. With
`γ → 0` the Avellaneda–Stoikov quotes become symmetric with spread `2/k`; with large `γ` they
are wide and react strongly to inventory.

**Risk–return frontier.** A plot of mean P&L against its std for a family of strategies. A
point up and to the left is better. It shows the price of risk reduction instead of a single
"best" strategy.

**Paired comparison.** Comparing two strategies episode by episode on the same random numbers
and analysing the differences. Luck that both share cancels, so the confidence interval of the
difference is much narrower than for two independent runs.

**Bootstrap.** Estimating the uncertainty of a statistic that has no simple formula (a ratio
of standard deviations, a certainty-equivalent difference) by recomputing it on many resamples
of the episodes drawn with replacement.

**Jump.** A sudden large move of the value, as on news. A quote that was fine a moment ago is
now on the wrong side of the price.

**Being picked off (sniped).** A stale quote is filled by someone who already sees the new
price. The market maker sells below or buys above the current value. The loss per pick-off is
how far the price moved through the quote; the number of pick-offs grows with latency. This is
why real market makers spend so much on speed.

**Liquidation cost.** Closing a position costs the spread and, for size, market impact. P&L
that ignores it flatters strategies that finish with big inventory.

## Stage D

**Robustness and fragile conclusions.** A result that holds only for one set of parameters is
a property of those parameters. Re-estimating it under other reasonable assumptions shows
whether its direction survives. A conclusion whose sign flips is labelled fragile and not
presented as a finding.

**Sanity checks (SUSPICIOUS flags).** Some results cannot be right: profit below the
break-even spread, a zero-profit market maker that earns money, a strategy that beats one that
sees the future, an accounting identity that does not add up. Checking for them automatically
catches bugs that would otherwise look like good news.

**Reproducibility.** Every number is tied to a seed, a config hash and a commit, and a
finished experiment can be rebuilt from scratch and compared with the stored result. A result
that cannot be regenerated is not evidence.

**Multiple comparisons and the trial log.** Try enough variants and one will look good by
chance. Counting every run, and deciding the criteria before running, is what keeps a
simulator from being a story generator.

## Stage E

**Making a market by hand.** In the game you are asked for a bid and an ask without knowing
the value, exactly the interview exercise. The habits to practise: start with a spread wide
enough for what the informed traders know (informed share times the value range), move both
quotes after every trade in the direction of the trade, and narrow the spread as you learn.

**Marking to the last trade.** During the game P&L is valued at the last trade price, because
the true value is unknown. It can look fine while you are being run over: buying all the way
down marks each purchase at the newest, lower price only after the next trade.

## Stage F

**Reference implementation and test oracle.** A slow, obviously-correct version is kept as the
specification, and the fast version must reproduce its output on the same inputs. Speed is
then never bought with a silent change of behaviour.

**Vectorisation.** Replacing a Python loop over episodes by numpy operations on whole arrays.
The loop over time steps stays, because each step depends on the previous one; the episodes
are independent, so they can be advanced together.

## Follow-up experiments

**Shared seeds are one observation.** When every grid point uses the same random numbers, their
errors are correlated: all of them can sit on the same side of the truth by chance. That is
ideal for comparing two strategies (the shared error cancels) and misleading for asking
whether a formula is biased. For the second question each cell needs its own seed.

**Pooled z.** With independent cells, the average z-score times the square root of the number
of cells is itself standard normal if there is no bias. It detects a small bias that has the
same sign everywhere, which no single cell could show.

**Selection inflates effects.** A pair of settings picked because it looked best in one run
will, on average, look less good in the next. A pattern found by inspecting results is
re-tested on new data with criteria fixed in advance before it is called a finding.

**Optimal for which objective?** A strategy derived as optimal maximises a stated objective
under stated assumptions. Change the objective slightly (here: charge for closing the final
position) and the ranking of strategies can change. Always ask what a "best" strategy is best
at.
