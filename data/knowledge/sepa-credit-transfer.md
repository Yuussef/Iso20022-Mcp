# SEPA Credit Transfer (SCT) usage rules for pacs.008 and pain.001

The EPC 2025 SCT implementation guidelines took effect on 5 October 2025. They are based on the 2019 ISO 20022 messages: pacs.008.001.08 between payment service providers (Inter-PSP guidelines, EPC115-06) and pain.001.001.09 from customer to bank (Customer-to-PSP guidelines, EPC132-08).

A SEPA Credit Transfer is in euro only. The amount must be between 0.01 and 999999999.99 euro with at most two decimals. The charge bearer code must be SLEV, and the service level code must be SEPA. In pacs.008 the charge bearer is mandatory; in pain.001 it is optional but recommended at payment information level.

Accounts of the debtor and the creditor are identified by IBAN only. Banks (agents) are identified by BIC only, in the BICFI element, either BIC8 or BIC11. Names of the debtor and creditor are limited to 70 characters.

Every SEPA PSP must support the Latin character set: a to z, A to Z, 0 to 9, and / - ? : ( ) . , ' + and space. References and identifiers such as the end-to-end identification must use only these characters, must not start or end with a slash, and must not contain a double slash. Other characters can be used only by bilateral or multilateral agreement.

Remittance information is either unstructured (one occurrence, at most 140 characters) or structured (one occurrence, with the tags and data inside it not exceeding 140 characters), never both.

Addresses can be structured (town name and country mandatory, no address line), hybrid (town name and country mandatory plus up to two address lines of 70 characters) or unstructured (one or two address lines and optionally the country). The address of the payer is mandatory when the payer's PSP or the payee's PSP is located in a non-EEA SEPA country such as Switzerland or the United Kingdom, and the country is then mandatory too. The EPC planned to end the unstructured format in November 2026, but in September 2026 it delayed that end date for all five EPC payment schemes; a new date will be set later.

SEPA covers 41 countries: the 27 EU member states, Iceland, Liechtenstein and Norway, and 11 non-EEA countries: Albania, Andorra, Moldova, Monaco, Montenegro, North Macedonia, San Marino, Serbia, Switzerland, the United Kingdom and Vatican City State. Some territories such as Guernsey, Jersey, the Isle of Man and Saint-Pierre-et-Miquelon are also in scope.

An IBAN check verifies the national length and structure from the IBAN Registry published by Swift and the ISO 7064 mod-97 check digits. It cannot prove that the account exists. A BIC check verifies the ISO 9362 format; a 0 as the second location character marks a test and training BIC.

This note is original project documentation summarising public EPC and Swift documents. It is not an EPC publication. Check the current EPC rulebooks and implementation guidelines before relying on it.

Sources: https://www.europeanpaymentscouncil.eu/what-we-do/epc-payment-schemes/sepa-credit-transfer-sct/sepa-credit-transfer-rulebook-and and https://www.europeanpaymentscouncil.eu/document-library/other/epc-list-sepa-scheme-countries and https://www.swift.com/standards/data-standards/iban-international-bank-account-number
