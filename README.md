# PayDoc AI

[![CI](https://github.com/Yuussef/Iso20022-Mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/Yuussef/Iso20022-Mcp/actions/workflows/ci.yml)

*PayDoc AI is the product name; the repository and Python package are `iso20022-mcp`.*

**ISO 20022 payment checks for people and AI agents.** It catches what the XSD lets through: SEPA Credit Transfer rules (EPC), CBPR+ pacs.008 rules (UETR, charges, currency decimals), structured, hybrid and unstructured postal addresses, IBAN and BIC validity, and what an MT103 loses on its way to pacs.008. Every check is deterministic, offline and sourced. The same operations are available as an **MCP server** for Claude and other agents, a **CLI**, an **agent skill**, and a **React + FastAPI workbench**.

> This is a portfolio project, not a payment processor, compliance product, or banking system. Use synthetic XML only.

## Try it in 60 seconds

You need [uv](https://docs.astral.sh/uv/). The first run downloads the package; the checks then run offline. The commands are pinned to the `v0.2.0` release; remove `@v0.2.0` to follow `main`.

```bash
uvx --from git+https://github.com/Yuussef/Iso20022-Mcp@v0.2.0 iso20022-check --iban "DE89 3704 0044 0532 0130 00"
```

From a clone, run the bundled samples:

```bash
uv run iso20022-check examples/sepa/pacs008-problems.xml --profile sepa
uv run iso20022-check examples/cbpr/pacs008-valid.xml --summary
uv run iso20022-check --mt103 examples/mt103/legacy-free-text.txt
```

`PASS` or `FAIL` comes first, then each finding with its rule ID, fix and XPath. The exit code is 0 when there are no rule errors, 1 when there are, and 2 when the input is unreadable. Add `--json` for the full result.

## Use with Claude (MCP)

The MCP server exposes these tools over stdio: `check_sepa_sct`, `check_cbpr_pacs008`, `check_cbpr_postal_addresses`, `explain_payment_status`, `read_iso20022_message`, `convert_mt103_to_pacs008`, `summarize_payment`, `validate_iban`, `validate_bic`, `validate_message`, `search_iso_documents`, `list_supported_messages` and `explain_validation_error`.

Claude Code:

```bash
claude mcp add iso20022 -- uvx --from git+https://github.com/Yuussef/Iso20022-Mcp@v0.2.0 iso20022-mcp
```

Claude Desktop (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "iso20022": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/Yuussef/Iso20022-Mcp@v0.2.0", "iso20022-mcp"]
    }
  }
}
```

Then ask, for example: *"Check this pacs.008 for CBPR+ and explain what to fix"*, or *"What does this MT103 lose when converted to pacs.008?"*.

## Agent skill

[`skills/iso20022-payment-reviewer/SKILL.md`](skills/iso20022-payment-reviewer/SKILL.md) teaches an agent when to run `iso20022-check`, how to present the findings, and which facts and limits to state, such as the deferred end date for unstructured addresses. Build the uploadable zip with:

```bash
uv run python scripts/build_skill_zip.py
```

The script refuses to build when the front matter is missing, a file is too large, or anything looks like a credential.

## Current status

| Capability | Status |
| --- | --- |
| FastAPI health and schema-registry endpoints | Implemented |
| Secure XML parsing and local XSD validation | Implemented; includes a synthetic demo XSD, not an official ISO 20022 schema |
| SEPA Credit Transfer check (EPC 2025 rules, pacs.008 and pain.001) | Implemented; needs no XSD; synthetic samples included |
| IBAN (ISO 13616 registry + mod-97) and BIC (ISO 9362) validation | Implemented; offline, format only |
| CBPR+ pacs.008 check (UETR, single transaction, charges, ISO 4217 decimals, IBAN/BIC, characters) | Implemented; needs no XSD; synthetic samples included |
| Payment summary (parties, amounts, bank chain, remittance) for pacs.008 and pain.001 | Implemented |
| MT103 → pacs.008 draft with a field-by-field conversion report | Implemented; migration aid, not a certified translator |
| Rejects, statuses and returns (pacs.002, pain.002, pacs.004) explained with ISO reason codes, SEPA/CBPR+ rules and matching to the original payment | Implemented |
| Reader for any ISO 20022 message (camt.053/054 entries and balances, codes, references) | Implemented; describes, does not validate |
| CBPR+ postal address check (structured / hybrid / unstructured) | Implemented; included in the CBPR+ check |
| Local source manifest and keyword search with provenance links | Implemented; starter corpus contains six original project notes |
| React dashboard, validator form, address check, XML file upload, search UI | Implemented |
| MCP server exposing shared domain operations over stdio | Implemented; install the optional `ai` dependencies |
| Bedrock Converse client invoking MCP tools and returning sources | Implemented; requires AWS credentials and a configured model with tool use |
| Starter evaluation cases | `data/evaluations/starter.jsonl` runs in the test suite; measured metrics are next |

The registry includes one synthetic demo schema so you can exercise the validator; it is not an official ISO 20022 schema. No official ISO message version is bundled. Add an approved XSD and register its exact message ID before validating real ISO message structures. The app never downloads a schema or guesses a version. The starter search is lexical keyword matching, not embeddings or semantic RAG. The optional AI path is disabled until configured and needs the `ai` dependency extra.

## Why this project

Payment developers need to inspect message structure, understand validation errors, and find the documentation that applies to a particular message version. PayDoc AI demonstrates how a senior software engineer can combine backend engineering, payment-domain experience, MCP, and grounded AI while keeping validation deterministic.

## Features

- **Version-explicit validation:** choose a registered message ID such as `pacs.008.001.08`; the server validates against its local XSD.
- **Structured diagnostics:** return schema/parser error code, message, line, column, and XPath when available.
- **CBPR+ pacs.008 check:** UETR, one transaction per message, DEBT/CRED/SHAR and charges information, ISO 4217 decimals, IBAN/BIC validity, the CBPR+ character set and postal addresses (see [below](#cbpr-pacs008-check)).
- **Payment summary:** who pays whom, how much, through which banks and why, for people and agents.
- **Rejects, statuses and returns:** explain a pacs.002, pain.002 or pacs.004 with the official ISO reason codes, check the SEPA (EPC) and CBPR+ rules, and match each status to the original payment (see [below](#rejects-statuses-and-returns)).
- **Read any message:** restate any ISO 20022 message (statements, notifications, investigations…) with its references, amounts, parties, explained codes, entries and balances.
- **MT103 → pacs.008:** draft the CBPR+ pacs.008 from an MT103 and report, field by field, what is mapped, defaulted, left unstructured, truncated or lost; the draft is then checked against CBPR+ (see [below](#mt103--pacs008-conversion)).
- **SEPA Credit Transfer check:** apply the EPC 2025 SCT rules that an XSD cannot enforce, such as euro-only amounts, SLEV, IBAN-only accounts and the non-EEA debtor address rule (see [below](#sepa-credit-transfer-check)).
- **IBAN and BIC validation:** national length and structure from the Swift IBAN Registry, mod-97 check digits, ISO 9362 BIC format, test BICs and SEPA membership. Offline, so it proves the format, not that the account exists.
- **CBPR+ postal address check:** classify every `PstlAdr` as structured, hybrid or unstructured and report rule violations with severity, XPath and a suggested fix (see [below](#cbpr-postal-address-check)).
- **Safe XML parsing:** disable network access, entity resolution, and DTD loading; reject any DOCTYPE; cap XML input length.
- **Source-backed lookup:** search local Markdown references and return a source ID, excerpt, and provenance link.
- **MCP tools:** list versions, validate a message, check SEPA credit transfers, CBPR+ pacs.008 and postal addresses, explain rejects and returns, read any message, summarise a payment, convert an MT103, validate IBANs and BICs, search local documents, and look up evidence related to an error.
- **Optional AI assistant:** Bedrock receives tool definitions through the MCP SDK and surfaces returned sources; it does not decide whether XML passes the XSD.
- **React + FastAPI:** a responsive dashboard, validator, knowledge search, and assistant call the real API.

XSD validation only checks the constraints represented by the chosen schema. It does not prove compliance with scheme-specific, community, or bank usage guidelines. ISO 20022 itself notes that implementation requirements depend on the community using a message. See the [official FAQ](https://www.iso20022.org/faq).

## SEPA Credit Transfer check

`POST /api/v1/checks/sepa-sct` (MCP tool `check_sepa_sct`) checks a pacs.008 (interbank) or pain.001 (customer to bank) against the EPC 2025 SCT implementation guidelines. It needs no XSD.

| Rule | Severity | What it catches |
| --- | --- | --- |
| `SEPA_CURRENCY`, `SEPA_AMOUNT_RANGE`, `SEPA_AMOUNT_DECIMALS` | error | Non-euro amount, outside 0.01 – 999 999 999.99, more than two decimals |
| `SEPA_CHARGE_BEARER` | error | Charge bearer other than `SLEV` (mandatory in pacs.008) |
| `SEPA_SERVICE_LEVEL`, `SEPA_SERVICE_LEVEL_MISSING` | error | Service level other than `SEPA`, or none |
| `SEPA_ACCOUNT_NOT_IBAN`, `SEPA_IBAN_*`, `SEPA_IBAN_OUTSIDE_SEPA` | error | Account not an IBAN, invalid IBAN, or IBAN country outside SEPA |
| `SEPA_AGENT_NOT_BIC`, `SEPA_BIC_*` | error | Agent identified by anything other than a valid `BICFI` |
| `SEPA_REFERENCE_FORMAT` | error | Identifier outside the Latin set, starting or ending with `/`, or containing `//` |
| `SEPA_CHARACTER_SET` | warning | Names, remittance or address lines outside the Latin set (allowed only by agreement) |
| `SEPA_NAME_*`, `SEPA_PARTY_MISSING` | error | Missing debtor or creditor, or name over 70 characters |
| `SEPA_REMITTANCE_*` | error | Both structured and unstructured, repeated, or over 140 characters |
| `SEPA_ADDRESS_*` | error / warning | EPC structured, hybrid and unstructured address rules; unstructured is a warning while the end date is deferred |
| `SEPA_DEBTOR_ADDRESS_REQUIRED`, `SEPA_ADDRESS_COUNTRY_REQUIRED` | error | Debtor address and country missing when an agent is in a non-EEA SEPA country (for example CH or GB) |

**Address end date.** The EPC planned to stop unstructured addresses in November 2026. In September 2026 it [delayed that end date](https://www.europeanpaymentscouncil.eu/sites/default/files/kb/file/2026-09/EPC153-22%20v2.2%20EPC%20guidance%20document%20-%20Provision%20of%20Addresses%20under%20the%20EPC%20Payment%20Schemes.pdf) for all five EPC schemes without setting a new one. Set `enforce_unstructured_address_removal` to simulate it.

Sources: the [EPC SCT rulebook and implementation guidelines](https://www.europeanpaymentscouncil.eu/what-we-do/epc-payment-schemes/sepa-credit-transfer-sct/sepa-credit-transfer-rulebook-and) (EPC115-06 and EPC132-08, 2025 v1.0), [EPC409-09 v8.0](https://www.europeanpaymentscouncil.eu/document-library/other/epc-list-sepa-scheme-countries) for SEPA countries, and the [Swift IBAN Registry](https://www.swift.com/standards/data-standards/iban-international-bank-account-number) in [`data/reference/`](data/reference). The check covers EPC usage rules only; a bank or clearing house may add its own.

`POST /api/v1/identifiers/iban` and `/identifiers/bic` (MCP tools `validate_iban`, `validate_bic`) validate a single identifier. Synthetic samples are in [`examples/sepa/`](examples/sepa).

## CBPR+ pacs.008 check

`POST /api/v1/checks/cbpr-pacs008` (MCP tool `check_cbpr_pacs008`) checks a cross-border pacs.008 against CBPR+ usage rules and includes the postal address check below. `POST /api/v1/summaries/payment` (MCP tool `summarize_payment`) restates a pacs.008 or pain.001 as parties, amounts, dates, charges, the chain of banks and the remittance information.

| Rule | Severity | What it catches |
| --- | --- | --- |
| `CBPR_SINGLE_TRANSACTION` | error | `NbOfTxs` other than 1, or more than one transaction |
| `CBPR_UETR_MISSING`, `CBPR_UETR_FORMAT` | error | No UETR, or not a lower-case UUID version 4 |
| `CBPR_CHARGE_BEARER` | error | Missing, or not DEBT, CRED or SHAR (SLEV is SEPA-only) |
| `CBPR_CHARGES_INFO_REQUIRED` | error | No charges information with CRED, with SHAR after a deduction, or with DEBT and prepaid charges |
| `CBPR_CURRENCY_DECIMALS`, `CBPR_CURRENCY_UNKNOWN` | error | More decimals than ISO 4217 allows (e.g. JPY 1500.5), or an unknown currency |
| `CBPR_IBAN_*`, `CBPR_BIC_*` | error | Invalid IBAN or BIC anywhere in the transaction |
| `CBPR_CHARACTER_SET` | warning | Text outside the CBPR+ character set |
| `CBPR_ADDR_*` | error / warning | Postal address rules (next section) |

Sources: the CBPR+ pacs.008.001.08 guideline as published on the [Goldman Sachs developer portal](https://developer.gs.com/docs/services/transaction-banking/cbpr+-pacs008/), the [Clearstream CBPR+ user guide](https://www.clearstream.com/caas/v1/media/4814538/data/ca917a93e9390d399c6c34ebe14032d0/cbpr-ug.pdf) (UETR mandatory in pacs.008), and ISO 4217 List One from [SIX](https://www.six-group.com/en/products-services/financial-information/market-reference-data/data-standards.html) in [`data/reference/iso4217.json`](data/reference/iso4217.json). Bank-specific rules are not applied. Samples are in [`examples/cbpr/`](examples/cbpr).

## MT103 → pacs.008 conversion

`POST /api/v1/convert/mt103` (MCP tool `convert_mt103_to_pacs008`) reads an MT103, with or without its `{1:}{2:}{3:}{4:}` blocks, and drafts a CBPR+ pacs.008.001.08. Every field gets a report line with a status: `mapped`, `defaulted`, `unstructured`, `truncated`, `missing` or `unmapped`. The draft then goes through `check_cbpr_pacs008`, so the gaps that MT data leaves become visible. A legacy MT103 with no UETR and free-text addresses, for example, fails the UETR rule and gets unstructured-address warnings.

| MT103 | pacs.008 |
| --- | --- |
| `{3:{121:…}}` | `PmtId/UETR` |
| `:20:` | `GrpHdr/MsgId`, `PmtId/InstrId` |
| `/ROC/` in `:70:` or `:72:` | `PmtId/EndToEndId` (otherwise `NOTPROVIDED`) |
| `:32A:` / `:33B:` / `:36:` | `IntrBkSttlmDt` + `IntrBkSttlmAmt` / `InstdAmt` / `XchgRate` |
| `:50A/F/K:` / `:59/59A/59F:` | `Dbtr` + `DbtrAcct` / `Cdtr` + `CdtrAcct` (option F gives a hybrid address; K stays unstructured) |
| `:52a:` / `:56A:` / `:57a:` | `DbtrAgt` / `IntrmyAgt1` / `CdtrAgt` |
| `:71A:` OUR / BEN / SHA | `ChrgBr` DEBT / CRED / SHAR |
| `:71F:` / `:71G:` | `ChrgsInf` (agent `NOTPROVIDED`) |
| `:70:` | `RmtInf/Ustrd` (140 characters) |
| `:72:` `/ACC/` / other codes | `InstrForCdtrAgt` / `InstrForNxtAgt` |

The mapping follows public bank guides: [Barclays MT103 vs pacs.008](https://www.barclayscorporate.com/content/dam/barclayscorporate-com/images/insights/innovation/ISO-Further-information-slides-15-16-18.pdf), [J.P. Morgan ISO 20022 mapping guide](https://www.jpmorgan.com/content/dam/jpmorgan/documents/payments/iso20022-mapping-guide.pdf) and the [Bank of Jamaica RTGS annex](https://boj.org.jm/wp-content/uploads/2024/02/Annex-I-Hybrid-Outputs.pdf). It is a **migration aid, not a certified Swift translation**: Swift's official translation rules are on MyStandards. Samples are in [`examples/mt103/`](examples/mt103).

## Rejects, statuses and returns

`POST /api/v1/explain/status` (MCP tool `explain_payment_status`) explains a **pacs.002** or **pain.002** status report or a **pacs.004** return. Pass the original pacs.008 or pain.001 as `original_xml` to match each status to its payment: by UETR first, then end-to-end, transaction or instruction identification. The amounts are compared too.

- **Every code is explained** from the ISO 20022 External Code Sets (release 2Q2026, in [`data/reference/iso_external_codes.json`](data/reference/iso_external_codes.json)): transaction and group statuses (RJCT, ACSC, PART…), status reasons (AC01, AM04…) and return reasons (AC04, MD07…).
- **SEPA rules** (EPC SCT Inter-PSP IG 2025):
  - a reject uses status RJCT, one reason with its originator, a reason from the EPC reject list (AM04 is not one of them), and the original end-to-end and transaction identifications;
  - a return uses a reason from the EPC return list, SLEV, and the returned amount equal to the original amount in euro.
- **CBPR+ rules:**
  - the original UETR is mandatory and must be a lower-case UUID v4;
  - with group status RJCT, every transaction must be RJCT;
  - a reject without a reason is a warning, because the reason is optional in CBPR+.
- `scheme` is detected (SEPA when SLEV or service level SEPA appears, CBPR+ when an original UETR appears) or forced with `sepa`, `cbpr` or `generic`.

`POST /api/v1/read` (MCP tool `read_iso20022_message`) describes **any** ISO 20022 message: its name and purpose, business application and group headers, references, amounts, parties and banks, status and reason codes with their meaning, statement entries with credit and debit totals, balances, and a structure outline. It says which tool can check the message. It does not validate it.

Samples are in [`examples/status/`](examples/status) and [`examples/read/`](examples/read).

## CBPR+ postal address check

The ISO 20022 XSD accepts addresses that CBPR+ rejects. `POST /api/v1/checks/postal-address` (and the MCP tool `check_cbpr_postal_addresses`) inspects every `PstlAdr` in a message and needs no schema file.

| Rule | Severity | What it catches |
| --- | --- | --- |
| `CBPR_ADDR_UNSTRUCTURED` | warning (error with `enforce_unstructured_removal`) | Address made only of `AdrLine` free text |
| `CBPR_ADDR_TOWN_MISSING` / `CBPR_ADDR_COUNTRY_MISSING` | error | Structured or hybrid address without `TwnNm` or `Ctry` |
| `CBPR_ADDR_TOO_MANY_LINES` | error | Hybrid address with more than two `AdrLine` |
| `CBPR_ADDR_TOO_LONG` | error | Element longer than its CBPR+ limit (`TwnNm` 35, `PstCd` 16, `AdrLine` 70, …) |
| `CBPR_ADDR_COUNTRY_FORMAT` | error | `Ctry` that is not a two-letter upper-case ISO 3166 code |
| `CBPR_ADDR_POSTCODE_IN_TOWN` | warning | Post code mapped into `TwnNm` (for example `75001 Paris`) |
| `CBPR_ADDR_DUPLICATED_IN_LINE` | warning | Hybrid `AdrLine` repeating the town already in `TwnNm` |
| `CBPR_ADDR_AGENT_HAS_BIC` | info | Agent identified by BIC, where the BIC alone is a valid option |

**Deadline status.** Swift planned to remove unstructured addresses from CBPR+ payment messages on 14 November 2026 (SR2026). On 27 August 2026 Swift [deferred all SR2026 payments changes](https://www.swift.com/insights/news/swift-accepts-community-request-extend-structured-address-migration-iso-20022-payment-messages), with new timing to be announced by December 2026. Unstructured addresses are therefore reported as warnings by default; set `enforce_unstructured_removal` to `true` to simulate the removal. Reporting and admin messages (camt.052/053/054/060, camt.025, admi.024) are out of scope, as in the [Swift FAQ](https://www.swift.com/standards/iso-20022/iso-20022-faqs/iso-20022-removal-unstructured-address).

Rules come from the Swift FAQ and news above and from the CBPR+ pacs.008.001.08 usage guideline as published on the [Goldman Sachs developer portal](https://developer.gs.com/docs/services/transaction-banking/cbpr+-pacs008/). They cover postal addresses only, not the rest of the message. Check the current CBPR+ usage guidelines on Swift MyStandards before relying on them.

```bash
curl -X POST http://127.0.0.1:8000/api/v1/checks/postal-address \
  -H "Content-Type: application/json" \
  -d "$(jq -Rs '{xml: .}' examples/postal-address/problems.xml)"
```

Synthetic samples are in [`examples/postal-address/`](examples/postal-address): `structured.xml`, `hybrid.xml` and `problems.xml`.

## Architecture

```text
React + Vite browser app
  ├── GET  /api/v1/health
  ├── GET  /api/v1/messages
  ├── POST /api/v1/validate ──> local, versioned XSD
  ├── POST /api/v1/checks/sepa-sct ──> EPC SEPA Credit Transfer rules (no XSD needed)
  ├── POST /api/v1/checks/cbpr-pacs008 ──> CBPR+ rules + addresses (no XSD needed)
  ├── POST /api/v1/summaries/payment ──> parties, amounts, bank chain
  ├── POST /api/v1/convert/mt103 ──> pacs.008 draft + conversion report + CBPR+ check
  ├── POST /api/v1/explain/status ──> pacs.002 / pain.002 / pacs.004 + ISO reason codes
  ├── POST /api/v1/read ──> any ISO 20022 message described
  ├── POST /api/v1/checks/postal-address ──> CBPR+ address rules (no XSD needed)
  ├── POST /api/v1/identifiers/{iban,bic} ──> IBAN Registry + mod-97, ISO 9362
  ├── POST /api/v1/search   ──> local sources + provenance
  └── POST /api/v1/ask      ──> Bedrock Converse ──> MCP client ──> MCP tools

Independent MCP stdio server ──> same Python domain services <── in-memory MCP client + Bedrock Converse
```

The MCP server and HTTP API call the same validation/search service functions in `app/services/`. The Bedrock adapter uses an in-memory MCP client; the server can also run independently over stdio for an MCP host.

## Requirements

- Python 3.11 or later
- [uv](https://docs.astral.sh/uv/)
- Node.js 22 or later and npm
- Git
- One local ISO 20022 XSD for the validation workflow (manual setup below)
- Optional: AWS Bedrock access and credentials for the AI assistant

## Run locally

### 1. Start the API

From the repository root:

```bash
uv sync
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

The API is at `http://127.0.0.1:8000`; interactive OpenAPI docs are at `http://127.0.0.1:8000/docs`.

To enable the model-backed assistant, install the optional dependencies and configure a Bedrock model that supports Converse tool use:

```bash
uv sync --extra ai
```

Set `BEDROCK_MODEL_ID` and `AWS_REGION` in your local `.env` or shell. The app uses the AWS SDK credential provider chain; follow your approved AWS login flow. Do not include confidential or customer data in assistant prompts.

### 2. Start the React app

In a second terminal:

```bash
cd frontend
npm ci
npm run dev
```

Open the local URL printed by Vite (normally `http://127.0.0.1:5173`). The Vite development server proxies `/api` to the FastAPI server on port 8000. `frontend/package-lock.json` is committed; use `npm ci` instead of `npm install` for an exact, reproducible install.

### Windows PowerShell

The same commands work in PowerShell. If you need a local environment file, copy the template with `Copy-Item .env.example .env`. Never add `.env` or credentials to Git.

## Deploy a free demo

The project includes a Render Blueprint for a single FastAPI web service that also serves the built React app. To deploy it, open the [Render Blueprint creation page](https://dashboard.render.com/blueprint/new?repo=https://github.com/Yuussef/Iso20022-Mcp), connect the public GitHub repository, and create the Blueprint. Render builds the frontend and API from `render.yaml` and assigns an `onrender.com` URL.

The free web service can spin down after 15 minutes without requests, so the first visit after inactivity may take a little longer. This is a portfolio demo: do not submit real payment messages, customer information, or confidential documents. No ISO XSD or AWS credentials are included; validation needs a schema you are permitted to use, and the AI assistant stays disabled until configured.

## Add a permitted local ISO 20022 schema

1. To verify the demo, choose `demo.000.001.01` in the validator and click **Load demo XML**. It should pass the bundled synthetic schema. This sample is not ISO 20022.
2. For a real message, visit the [official ISO 20022 Message Definitions catalogue](https://www.iso20022.org/iso-20022-message-definitions) and filter to the Payments domain.
3. Select one message definition and record its **complete identifier and version**. Start with one `pacs.008` version only; do not mix versions in a registry entry.
4. From the relevant message set, obtain the XSD and the smallest useful official reference document. ISO notes that message-set documentation (such as MDRs/MUGs) is provided at message-set level, while each message definition has its own schema.
5. Review the terms for the files. Put the XSD in `data/schemas/` for local use. `.gitignore` excludes downloaded `*.xsd` files by default; do not force-add third-party files unless their terms permit redistribution.
6. Edit `data/schemas/registry.json` with the **actual** identifier and filename from the catalogue:

   ```json
   {
     "pacs.008.001.08": {
       "title": "FinancialInstitutionToFinancialInstitutionCustomerCreditTransferV08",
       "file": "pacs.008.001.08.xsd"
     }
   }
   ```

   These values show the registry shape only. Confirm that the selected official version and downloaded filename really match; update both if they do not.

7. Restart neither API nor UI: the API reads the registry on each request. Refresh the dashboard; the version appears when its local XSD is present.
8. Use synthetic XML for validation. A missing/unregistered XSD returns HTTP `409` with setup guidance; malformed XML returns a deterministic invalid result; XSD failures return diagnostics.

If the local schema package uses XSD imports/includes, keep the required companion schemas beside it and verify that the selected XSD resolves them from the local directory. Do not point the registry to an arbitrary user-uploaded path.

## API examples

Health:

```bash
curl http://127.0.0.1:8000/api/v1/health
```

List registered versions and whether their local XSD is present:

```bash
curl http://127.0.0.1:8000/api/v1/messages
```

Validate a synthetic XML message. This abbreviated sample illustrates the request shape; its expected XSD result depends on the exact schema version you install:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/validate \
  -H "Content-Type: application/json" \
  --data-binary @examples/validate-request.json
```

Search the starter corpus:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/search \
  -H "Content-Type: application/json" \
  --data-binary @examples/search-request.json
```

Validation request JSON is in [`examples/validate-request.json`](examples/validate-request.json), and a search request is in [`examples/search-request.json`](examples/search-request.json). Search scores are simple matched-keyword counts; they are not confidence scores.

Ask the optional assistant and launch the independent MCP server:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/ask \
  -H "Content-Type: application/json" \
  -d '{"question":"How should I interpret this validation error?"}'

uv run --extra ai python -m app.mcp_server.server
uv run --extra ai mcp dev app/mcp_server/server.py
```

In PowerShell, use `curl.exe` (not the `curl` alias) and keep each request on one line, for example: `curl.exe -X POST http://127.0.0.1:8000/api/v1/search -H "Content-Type: application/json" --data-binary "@examples/search-request.json"`. The MCP Inspector also needs Node.js and `npx` on `PATH`.

## Tests

The test suite uses only the bundled synthetic schema and starter corpus; it needs no ISO files, AWS credentials, or network access.

```bash
uv sync --extra dev --extra ai
uv run pytest
uv run ruff check app tests
```

The MCP server test is skipped when the optional `ai` extra is not installed. `tests/test_evaluations.py` runs every case in `data/evaluations/starter.jsonl` as a regression test. CI runs the same checks on Python 3.11 and 3.12 and builds the frontend.

## Detailed roadmap: MCP + grounded LLM

### Step 1 — Load a small, traceable corpus

- Use one official `pacs.008` XSD version and one or two permitted reference documents.
- Keep the complete message ID/version with all schema, document, and retrieval metadata.
- Expand `data/knowledge/sources.json` with a stable ID, document title, version/message ID (when specific), official URL, local filename, and retrieval date.
- Preserve headings and page/section references during extraction so citations can identify where a passage came from.
- Keep restricted source files out of Git unless redistribution is allowed. Commit the manifest, original project notes, ingestion code, and instructions instead.
- Add more message versions only after version-filtered retrieval and validation work correctly.

### Step 2 — Extract reusable deterministic services

- XSD validation, registry loading, and document lookup live in `app/services/` and are shared by HTTP and MCP adapters.
- Add richer ingestion/search (section and page retention, chunking, and eventually embedding-based retrieval) without changing the service contract.
- Return stable machine-readable errors for malformed XML, unknown message versions, unavailable schemas, and XSD failures.
- Keep schema selection allowlisted; disable external entity/network resolution and apply request/result limits.

### Step 3 — Expose the services through MCP

The server uses the [official MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk), is an optional `ai` dependency extra, and defaults to local stdio transport. The server and Bedrock client are implemented, and the test suite exercises every tool through the in-memory MCP client; Inspector verification remains to be added.

Initial tools:

| Tool | Inputs | Result |
| --- | --- | --- |
| `list_supported_messages` | none | Registered message IDs/versions and local schema availability |
| `validate_message` | `message_id`, `xml` | Deterministic validity and structured diagnostics |
| `check_cbpr_postal_addresses` | `xml`, optional `enforce_unstructured_removal` | Per-address format and CBPR+ findings with XPath and suggested fix |
| `check_sepa_sct` | `xml`, optional `enforce_unstructured_address_removal` | Per-transaction EPC SCT findings with XPath and suggested fix |
| `validate_iban` / `validate_bic` | `iban` / `bic` | Format, structure, check digits, parts and SEPA membership |
| `check_cbpr_pacs008` | `xml`, optional `enforce_unstructured_removal` | CBPR+ message, transaction and address findings |
| `summarize_payment` | `xml` | Parties, amounts, dates, charges, bank chain and remittance for pacs.008 or pain.001 |
| `convert_mt103_to_pacs008` | `mt103` | pacs.008 draft, field-by-field report and CBPR+ check of the draft |
| `explain_payment_status` | `xml`, optional `original_xml`, `scheme` | Statuses and reasons explained, SEPA/CBPR+ findings, match with the original payment |
| `read_iso20022_message` | `xml` | Any message restated: references, amounts, parties, codes, entries, balances, outline |
| `search_iso_documents` | `query`, optional `message_id`, `limit` | Excerpts with source ID, version, section/page, and provenance |
| `explain_validation_error` | `message_id`, error details | Matching source excerpts; no invented rule when no source matches |

The tools return structured results. The MCP server provides tools; it does not call the model itself. The Bedrock client supplies the model's tool calls to the MCP client and passes results back through Converse.

### Step 4 — Connect the optional LLM client

- The React assistant calls FastAPI `/api/v1/ask`; `app/llm/bedrock.py` uses the official in-memory MCP client and AWS Bedrock Converse tool use.
- Keep provider-specific orchestration isolated; add another adapter only when needed.
- Let the client discover tools, send the user's question and tool definitions to the model, validate model tool arguments, execute requested MCP calls, and return tool results for a final explanation.
- Require the answer to cite only source IDs actually returned by search. If retrieval has no relevant evidence, say so.
- Display deterministic validation status/errors separately from generated explanation.
- Keep this feature optional: core validation/search must work without model credentials.
- Store credentials only in the normal AWS credential chain or ignored environment configuration. Never commit keys, prompts containing sensitive data, or customer XML.

### Step 5 — Expand samples and evaluate behavior

- Add synthetic valid and invalid XML fixtures for the exact selected XSD version: malformed XML, missing required content, invalid code/value, and unsupported version.
- Derive each expected validation outcome by running the deterministic validator against the local schema; do not guess expected results.
- A starter JSONL set is in `data/evaluations/starter.jsonl`; expand it with cases for the selected schema, expected source IDs, and criteria for a correct answer. Keep copyrighted excerpts out unless their terms permit it.
- Track validation expected-result accuracy, retrieval hit@k/recall@k, version-filter correctness, citation correctness, and manually reviewed grounded-answer quality.
- Measure latency and model/token cost for the LLM path only if it is implemented.
- Publish measured results with the dataset size and limitations. Do not state targets or performance numbers before running the evaluation.

## Example expected behavior

### Deterministic validation

Input: synthetic XML and an explicitly registered message version.

Expected: a JSON result containing that message ID, `valid: true|false`, a result kind, and structured diagnostics. A parser error, unsupported version, unavailable XSD, and schema error are distinct conditions. The exact XSD diagnostics depend on the downloaded version and parser.

### Grounded assistant

Question: “Why did this synthetic `pacs.008` message fail validation?”

Expected flow: call `validate_message` → search for the relevant field/rule → explain the validator's result → cite returned source IDs → clearly state that XSD validity does not prove scheme or bank compliance. If no source supports the explanation, say it cannot be confirmed from the loaded corpus.

## Data handling and limits

- Use synthetic sample messages only. Do not use production payment traffic or internal employer documentation.
- Keep downloaded XSDs/documents local unless redistribution terms explicitly permit committing them.
- Do not commit `.env`, API keys, AWS credentials, or private source documents.
- Treat retrieved document text and XML as untrusted data, never as instructions for the model.
- XSD validity is not scheme-level or institution-level compliance.
- The current search is basic token overlap over local Markdown; it is not semantic RAG and should not be described as such.

## Publish to GitHub

This project is published at [github.com/Yuussef/Iso20022-Mcp](https://github.com/Yuussef/Iso20022-Mcp). Clone it with:

```bash
git clone https://github.com/Yuussef/Iso20022-Mcp.git
cd Iso20022-Mcp
```

To publish later changes, commit them on `main` and run `git push`. Do not force-add local XSDs or `.env` files; `.gitignore` excludes them by default. `frontend/package-lock.json` is committed, so use `npm ci` for reproducible installs.

## References

- [ISO 20022 Message Definitions catalogue](https://www.iso20022.org/iso-20022-message-definitions)
- [ISO 20022 Catalogue of Messages](https://www.iso20022.org/catalogue-messages)
- [ISO 20022 FAQ](https://www.iso20022.org/faq)
- [Model Context Protocol](https://modelcontextprotocol.io/)
- [Official MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)

## License and source-data note

The original project code is released under the [MIT License](LICENSE). This license does not automatically grant redistribution rights to ISO schemas, message reports, or other third-party materials. Keep source files, provenance, and their terms clearly documented and separate from original code.
