# TAKAutomator

A smart pipeline that leverages GPT to generate and validate Temporal Abstraction Knowledge (TAK) XML files based on structured business logic and schema constraints. TAKAutomator simplifies and automates the process of authoring complex TAK files for knowledge-driven systems, ensuring schema compliance and organizational business rules.

---

## 🧠 What It Does

TAKAutomator:
- 🧾 Reads structured definitions from an Excel file (e.g., TAK ID, concept type, persistence, etc.).
- 🔍 Extracts schema rules and templates to guide TAK XML structure.
- 🧠 Uses a local LLM agent (e.g., OpenAI GPT) to generate XML output that matches schema and business logic.
- ✅ Validates output against schema and Excel-based constraints using dual validation (`TAKok`, `Excelok`).
- 🔄 Iteratively corrects and retries generation based on feedback.
- 📁 Saves valid TAKs to organized folders and tracks progress in a registry file (`tak_registry.json`), and compress them as zip for deployment upon request (`main.py`).

---

## 📦 Project Structure

```bash
TAKAutomator/
│
├── Config/                      # Configuration files (paths,constants, engine)
├── tak_automator.py            # Main automation logic (TAKAutomator class)
├── llm_agent.py                # LLM agent wrapper for OpenAI API
├── tak_ok.py                   # TAK validation logic (schema + business rules)
├── excel_ok.py                 # Excel validation logic
├── main.py                     # API activation and package compression.
├── tak_templates/              # Templates for each TAK concept type (used for LLM guidance)
├── tak_registry.json           # Local tracking of already-generated TAKs
├── requirements.txt            # Python dependencies
└── README.md
```

## Installation
### Prerequisites

- Python 3.7 or higher
- Access to OpenAI API (a `secret_keys.py` file)
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

4. Comfigure validator and agent in `Config.agent_config.py` and `Config.validator_config.py`


## Usage

- The tool will validate the Excel file.
- Iterate through required sheets (raw_concepts, states, events).
- Generate TAK XMLs one by one using GPT, validating each.
- Valid TAKs are saved in TAKs/<sheet_name>/ folders.
- Invalid TAKs are also saved with _INVALID_ suffix for manual review.

To test with a single TAK and avoid burning LLM quota, run in test mode:

```bash
automator.run(test_mode=True)
```

## Features

- Dual-level validation (XSD schema + business logic)
- Token tracking for LLM cost-awareness
- Retry mechanism with feedback on failed generation
- Persistent tracking via JSON registry
- Template-driven prompting (improves LLM accuracy)
- Modular: easy to extend with new concept types or logic rules

## TO-DOs and Improvements

1. Improve schema parsing for automated structure generation instead of relying on XML templates
2. Extend support for additional TAK types:
    - pattern
    - trends
    - states to non-numeric concepts? No format / validation at the moment
    - states and contexts can only handle 1 inducer/derived ID at the moment. To expand we'll need to enhance the logic.
3. Range states still needs some work, as the LLM outputs non-covering ranges (for example, multiple `x >= thresh_i` for multiple thresholds in a row, causing the abstraction to ignore some state values). `TAKok` enforces and notify on these restrictions but the model is slow to adapt.

## Notes
- Templates are stored under tak_templates/ and must match Excel concept types.
- The generated XMLs are validated using the schema provided in ValidatorConfig.SCHEMA_PATH.

## GIT Commit Tips
Once you've made changes, commit and push as usual:

```bash
git add .
git commit -m "Commit message"
git push -u origin main
```