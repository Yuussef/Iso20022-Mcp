# From MT103 to pacs.008: what carries over and what is lost

On the Swift network, the MT103 customer credit transfer was replaced by the ISO 20022 pacs.008 when the MT/MX coexistence period for payment instructions ended in November 2025. Many systems still produce MT103-style data, so translation remains common.

Public bank mapping guides describe the main correspondences. The UETR in field 121 of the user header (block 3) becomes the payment identification UETR. Field 20, the sender's reference, becomes the instruction identification. The customer's end-to-end reference comes from a /ROC/ code in field 70 or field 72; when there is none, the end-to-end identification is set to NOTPROVIDED. Field 32A gives the interbank settlement date, currency and amount, and field 33B gives the instructed amount. MT amounts use a comma as the decimal separator.

Field 50 (ordering customer) becomes the debtor, field 52 (ordering institution) the debtor agent, field 56 the intermediary agent, field 57 (account with institution) the creditor agent and field 59 (beneficiary customer) the creditor. Field 71A maps OUR to DEBT, BEN to CRED and SHA to SHAR. Field 70 becomes unstructured remittance information, limited to 140 characters. In field 72, /ACC/ instructions go to the instruction for the creditor agent, and other codes to the instruction for the next agent.

Options F of fields 50 and 59 carry a name (1/), address lines (2/) and country and town (3/), so they can produce a hybrid postal address. Options K and plain 59 are free text: the address stays unstructured, and only two address lines can be kept in CBPR+, so a third line is lost. An MT103 without a UETR, or with only free-text addresses, produces a pacs.008 that fails or will fail CBPR+ rules. Fields without a pacs.008 equivalent in a simple mapping, such as 77B regulatory reporting, must be handled separately.

This note is original project documentation summarising public bank guides. It is not a Swift publication; Swift's official translation rules are published on MyStandards.

Sources: https://www.barclayscorporate.com/content/dam/barclayscorporate-com/images/insights/innovation/ISO-Further-information-slides-15-16-18.pdf and https://www.jpmorgan.com/content/dam/jpmorgan/documents/payments/iso20022-mapping-guide.pdf
