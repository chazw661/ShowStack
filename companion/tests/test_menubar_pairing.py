import unittest

import menubar_app as m

TOKEN = "cd4c1e0a-2b3c-4d5e-8f90-123456789abc"


class PairingPasteTests(unittest.TestCase):
    def test_bare_token_names_no_server(self):
        self.assertEqual(m.parse_pairing("  %s \n" % TOKEN), (TOKEN, ""))

    def test_start_link_takes_its_server(self):
        link = "showstack-listen://start?token=%s&api=http%%3A%%2F%%2F127.0.0.1%%3A8000&client=x" % TOKEN
        self.assertEqual(m.parse_pairing(link), (TOKEN, "http://127.0.0.1:8000"))

    def test_terminal_command_takes_token_and_api(self):
        cmd = "python listen_companion.py \\\n  --token %s \\\n  --api https://showstack.io/" % TOKEN
        self.assertEqual(m.parse_pairing(cmd), (TOKEN, "https://showstack.io"))

    def test_listen_page_address_is_not_a_server(self):
        url = "https://192.168.1.42:8443/listen?token=%s" % TOKEN
        self.assertEqual(m.parse_pairing(url), (TOKEN, ""))

    def test_server_labels(self):
        self.assertEqual(m.server_label("https://showstack.io"), "showstack.io")
        self.assertEqual(m.server_label("http://127.0.0.1:8000"), "127.0.0.1:8000")
        self.assertEqual(m.server_label(""), "showstack.io")


if __name__ == "__main__":
    unittest.main()
