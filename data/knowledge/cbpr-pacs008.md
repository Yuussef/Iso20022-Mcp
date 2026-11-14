# CBPR+ pacs.008 usage rules beyond the XSD

CBPR+ (Cross-Border Payments and Reporting Plus) is the Swift community's usage guideline for ISO 20022 cross-border payments. For customer credit transfers it uses pacs.008.001.08. The XSD accepts many messages that CBPR+ rejects.

A CBPR+ pacs.008 carries exactly one transaction: the group header's number of transactions is always 1. To send several payments, send several messages.

The UETR (Unique End-to-end Transaction Reference) is mandatory in a CBPR+ pacs.008. It is a UUID version 4 as defined in RFC 4122, written in lower case, for example 3f2b8c4e-9a1d-4e7b-8c2f-5d6a7b8c9d0e. The third group starts with 4 and the fourth group starts with 8, 9, a or b. The UETR stays the same along the whole payment chain and is used for tracking.

The charge bearer is mandatory and must be DEBT (all charges paid by the debtor), CRED (all charges paid by the creditor) or SHAR (shared). SLEV is a SEPA code and is not used in CBPR+. Charges information is mandatory when the charge bearer is CRED. With SHAR it is mandatory when charges were deducted, which shows as a settlement amount lower than the instructed amount. With DEBT it is mandatory for prepaid charges, when the settlement amount is higher than the instructed amount.

Amounts must respect the number of decimals that ISO 4217 gives the currency: none for the Japanese yen (JPY) or the Korean won (KRW), three for the Kuwaiti dinar (KWD) or the Bahraini dinar (BHD), and two for most currencies such as USD, EUR and GBP. SIX publishes the ISO 4217 list as maintenance agency.

Text fields use the CBPR+ character set: letters, digits, space and the characters / - ? : ( ) . , ' + ! # $ % & * = ^ _ ` { | } ~ " ; < > @ [ \ ]. Accented and non-Latin characters must be transliterated.

Postal addresses follow the CBPR+ structured, hybrid or unstructured rules: town and country are mandatory in structured and hybrid addresses, a hybrid address has at most two address lines, and the removal of unstructured addresses, planned for November 2026, was deferred by Swift on 27 August 2026.

This note is original project documentation summarising public sources. It is not a Swift publication, and individual banks may add their own rules. Check the current CBPR+ usage guidelines on Swift MyStandards before relying on it.

Sources: https://developer.gs.com/docs/services/transaction-banking/cbpr+-pacs008/ and https://www.clearstream.com/caas/v1/media/4814538/data/ca917a93e9390d399c6c34ebe14032d0/cbpr-ug.pdf and https://www.six-group.com/en/products-services/financial-information/market-reference-data/data-standards.html
