class GeneralConfig:
    """
    This class contains general configuration settings for the TAK Automator.
    """
    FILES_TO_REMOVE = [
        'RAW_CONCEPTS_BASAL_ROUTE.xml', 
        'RAW_CONCEPTS_BOLUS_ROUTE.xml',
        'BASAL_BITZUA_EVENT.xml',
        'BOLUS_BITZUA_EVENT.xml']  # You can hardcode or dynamically add known invalids here