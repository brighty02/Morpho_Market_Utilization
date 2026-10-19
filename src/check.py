import requests

MARKET = "0x4fe72543c5c95cd6b5f3cb516cd235ba882e2e705fe3424db6f99dfe5811d0d3"

q = """
query($id: String!, $chainId: Int!) {
  marketById(marketId: $id, chainId: $chainId) {
    marketId
    loanAsset { symbol decimals address }
    collateralAsset { symbol address }
    lltv
    oracle { address}
  }
}
"""

r = requests.post("https://api.morpho.org/graphql", json={"query": q, "variables": 
{"id": MARKET, "chainId": 1}}).json()

print(r["data"]["marketById"])
