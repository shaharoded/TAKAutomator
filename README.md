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
- 📁 Saves valid TAKs to organized folders and tracks progress in a registry file (`tak_registry.json`).

---

## 📦 Project Structure

```bash
TAKAutomator/
│
├── Config/                      # Configuration files (paths, constants, engine)
├── tak_automator.py            # Main automation logic (TAKAutomator class)
├── llm_agent.py                # LLM agent wrapper for OpenAI API
├── tak_ok.py                   # TAK validation logic (schema + business rules)
├── excel_ok.py                 # Excel validation logic
├── tak_templates/              # Templates for each TAK concept type (used for LLM guidance)
├── sample_tak.xml              # Optional test file
├── tak_registry.json           # Local tracking of already-generated TAKs
├── requirements.txt            # Python dependencies
└── README.md
```

## Installation

### Prerequisites

- Python 3.7 or higher

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
venv\Scripts\activate
```

3. Install dependencies:

```bash
pip install -r requirements.txt
```

4. Pushing to git (after initiating the folder and connecting to git):

```bash
git add .
git commit -m "Commit message"
git push -u origin main
```