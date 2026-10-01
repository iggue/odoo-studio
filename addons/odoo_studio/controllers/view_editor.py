# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo.http import Controller, request, route


class OdooStudioViewEditor(Controller):
    """ Routes of the form view editor: each of them returns the up-to-date
    data of the edited view (see `_get_editor_data`). """

    @route('/odoo_studio/form/load', type='jsonrpc', auth='user', readonly=True)
    def form_load(self, model, view_id=False):
        editor = request.env['odoo_studio.view.editor']
        return editor._get_editor_data(editor._get_form_view(model, view_id))

    @route('/odoo_studio/form/edit', type='jsonrpc', auth='user')
    def form_edit(self, model, view_id, operation):
        editor = request.env['odoo_studio.view.editor']
        view = editor._get_form_view(model, view_id)
        field_name = editor._apply_operation(view, operation)
        return {**editor._get_editor_data(view), 'field_name': field_name}

    @route('/odoo_studio/form/undo', type='jsonrpc', auth='user')
    def form_undo(self, model, view_id):
        editor = request.env['odoo_studio.view.editor']
        view = editor._get_form_view(model, view_id)
        editor._undo(view)
        return editor._get_editor_data(view)

    @route('/odoo_studio/form/reset', type='jsonrpc', auth='user')
    def form_reset(self, model, view_id):
        editor = request.env['odoo_studio.view.editor']
        view = editor._get_form_view(model, view_id)
        editor._reset(view)
        return editor._get_editor_data(view)
