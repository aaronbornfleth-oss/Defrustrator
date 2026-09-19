import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from hardware import SPECIAL_CATEGORIES
from session import workspace
from test_converter import item
from converter import Report
from row_history import RowHistory


class ApiTests(unittest.TestCase):
    def setUp(self):
        workspace.clear()
        from main import app
        self.client = TestClient(app)

    def tearDown(self):
        workspace.clear()

    def load_report(self):
        report = Report('example.pdf', 'API job', [
            item('49 3/8'),
            item('6', '5-Piece Drawer Front'),
            item('4', 'Drawer Box', 'boxes'),
        ])
        report.items[2].group = 'Drawer Box'
        from hardware import HardwareItem, HINGE_PART, DEFAULT_SPACER_PART
        report.hardware = [
            HardwareItem('hinges', 4, HINGE_PART, 'Euro Frameless', 7),
            HardwareItem('spacers', 4, DEFAULT_SPACER_PART, 'Spacers', 7),
        ]
        report.hardware_pages = [7]
        workspace.accept_report(report)
        return report

    def test_health_and_empty_session(self):
        self.assertEqual(self.client.get('/api/health').json()['version'], '1.21')
        data = self.client.get('/api/session').json()
        self.assertFalse(data['has_report'])
        self.assertEqual(data['app_name'], 'Mozaik to Decorative Defrustrator')

    def test_import_pdf_and_clipboard_contract(self):
        pdf = Path(__file__).resolve().parents[1] / 'samples' / 'Spigener-report-2026-09-15-1000.pdf'
        if not pdf.exists():
            self.skipTest('frozen PDF missing')
        with pdf.open('rb') as handle:
            response = self.client.post('/api/import/pdf', files={'file': ('Spigener.pdf', handle, 'application/pdf')})
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()
        self.assertEqual(data['counts']['doors'], 31)
        self.assertEqual(data['counts']['fronts'], 20)
        self.assertEqual(data['counts']['boxes'], 19)
        self.assertEqual(data['counts']['trays'], 6)
        self.assertEqual(len([row for row in data['items'] if not row['deleted']]), 45)
        copied = self.client.post('/api/export/clipboard', json={'kind': 'doors'}).json()['text']
        self.assertTrue(copied.startswith('Type\tQty\tWidth'))
        self.assertFalse(copied.endswith('\n'))
        self.assertIn('\tBore\t', copied.split('\r\n')[0])
        csv_bytes = self.client.get('/api/export/csv/doors')
        self.assertEqual(csv_bytes.status_code, 200)
        self.assertTrue(csv_bytes.text.startswith('Type,Qty,Width'))
        self.assertIn('Bore ', csv_bytes.text.splitlines()[0])

    def test_edit_undo_custom_highlight_and_order_download(self):
        self.load_report()
        response = self.client.post('/api/items/type?index=0', json={'label': 'Glass Front Door'})
        self.assertEqual(response.status_code, 200)
        row = response.json()['items'][0]
        self.assertEqual(row['type'], 'Glass')
        self.assertTrue(row['customized'])
        self.assertIn('Type', row['changed_fields'])
        undo = self.client.post('/api/undo').json()
        self.assertEqual(undo['items'][0]['type'], 'Door')
        self.assertFalse(undo['items'][0]['customized'])
        order = self.client.get('/api/export/order')
        self.assertEqual(order.status_code, 200)
        self.assertTrue(order.headers['content-disposition'].endswith('.mddorder"'))
        payload = json.loads(order.content)
        self.assertEqual(payload['format'], 'mozaik-decorative-order')
        self.assertEqual(payload['version'], 1)

    def test_custom_bore_conflict_then_split(self):
        self.load_report()
        payload = {
            'fields': {
                'Quantity': '2', 'Width': '17 27/32', 'Height': '49 3/8', 'Type': 'Door',
                'Location': 'L', 'French Lite': '', 'Top Bore Position': '7',
                'Center Bore Position': '24 11/16', 'Bottom Bore Position': '4',
            },
            'center_reference': 'Top — Decorative',
            'manual_positions': ['top'],
        }
        conflict = self.client.post('/api/items/0/edit', json=payload)
        self.assertEqual(conflict.status_code, 409)
        self.assertEqual(conflict.json()['pending'], 'custom_bores')
        payload['decision'] = {'duplicate': True}
        applied = self.client.post('/api/items/0/edit', json=payload)
        self.assertEqual(applied.status_code, 200, applied.text)
        rows = [row for row in applied.json()['items'] if row['kind'] == 'doors' and not row['is_front']]
        self.assertEqual([(row['qty'], row['location']) for row in rows[:2]], [(1, 'L'), (1, 'R')])
        self.assertEqual(rows[0]['values'][8], '7')

    def test_hardware_generate_is_draft_only(self):
        self.load_report()
        special = {category: [{'part_number': '', 'quantity': '', 'unit': 'each'}]
                   for category in SPECIAL_CATEGORIES}
        with tempfile.TemporaryDirectory() as directory:
            settings = Path(directory) / 'parts.json'
            with patch.dict(os.environ, {'DEFRUSTRATOR_HARDWARE_PARTS': str(settings)}):
                response = self.client.post('/api/hardware/generate', json={
                    'parts': {}, 'quantities': {}, 'special': special,
                    'email': '', 'generated_body': '', 'preview': False,
                })
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()['body']
        self.assertIn('4 each - 71B3590', body)
        self.assertIn('4 each - 174H7100I', body)
        self.assertIn('Please confirm availability', body)
        self.assertNotIn('mailto:', body.lower())

    def test_invalid_order_leaves_current_work(self):
        self.load_report()
        self.client.post('/api/items/type?index=0', json={'label': 'Glass'})
        before = self.client.get('/api/session').json()['items'][0]['type']
        response = self.client.post('/api/import/order', files={
            'file': ('bad.mddorder', b'{broken', 'application/json'),
        })
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.client.get('/api/session').json()['items'][0]['type'], before)

    def test_wrong_extension_rejected_for_pdf(self):
        response = self.client.post('/api/import/pdf', files={'file': ('notes.txt', b'hello', 'text/plain')})
        self.assertEqual(response.status_code, 400)

    def test_shopify_iframe_and_cors_headers(self):
        health = self.client.get('/api/health', headers={'Origin': 'https://leftcoastoriginal.com'})
        csp = health.headers.get('content-security-policy', '')
        self.assertIn('frame-ancestors', csp)
        self.assertIn('https://*.myshopify.com', csp)
        self.assertIn('leftcoastoriginal.com', csp)
        self.assertIn('leftcoastcabinets.com', csp)
        self.assertNotIn('DENY', health.headers.get('x-frame-options', '').upper())
        self.assertNotIn('SAMEORIGIN', health.headers.get('x-frame-options', '').upper())
        self.assertEqual(health.headers.get('access-control-allow-origin'), 'https://leftcoastoriginal.com')

        shop = self.client.get(
            '/api/health',
            headers={'Origin': 'https://left-coast-cabinets.myshopify.com'},
        )
        self.assertEqual(
            shop.headers.get('access-control-allow-origin'),
            'https://left-coast-cabinets.myshopify.com',
        )

        cabinets = self.client.get(
            '/api/health',
            headers={'Origin': 'https://www.leftcoastcabinets.com'},
        )
        self.assertEqual(
            cabinets.headers.get('access-control-allow-origin'),
            'https://www.leftcoastcabinets.com',
        )


if __name__ == '__main__':
    unittest.main()
