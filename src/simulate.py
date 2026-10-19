import numpy as np, pandas as pd

df = pd.read_csv("Morpho_market_data.csv",
parse_dates=["x"]).set_index("x").sort_index()
df = df[df["supply"] > 10_000]
u = df["utilization"].clip(0, 1).values

# Empirical Markov chain on 10% bins (Top bins matches the IRM kink)
n = 10
edges = np.linspace(0, 1, n + 1)
b = np.digitize(u, edges[1:-1])
T = np.zeros((n, n))
for i, j in zip(b[:-1], b[1:]):
    T[i, j] += 1
for i in range(n):
    if T[i].sum() == 0:
        T[i, i] = 1
p = T / T.sum(1, keepdims=True)
cdf = p.cumsum(1)
pools = [u[b == k] for k in range(n)]

# Simulate
rng = np.random.default_rng(0)
N, H = 10_000, 90
state = np.full(N, b[-1])
U = np.empty((H, N))
for t in range(H):
    r = rng.random(N)
    state = np.minimum((r[:, None] > cdf[state]).sum(1), n - 1)
for k in np.unique(state):
    m = state == k
    U[t, m] = rng.choice(pools[k], m.sum())

# Morpho AdaptiveCurveIRM shape, rate_at_target held fixed

def borrow_rate(u, r_t=0.04, k=4, tgt=0.9):
    err = np.where(u > tgt, (u - tgt) / (1 - tgt), (u - tgt) / tgt)
    return r_t * np.where(err > 0, (k - 1) * err + 1, (1 - 1 / k) * err + 1)

S0 = df["supply"].iloc[-1]
DEP, HURDLE, FEE = 5e6, 0.045, 0.0
# Marke fee
Ueff = U * S0 / (S0 + DEP)
# utilization
apy = borrow_rate(Ueff) * Ueff * (1 - FEE)

print("U percentiles @ day 90:", np.percentile(U[-1], [5, 25, 50, 75, 95]).round(3))
print("mean supply APY (always in):", apy.mean().round(4))
print("P(APY > hurdle):", (apy > HURDLE).mean().round(3))
print("option value:", np.maximum(apy - HURDLE, 0).mean().round(4))