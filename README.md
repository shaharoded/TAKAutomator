# TAKAutomator

A smart pipeline that leverages `gpt-instruct` models to generate and validate Temporal Abstraction Knowledge (TAK) XML files based on structured business logic and schema constraints. TAKAutomator simplifies and automates the process of authoring complex TAK files for knowledge-driven systems, ensuring schema compliance and organizational business rules.

---

## 🧠 What It Does

TAKAutomator:
- 🧾 Reads structured definitions from an Excel file (e.g., TAK ID, concept type, persistence, etc.) - The business logic.
- 🔍 Extracts schema rules and templates using RAG to guide TAK XML structure.
- 🧠 Uses a local LLM agent (e.g., OpenAI GPT) to generate XML output that matches schema and business logic.
- ✅ Validates output against schema and the business logic constraints using dual validation (`TAKok`, `Excelok`).
- 🔄 Iteratively corrects and retries generation based on feedback.
- 📁 Saves valid TAKs to organized folders and tracks progress in a registry file (`tak_registry.json`), and compress them as zip for deployment upon request (`main.py`).

---

## 📦 Project Structure

```bash
TAKAutomator/
│
├── Config/                     # Configuration files (paths,constants, engine)
├────── agent_config.py         # Parameters file for LLM agent
├────── validator_config.py     # Parameters file for validator program
├────── general_config.py       # Parameters file for main program
├── TAKs/                       # Srotes the generated TAK files (auto-generated duting run())
├── tak_automator.py            # Main automation logic (TAKAutomator class)
├── llm_agent.py                # LLM agent wrapper for OpenAI API
├── tak_ok.py                   # TAK validation logic (schema + business rules)
├── excel_ok.py                 # Excel validation logic
├── main.py                     # API activation and package compression.
├── utils.py                    # A few utility functions shared accross modules
├── tak_templates/              # Templates for each TAK concept type (used for LLM guidance)
├── tak_registry.json           # Local tracking of already-generated TAKs (auto-generated duting run())
├── log_sheet.txt               # Log file to monitor errors / warnings.
├── requirements.txt            # Python dependencies
├── schema.xsd                  # A valid schema file used to validate the TAK files
├── schema_for_spyxml.txt       # The legacy schema in the lab. Non compatible with Python but compatible with SPY-XML
└── README.md
```

## Installation
### Prerequisites

- Python 3.7 or higher
- Access to OpenAI API (a `secret_keys.py` file) - Note it's structure based on the Client call in `llm_agent.py`
- A valid schema .xsd file
- A well-structured `taks.xlsx` file with proper TAK definitions

### Setup

1. Clone the repository:

```bash
git clone https://github.com/shaharoded/TAKAutomator.git
cd TAKAutomator
```

2. Create and activate a virtual environment:

```bash
# On Windows
python -m venv venv
.\venv\Scripts\Activate

# On macOS/Linux
python3 -m venv venv
source venv/bin/activate
```

3. Install dependencies:

```bash
pip install -r requirements.txt
```

4. Configure validator and agent in `Config.agent_config.py` and `Config.validator_config.py` based on your need.


## Usage

- The tool will validate the Excel file.
- Iterate through required sheets (`ValidatorConfig.REQUIRED_SHEETS`).
- Generate TAK XMLs one by one using GPT, validating each.
- Valid TAKs are saved in TAKs/<sheet_name>/ folders.
- Invalid TAKs are also saved with _INVALID_ substring for manual review. Rejects will be logged in `log_sheet.txt`.
- Possibly invalid TAKs are saved with _VALIDATE_ substring for manual review. These are caused because the validator was unable to parse the TAK hierarchy properly to find the Excel values. Rejects will be logged in `log_sheet.txt`.

To test with a single TAK and avoid burning LLM quota, run in test mode:

```bash
automator.run(test_mode=True)
```

## When to use each TAK type

| TAK Type | Purpose (What it models) | Derived From | Temporal? | Use When… | Key Fields to Set | Example |
|---|---|---|---|---|---|---|
| **Raw Concept** | A base measurable or categorical signal as captured in the source data. | Source system / raw feed. | N/A (foundation) | You need a canonical identifier and bounds/values for something you’ll reuse (labs, vitals, meds, events). | `TYPE` (numeric/nominal/time), allowed range or allowed values, units/scale. | GLUCOSE_LAB_MEASURE, HEART_RATE, INSULIN_BOLUS_DOSE. | 
| **State** | A discretization (binning) or label over a raw concept (or event attribute). | One raw concept (recommended) or a single event attribute. | Yes (as intervals) | You need clinically meaningful buckets (e.g., Low/Normal/High) or policy thresholds. | `DERIVED_FROM`, `STATE_LABELS`, `MAPPING` (bins cover full range, no gaps/overlaps). | GLUCOSE_MEASURE_STATE with 6 bins from severe hypo → hyper. |
| **Event** | A point or instantaneous occurrence (procedure, admin action) with optional attributes. | Triggers in source data (and zero or more raw attributes). | Point-in-time | You need to anchor patterns or contexts on something that “happens now”. | `ATTRIBUTES` (list of raw concept IDs), event metadata. | INSULIN_BOLUS_GIVEN with attribute DOSE. |
| **Context** | A time window derived from an inducer (event/state) that gates meaning of other abstractions. | One inducer (`INDUCER_ID`) + from/until rules (+ optional clipper). | Yes (as intervals) | Something is only relevant within a bounded window (e.g., “On Steroids”, “Post-Op Day 0–3”). | `INDUCER_ID`, `FROM_*`/`UNTIL_*` (bound, shift, granularity), optional `CLIPPER_*`. | “ON_STEROIDS_CONTEXT”: from STEROIDS_DOSAGE start until 7 days after last dose. |
| **Trend** | Directional change (INC/DEC/SAME) over a numeric raw concept across time. | One numeric raw concept (or numeric event attribute). | Yes (as intervals) | Clinical signal comes from **trajectory** rather than level (e.g., rising Troponin, falling BP). | `significant-variation` (Δ threshold), `time-steady value/granularity`, local/global persistence (good-before/after), derived-from ID. | TROPONIN_MEASURE_TREND with Δ≥20% over ≤12h, local persistence 6h/12h. |
| **Pattern** *(future)* | Composition of states/events/contexts/trends in specific order or logic. | Existing TAKs (as building blocks). | Yes (composable) | You need multi-step constructs (e.g., “hypotension despite fluids”, “rebound hyperglycemia”). | Temporal relations, sequence windows, logical operators. | “DKA_PATTERN”: Ketones high + glucose high + bicarbonate low with overlap. |
| **Scenario** *(future)* | High-level clinical storyline comprising multiple patterns and contexts. | Patterns + contexts + events. | Yes (long horizon) | You need coarse-grained pathways (“perioperative course”, “sepsis workup”). | Phase boundaries, entry/exit criteria. |

>> The Excel file has 2 additional sheets that are ignored by the automation: "not_included" and "flat_context", where the latter is a list of concepts that are not temporally important, are not a part of patterns, and should only be included for ML purposes (externally, as a 2D context vector) and not as a mediator output.

### Notes

**Trends: “time-steady” vs “local persistence”**
- **time-steady** = the minimum continuous duration a level/gradient must hold before we call it a trend (e.g., ≥12h of rising troponin).
- **local persistence** (*good-before / good-after*) = the stitching tolerance between adjacent qualifying points—how far apart two samples may be and still belong to the same trend interval.
  - **good-before**: how far back a prior point can be and still count as contiguous.
  - **good-after**: how far forward the next point can be and still keep the interval alive.
- In the XML, time units are expressed with the **`granularity`** attribute (not `unit`).
- Mental model: *time-steady* filters noisy blips; *local persistence* bridges sparse sampling.

**Contexts and Patterns**
- Certain contexts can replace the need for some states, like descriptions of "under influence".
- Try to properly define the correct difference between `flat_context` and `context`.
- If patterns are also calculated, you may want to move some of the `context` to the flat context vector, to avoid redundant tolkens describing the same thing. 

**What the Mediator emits vs what we train on**
- By default the Mediator emits **States**, **Trends**, **Contexts**, **Patterns** and suppresses **Events** and **Raw Concepts**.
- **Workflow we use**
  1. Define background/observational signals as **Context** concepts (e.g., “On statin”, “CKD present”).
  2. Allow **Patterns** to reference these Contexts during mining/validation.
  3. After mining, remove background Context intervals from the temporal output **unless** their timing is clinically useful, and copy their information into a static **[CTX]** vector (captured once in the first 24–48h) that we prepend to the model’s sequence.
  4. Keep time-bounded Contexts in the temporal stream only when their on/off timing is itself predictive (e.g., “On steroids (day 0–5)”).
  5. Treat **Events** as true point occurrences for modeling; if the Mediator suppressed them, re-inject them as point events in the output so the model can align sequences to clinical actions (e.g., Heart Attack at time T).
  6. Remove `Same` value from **TRENDS**. Since every trend has a state as well, no need for these.
  7. Be sure that nothing has an `End Time` after the discharge from hospital.

**Practical tips**
- Use Context → static **[CTX]** when the signal is relatively stable over the admission or mainly prognostic (e.g., baseline CKD, albumin in first 48h).
- Keep as temporal (State/Trend/Context) when the **timing or dynamics** matter for downstream decisions (e.g., rising ketones, hypotension despite fluids, “on vasopressors”).
- For **Trends**, pick `significant-variation` large enough to ignore noise but small enough to capture meaningful shifts; pair with a realistic `time-steady` for the lab’s sampling cadence, and set local persistence to bridge typical gaps in ordering frequency.


## Features

- Dual-level validation (XSD schema + business logic)
- Token tracking for LLM cost-awareness
- Retry mechanism with feedback on failed generation
- Persistent tracking via JSON registry
- Template-driven prompting (improves LLM accuracy)
- Modular: easy to extend with new concept types or logic rules - just add relevant functions and templates, and extend the Excel

## TO-DOs and Improvements

1. Extend support for additional TAK types:
    - patterns
    - scenarios
    - states and contexts can only handle 1 inducer/derived ID at the moment. To expand we'll need to enhance the logic.

NOTE: When defining new templates validation problems might happen in TAKok, as it will sometime fail to find the actual value in the XML to compare against the Excel, which will result in a warning that is not true. This happens because the validation function fails to correctly retrieve all of the values that should appear in the template from the generated TAK. These TAKs will be saved with the prefix _VALIDATE_ so you can manually monitor them. In order to solve locally, you'll need to update the param `ValidatorConfig.SPECIAL_FIELD_MAP` that contains direct paths to these problematic attributes.

## Notes
- Templates are stored under `tak_templates/` and must match Excel concept types (sheet names)
- The generated XMLs are validated using the schema provided in ValidatorConfig.SCHEMA_PATH

## GIT Commit Tips
Once you've made changes, commit and push as usual:

```bash
git add .
git commit -m "Commit message"
git push -u origin main
```