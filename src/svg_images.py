"""Validate passive vector charts before embedding or downloading them."""
import re
import xml.etree.ElementTree as ET

SVG = 'http://www.w3.org/2000/svg'
XLINK = 'http://www.w3.org/1999/xlink'
TAGS = {'svg', 'g', 'defs', 'path', 'rect', 'circle', 'ellipse', 'line', 'polyline',
        'polygon', 'text', 'tspan', 'use', 'clipPath', 'style', 'title', 'desc',
        'linearGradient', 'radialGradient', 'stop'}


def passive_svg(raw):
    if len(raw) > 20 * 1024 * 1024: raise ValueError('SVG ist zu groß.')
    text = raw.decode('utf-8-sig')
    # Matplotlib emits a public SVG DTD. Never allow entity declarations or an
    # internal subset; ElementTree must not expand document-defined entities.
    if re.search(r'<!ENTITY|<!DOCTYPE[^>]*\[', text, re.I): raise ValueError('SVG-Entitäten sind nicht erlaubt.')
    text = re.sub(r'<!DOCTYPE[^>]*>', '', text, flags=re.I)
    try: root = ET.fromstring(text)
    except ET.ParseError: raise ValueError('Ungültiges SVG.') from None
    if root.tag != '{'+SVG+'}svg': raise ValueError('Kein SVG-Dokument.')
    for parent in root.iter():
        for child in list(parent):
            if child.tag == '{'+SVG+'}metadata': parent.remove(child)
    for node in root.iter():
        tag = node.tag.removeprefix('{'+SVG+'}')
        if tag not in TAGS or not node.tag.startswith('{'+SVG+'}'):
            raise ValueError('SVG enthält nicht unterstützte aktive oder eingebettete Inhalte.')
        for key, value in node.attrib.items():
            name = key.split('}')[-1].lower()
            if name.startswith('on') or name in ('base', 'src'):
                raise ValueError('Aktive SVG-Attribute sind nicht erlaubt.')
            if name == 'href' and not re.fullmatch(r'#[A-Za-z_][\w.:-]*', value):
                raise ValueError('SVG darf nur interne Verweise enthalten.')
        # Allow Matplotlib's inline CSS, but no CSS escapes, imports or external
        # URL loads. Clip paths/gradients may reference a local fragment only.
        values = list(node.attrib.values()) + ([node.text or ''] if tag == 'style' else [])
        for value in values:
            if '\\' in value or '@' in value or re.search(r'expression\s*\(|javascript\s*:', value, re.I):
                raise ValueError('Nicht unterstützte SVG-Formatierung.')
            cleaned = re.sub(r'url\(\s*#[A-Za-z_][\w.:-]*\s*\)', '', value, flags=re.I)
            if re.search(r'url\s*\(', cleaned, re.I): raise ValueError('Externe SVG-Ressourcen sind nicht erlaubt.')
    ET.register_namespace('', SVG);ET.register_namespace('xlink', XLINK)
    return ET.tostring(root, encoding='utf-8', xml_declaration=True)
