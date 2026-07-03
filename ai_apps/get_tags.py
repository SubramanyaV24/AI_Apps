import frappe

def get_tags():
    tags = frappe.get_all('Trait Tags', fields=['name', 'parent_trait', 'tag_type'])
    for t in tags:
        if t.tag_type == 'Sub':
            print(f"{t.name} -> {t.parent_trait}")
