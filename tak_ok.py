from lxml import etree
from typing import Tuple
import pandas as pd

# Local Code
from Config.validator_config import ValidatorConfig


class TAKok:
    """
    TAKok is a validation class that verifies TAK XML files both against the provided XSD schema
    and cross-checks their structure and content with business logic defined in an Excel configuration file.
    
    The class ensures:
    - Structural validity using XML Schema (XSD)
    - Business rule consistency by comparing with taks.xlsx definitions
    
    Attributes:
        schema (etree.XMLSchema): Compiled XML schema for validation
        excel (dict): Dictionary of DataFrames from Excel, keyed by sheet name
    """

    def __init__(self, schema_path: str, excel_path: str):
        """
        Initialize TAKok with paths to the schema and the business logic Excel file.

        Args:
            schema_path (str): Path to the XML schema (.xsd)
            excel_path (str): Path to the business logic Excel file (e.g., taks.xlsx)

        Raises:
            RuntimeError: If schema or Excel cannot be loaded
        """
        try:
            self.schema_doc = etree.parse(schema_path)
            self.schema = etree.XMLSchema(self.schema_doc)
        except Exception as e:
            raise RuntimeError(f"Failed to load schema from {schema_path}: {e}")

        try:
            self.excel = pd.read_excel(excel_path, sheet_name=None, dtype=str)
        except Exception as e:
            raise RuntimeError(f"Failed to load Excel from {excel_path}: {e}")

    def validate(self, tak_text: str) -> Tuple[bool, str]:
        """
        Validate a TAK XML string against both the schema and business rules.

        Args:
            tak_text (str): The TAK XML content as a string

        Returns:
            Tuple[bool, str]: (True, "Valid") if valid, otherwise (False, reason)
        """
        try:
            doc = etree.fromstring(tak_text.encode('utf-8'))
        except etree.XMLSyntaxError as e:
            return False, f"XML syntax error: {e}"

        if not self.schema.validate(doc):
            errors = [str(error) for error in self.schema.error_log]
            return False, "Schema validation errors: " + "; ".join(errors)

        root_tag = doc.tag
        tak_id = doc.get("id")
        sheet = self._get_sheet_for_tag(root_tag)

        if sheet is None:
            return False, f"Unrecognized TAK type with root tag <{root_tag}>."

        df = self.excel[sheet]
        row = df[df['ID'] == tak_id]
        if row.empty:
            return False, f"No matching ID '{tak_id}' found in sheet '{sheet}'."

        row = row.iloc[0]
        errors = []

        # Business Logic Checks
        if sheet == "raw_concepts":
            typ = row.get("TYPE", "").lower()
            if typ == "raw-numeric":
                if doc.find(".//numeric-allowed-values") is None:
                    errors.append("Missing <numeric-allowed-values> for raw-numeric concept.")
            elif typ == "raw-nominal":
                if doc.find(".//nominal-allowed-values") is None:
                    errors.append("Missing <nominal-allowed-values> for raw-nominal concept.")

        elif sheet == "states":
            derived_from = row.get("DERIVED_FROM")
            if doc.find(".//derived-from") is None:
                errors.append("Missing <derived-from> block in state.")
            if pd.notna(row.get("MAPPING")) and row.get("MAPPING").strip():
                if doc.find(".//mapping-function") is None:
                    errors.append("Missing <mapping-function> element despite MAPPING specified in Excel.")

        elif sheet == "events":
            if doc.find(".//attributes") is None:
                errors.append("Missing <attributes> block in event.")

        if errors:
            return False, "; ".join(errors)

        return True, "Valid"

    def _get_sheet_for_tag(self, tag: str) -> str:
        """
        Internal helper to map root XML tag to Excel sheet name.

        Args:
            tag (str): Root tag from the TAK XML (e.g., 'state')

        Returns:
            str: Corresponding sheet name (e.g., 'states') or None if unknown
        """
        tag_to_sheet = {
            "numeric-raw-concept": "raw_concepts",
            "nominal-raw-concept": "raw_concepts",
            "state": "states",
            "event": "events"
        }
        return tag_to_sheet.get(tag)


if __name__ == "__main__":
    import sys

    try:
        with open("sample_tak.xml", "r", encoding="utf-8") as f:
            sample_tak = f.read()
    except Exception as e:
        sys.exit(f"Error reading sample TAK file: {e}")

    try:
        validator = TAKok(ValidatorConfig.SCHEMA_PATH, ValidatorConfig.EXCEL_PATH)
    except RuntimeError as e:
        sys.exit(f"Initialization error: {e}")

    valid, message = validator.validate(sample_tak)
    if valid:
        print("TAK file is valid!")
    else:
        print("TAK file is invalid:", message)