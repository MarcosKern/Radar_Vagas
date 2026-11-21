import io
import unittest
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from radar.resume import DEFAULT_TEMPLATE, normalize_template, generate_docx

class LayoutCustomizationTests(unittest.TestCase):
    def test_backward_compatible_defaults(self):
        t=normalize_template({'font':'Arial'})
        self.assertEqual(t['page_size'],'A4')
        self.assertEqual(t['section_order'],DEFAULT_TEMPLATE['section_order'])

    def test_validation(self):
        invalid=[{'margin_mm':9},{'body_font_pt':20},{'layout_preset':'bad'},{'header_alignment':'right'},{'section_order':['summary','summary']},{'page_size':'Tabloid'}]
        for val in invalid:
            with self.subTest(val=val),self.assertRaises(ValueError):normalize_template(val)

    def test_docx_layout_settings_affect_word_document(self):
        opts=normalize_template({'layout_preset':'modern','page_size':'Letter','margin_mm':24,
          'body_font_pt':11,'name_font_pt':22,'section_font_pt':13,'line_spacing':1.25,
          'section_spacing_pt':10,'header_alignment':'center',
          'section_order':['education','summary','experience','skills','languages','certifications','projects']})
        data,_=generate_docx({'title':'Analista Júnior','description':'Azure SQL'},template=opts)
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            doc=z.read('word/document.xml').decode('utf-8')
            styles=z.read('word/styles.xml').decode('utf-8')
            ET.fromstring(doc);ET.fromstring(styles)
        self.assertIn('w:w="12240"',doc)
        self.assertIn('w:top="1361"',doc)  # 24 mm converted to twips
        self.assertIn('<w:jc w:val="center"/>',doc)
        self.assertLess(doc.find('FORMAÇÃO ACADÊMICA'),doc.find('RESUMO PROFISSIONAL'))
        self.assertIn('w:sz w:val="44"',styles)
        self.assertIn('w:sz w:val="26"',styles)
        self.assertIn('w:line="300"',styles)

    def test_included_sections_remain_optional(self):
        opts={'include_projects':False,'include_languages':False,'include_certifications':False}
        data,_=generate_docx({'title':'IT Support'},template=opts)
        with zipfile.ZipFile(io.BytesIO(data)) as z:txt=z.read('word/document.xml').decode()
        self.assertNotIn('PROJETOS TÉCNICOS',txt)
        self.assertNotIn('IDIOMAS',txt)

    def test_no_float_button_or_glow(self):
        root=Path(__file__).resolve().parents[1]
        js=(root/'web/assets/app.js').read_text(encoding='utf-8')
        css=(root/'web/assets/custom.css').read_text(encoding='utf-8')
        html=(root/'web/index.html').read_text(encoding='utf-8')
        self.assertIn('resume-card-btn',js)
        self.assertNotIn('resume-float-btn',js)
        self.assertNotIn('followResumeCursor',js)
        self.assertIn('resumeLayoutEditor',html)
        self.assertIn('resumePagePreview',html)
        self.assertIn('resumeSectionOrder',html)
        self.assertIn('V0.18',html)
        self.assertIn('box-shadow:none!important',css)

if __name__=='__main__':unittest.main()
