# Part of Odoo. See LICENSE file for full copyright and licensing details.

from collections import defaultdict

from odoo import api, models

from .odoo_studio_view_editor import NODE_INDEX_ATTRIBUTE


class Base(models.AbstractModel):
    _inherit = 'base'

    @api.model
    def _get_view(self, view_id=None, view_type='form', **options):
        arch, view = super()._get_view(view_id, view_type, **options)
        if view_type == 'form' and self.env.context.get('odoo_studio_editor'):
            # Number the main field nodes (the ones that are not part of a
            # subview) of the complete architecture, before the nodes the user
            # has no access to are removed, so that the editor can target them
            # with xpaths that are valid for everyone.
            counters = defaultdict(int)
            for node in arch.xpath('//field[not(ancestor::field)]'):
                counters[node.get('name')] += 1
                node.set(NODE_INDEX_ATTRIBUTE, str(counters[node.get('name')]))
        return arch, view

    @api.model
    def _get_view_cache_key(self, view_id=None, view_type='form', **options):
        key = super()._get_view_cache_key(view_id, view_type, **options)
        return key + (bool(self.env.context.get('odoo_studio_editor')),)
