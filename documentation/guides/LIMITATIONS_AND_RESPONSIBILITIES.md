# Known Limitations, Exclusions, and Responsibilities

This document summarizes the technical and operational boundary of the delivered release.
The executed contract controls if its terms differ from this technical summary.

## Delivered production baseline

- GNET source and training system under the customer release identity.
- The MA2Cross_Zona strategy source and local-training implementation using the canonical
  13-feature contract.
- A disabled registry template, compiled bridge DLLs, DLL source, and EasyLanguage source.
- Training architecture, feature definitions, hyperparameters, thresholds, validation code,
  and procedures for creating the customer's model locally.
- Volume-profile source, offline preparation, canonical VP mathematics, and research utilities.

## Current technical limitations

- The production MA2Cross model consumes only the canonical 13-feature stream.
- VP features are research functionality and are not wired into the delivered live model.
- TradeStation, Docker Desktop, Python.org CPython, market data, and Internet access are
  external prerequisites rather than bundled products.
- Live behavior depends on TradeStation, data quality, market conditions, machine resources,
  networking, and third-party software availability.
- No software or model result guarantees profitability, accuracy, uptime, expected value,
  drawdown, or a particular return-risk relationship.

## Customer responsibilities after delivery

- Maintain valid Windows, TradeStation, Docker, market-data, and other third-party licenses.
- Maintain, update, secure, back up, and test open-source and third-party dependencies after
  the agreed delivery/support period. Review license or compatibility changes before updating.
- Keep credentials and generated `.env` files private and out of source control or support
  attachments.
- Validate dependency, model, and strategy changes in simulation before live use.
- Configure accounts, position sizing, stops, targets, permissions, risk limits, and live
  automation safely.
- Supply properly licensed historical data for the initial MA2Cross_Zona training and all
  later retraining, VP work, or new models.
- Monitor the system and retain logs, backups, acceptance records, and release hashes.

## Excluded unless separately agreed in writing

- Guaranteed financial or model performance.
- Development, integration, or training of additional strategies.
- Production wiring of VP features into live inference.
- Ongoing monitoring, retraining, dependency maintenance, security administration, or 24/7
  operational support.
- Maintenance of customer or third-party modifications.
- Brokerage, regulatory, legal, fiduciary, portfolio-management, or investment advice.
- All licensor historical or processed datasets, trade labels, model weights, scalers,
  predictions, frozen holdouts, metrics, and generated model artifacts.
- Credentials, accounts, private logs, Redis contents, development history, and third-party
  installers.
