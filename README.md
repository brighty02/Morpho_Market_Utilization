# Morpho Lending Market Analytics

A Python script for querying and analyzing historical lending market data from the Morpho API.

The script retrieves historical market data to examine utilization, supply and borrow rates, and liquidity conditions over time. It is designed to support research into lending market dynamics, particularly whether periods of elevated utilization create attractive opportunities for deploying idle capital.

## Overview

The analysis focuses on metrics that help evaluate lending market conditions:

- **Utilization:** Identifies periods of high borrowing relative to supplied assets.
- **Supply APY:** Examines the yield available to lenders across different market conditions.
- **Borrow APY:** Tracks borrowing costs and rate changes over time.
- **Stress episodes:** Identifies periods where utilization meets or exceeds a specified threshold.
- **Liquidity conditions:** Helps assess how much liquidity remains available during elevated utilization.
- **Aggregate health factor (HF):** Provides an aggregate view of borrower collateral health, where supported by the underlying data and calculation.

These metrics can be used to investigate whether lending market stress creates sufficiently attractive opportunities to justify the opportunity cost of holding idle capital.

## Usage
python src/metrics.py <market_contract> <chain_id>

## Requirements

- Python 3
- Internet connection
- Access to the public Morpho API

Install any required Python dependencies before running the script.

If the repository includes a `requirements.txt` file, install the dependencies with:

```bash
pip install -r requirements.txt


