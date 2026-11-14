# CBPR+ postal address: structured, hybrid and unstructured

ISO 20022 offers three ways to fill a postal address (PstlAdr). A structured address puts each part in its own element, such as StrtNm, BldgNb, PstCd, TwnNm and Ctry. An unstructured address uses only free-text AdrLine lines. A hybrid address, allowed in CBPR+ since Standards Release 2025, combines structured elements with at most two AdrLine lines of up to 70 characters.

In CBPR+, a structured or hybrid address must contain at least the town name (TwnNm) and the ISO 3166 two-letter country code (Ctry). For agents, identifying the bank by its BIC alone remains a valid option, so an agent identified by BICFI needs no postal address.

Swift planned to remove unstructured addresses from CBPR+ payment messages on 14 November 2026, as part of Standards Release 2026. On 27 August 2026 Swift deferred all SR2026 payments changes, including this removal, after communities asked for more time. Swift said it would announce the new timing by December 2026. The requirement still applies to all agents and parties in CBPR+ payment messages, except reporting and admin messages such as camt.052, camt.053, camt.054, camt.060, camt.025 and admi.024.

Common data quality problems seen in structured addresses include a post code inside the town name (for example TwnNm "75001 Paris" instead of PstCd 75001 and TwnNm Paris) and the same town repeated in an AdrLine of a hybrid address. Both weaken sanctions screening and transaction monitoring.

Element length limits in the CBPR+ pacs.008 usage guideline include TwnNm 35 characters, PstCd 16, BldgNb 16, StrtNm 70 and AdrLine 70.

This note is original project documentation summarising public Swift pages and a published bank usage guideline. It is not a Swift publication. Check the current CBPR+ usage guidelines on Swift MyStandards before relying on it.

Sources: https://www.swift.com/standards/iso-20022/iso-20022-faqs/iso-20022-removal-unstructured-address and https://www.swift.com/insights/news/swift-accepts-community-request-extend-structured-address-migration-iso-20022-payment-messages and https://developer.gs.com/docs/services/transaction-banking/cbpr+-pacs008/
