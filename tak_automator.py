import os
import json
import pandas as pd

# Local Code
from Config.validator_config import ValidatorConfig
from tak_ok import TAKok
from excel_ok import Excelok
from llm_agent import LLMAgent


class TAKAutomator:
    def __init__(self, max_iters: int):
        self.max_iters = max_iters
        self.llm = LLMAgent()
        self.excel_validator = Excelok(ValidatorConfig.EXCEL_PATH)
        self.tak_validator = TAKok(ValidatorConfig.SCHEMA_PATH, ValidatorConfig.EXCEL_PATH)
        self.excel = pd.read_excel(ValidatorConfig.EXCEL_PATH, sheet_name=None, dtype=str)

    def run(self):
        valid, msg = self.excel_validator.validate()
        if not valid:
            print("Excel validation failed:", msg)
            return

        os.makedirs("TAKs", exist_ok=True)

        for sheet in ValidatorConfig.REQUIRED_SHEETS:
            if sheet not in self.excel or self.excel[sheet].dropna(how='all').shape[0] <= 1:
                continue  # skip empty or missing sheet

            os.makedirs(f"TAKs/{sheet}", exist_ok=True)
            df = self.excel[sheet]

            for _, row in df.iterrows():
                tak_name = row['TAK_NAME']
                tak_id = row['ID']
                concept_type = sheet[:-1].upper()  # raw_concepts -> RAW, events -> EVENT, etc.
                prev_outputs = set()
                feedback = ""
                prompt = self._build_prompt(row, sheet)

                for attempt in range(self.max_iters):
                    gen_text = self.llm.generate_response(prompt)

                    if gen_text in prev_outputs:
                        print(f"Stuck in loop for {tak_name}, saving as INVALID.")
                        break

                    prev_outputs.add(gen_text)
                    valid, validation_msg = self.tak_validator.validate(gen_text)

                    if valid:
                        filename = f"TAKs/{sheet}/{concept_type}_{tak_name}.xml"
                        with open(filename, 'w', encoding='utf-8') as f:
                            f.write(gen_text)
                        break
                    else:
                        feedback = validation_msg
                        prompt = self._build_prompt(row, sheet, previous_attempt=gen_text, feedback=feedback)
                else:
                    filename = f"TAKs/{sheet}/{concept_type}_INVALID_{tak_name}.xml"
                    with open(filename, 'w', encoding='utf-8') as f:
                        f.write(gen_text)
                    print(f"Saved invalid TAK for verification: {filename}\nErrors: {feedback}")

    def _build_prompt(self, row, sheet, previous_attempt: str = None, feedback: str = None) -> str:
        metadata = row.to_dict()
        system_instruction = ""  # Use the SYSTEM_PROMPT already in ReaderConfig
        data_block = json.dumps(metadata, indent=2)

        additions = ""
        if feedback:
            additions += f"\n<!-- Previous attempt had issues: {feedback} -->"
        if previous_attempt:
            additions += f"\n<!-- Previous XML attempt:\n{previous_attempt}\n-->"

        return f"""
You are provided with a TAK specification in JSON form. Based on this, generate a valid XML that matches the TAK schema.
{additions}

TAK Specification:
{data_block}
"""


if __name__ == "__main__":
    automator = TAKAutomator(max_iters=3)
    automator.run()