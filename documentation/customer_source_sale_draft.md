# Customer Source-Code Sale — Discussion Draft

> Commercial discussion draft only. Have a qualified attorney adapt it to the governing law and the final transaction.

## 1. Parties and effective date

Identify the seller, customer, addresses, and effective date.

## 2. Delivered product

The delivered product is a source-code copy of the GNET application and its training system at the version identified by the release tag, delivery date, and SHA-256 manifest. The delivery should enumerate the Python source, C++ DLL source and binaries, EasyLanguage source, canonical feature modules, model registry, model artifacts, tests, setup documentation, and training utilities included.

The specifically listed MA2 baseline bars, trades, and labeled 13-feature dataset are included. Other historical market data, brokerage credentials, accounts, private logs, Redis contents, development history, and third-party software are excluded unless specifically listed.

## 3. Ownership and license

The seller retains all ownership and intellectual-property rights in GNET and may continue to possess, use, modify, develop, license, and sell it without restriction from the customer.

The customer receives a perpetual, non-exclusive, non-revocable license to possess, run, copy for internal backup, and modify the delivered source code for the customer's own use. The customer owns its physical/digital delivered copy and its customer-created modifications, subject to the seller's continuing ownership of the underlying GNET code incorporated into those modifications.

The transaction does not assign the GNET intellectual property, grant exclusivity, create joint ownership, or prevent either party from independently developing and using its own copy.

The agreement must explicitly state whether the customer may redistribute, sublicense, publish, resell, provide hosted access to, or transfer the application or derivative works. A conservative default is that none of those rights are granted without the seller's written consent.

## 4. Third-party components

Python, PyTorch, scikit-learn, Redis, Docker, TradeStation, Windows Terminal, Visual Studio build tools, and other third-party components remain governed by their respective licenses and terms. The seller cannot transfer ownership of those components or the customer's rights to TradeStation/CME data.

## 5. Scope and acceptance

Define the accepted baseline as the MA2CrossLE pipeline using the canonical 13-feature model, registry threshold, and artifacts named in the manifest. Acceptance should require:

1. Successful automated installation verification.
2. Successful simulated TradeStation candidate, exact-candidate decision, entry, stop-loss, and profit-target test.
3. Written acceptance or expiration of a defined review period.

State whether the unfinished volume-profile deployment is excluded, included only if completed before a fixed cutoff, or provided later under a separate milestone.

## 6. Delivery and installation

Specify delivery medium, checksum verification, supported Windows/Python/TradeStation versions, standard installation directory, and the number of installation sessions included. Clarify that the customer is responsible for valid third-party accounts, licenses, market-data access, hardware, networking, backups, and safe TradeStation account configuration.

## 7. Support, corrections, and future work

State the exact support period and response expectations. Distinguish reproducible defects in the delivered baseline from enhancements, retraining, new strategies, broker/platform changes, VP deployment, data acquisition, and customer modifications. Define whether updates are included, billable, or outside scope.

## 8. Trading-risk disclosures

State prominently that the software is experimental trading technology, not investment advice; historical/backtest performance does not guarantee future results; latency, slippage, gaps, outages, data errors, model drift, and platform failures can cause losses; and the customer alone controls whether live automation is enabled and assumes all trading decisions and losses.

Require acceptance testing in simulation before any live use. Consider requiring customer-set risk limits and an independent kill switch.

## 9. Warranties and liability

Define any limited conformance warranty, disclaim implied warranties to the extent legally permitted, exclude promised profitability, and negotiate liability limitations, excluded damages, and any cap. These clauses require jurisdiction-specific legal review.

## 10. Confidentiality and security

Define whether the source is confidential, permitted recipients such as employees/contractors, minimum protection requirements, breach notification, credential handling, and return/destruction obligations if the agreement terminates.

## 11. Payment, taxes, and delivery trigger

Specify price, deposit/final-payment schedule, taxes, when delivery occurs, what constitutes acceptance, refund rules, and treatment of chargebacks or non-payment.

## 12. Termination and survival

Specify whether the perpetual license survives ordinary termination after full payment, what happens after material breach, and which confidentiality, ownership, liability, and payment clauses survive.

## 13. General terms

Include governing law, venue or arbitration, notices, assignment, force majeure, entire agreement, amendment, waiver, severability, and counterpart/electronic-signature provisions.

## Delivery schedule

Attach a schedule containing:

- Release name, tag/commit, date, and archive checksum.
- Complete file manifest and included model identifier.
- Included and excluded functionality.
- Supported environment and installation path.
- Acceptance procedure and results.
- Support/update entitlement.
- Any VP milestone and its deadline.
