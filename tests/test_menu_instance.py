import socket
import tempfile
import unittest
from pathlib import Path

from zekniri.menu_instance import release_listener, start_or_toggle


class MenuInstanceTest(unittest.TestCase):
    def test_second_activation_sends_toggle_to_existing_menu(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "menu.sock"
            try:
                server = start_or_toggle(path)
            except PermissionError as exc:
                self.skipTest(f"sandbox blocks Unix sockets: {exc}")
            self.assertIsNotNone(server)
            try:
                self.assertIsNone(start_or_toggle(path))
                server.settimeout(0.5)
                connection, _ = server.accept()
                with connection:
                    self.assertEqual(connection.recv(32), b"toggle")
            finally:
                release_listener(server, path)
            self.assertFalse(path.exists())

    def test_stale_socket_is_replaced(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "menu.sock"
            stale = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            try:
                stale.bind(str(path))
            except PermissionError as exc:
                stale.close()
                self.skipTest(f"sandbox blocks Unix sockets: {exc}")
            stale.close()
            server = start_or_toggle(path)
            self.assertIsNotNone(server)
            release_listener(server, path)


if __name__ == "__main__":
    unittest.main()
