import os
from lxml import etree
import pandas as pd

# Local Code
from Config.validator_config import ValidatorConfig
from Config.agent_config import AgentConfig
from tak_ok import TAKok
from excel_ok import Excelok
from llm_agent import LLMAgent


class TAKAutomator:
    def __init__(self, max_iters: int):
        self.schema_path = ValidatorConfig.SCHEMA_PATH
        self.excel_path = ValidatorConfig.EXCEL_PATH
        self.max_iters = max_iters
        self.excel_validator = Excelok(self.excel_path)
        self.tak_validator = TAKok(self.schema_path, self.excel_path)
        self.llm = LLMAgent()

    def run(self):
        valid, msg = self.excel_validator.validate()
        if not valid:
            print(f"[ERROR]: Excel validation failed: {msg}")
            return

        excel = pd.read_excel(self.excel_path, sheet_name=None, dtype=str)
        os.makedirs("TAKs", exist_ok=True)

        for sheet in ValidatorConfig.REQUIRED_SHEETS:
            if sheet not in excel:
                continue

            df = excel[sheet].dropna(how='all')
            if df.shape[0] <= 1:
                continue

            sheet_folder = os.path.join("TAKs", sheet)
            os.makedirs(sheet_folder, exist_ok=True)

            for _, row in df.iterrows():
                tak_id = row['ID']
                tak_name = row['TAK_NAME']
                prev_outputs = []
                feedback = ""

                for i in range(self.max_iters):
                    prompt = self._build_prompt(sheet, row, feedback, prev_outputs)
                    tak_text = self.llm.generate_response(prompt)
                    prev_outputs.append(tak_text)

                    valid, message = self.tak_validator.validate(tak_text, tak_id)
                    if valid:
                        filename = f"{sheet.upper()}_{tak_name}.xml"
                        self._write_file(sheet_folder, filename, tak_text)
                        break
                    elif i == self.max_iters - 1 or tak_text in prev_outputs[:-1]:
                        filename = f"{sheet.upper()}_INVALID_{tak_name}.xml"
                        self._write_file(sheet_folder, filename, tak_text)
                        print(f"[WARNING]: Saved invalid TAK for manual check: {filename}. Errors: {message}")
                    else:
                        feedback = message
                return "This is just a test"

    def _write_file(self, folder: str, filename: str, content: str):
        with open(os.path.join(folder, filename), 'w', encoding='utf-8') as f:
            f.write(content)
            
    def _extract_schema_for_type(self, schema_path: str, concept_type: str) -> str:
        """
        Extract only the schema portion relevant to a given concept type (e.g., 'state', 'numeric-raw-concept').
        Returns it as a string (XML).
        """
        tree = etree.parse(schema_path)
        root = tree.getroot()
        
        for element in root.findall(".//{http://www.w3.org/2001/XMLSchema}element"):
            if element.get("name") == concept_type:
                return etree.tostring(element, pretty_print=True, encoding='unicode')
        
        raise ValueError(f"Concept type '{concept_type}' not found in schema.")

    def _build_prompt(self, sheet: str, row: pd.Series, feedback: str, previous: list) -> str:
        concept_type = sheet if sheet in ["states", "events"] else row.get("TYPE", "").strip()
        schema_fragment = self._extract_schema_for_type(ValidatorConfig.SCHEMA_PATH, concept_type)
        
        parts = [
            f"You are creating a TAK file of type '{sheet}', named '{row['TAK_NAME']}' with ID '{row['ID']}'.",
            f"Please use the official TAK schema and structure it accordingly. Here is the relevant schema section:",
            schema_fragment,
            "\nRefer to the following business logic requirements and structure accordingly:",
            row.to_json()
        ]

        # Add schema and business logic instructions placeholder
        parts.append("Refer to the following business logic requirements and structure accordingly.")
        parts.append(row.to_json())

        if feedback:
            parts.append("\nPrevious attempt had the following issues:")
            parts.append(feedback)

        if previous:
            parts.append("\nHere is the previous version that had issues:")
            parts.append(previous[-1])

        return "\n\n".join(parts)
    

if __name__ == "__main__":
    automator = TAKAutomator(max_iters=AgentConfig.MAX_ITERS)
    automator.run()