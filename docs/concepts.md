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
