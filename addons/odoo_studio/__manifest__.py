# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    'name': "Odoo Studio",
    'category': 'Customizations',
    'sequence': 300,
    'summary': "Form view customization engine of a WYSIWYG editor",
    'description': """
Odoo Studio
===========

Server side of a WYSIWYG form view editor:

* JSON-RPC routes to load a form view for edition, to add, move and remove its
  fields or change their label, tooltip, placeholder, widget and modifiers, to
  undo the last change and to reset the view,
* creation of custom fields, including rich text (html) fields,
* all the customizations of a view are stored in a single inheriting view, so
  that they survive the updates of the customized module.

The web client provides the helper preparing the architecture of the edited
view for its live preview.
    """,
    'depends': ['web', 'html_editor'],
    'assets': {
        'web.assets_backend': [
            'odoo_studio/static/src/**/*',
        ],
    },
    'icon': '/odoo_studio/static/description/icon.svg',
    'author': 'iggue',
    'license': 'LGPL-3',
}
