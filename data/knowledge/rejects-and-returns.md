# Rejects, statuses and returns: pacs.002, pain.002 and pacs.004

A payment can fail at two moments. Before settlement, the receiving bank or the clearing system rejects it with a status report: pacs.002 between banks, or pain.002 from a bank to its customer. After settlement, the creditor's bank sends the money back with a payment return, pacs.004.

A status report gives a transaction status such as RJCT (rejected), ACCP (accepted after technical and profile checks), ACSP (accepted, settlement in process), ACSC (settlement completed) or PDNG (pending). A group status such as PART means that only part of a batch was accepted. Each rejection or return should carry a reason code from the ISO 20022 external code sets, for example AC01 (account number invalid or missing), AC04 (account closed), AM04 (insufficient funds), AM05 (duplicate payment), MD07 (beneficiary deceased), RC01 (bank identifier incorrect) or MS03 (reason not specified). The ISO code sets are published quarterly by the ISO 20022 Registration Authority.

In SEPA Credit Transfer, the EPC limits which reasons can be used. A reject (pacs.002) uses only AC01, AG02, AM05, CNOR, DNOR, ED05, ERIN, FF01, MS03, RC01, RR01 to RR04 and TM01, with transaction status RJCT, one reason, and the originator of the reason. A return (pacs.004) uses only AC01, AC04, AC06, AG01, AG02, AM05, BE04, CNOR, ERIN, MD07, MS02, MS03, RC01 and RR01 to RR04, or FOCR when it answers a recall. The returned amount must equal the original amount, in euro, with charge bearer SLEV. Insufficient funds (AM04) is not an inter-bank SEPA Credit Transfer reject reason.

In CBPR+, a pacs.002 carries the original UETR and a transaction status. The reason is optional, but without it the cause of a rejection cannot be explained. When the group status is RJCT, every transaction status must be RJCT.

To find which payment a status or return refers to, match the original UETR first, then the original end-to-end identification, transaction identification or instruction identification. The original message identification and amount should also agree with the original payment.

This note is original project documentation summarising public ISO, EPC and bank guidance. It is not an official publication.

Sources: https://www.iso20022.org/catalogue-messages/additional-content-messages/external-code-sets and https://www.europeanpaymentscouncil.eu/sites/default/files/kb/file/2025-10/EPC115-06%20SCT%20Inter-PSP%20IG%202025%20V1.0.pdf and https://developer.gs.com/docs/services/transaction-banking/cbpr+-pacs002
