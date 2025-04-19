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
├── TAKs/                       # Srotes the generated TAK files (auto-generated duting run())
├── tak_automator.py            # Main automation logic (TAKAutomator class)
├── llm_agent.py                # LLM agent wrapper for OpenAI API
├── tak_ok.py                   # TAK validation logic (schema + business rules)
├── excel_ok.py                 # Excel validation logic
├── main.py                     # API activation and package compression.
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
- Modular: easy to extend with new concept types or logic rules - just add relevant functions and templates, and extend the Excel

## TO-DOs and Improvements

1. Improve schema parsing for automated structure generation instead of relying on XML templates
2. Extend support for additional TAK types:
    - pattern
    - trends
    - states to non-numeric concepts? No format / validation at the moment
    - states and contexts can only handle 1 inducer/derived ID at the moment. To expand we'll need to enhance the logic.
3. Validation problem in TAKok for raw_concepts, as it will sometime fail to find the actual value in the XML to compare against the Excel, which will result in a warning that is not true. This happens because the validation function fails to correctly retrieve all of the values that should appear in the template from the generated TAK. Mostly annoying but harmless. These TAKs will be saved with the prefix _VALIDATE_ so you can manually monitor them. Happens mostry in `numeric-raw-concept` files where some values are under tricky hierarchies.

## Notes
- Templates are stored under `tak_templates/` and must match Excel concept types
- The generated XMLs are validated using the schema provided in ValidatorConfig.SCHEMA_PATH

## GIT Commit Tips
Once you've made changes, commit and push as usual:

```bash
git add .
git commit -m "Commit message"
git push -u origin main
```