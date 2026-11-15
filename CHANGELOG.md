# Changelog

Versions are git tags; install one with `uvx --from git+https://github.com/Yuussef/Iso20022-Mcp@vX.Y.Z iso20022-check`.

## v0.3.0

- **Rejects, statuses and returns** (`explain_payment_status`, `iso20022-check status.xml`):
  - covers pacs.002, pain.002 and pacs.004;
  - every status and reason code is explained from the ISO 20022 External Code Sets (2Q2026);
  - SEPA reject and return rules from the EPC 2025 guidelines: allowed reasons, originator, original references, returned amount equal to the original;
  - CBPR+ rules on the original UETR and on group versus transaction status;
  - optional matching to the original pacs.008 or pain.001 by UETR or references.
- **Reader for any ISO 20022 message** (`read_iso20022_message`, `iso20022-check message.xml`):
  - headers, references, amounts, parties and agents;
  - codes with their ISO meaning;
  - camt.052/053/054 entries with credit and debit totals, and balances;
  - a structure outline and the tools that can check the message.
- **Web workbench:** "Rejects & returns" and "Read any message" pages, plus a fix for the MT103 page overflow and a new Overview.
- **MCP server:** 13 tools. The server now reports the installed package version.

## v0.2.0

- **Installable package** `iso20022-mcp`: the `iso20022-mcp` MCP server (stdio) and the `iso20022-check` CLI.
- **Rule checks:**
  - SEPA Credit Transfer (EPC 2025, pacs.008 and pain.001);
  - CBPR+ pacs.008 (UETR, single transaction, charges, ISO 4217 decimals);
  - CBPR+ postal addresses.
- **Identifiers:** IBAN (Swift IBAN Registry, mod-97) and BIC (ISO 9362).
- **Migration and summaries:** MT103 to pacs.008 draft with a field-by-field report, and a payment summary.
- **Agent skill** for Agensi, and README instructions for Claude Code and Claude Desktop.
