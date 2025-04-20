import pandas as pd
import os

def get_template(sheet:str, row: pd.Series) -> str:
    """
    Loads the appropriate XML template from the `tak_templates` directory.

    Args:
        sheet (str): The Excel sheet name (e.g., 'raw_concepts')
        row (pd.Series): The processed row from the Excel sheet

    Returns:
        str: Contents of the XML template with placeholders
        bool: True if the template exists, False otherwise
    """
    # Get correct template
    if sheet == "raw_concepts":
        template = row.get("TYPE", "").lower()
    elif sheet == "states":
        if row.get("MAPPING"):
            template = 'state-from-numeric'
        else:
            template = 'state-from-nominal'
    else:
        # Default to sheet_name template without trailing 's
        template = sheet[:-1] 
    template_path = os.path.join("tak_templates", f"{template}.xml")
    if os.path.exists(template_path):
        with open(template_path, 'r', encoding='utf-8') as f:
            return f.read()
    raise FileNotFoundError(f"No template available for '{template}'")