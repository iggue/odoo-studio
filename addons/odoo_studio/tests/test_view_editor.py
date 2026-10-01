# Part of Odoo. See LICENSE file for full copyright and licensing details.

from lxml import etree

from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import new_test_user, tagged
from odoo.tools import mute_logger

from odoo.addons.base.tests.common import BaseCommon


@tagged('post_install', '-at_install')
class TestOdooStudioViewEditor(BaseCommon):
    _test_user_groups = ('base.group_system',)

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.editor = cls.env['odoo_studio.view.editor']
        cls.view = cls.env['ir.ui.view'].create({
            'name': 'odoo_studio.test.partner.form',
            'model': 'res.partner',
            'type': 'form',
            'priority': 1000,
            'arch': """
                <form>
                    <sheet>
                        <group>
                            <group>
                                <field name="name"/>
                                <label for="email"/>
                                <div><field name="email" nolabel="1"/></div>
                                <field name="phone"/>
                            </group>
                            <group>
                                <field name="phone" invisible="not email"/>
                                <field name="child_ids">
                                    <list><field name="name"/></list>
                                </field>
                            </group>
                        </group>
                    </sheet>
                </form>
            """,
        })

    def _get_arch(self):
        """ Return the architecture of the view as the users get it. """
        arch = self.env['res.partner'].get_views([(self.view.id, 'form')])['views']['form']['arch']
        return etree.fromstring(arch)

    def _get_main_field_names(self):
        return [node.get('name') for node in self._get_arch().xpath('//field[not(ancestor::field)]')]

    def _apply(self, **operation):
        return self.editor._apply_operation(self.view, operation)

    def test_get_form_view(self):
        self.assertEqual(self.editor._get_form_view('res.partner', self.view.id), self.view)
        default_view = self.editor._get_form_view('res.partner')
        self.assertEqual(default_view.type, 'form')
        self.assertEqual(default_view.mode, 'primary')
        self.assertNotEqual(default_view, self.view, "The view with the lowest priority is the default one")

        list_view = self.env['ir.ui.view'].create({
            'model': 'res.partner',
            'type': 'list',
            'arch': '<list><field name="name"/></list>',
        })
        for model_name, view_id in [
            ('base', False),
            ('res.partner.nope', False),
            (['res.partner'], False),
            ('res.partner', list_view.id),
            ('res.partner', True),
            ('res.partner', str(self.view.id)),
            ('res.partner.category', self.view.id),
        ]:
            with self.subTest(model_name=model_name, view_id=view_id), self.assertRaises(UserError):
                self.editor._get_form_view(model_name, view_id)

    def test_editor_data(self):
        data = self.editor._get_editor_data(self.view)
        self.assertEqual(data['view_id'], self.view.id)
        self.assertEqual(data['model_description'], "Contact")
        self.assertTrue(data['can_create_fields'])
        self.assertFalse(data['is_customized'])
        self.assertEqual(data['fields']['email']['type'], 'char')
        self.assertIn('res.partner', data['models'])

        # the main field nodes are numbered per field name, the subviews are not
        arch = etree.fromstring(data['arch'])
        self.assertEqual(
            [(node.get('name'), node.get('data-odoo-studio-index')) for node in arch.iter('field')],
            [('name', '1'), ('email', '1'), ('phone', '1'), ('phone', '2'), ('child_ids', '1'), ('name', None)],
        )
        # the regular views are left untouched
        self.assertFalse(self._get_arch().xpath('//field[@data-odoo-studio-index]'))

    def test_add_existing_field(self):
        field_name = self._apply(
            type='add', field='website', target={'name': 'phone', 'index': 2}, position='after',
        )
        self.assertEqual(field_name, 'website')
        self.assertEqual(self._get_main_field_names(), ['name', 'email', 'phone', 'phone', 'website', 'child_ids'])

        studio_view = self.editor._get_studio_views(self.view)
        self.assertEqual(len(studio_view), 1)
        self.assertEqual(studio_view.inherit_id, self.view)
        self.assertEqual(studio_view.mode, 'extension')
        self.assertTrue(self.editor._get_editor_data(self.view)['is_customized'])

        # the next operations are stored in the same view
        self._apply(type='add', field='function', target={'name': 'name'}, position='before')
        self.assertEqual(self.editor._get_studio_views(self.view), studio_view)
        self.assertEqual(
            self._get_main_field_names(),
            ['function', 'name', 'email', 'phone', 'phone', 'website', 'child_ids'],
        )

    def test_add_new_fields(self):
        char_name = self._apply(
            type='add', target={'name': 'name'}, position='after',
            new_field={'type': 'char', 'label': "Référence client"},
        )
        self.assertEqual(char_name, 'x_studio_reference_client')
        other_char_name = self._apply(
            type='add', target={'name': 'name'}, position='after',
            new_field={'type': 'char', 'label': "Reference (client)"},
        )
        self.assertEqual(other_char_name, 'x_studio_reference_client_2')
        html_name = self._apply(
            type='add', target={'name': 'email'}, position='after',
            new_field={'type': 'html', 'label': "Rich notes"},
        )
        selection_name = self._apply(
            type='add', target={'name': 'email'}, position='after',
            new_field={'type': 'selection', 'label': "Level", 'selection': ["Low", " High ", "High"]},
        )
        many2one_name = self._apply(
            type='add', target={'name': 'email'}, position='after',
            new_field={'type': 'many2one', 'label': "Birth country", 'relation': 'res.country'},
        )

        fields = self.env['ir.model.fields'].search([('model', '=', 'res.partner'), ('name', '=like', 'x_studio_%')])
        self.assertEqual(
            sorted(fields.mapped(lambda field: (field.name, field.ttype, field.field_description, field.state))),
            [
                ('x_studio_birth_country', 'many2one', "Birth country", 'manual'),
                ('x_studio_level', 'selection', "Level", 'manual'),
                ('x_studio_reference_client', 'char', "Référence client", 'manual'),
                ('x_studio_reference_client_2', 'char', "Reference (client)", 'manual'),
                ('x_studio_rich_notes', 'html', "Rich notes", 'manual'),
            ],
        )
        self.assertEqual(self.env['res.partner']._fields[many2one_name].comodel_name, 'res.country')
        self.assertEqual(
            list(self.env['res.partner']._fields[selection_name].selection),
            [('low', "Low"), ('high', "High"), ('high_2', "High")],
        )
        self.assertEqual(
            self._get_main_field_names(),
            ['name', other_char_name, char_name, 'email', many2one_name, selection_name, html_name,
             'phone', 'phone', 'child_ids'],
        )

        # the custom fields are usable right away
        partner = self.env['res.partner'].create({
            'name': "Studio",
            char_name: "REF",
            html_name: "<p>Hello</p><script>alert(1)</script>",
            selection_name: 'high_2',
            many2one_name: self.env.ref('base.be').id,
        })
        self.assertEqual(partner[html_name], "<p>Hello</p>", "The html fields are sanitized")

    def test_add_invalid(self):
        for operation in [
            {'type': 'add', 'target': {'name': 'name'}, 'position': 'after', 'field': 'nope'},
            {'type': 'add', 'target': {'name': 'name'}, 'position': 'after', 'field': ['name']},
            {'type': 'add', 'target': {'name': 'name'}, 'position': 'inside', 'field': 'website'},
            {'type': 'add', 'target': {'name': 'name'}, 'position': 'after', 'new_field': {'type': 'binary', 'label': "Bin"}},
            {'type': 'add', 'target': {'name': 'name'}, 'position': 'after', 'new_field': {'type': 'char', 'label': " "}},
            {'type': 'add', 'target': {'name': 'name'}, 'position': 'after', 'new_field': {'type': 'char', 'label': "Notes"}},
            {'type': 'add', 'target': {'name': 'name'}, 'position': 'after', 'new_field': {'type': 'char', 'label': "Login "}},
            {'type': 'add', 'target': {'name': 'name'}, 'position': 'after', 'new_field': {'type': 'selection', 'label': "Sel"}},
            {'type': 'add', 'target': {'name': 'name'}, 'position': 'after', 'new_field': {'type': 'selection', 'label': "Sel", 'selection': [""]}},
            {'type': 'add', 'target': {'name': 'name'}, 'position': 'after', 'new_field': {'type': 'many2one', 'label': "M2o"}},
            {'type': 'add', 'target': {'name': 'name'}, 'position': 'after', 'new_field': {'type': 'many2one', 'label': "M2o", 'relation': 'base'}},
            {'type': 'add', 'target': {'name': 'name'}, 'position': 'after', 'new_field': {'type': 'many2one', 'label': "M2o", 'relation': 'res.nope'}},
        ]:
            with self.subTest(operation=operation), self.assertRaises(UserError):
                self.editor._apply_operation(self.view, operation)
        self.assertFalse(self.editor._get_studio_views(self.view))
        self.assertFalse(self.env['ir.model.fields'].search([('model', '=', 'res.partner'), ('name', '=like', 'x_studio_%')]))

    def test_invalid_target(self):
        for target in [
            None,
            'name',
            {},
            {'name': "name'] | //*[@name='"},
            {'name': 'name', 'index': 0},
            {'name': 'name', 'index': '1'},
            {'name': 'name', 'index': True},
        ]:
            with self.subTest(target=target), self.assertRaises(UserError):
                self._apply(type='add', field='website', target=target, position='after')
        for operation in [None, {}, {'type': 'replace'}, {'type': ['add']}]:
            with self.subTest(operation=operation), self.assertRaises(UserError):
                self.editor._apply_operation(self.view, operation)

        # the view is validated as a whole
        with mute_logger('odoo.addons.base.models.ir_ui_view'), self.assertRaises(ValidationError):
            self._apply(type='add', field='website', target={'name': 'phone', 'index': 3}, position='after')
        self.assertFalse(self.editor._get_studio_views(self.view))

    def test_move(self):
        field_name = self._apply(type='move', node={'name': 'phone', 'index': 2}, target={'name': 'name'}, position='before')
        self.assertEqual(field_name, 'phone')
        arch = self._get_arch()
        self.assertEqual(
            [(node.get('name'), node.get('invisible')) for node in arch.xpath('//field[not(ancestor::field)]')],
            [('phone', 'not email'), ('name', None), ('email', None), ('phone', None), ('child_ids', None)],
        )

        self._apply(type='move', node={'name': 'child_ids'}, target={'name': 'email'}, position='after')
        self.assertEqual(self._get_main_field_names(), ['phone', 'name', 'email', 'child_ids', 'phone'])

        with self.assertRaises(UserError):
            self._apply(type='move', node={'name': 'name'}, target={'name': 'name', 'index': 1}, position='after')

    def test_attributes(self):
        self._apply(type='attributes', target={'name': 'phone', 'index': 2}, attributes={
            'string': "Mobile <b>phone</b>",
            'help': "Where to call",
            'placeholder': "+32 ...",
            'widget': 'phone',
            'required': 'True',
            'readonly': 'False',
            'invisible': '',
        })
        first_phone, second_phone = self._get_arch().xpath("//field[@name='phone']")
        self.assertNotIn('string', first_phone.attrib)
        self.assertEqual(second_phone.get('string'), "Mobile <b>phone</b>")
        self.assertEqual(second_phone.get('help'), "Where to call")
        self.assertEqual(second_phone.get('placeholder'), "+32 ...")
        self.assertEqual(second_phone.get('widget'), 'phone')
        self.assertEqual(second_phone.get('required'), 'True')
        self.assertEqual(second_phone.get('readonly'), 'False')
        self.assertNotIn('invisible', second_phone.attrib)

        # an empty value removes the attribute
        self._apply(type='attributes', target={'name': 'phone', 'index': 2}, attributes={'widget': '', 'string': ''})
        second_phone = self._get_arch().xpath("//field[@name='phone']")[1]
        self.assertNotIn('widget', second_phone.attrib)
        self.assertNotIn('string', second_phone.attrib)

        for attributes in [
            {},
            [('string', 'Phone')],
            {'class': 'd-none'},
            {'invisible': 'email'},
            {'required': True},
            {'widget': 'phone" onclick="alert(1)'},
            {'string': 42},
        ]:
            with self.subTest(attributes=attributes), self.assertRaises(UserError):
                self._apply(type='attributes', target={'name': 'phone'}, attributes=attributes)

    def test_attributes_required_field(self):
        view = self.env['ir.ui.view'].create({
            'model': 'res.partner.category',
            'type': 'form',
            'arch': '<form><field name="name"/><field name="color"/></form>',
        })
        with self.assertRaises(UserError):
            self.editor._apply_operation(view, {
                'type': 'attributes', 'target': {'name': 'name'}, 'attributes': {'required': 'False'},
            })
        self.editor._apply_operation(view, {
            'type': 'attributes', 'target': {'name': 'color'}, 'attributes': {'required': 'False'},
        })

    def test_remove(self):
        # the label of the field is removed with its last node
        self._apply(type='remove', target={'name': 'email'})
        arch = self._get_arch()
        self.assertFalse(arch.xpath("//label[@for='email']"))
        self.assertEqual(
            [(node.get('name'), node.get('invisible')) for node in arch.xpath('//field[not(ancestor::field)]')],
            [('name', None), ('phone', None), ('phone', 'not email'), ('child_ids', None),
             ('email', 'True')],
            "The fields used by the modifiers are added back as invisible fields",
        )

        self._apply(type='remove', target={'name': 'phone', 'index': 2})
        self.assertEqual(self._get_main_field_names()[:3], ['name', 'phone', 'child_ids'])
        self._apply(type='remove', target={'name': 'phone'})
        self.assertEqual(self._get_main_field_names()[:2], ['name', 'child_ids'])

    def test_remove_labelled_duplicate(self):
        self._apply(type='add', field='email', target={'name': 'name'}, position='after')
        self._apply(type='remove', target={'name': 'email', 'index': 2})
        self.assertEqual(len(self._get_arch().xpath("//label[@for='email']")), 1)
        self.assertEqual(self._get_main_field_names(), ['name', 'email', 'phone', 'phone', 'child_ids'])

    def test_undo_reset(self):
        initial_fields = self._get_main_field_names()
        self._apply(type='add', field='website', target={'name': 'name'}, position='after')
        self._apply(type='remove', target={'name': 'phone', 'index': 2})
        self._apply(type='move', node={'name': 'phone'}, target={'name': 'name'}, position='before')
        self.assertEqual(self._get_main_field_names(), ['phone', 'name', 'website', 'email', 'child_ids'])

        self.editor._undo(self.view)
        self.assertEqual(self._get_main_field_names(), ['name', 'website', 'email', 'phone', 'child_ids'])
        self.editor._undo(self.view)
        self.assertEqual(self._get_main_field_names(), ['name', 'website', 'email', 'phone', 'phone', 'child_ids'])
        self.editor._undo(self.view)
        self.assertEqual(self._get_main_field_names(), initial_fields)
        self.assertFalse(self.editor._get_studio_views(self.view))
        self.editor._undo(self.view)
        self.assertEqual(self._get_main_field_names(), initial_fields)

        field_name = self._apply(
            type='add', target={'name': 'name'}, position='after', new_field={'type': 'text', 'label': "Memo"},
        )
        self._apply(type='remove', target={'name': 'phone'})
        self.editor._reset(self.view)
        self.assertEqual(self._get_main_field_names(), initial_fields)
        self.assertFalse(self.editor._get_studio_views(self.view))
        self.assertIn(field_name, self.env['res.partner']._fields, "The custom fields are kept")

    def test_access(self):
        user = new_test_user(self.env, login='odoo_studio_manager', groups='base.group_user,base.group_erp_manager')
        editor = self.editor.with_user(user)
        with self.assertRaises(AccessError):
            editor._get_form_view('res.partner', self.view.id)
        with self.assertRaises(AccessError):
            editor._get_editor_data(self.view)
        with self.assertRaises(AccessError):
            editor._apply_operation(self.view, {'type': 'add', 'field': 'website', 'target': {'name': 'name'}, 'position': 'after'})
        with self.assertRaises(AccessError):
            editor._undo(self.view)
        with self.assertRaises(AccessError):
            editor._reset(self.view)
        self.assertFalse(self.editor._get_studio_views(self.view))
