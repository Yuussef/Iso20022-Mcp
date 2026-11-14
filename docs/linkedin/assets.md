# Visuals to prepare for LinkedIn and Agensi

Use the synthetic samples only. Every BIC is a fictitious `DEMO…` code, and the IBANs are the IBAN Registry's published examples.

## Before you post

1. Merge the open PRs and check that CI is green.
2. Redeploy the Render demo and open each page once, since the free plan sleeps after 15 minutes.
3. Replace `[GitHub link]` and `[demo link]` in the post drafts.
4. The install commands are pinned to the `v0.2.0` tag. For a new release, bump `version` in `pyproject.toml`, tag `vX.Y.Z` on `main`, then update the `@v…` pins in the README and in `SKILL.md`. A test checks that the pins match the package version.

## Screenshots (1200 × 675 or 1080 × 1080)

| # | What | How |
| --- | --- | --- |
| 1 | **SEPA check** with "pacs.008 with problems": the red verdict and the list of EPC findings | Web app, **SEPA check** tab, click the sample, then **Check SEPA rules** |
| 2 | **CBPR+ check** with the valid sample: the payment route card (debtor → banks → creditor) and the green verdict | **CBPR+ check** tab, **Valid pacs.008** |
| 3 | **MT103 → pacs.008** with the legacy sample: the field mapping (MISSING, UNSTRUCTURED, TRUNCATED, NOT CARRIED) next to the draft XML | **MT103 → pacs.008** tab, **Legacy MT103** |
| 4 | Terminal: `iso20022-check examples/sepa/pacs008-problems.xml --profile sepa` | Shows that the same rules work in CI and scripts |

## GIF or short video (15–30 seconds)

Claude Desktop with the MCP server added (see the README):

1. Paste `examples/cbpr/pacs008-problems.xml` and ask: *"Will this cross-border payment be accepted? Explain what to fix."*
2. Show Claude calling `check_cbpr_pacs008` and listing the UETR, JPY decimals and SLEV findings.
3. Ask: *"And what would this MT103 look like as a pacs.008?"* with `examples/mt103/legacy-free-text.txt`.

Free tools: ScreenToGif (Windows) or the built-in recorder in Windows 11 (Win + Alt + R).

## Agensi listing

- **Upload:** `dist/iso20022-payment-reviewer.zip` (build it with `uv run python scripts/build_skill_zip.py`).
- **Title:** ISO 20022 Payment Reviewer: SEPA, CBPR+, MT103
- **Short description:** Offline checks for pacs.008, pain.001, MT103, IBAN and BIC against public EPC and CBPR+ rules, with plain-language explanations and fixes.
- **Category:** Development or Operations.
- **Price:** your choice. A free first version helps collect reviews; a paid version needs a connected payout method.
- **State clearly in the listing:**
  - one-time install from GitHub/PyPI, then offline;
  - no certified Swift translation;
  - synthetic data recommended.
