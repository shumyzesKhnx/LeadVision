# Phase 3 — Your ideal customers

Phase 2 saved **who you are and what you sell**. Phase 3 saves **which customers you want**. ICP means **ideal customer profile**. You can create more than one profile for your agency.

Implemented requirements: FR-03–05 and configuration portions of SCORE-01–04, DATA-02 and SEM-03/04. This phase stores rules; it does not analyze or score companies yet.

## 1. Create a customer profile

The server is running. Refresh [Swagger](http://127.0.0.1:8000/docs), then find **Customer profiles (ICP)**.

Open **POST /api/v1/icps → Try it out**. Replace the entire request body with this:

```json
{
  "name": "UK software companies",
  "target_text": "UK software companies with 20 to 100 employees that need a better website.",
  "criteria": {
    "industries": ["software"],
    "countries": ["GB"],
    "employee_min": 20,
    "employee_max": 100
  },
  "desired_needs": ["Website redesign"]
}
```

Click **Execute**. Expect **201**. Scroll to **Response body**. Copy the profile's top-level `id`, without quotation marks, for later steps. This is the **ICP ID**, not your agency or service ID.

The example means: “I want UK software companies with 20–100 employees that could need website redesign.” `GB` is the country code for the United Kingdom; `UK` is accepted and saved as `GB`.

## 2. View it

Open **GET /api/v1/icps → Try it out → Execute**. Find the profile under **Response body → items**.

You can also use **GET /api/v1/icps/{icp_id}**, entering the copied ICP ID. Expect **200**.

The response includes two different numbers:

| Field | Meaning |
|---|---|
| Top-level `revision` | Changes when you edit the profile, including its name or archive status. Use it in If-Match. |
| `current_version.version` | Changes only when customer criteria or scoring settings change. Older configurations remain saved. |

## 3. Change the customer description

Open **PATCH /api/v1/icps/{icp_id} → Try it out**. Enter the ICP ID. In **If-Match**, enter `"1"`, including the quotes, if its current revision is still 1.

Replace the entire body with:

```json
{
  "target_text": "UK software companies with 20 to 100 employees that need website redesign and SEO."
}
```

Execute. Expect **200**, revision **2**, and current configuration version **2**. Unmentioned fields stay unchanged.

Open **GET /api/v1/icps/{icp_id}/versions**, enter the same ID, and Execute. In **Response body → items**, version 2 appears first and version 1 remains unchanged below it.

Use the latest top-level revision for subsequent edits. Old revisions return **409 EDIT_CONFLICT**; a missing If-Match returns **428**. Reload with GET before retrying.

## Other settings, when you need them

- **Archive:** PATCH `{"archived": true}` with the current revision. Archived profiles disappear from the default list; set `include_archived=true` to see them. PATCH `{"archived": false}` to reactivate. History stays saved.
- **Weights:** Default importance is industry 25, geography 20, size 15, semantic/text similarity 40 and visual 0. They are relative weights. Criteria you have not selected are excluded from the scoring denominator. At least one applicable component must have positive weight. Positive semantic weight requires target text.
- **Thresholds:** High starts at 75, Medium at 50, and minimum evidence coverage is 0.6 (60%). These settings will be used by later scoring modules.
- **Exclusions:** Optional `exclusions.industries` and `exclusions.countries` contain explicit excluded values. Optional exclusion employee bounds describe a forbidden range, including its endpoints. Missing bounds are open-ended. Future matching only enforces exclusions against known/reviewed facts, not model guesses.
- **Preferences:** `preferences_text` is guidance for future semantic analysis. Writing “exclude country X” here does not create an enforced exclusion. Use structured exclusions instead.
- **Vocabulary:** GET `/api/v1/icps/options` shows valid country codes, region presets and industry synonyms. Industry labels are lowercased with spaces normalized; SaaS maps to software. Regions are explicit presets: `uk`, `eu`, `north_america` and `gcc`; the options response lists their exact country sets. Arbitrary industry labels are supported with exact matching.
- **Nested objects:** PATCH replaces a supplied `criteria`, `exclusions`, `weights` or `thresholds` object completely. Include all settings you want to retain inside it. Omitted members take defaults. Top-level omitted fields stay unchanged. Empty lists/text clear optional selections; size bounds can be null. Required top-level objects cannot be null.
- **Visual scoring:** Remains disabled. An invented calibration ID cannot enable it; reviewed calibration is a later prerequisite.

Do not create the example repeatedly unless you want several profiles. Unlike the singleton agency, multiple ICPs are allowed.

## Verification and limits

**126 tests passed**, including the previous 90 checks. New checks cover canonical criteria, invalid ranges/weights/thresholds, known-fact exclusions, immutable history, archive/reactivation, pagination, edit conflicts, concurrent edits, rollback and persistence after restart. Schema 2 → 3 upgrade tests preserve agency/service records and roll back injected upgrade failures.

The real database was snapshotted before upgrading. Live health, Swagger, OpenAPI and ICP listing returned **200**; health reported application **0.3.0**, schema **3** and database ready. Exact agency/service record fingerprints matched before/after the upgrade, and the foreign-key check was clean. No example ICP was inserted into your real database by implementation tests.

Weights-only edits change the full configuration hash while retaining the semantic-input hash. Target text, desired needs or preference edits also change the semantic-input hash. Name/archive edits do not append an analytical version. Identical normalized edits do not increase revision or add history.

The edit response's `invalidation` describes configuration changes for this operation, not a permanent result status. Phase 4 now reports actual linked campaign counts; result counts stay zero until analysis/scoring tables exist. Later analysis/score modules must compare their saved version ID with the profile's current version and integrate affected-result counts. Archived profiles cannot be selected for new work through the shared service guard.

Run the checks again with `scripts/test.ps1`. Records remain saved after server restart. Next: **Phase 4 — campaigns**, where you organize a group of prospects around a customer profile.
