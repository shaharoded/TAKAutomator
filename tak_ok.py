import json
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
            elif typ == "time-raw-concept" and doc.find(".//time-allowed-values") is None:
                issues.append("Missing <time-allowed-values> for time-raw-concept.")

        elif sheet == "states":
            if doc.find(".//derived-from") is None:
                issues.append("Missing <derived-from> block in state.")
            if pd.notna(row.get("MAPPING")) and row.get("MAPPING").strip():
                if doc.find(".//mapping-function") is None:
                    issues.append("Missing <mapping-function> element despite MAPPING specified in Excel.")
                else:
                    try:
                        # Parse Excel MAPPING column as a list of [min, max] lists
                        excel_bins = json.loads(row["MAPPING"])
                        excel_bins = [(float(b[0]), float(b[1])) for b in excel_bins if isinstance(b, list) and len(b) == 2]
                    except Exception as e:
                        issues.append(f"Failed to parse Excel MAPPING as bins: {e}")
                        excel_bins = []

                    # Add threshold logic validation
                    issues += self._validate_state_range_coverage(doc, excel_bins)

        elif sheet == "events":
            if doc.find(".//Attributes") is None:
                issues.append("Missing <Attributes> block in event.")
        
        elif sheet == "contexts":
            inducers = doc.findall(".//inducer-entity")
            if not inducers:
                issues.append("Missing <inducer-entity> block in context.")

            for inducer in inducers:
                has_from = inducer.find(".//from") is not None
                has_until = inducer.find(".//until") is not None
                if not (has_from or has_until):
                    issues.append(f"Inducer {inducer.get('id')} must have at least <from> or <until> block.")

                for tag in ["from", "until"]:
                    tag_block = inducer.find(tag)
                    if tag_block is not None:
                        tg = tag_block.find(".//time-gap")
                        if tg is None or not tg.get("value") or not tg.get("granularity"):
                            issues.append(f"{tag.title()} block in inducer {inducer.get('id')} missing value or granularity.")

            clippers = doc.findall(".//clipper-entity")
            for clipper in clippers:
                if clipper.find(".//from") is None or clipper.find(".//time-gap") is None:
                    issues.append(f"Clipper {clipper.get('id')} is missing <from> or <time-gap>.")
                else:
                    tg = clipper.find(".//time-gap")
                    if not tg.get("value") or not tg.get("granularity"):
                        issues.append(f"Clipper {clipper.get('id')} has invalid <time-gap> settings.")

        if issues:
            return False, "Business logic issues: " + "; ".join(issues)

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
            "time-raw-concept": "raw_concepts",
            "state": "states",
            "event": "events",
            "pattern": "patterns",
            "context": "contexts",
            "scenario": "scenarios"
        }
        return tag_to_sheet.get(tag)
    
    # def _validate_state_range_coverage(self, doc: etree._Element) -> List[str]:
    #     """
    #     Validates bin coverage in a <state> TAK's <mapping-function>. Ensures:
    #     - Each bin has a valid comparison or logical structure.
    #     - Bin descriptions are printed clearly (e.g., "x < 54", "70 <= x < 140").
    #     - The full numeric range is covered without overlaps or gaps.

    #     Returns:
    #         List[str]: List of issues found, including faulty bins and problematic transitions.
    #     """
    #     def op_symbol(op: str) -> str:
    #         return {
    #             "smaller": "<",
    #             "smaller-equal": "<=",
    #             "bigger": ">",
    #             "bigger-equal": ">=",
    #             "equal": "==",
    #             "not-equal": "!="
    #         }.get(op, op)

    #     def is_overlap(upper: Tuple[float, str], lower: Tuple[float, str]) -> bool:
    #         if not upper or not lower:
    #             return False
    #         val_u, op_u = upper
    #         val_l, op_l = lower

    #         if val_u > val_l:
    #             return True
    #         if val_u < val_l:
    #             return False

    #         # Same value — check if both allow equality
    #         return op_u in ("smaller-equal", "==") and op_l in ("bigger-equal", "==")

    #     def is_gap(upper: Tuple[float, str], lower: Tuple[float, str]) -> bool:
    #         if not upper or not lower:
    #             return False
    #         val_u, op_u = upper
    #         val_l, op_l = lower

    #         if val_u < val_l:
    #             # Check if there's a gap between the ranges
    #             return not (op_u in ("smaller-equal", "==") or op_l in ("bigger-equal", "=="))
    #         return False  # val_u >= val_l → no gap

    #     issues = []
    #     bins = doc.findall(".//mapping-function-2-value")
    #     ranges = []

    #     if not bins:
    #         return ["Missing <mapping-function-2-value> bins."]

    #     for idx, bin_elem in enumerate(bins):
    #         label = bin_elem.get("value", f"Bin {idx}")
    #         eval_tree = bin_elem.find(".//evaluation-tree")
    #         if eval_tree is None:
    #             issues.append(f"Bin {idx} ('{label}'): Missing <evaluation-tree>.")
    #             continue

    #         logic = eval_tree.find(".//logical-function")
    #         comp = eval_tree.find(".//comparison-function")
    #         lower = upper = None
    #         desc = ""

    #         if logic is not None:
    #             ops = logic.findall(".//comparison-function")
    #             for op in ops:
    #                 operator = op.get("comparison-operator")
    #                 val = float(op.findtext(".//double"))
    #                 if operator.startswith("bigger"):
    #                     lower = (val, operator)
    #                 elif operator.startswith("smaller"):
    #                     upper = (val, operator)
    #             if lower and upper:
    #                 desc = f"x {op_symbol(lower[1])} {lower[0]} AND x {op_symbol(upper[1])} {upper[0]}"
    #             else:
    #                 desc = "Invalid logical-function"
    #         elif comp is not None:
    #             operator = comp.get("comparison-operator")
    #             val = float(comp.findtext(".//double"))
    #             if operator.startswith("bigger"):
    #                 lower = (val, operator)
    #             elif operator.startswith("smaller"):
    #                 upper = (val, operator)
    #             desc = f"x {op_symbol(operator)} {val}"
    #         else:
    #             issues.append(f"Bin {idx} ('{label}'): No valid comparison or logic.")
    #             continue

    #         ranges.append({
    #             "idx": idx,
    #             "label": label,
    #             "lower": lower,
    #             "upper": upper,
    #             "description": desc
    #         })

    #     # Describe all ranges
    #     for r in ranges:
    #         issues.append(f"Bin {r['idx']} ('{r['label']}'): {r['description']}")

    #     # Sort by lower bound value
    #     sorted_ranges = sorted(ranges, key=lambda r: r['lower'][0] if r['lower'] else float('-inf'))

    #     # Check gaps and overlaps between adjacent bins
    #     for i in range(len(sorted_ranges) - 1):
    #         r1 = sorted_ranges[i]
    #         r2 = sorted_ranges[i + 1]
    #         upper1 = r1["upper"]
    #         lower2 = r2["lower"]

    #         if upper1 and lower2:
    #             print(f"🧪 Checking gap/overlap between Bin {r1['idx']} ('{r1['label']}') and Bin {r2['idx']} ('{r2['label']}')")
    #             print(f"    Upper: {upper1}, Lower: {lower2}")

    #             if is_overlap(upper1, lower2):
    #                 issues.append(
    #                     f"Range overlap: Bin {r1['idx']} ('{r1['label']}') and Bin {r2['idx']} ('{r2['label']}') "
    #                     f"overlap between {lower2[0]} and {upper1[0]}."
    #                 )
    #             elif is_gap(upper1, lower2):
    #                 issues.append(
    #                     f"Range gap: Bin {r1['idx']} ('{r1['label']}') ends at {upper1[0]}, "
    #                     f"but Bin {r2['idx']} ('{r2['label']}') starts at {lower2[0]}."
    #                 )

    #     return issues


    def _validate_state_range_coverage(self, doc: etree._Element, excel_bins: List[Tuple[float, float]]) -> List[str]:
        """
        Validates the <mapping-function> coverage in a <state> TAK:
        - All bins must follow the format: lower_bound <= x < upper_bound
        - Validates no overlaps or gaps between adjacent bins
        - Verifies the thresholds used in XML match those defined in Excel

        Args:
            doc: The parsed XML <state> element
            excel_bins: A list of (min, max) pairs from the Excel's MAPPING column

        Returns:
            A list of human-readable issues found in the XML definition.
        """
        def extract_bounds(bin_elem) -> Tuple[Tuple[float, str], Tuple[float, str]]:
            logic = bin_elem.find(".//logical-function")
            if logic is not None:
                comparisons = logic.findall(".//comparison-function")
                lower = upper = None
                for comp in comparisons:
                    op = comp.get("comparison-operator")
                    val = float(comp.findtext(".//double"))
                    if op.startswith("bigger"):
                        lower = (val, op)
                    elif op.startswith("smaller"):
                        upper = (val, op)
                return lower, upper
            return None, None

        def is_overlap(prev_upper, curr_lower):
            val_u, op_u = prev_upper
            val_l, op_l = curr_lower
            if val_u > val_l:
                return True
            elif val_u == val_l:
                return not (op_u == "smaller" and op_l == "bigger-equal")
            return False

        def is_gap(prev_upper, curr_lower):
            val_u, _ = prev_upper
            val_l, _ = curr_lower
            return val_u != val_l
        
        def describe_range(lower: Tuple[float, str], upper: Tuple[float, str]) -> str:
            """
            Convert a lower and upper bound with operators into a readable string like:
            '70 <= x < 140'
            """
            op_map = {
                "bigger": ">",
                "bigger-equal": ">=",
                "smaller": "<",
                "smaller-equal": "<="
            }
            lower_op = op_map.get(lower[1], lower[1])
            upper_op = op_map.get(upper[1], upper[1])
            return f"x {lower_op} {lower[0]} AND x {upper_op} {upper[0]}"

        issues = []
        bins = doc.findall(".//mapping-function-2-value")
        if not bins:
            return ["Missing <mapping-function-2-value> bins."]

        parsed_bins = []
        for idx, bin_elem in enumerate(bins):
            label = bin_elem.get("value", f"Bin {idx}")
            lower, upper = extract_bounds(bin_elem)

            if not lower or not upper:
                issues.append(f"Bin {idx} ('{label}') must contain BOTH lower and upper bounds using logical-function.")
                continue

            range_desc = describe_range(lower, upper)
            issues.append(f"Bin {idx} ('{label}') range: {range_desc}")
            parsed_bins.append({
                "idx": idx,
                "label": label,
                "lower": lower,
                "upper": upper,
                "desc": range_desc
            })

        # Sort bins by lower value
        sorted_bins = sorted(parsed_bins, key=lambda b: b["lower"][0])
        actual_issues = []

        for i in range(len(sorted_bins) - 1):
            b1 = sorted_bins[i]
            b2 = sorted_bins[i + 1]

            if is_overlap(b1["upper"], b2["lower"]):
                actual_issues.append(
                    f"Overlap between Bin {b1['idx']} ('{b1['label']}') [{b1['desc']}] and "
                    f"Bin {b2['idx']} ('{b2['label']}') [{b2['desc']}]."
                )
            elif is_gap(b1["upper"], b2["lower"]):
                actual_issues.append(
                    f"Gap between Bin {b1['idx']} ('{b1['label']}') [{b1['desc']}] and "
                    f"Bin {b2['idx']} ('{b2['label']}') [{b2['desc']}]."
                )

        xml_bounds_set = {round(b["lower"][0], 6) for b in sorted_bins}.union(
            {round(b["upper"][0], 6) for b in sorted_bins}
        )
        excel_bounds_set = {round(low, 6) for low, high in excel_bins}.union(
            {round(high, 6) for low, high in excel_bins}
        )

        missing_in_xml = excel_bounds_set - xml_bounds_set
        if missing_in_xml:
            actual_issues.append(f"Threshold mismatch: The following values exist in Excel but not in XML: {sorted(missing_in_xml)}")

        # Threshold value checks
        xml_bounds_set = {round(b["lower"][0], 6) for b in sorted_bins}.union(
            {round(b["upper"][0], 6) for b in sorted_bins}
        )
        excel_bounds_set = {round(low, 6) for low, high in excel_bins}.union(
            {round(high, 6) for low, high in excel_bins}
        )

        missing_from_excel = sorted(xml_bounds_set - excel_bounds_set)
        if missing_from_excel:
            actual_issues.append(f"These values are used in XML but not found in Excel MAPPING: {missing_from_excel}")

        # Only show range descriptions if there is a problem
        if actual_issues:
            bin_descriptions = [f"Bin {b['idx']} ('{b['label']}') range: {b['desc']}" for b in sorted_bins]
            return bin_descriptions + actual_issues
        return []


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