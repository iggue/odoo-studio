import { combineAttributes, parseXML, serializeXML, visitXML } from "@web/core/utils/xml";

/** Set by the server on the main field nodes of the edited view (see `_get_view`) */
export const NODE_INDEX_ATTRIBUTE = "data-odoo-studio-index";
/** Set on the editable field nodes, and suffixed by their id */
export const NODE_CLASS = "o_odoo_studio_node";
/** Set on the elements that are revealed while showing the invisible elements */
export const INVISIBLE_CLASS = "o_odoo_studio_invisible";
/** Attributes of the field nodes that can be edited with the properties panel */
export const EDITABLE_ATTRIBUTES = [
    "string",
    "help",
    "placeholder",
    "widget",
    "invisible",
    "readonly",
    "required",
];
/** The server only targets field nodes with such names (they are xpath-safe) */
const FIELD_NAME_REGEXP = /^[A-Za-z_][A-Za-z0-9_]*$/;
const FALSY_VALUES = ["", "0", "False", "false"];

/**
 * @typedef {Object} StudioNode
 * @property {string} id id of the field node in the form renderer (the "for"
 *  attribute of its labels)
 * @property {string} name name of the field
 * @property {number} index rank of the node among the main field nodes of the
 *  same field, in the complete architecture (i.e. the one the server knows)
 * @property {Object<string, string>} attrs values of the editable attributes
 *
 * @typedef {Object} PreparedArch
 * @property {string} arch architecture to render
 * @property {Object<string, StudioNode>} nodes editable nodes, by id
 */

/**
 * @param {string} value
 * @returns {boolean} whether the given modifier value is statically truthy
 */
export function isTruthyModifier(value) {
    return !FALSY_VALUES.includes(value ?? "");
}

/**
 * Prepares the architecture of the edited form view to be rendered by the
 * preview: the main field nodes (i.e. that are not part of a subview) numbered
 * by the server are marked with classes to find them in the DOM, and the
 * invisible elements are optionally revealed.
 *
 * The ids of the nodes are the ones the form renderer gives to the field nodes
 * (see `FormArchParser`), so they are also the "for" attributes of their
 * labels.
 *
 * @param {string} arch
 * @param {Object} [options]
 * @param {boolean} [options.showInvisible=false]
 * @returns {PreparedArch}
 */
export function prepareArch(arch, { showInvisible = false } = {}) {
    const root = parseXML(arch);
    // the editor displays the standard form view, whatever the model
    root.removeAttribute("js_class");
    const nodes = {};
    const nextIds = {};
    const reveal = (el) => {
        if (showInvisible && isTruthyModifier(el.getAttribute("invisible"))) {
            el.removeAttribute("invisible");
            combineAttributes(el, "class", INVISIBLE_CLASS);
        }
    };
    visitXML(root, (el) => {
        if (el.tagName !== "field") {
            reveal(el);
            return;
        }
        const name = el.getAttribute("name");
        nextIds[name] ??= 0;
        const id = `${name}_${nextIds[name]++}`;
        const index = parseInt(el.getAttribute(NODE_INDEX_ATTRIBUTE));
        el.removeAttribute(NODE_INDEX_ATTRIBUTE);
        // the fields added by the server for the modifiers are not numbered
        if (index && FIELD_NAME_REGEXP.test(name)) {
            const attrs = {};
            for (const attr of EDITABLE_ATTRIBUTES) {
                if (el.hasAttribute(attr)) {
                    attrs[attr] = el.getAttribute(attr);
                }
            }
            nodes[id] = { id, name, index, attrs };
            combineAttributes(el, "class", [NODE_CLASS, `${NODE_CLASS}_${id}`]);
            reveal(el);
        }
        // the subviews are not editable
        return false;
    });
    return { arch: serializeXML(root), nodes };
}
