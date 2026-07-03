import logging
import frappe

def get_logger(module_name: str) -> logging.Logger:
    """Return a configured logger for proctor integration.

    In Frappe, logger prints to the standard Frappe logs and standard output.
    """
    logger = frappe.logger("proctor_api")
    return logger
