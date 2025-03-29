import os
from lxml import etree
import pandas as pd
import json

# Local Code
from Config.validator_config import ValidatorConfig
from Config.agent_config import AgentConfig
from tak_ok import TAKok
from excel_ok import Excelok
from llm_agent import LLMAgent


class TAKAutomator:
    """
    Automates the generation and validation of TAK (Temporal Abstraction Knowledge) XML files.
    
    This class uses an LLM to generate TAKs from structured Excel data, validates them using
    a schema and business rules, and writes the resulting XML files to disk. It avoids regenerating
    already processed TAKs using a local registry file.
    """
    def __init__(self):
        """
        Initialize the TAKAutomator with maximum LLM retry attempts.
        """
        self.schema_path = ValidatorConfig.SCHEMA_PATH
        self.excel_path = ValidatorConfig.EXCEL_PATH
        self.max_iters = AgentConfig.MAX_ITERS
        self.excel_validator = Excelok(self.excel_path)
        self.tak_validator = TAKok(self.schema_path, self.excel_path)
        self.llm = LLMAgent()
        self.registry_path = "tak_registry.json"
        self.registry = self._load_registry()
    
    def _load_registry(self):
        """
        Load the registry of previously created TAKs to prevent duplication.
        """
        if os.path.exists(self.registry_path):
            with open(self.registry_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}

    def _save_registry(self):
        """
        Save the TAK registry to disk.
        """
        with open(self.registry_path, 'w', encoding='utf-8') as f:
            json.dump(self.registry, f, indent=2)

    def run(self, test_mode=False):
        """
        Main workflow to process the Excel file and create TAK files.
        
        Args:
            test_mode (bool): If True, only processes a single TAK for testing purposes.
        """
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
                
                if tak_id in self.registry:
                    print(f"[SKIP]: TAK {tak_id} already generated as {self.registry[tak_id]}")
                    continue

                for i in range(self.max_iters):
                    prompt = self._build_prompt(sheet, row, feedback, prev_outputs)
                    tak_text = self.llm.generate_response(prompt)
                    prev_outputs.append(tak_text)

                    valid, message = self.tak_validator.validate(tak_text, tak_id)
                    print(f"[GENERATED TAK VALIDATION MESSAGE]: {message}")
                    if valid:
                        filename = f"{sheet.upper()}_{tak_name}.xml"
                        self._write_file(sheet_folder, filename, tak_text)
                        self.registry[tak_id] = filename
                        self._save_registry()
                        break
                    elif i == self.max_iters - 1 or tak_text in prev_outputs[:-1]:
                        filename = f"{sheet.upper()}_INVALID_{tak_name}.xml"
                        self._write_file(sheet_folder, filename, tak_text)
                        self.registry[tak_id] = filename
                        self._save_registry()
                        print(f"[WARNING]: Saved invalid TAK for manual check: {filename}. Errors: {message}")
                    else:
                        feedback = message
                    
                if test_mode:
                    print("[TEST MODE]: Exiting after first TAK. Bye.")
                    return

    def _write_file(self, folder: str, filename: str, content: str):
        """
        Save a TAK file to disk.

        Args:
            folder (str): Target directory.
            filename (str): File name.
            content (str): XML content to write.
        """
        with open(os.path.join(folder, filename), 'w', encoding='utf-8') as f:
            f.write(content)
            
    def _extract_schema_for_type(self, schema_path: str, concept_type: str) -> str:
        """
        Extract only the relevant part of the schema corresponding to the TAK type.

        Args:
            schema_path (str): Path to the schema file.
            concept_type (str): TAK concept type (e.g. 'state', 'numeric-raw-concept').

        Returns:
            str: XML string of the relevant schema section.

        Raises:
            ValueError: If the concept type is not found in the schema.
        """
        tree = etree.parse(schema_path)
        root = tree.getroot()
        
        for element in root.findall(".//{http://www.w3.org/2001/XMLSchema}element"):
            if element.get("name") == concept_type:
                return etree.tostring(element, pretty_print=True, encoding='unicode')
        
        raise ValueError(f"Concept type '{concept_type}' not found in schema.")

    def _build_prompt(self, sheet: str, row: pd.Series, feedback: str, previous: list) -> str:
        """
        Build a complete prompt for the LLM based on Excel row and prior context.

        Args:
            sheet (str): Current sheet name (e.g., 'raw_concepts').
            row (pd.Series): The row containing TAK data.
            feedback (str): Feedback from previous LLM attempts.
            previous (list): List of previous TAK generations.

        Returns:
            str: A full prompt string to be sent to the LLM.
        """
        concept_type = sheet if sheet in ["states", "events"] else row.get("TYPE", "").strip()
        schema_fragment = self._extract_schema_for_type(ValidatorConfig.SCHEMA_PATH, concept_type)
        
        parts = [
            f"You are creating a TAK file of type '{concept_type}', named '{row['TAK_NAME']}' with ID '{row['ID']}'.",
            "Please follow this XML schema fragment to ensure the structure is valid:",
            schema_fragment,
            "Below is the Excel row defining all business logic fields. You must reflect this information in the XML accurately:",
            row.to_json(),
            "Ensure all mandatory blocks from the schema are present, even if empty. For example: <categories>, <synonyms>, <clippers>, etc.",
            "For nominal-raw-concept: include <nominal-allowed-values> with nested <persistence> and <values> blocks. Wrap each allowed value in <nominal-allowed-value>.",
            "For persistence: include both global and local persistence with their required attributes (e.g., granularity, behavior)."
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
    automator = TAKAutomator()
    automator.run(test_mode=True)