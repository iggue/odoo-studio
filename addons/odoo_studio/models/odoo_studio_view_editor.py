# Part of Odoo. See LICENSE file for full copyright and licensing details.

import re
import unicodedata

from lxml import etree
from lxml.builder import E

from odoo import api, models
from odoo.exceptions import AccessError, UserError
from odoo.fields import Command

# Prefix of the names of the inheriting views holding the customizations
STUDIO_VIEW_PREFIX = "Odoo Studio: "
# Customizations are applied after the extensions of the modules
STUDIO_VIEW_PRIORITY = 99
# Set on the main field nodes of the architectures loaded by the editor: rank
# of the node among the main field nodes with the same name (see `_get_view`)
NODE_INDEX_ATTRIBUTE = 'data-odoo-studio-index'
# Field names and widget names: they are safe to use in an xpath expression
NAME_PATTERN = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')

OPERATION_TYPES = ('add', 'move', 'attributes', 'remove')
POSITIONS = ('before', 'after')
TEXT_ATTRIBUTES = ('string', 'help', 'placeholder')
BOOLEAN_ATTRIBUTES = ('invisible', 'readonly', 'required')
BOOLEAN_VALUES = ('True', 'False', '')
NEW_FIELD_TYPES = (
    'boolean', 'char', 'date', 'datetime', 'float', 'html', 'integer', 'many2one',
    'selection', 'text',
)
FIELD_DESCRIPTION_ATTRIBUTES = ['help', 'readonly', 'relation', 'required', 'string', 'type']


def _slugify(text):
    """ Return an identifier made of the lowercase ascii letters and digits of
    ``text``, the other characters being replaced by underscores. """
    text = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('ascii')
    return re.sub(r'[^a-z0-9]+', '_', text.lower()).strip('_')


class OdooStudioViewEditor(models.AbstractModel):
    """ Customize the form views, by applying the operations performed with the
    editor on an inheriting view (one per customized view). Every operation is
    a top-level ``<data>`` element of that view, so that the last one can be
    undone. """
    _name = 'odoo_studio.view.editor'
    _description = "Odoo Studio View Editor"

    @api.model
    def _check_editor_access(self):
        if not self.env.su and not self.env.user._is_system():
            raise AccessError(self.env._("Only the administrators can customize the views."))

    @api.model
    def _get_form_view(self, model_name, view_id=False):
        """ Return the primary form view of the model to customize: the view
        ``view_id`` if given, the default form view of the model otherwise. """
        self._check_editor_access()
        if (
            not isinstance(model_name, str) or model_name not in self.env
            or self.env[model_name]._abstract or self.env[model_name]._transient
        ):
            raise UserError(self.env._("The views of the model %s cannot be customized.", model_name))
        View = self.env['ir.ui.view']
        if view_id and (not isinstance(view_id, int) or isinstance(view_id, bool)):
            raise UserError(self.env._("Invalid view: %s", view_id))
        view = View.browse(view_id or View.default_view(model_name, 'form')).exists()
        if not view or view.model != model_name or view.type != 'form' or view.mode != 'primary':
            raise UserError(self.env._("There is no form view to customize for the model %s.", model_name))
        return view

    @api.model
    def _get_studio_views(self, view):
        """ Return the views holding the customizations of ``view``, in the
        order they are applied. """
        return self.env['ir.ui.view'].search([
            ('inherit_id', '=', view.id),
            ('mode', '=', 'extension'),
            ('name', '=like', f'{STUDIO_VIEW_PREFIX}%'),
        ], order='priority, id')

    @api.model
    def _get_editor_data(self, view):
        """ Return everything the editor needs to display ``view``. """
        self._check_editor_access()
        model = self.env[view.model]
        views = model.with_context(odoo_studio_editor=True).get_views([(view.id, 'form')])
        return {
            'view_id': view.id,
            'view_name': view.name,
            'model_description': self.env['ir.model']._get(view.model).name,
            'arch': views['views']['form']['arch'],
            'models': views['models'],
            'fields': model.fields_get(attributes=FIELD_DESCRIPTION_ATTRIBUTES),
            'can_create_fields': model._auto,
            'is_customized': bool(self._get_studio_views(view)),
        }

    @api.model
    def _apply_operation(self, view, operation):
        """ Customize ``view`` with the given operation, a dict with a key
        ``type`` (``add``, ``move``, ``attributes`` or ``remove``) and the keys
        expected by the corresponding ``_get_<type>_specs`` method.

        :return: the name of the field that has been added or moved, if any
        """
        self._check_editor_access()
        if not isinstance(operation, dict) or operation.get('type') not in OPERATION_TYPES:
            raise UserError(self.env._("Invalid operation."))
        get_specs = {
            'add': self._get_add_specs,
            'move': self._get_move_specs,
            'attributes': self._get_attributes_specs,
            'remove': self._get_remove_specs,
        }[operation['type']]
        specs, field_name = get_specs(view, operation)
        # The specs of the nested <data> elements are applied after the others:
        # every operation must be wrapped to keep them in order.
        operation_node = E.data(*specs)
        studio_view = self._get_studio_views(view)[-1:]
        if studio_view:
            arch = self._get_studio_arch(studio_view)
            arch.append(operation_node)
            self._set_studio_arch(studio_view, arch)
        else:
            self.env['ir.ui.view'].with_context(lang=None).create({
                'name': f"{STUDIO_VIEW_PREFIX}{view.name} customization",
                'type': view.type,
                'model': view.model,
                'inherit_id': view.id,
                'mode': 'extension',
                'priority': STUDIO_VIEW_PRIORITY,
                'arch': self._serialize_arch(E.data(operation_node)),
            })
        return field_name

    @api.model
    def _undo(self, view):
        """ Cancel the last operation applied on ``view``. """
        self._check_editor_access()
        studio_view = self._get_studio_views(view)[-1:]
        if not studio_view:
            return
        arch = self._get_studio_arch(studio_view)
        operation_nodes = list(arch.iterchildren(etree.Element))
        if len(operation_nodes) > 1:
            arch.remove(operation_nodes[-1])
            self._set_studio_arch(studio_view, arch)
        else:
            studio_view.unlink()

    @api.model
    def _reset(self, view):
        """ Cancel all the customizations of ``view``; the custom fields are
        kept, as they may hold data. """
        self._check_editor_access()
        self._get_studio_views(view).unlink()

    @api.model
    def _get_studio_arch(self, studio_view):
        parser = etree.XMLParser(remove_blank_text=True)
        return etree.fromstring(studio_view.arch_base, parser)

    @api.model
    def _set_studio_arch(self, studio_view, arch):
        studio_view.with_context(lang=None).arch_base = self._serialize_arch(arch)

    @api.model
    def _serialize_arch(self, arch):
        etree.indent(arch, space='    ')
        return etree.tostring(arch, encoding='unicode')

    # ------------------------------------------------------------
    # Operations
    # ------------------------------------------------------------

    @api.model
    def _get_node_xpath(self, node):
        """ Return the xpath locating the given main field node (i.e. that is
        not part of a subview) of the architecture of the view.

        :param dict node: the name of the field, and the rank of the node among
            the main field nodes with that name (1 by default)
        """
        name = isinstance(node, dict) and node.get('name')
        index = isinstance(node, dict) and node.get('index', 1)
        if (
            not isinstance(name, str) or not NAME_PATTERN.match(name)
            or not isinstance(index, int) or isinstance(index, bool) or index < 1
        ):
            raise UserError(self.env._("Invalid field node: %s", node))
        xpath = f"//field[@name='{name}'][not(ancestor::field)]"
        return xpath if index == 1 else f"({xpath})[{index}]"

    @api.model
    def _get_position(self, operation):
        position = operation.get('position')
        if position not in POSITIONS:
            raise UserError(self.env._("Invalid position: %s", position))
        return position

    @api.model
    def _get_add_specs(self, view, operation):
        """ Add a field next to a field node.

        Operation keys: ``target`` (see `_get_node_xpath`), ``position``
        (``before`` or ``after``), and either ``field`` (the name of an
        existing field) or ``new_field`` (see `_create_field`).
        """
        position = self._get_position(operation)
        target = self._get_node_xpath(operation.get('target'))
        if operation.get('new_field'):
            field_name = self._create_field(view.model, operation['new_field'])
        else:
            field_name = operation.get('field')
            if not isinstance(field_name, str) or field_name not in self.env[view.model]._fields:
                raise UserError(self.env._("Unknown field: %s", field_name))
        return [E.xpath(E.field(name=field_name), expr=target, position=position)], field_name

    @api.model
    def _get_move_specs(self, view, operation):
        """ Move a field node next to another one.

        Operation keys: ``node`` and ``target`` (see `_get_node_xpath`), and
        ``position`` (``before`` or ``after``).
        """
        position = self._get_position(operation)
        target = self._get_node_xpath(operation.get('target'))
        node = self._get_node_xpath(operation.get('node'))
        if node == target:
            raise UserError(self.env._("A field cannot be moved next to itself."))
        spec = E.xpath(E.xpath(expr=node, position='move'), expr=target, position=position)
        return [spec], operation['node']['name']

    @api.model
    def _get_attributes_specs(self, view, operation):
        """ Set (or remove, with an empty value) attributes of a field node.

        Operation keys: ``target`` (see `_get_node_xpath`) and ``attributes``
        (a dict mapping attribute names to their values).
        """
        target = self._get_node_xpath(operation.get('target'))
        attributes = operation.get('attributes')
        if not isinstance(attributes, dict) or not attributes:
            raise UserError(self.env._("There is no attribute to set."))
        field = self.env[view.model]._fields.get(operation['target']['name'])
        spec = E.xpath(expr=target, position='attributes')
        for name, value in attributes.items():
            if name in BOOLEAN_ATTRIBUTES:
                is_valid = value in BOOLEAN_VALUES
            elif name in TEXT_ATTRIBUTES:
                is_valid = isinstance(value, str)
            elif name == 'widget':
                is_valid = isinstance(value, str) and (not value or NAME_PATTERN.match(value))
            else:
                is_valid = False
            if not is_valid:
                raise UserError(self.env._(
                    "Invalid value for the attribute %(attribute)s: %(value)s",
                    attribute=name, value=value,
                ))
            if name == 'required' and value == 'False' and field and field.required:
                raise UserError(self.env._("The field %s is always required.", field.name))
            spec.append(E.attribute(value, name=name))
        return [spec], None

    @api.model
    def _get_remove_specs(self, view, operation):
        """ Remove a field node, and its labels if it is the only node of that
        field (they would reference a missing field otherwise).

        Operation keys: ``target`` (see `_get_node_xpath`).
        """
        target = self._get_node_xpath(operation.get('target'))
        name = operation['target']['name']
        arch = view._get_combined_arch()
        specs = []
        if len(arch.xpath(f"//field[@name='{name}'][not(ancestor::field)]")) == 1:
            label_xpath = f"//label[@for='{name}'][not(ancestor::field)]"
            specs += [E.xpath(expr=label_xpath, position='replace') for _label in arch.xpath(label_xpath)]
        specs.append(E.xpath(expr=target, position='replace'))
        return specs, None

    # ------------------------------------------------------------
    # Custom fields
    # ------------------------------------------------------------

    @api.model
    def _create_field(self, model_name, values):
        """ Create a custom field on the given model and return its name.

        :param dict values: ``type`` (one of ``NEW_FIELD_TYPES``), ``label``,
            ``selection`` (the labels of the options, for selection fields)
            and ``relation`` (the comodel, for many2one fields)
        """
        model = self.env[model_name]
        if not model._auto:
            raise UserError(self.env._("Fields cannot be added to the model %s.", model_name))
        if not isinstance(values, dict) or values.get('type') not in NEW_FIELD_TYPES:
            raise UserError(self.env._("Invalid field type."))
        label = values.get('label')
        if not isinstance(label, str) or not label.strip():
            raise UserError(self.env._("The field must have a label."))
        label = label.strip()
        for model_name_ in (model_name, *model._inherits_children):
            if any(field.string == label for field in self.env[model_name_]._fields.values()):
                raise UserError(self.env._("There is already a field labelled %s, please choose another label.", label))
        field_values = {
            'name': self._get_new_field_name(model, label),
            'field_description': label,
            'model_id': self.env['ir.model']._get_id(model_name),
            'ttype': values['type'],
            'state': 'manual',
        }
        if values['type'] == 'selection':
            field_values['selection_ids'] = self._get_selection_commands(values.get('selection'))
        elif values['type'] == 'many2one':
            relation = values.get('relation')
            if (
                not isinstance(relation, str) or relation not in self.env
                or self.env[relation]._abstract or self.env[relation]._transient
            ):
                raise UserError(self.env._("Invalid related model: %s", relation))
            field_values['relation'] = relation
        return self.env['ir.model.fields'].create(field_values).name

    @api.model
    def _get_new_field_name(self, model, label):
        # leave room for a suffix within the 63 characters of the identifiers
        name = base_name = f"x_studio_{_slugify(label) or 'field'}"[:58].rstrip('_')
        suffix = 1
        while name in model._fields:
            suffix += 1
            name = f"{base_name}_{suffix}"
        return name

    @api.model
    def _get_selection_commands(self, labels):
        if (
            not isinstance(labels, list) or not labels
            or not all(isinstance(label, str) and label.strip() for label in labels)
        ):
            raise UserError(self.env._("A selection field must have options."))
        commands = []
        values = set()
        for sequence, label in enumerate(labels):
            value = base_value = _slugify(label) or 'option'
            suffix = 1
            while value in values:
                suffix += 1
                value = f"{base_value}_{suffix}"
            values.add(value)
            commands.append(Command.create({'value': value, 'name': label.strip(), 'sequence': sequence}))
        return commands
