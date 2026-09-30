# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    'name': "Odoo Studio",
    'category': 'Customizations',
    'sequence': 300,
    'summary': "Customize your form views with a WYSIWYG editor",
    'description': """
Odoo Studio
===========

Customize the form views of your apps without writing any code:

* open the editor from the systray while browsing any model,
* see a live preview of the form, rendered by the web client itself,
* click a field to edit its label, tooltip, placeholder and widget, or to make
  it required, readonly or invisible,
* drag and drop existing fields or brand new custom fields (including rich text
  fields, edited with the WYSIWYG html editor) anywhere in the form,
* move and remove fields, undo the last change or reset the view.

All the customizations of a view are stored in a single inheriting view, so
that they survive the updates of the customized module.
    """,
    'depends': ['web', 'html_editor'],
    'assets': {
        'web.assets_backend': [
            'odoo_studio/static/src/**/*',
        ],
        'web.assets_tests': [
            'odoo_studio/static/tests/tours/**/*',
        ],
        'web.assets_unit_tests': [
            'odoo_studio/static/tests/**/*.test.js',
        ],
    },
    'icon': '/odoo_studio/static/description/icon.svg',
    'application': True,
    'author': 'iggue',
    'license': 'LGPL-3',
}
