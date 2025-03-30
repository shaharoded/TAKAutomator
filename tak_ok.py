from lxml import etree
from typing import Tuple, List
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

    def validate(self, tak_text: str, tak_id: str = None) -> Tuple[bool, str]:
        """
        Validate a TAK XML string against both the schema and business rules.

        Args:
            tak_text (str): The TAK XML content as a string
            tak_id (str, optional): TAK identifier. If None, will extract from XML.

        Returns:
            Tuple[bool, str]: 
                - (True, "Valid") if valid
                - (False, "Critical error: ...") for structural issues that should break the loop
                - (False, "Business issues: ...") for fixable problems LLM can iterate on
        """
        # === CRITICAL: Invalid XML ===
        try:
            doc = etree.fromstring(tak_text.encode('utf-8'))
        except etree.XMLSyntaxError as e:
            return False, f"Critical error: XML syntax error: {e}"

        # === CRITICAL: Schema invalid ===
        if not self.schema.validate(doc):
            errors = [str(error) for error in self.schema.error_log]
            return False, "Critical error: Schema validation errors: " + "; ".join(errors)

        # === CRITICAL: Type or ID mismatch ===
        root_tag = doc.tag
        tak_id_from_xml = doc.get("id")
        tak_id = tak_id or tak_id_from_xml

        if tak_id != tak_id_from_xml:
            return False, f"Critical error: TAK ID mismatch. Expected={tak_id}, but got={tak_id_from_xml} in XML."

        sheet = self._get_sheet_for_tag(root_tag)
        if sheet is None:
            return False, f"Critical error: Unrecognized TAK type with root tag <{root_tag}>."

        df = self.excel[sheet]
        row = df[df['ID'] == tak_id]
        if row.empty:
            return False, f"Critical error: No matching ID '{tak_id}' found in sheet '{sheet}'."

        # === BUSINESS LOGIC VALIDATION ===
        row = row.iloc[0]
        issues = []

        if sheet == "raw_concepts":
            typ = row.get("TYPE", "").lower()
            if typ == "numeric-raw-concept" and doc.find(".//numeric-allowed-values") is None:
                issues.append("Missing <numeric-allowed-values> for numeric-raw-concept.")
            elif typ == "nominal-raw-concept" and doc.find(".//nominal-allowed-values") is None:
                issues.append("Missing <nominal-allowed-values> for nominal-raw-concept.")

        elif sheet == "states":
            if doc.find(".//derived-from") is None:
                issues.append("Missing <derived-from> block in state.")
            if pd.notna(row.get("MAPPING")) and row.get("MAPPING").strip():
                if doc.find(".//mapping-function") is None:
                    issues.append("Missing <mapping-function> element despite MAPPING specified in Excel.")
                else:
                    # NEW: Add threshold logic validation
                    issues += self._validate_state_range_coverage(doc)

        elif sheet == "events":
            if doc.find(".//Attributes") is None:
                issues.append("Missing <Attributes> block in event.")

        if issues:
            return False, "Business issues: " + "; ".join(issues)

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
            "event": "events",
            "pattern": "patterns",
            "context": "contexts",
            "scenario": "scenarios"
        }
        return tag_to_sheet.get(tag)
    
    def _validate_state_range_coverage(self, doc: etree._Element) -> List[str]:
        """
        Validates that the mapping-function in a state TAK has proper bin range coverage.
        Ensures that:
        - The first bin is a lower-bound (e.g., x < threshold1)
        - The last bin is an upper-bound (e.g., x >= thresholdN)
        - Intermediate bins are ranges (e.g., x >= threshold1 and x < threshold2)

        Args:
            doc (etree._Element): Parsed XML tree for the TAK

        Returns:
            List[str]: List of any range-related issues found
        """
        issues = []

        bins = doc.findall(".//mapping-function-2-value")
        if not bins:
            return ["Missing <mapping-function-2-value> bins."]

        for idx, bin_elem in enumerate(bins):
            eval_tree = bin_elem.find(".//evaluation-tree")
            if eval_tree is None:
                issues.append(f"Bin {idx}: Missing <evaluation-tree>.")
                continue

            logic = eval_tree.find(".//logical-function")
            comp = eval_tree.find(".//comparison-function")

            if idx == 0:
                # Expect a single comparison like x < X
                if comp is None:
                    issues.append(f"Bin {idx}: Expected a single <comparison-function> for lower bound.")
                else:
                    op = comp.get("comparison-operator", "")
                    if op not in ("smaller", "smaller-equal"):
                        issues.append(f"Bin {idx}: Expected 'smaller' or 'smaller-equal' but got '{op}'.")
            elif idx == len(bins) - 1:
                # Expect a single comparison like x >= X
                if comp is None:
                    issues.append(f"Bin {idx}: Expected a single <comparison-function> for upper bound.")
                else:
                    op = comp.get("comparison-operator", "")
                    if op not in ("bigger", "bigger-equal"):
                        issues.append(f"Bin {idx}: Expected 'bigger' or 'bigger-equal' but got '{op}'.")
            else:
                # Expect a logical AND with two valid comparisons
                if logic is None:
                    issues.append(f"Bin {idx}: Expected <logical-function> with two range comparisons.")
                else:
                    operands = logic.findall(".//operand")
                    if len(operands) != 2:
                        issues.append(f"Bin {idx}: Logical function must contain exactly 2 operands.")
                        continue

                    ops = []
                    for operand in operands:
                        cmp_node = operand.find(".//comparison-function")
                        if cmp_node is not None:
                            ops.append(cmp_node.get("comparison-operator", ""))

                    if not any(op in ("bigger", "bigger-equal") for op in ops) or \
                    not any(op in ("smaller", "smaller-equal") for op in ops):
                        issues.append(f"Bin {idx}: Expected both lower and upper comparisons in logical function.")

        return issues


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