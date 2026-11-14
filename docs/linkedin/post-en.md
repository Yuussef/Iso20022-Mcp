# LinkedIn post draft (English)

> Review and adapt in your own words before posting. Replace [demo link] and [GitHub link]. Use a screenshot or the GIF as the first image (see `assets.md`).

---

**A valid ISO 20022 XSD does not mean "payment accepted".**

While moving payment flows to ISO 20022, I kept seeing the same thing: the message passes schema validation, then gets rejected or repaired further down the chain. The rules that matter, the EPC rules for SEPA and CBPR+ for Swift, are not in the XSD.

So I built an open-source tool that checks those rules, deterministically and offline:

🇪🇺 **SEPA Credit Transfer** (EPC 2025 guidelines, pacs.008 and pain.001): euro only, SLEV, IBANs from the 41 SEPA countries, the Latin character set, 140-character remittance… and a rule few developers know: the debtor address becomes mandatory as soon as a Swiss or UK bank is in the chain.

🌍 **CBPR+ pacs.008**: one transaction per message, UETR as a UUID v4, DEBT/CRED/SHAR, and ISO 4217 decimals (a JPY amount with cents gets rejected).

🏠 **Postal addresses**: structured, hybrid or unstructured. A detail I checked in the official sources: Swift (27 August 2026) and the EPC (September 2026) both **deferred** the end of unstructured addresses planned for November 2026. The tool says so instead of repeating an outdated date.

🔁 **MT103 → pacs.008**: a draft message plus a field-by-field report showing what a legacy MT103 loses on the way (no UETR, free-text addresses, a 77B field with no equivalent).

🤖 Everything is exposed as an **MCP server**, so Claude or another AI agent can call the checks and explain each error, without ever deciding on its own whether a payment is valid.

What I took away:
• The longest part was **verifying every rule** against EPC, Swift and SIX documents, not writing the code.
• Useful AI in payments is **tool-backed** AI: deterministic, sourced rules, and a model that explains them.

The project is open source, with 280+ tests and CI: [GitHub link]
Demo: [demo link]

If you work on SEPA, CBPR+ or MT → MX migration, I'd like to hear which rules cause you the most trouble.

#ISO20022 #SEPA #SWIFT #Payments #CBPR #MCP #AI #OpenSource
