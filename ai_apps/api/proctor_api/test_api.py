import frappe
from werkzeug.wrappers import Response

@frappe.whitelist(allow_guest=True)
def test_range():
    content = b"0123456789" * 100
    resp = Response(content, mimetype="text/plain")
    resp.make_conditional(frappe.local.request.environ)
    return resp
