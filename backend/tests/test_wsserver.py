import unittest
import sys
import os

# Add the backend directory to python path so we can import wsserver
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from wsserver import canonicalize_instrument_key, canonicalize_instrument_keys

class TestWsServer(unittest.TestCase):
    def test_canonicalize_instrument_key(self):
        # Test exact match aliases
        self.assertEqual(canonicalize_instrument_key("NIFTY"), "NSE_INDEX|Nifty 50")
        self.assertEqual(canonicalize_instrument_key("BANKNIFTY"), "NSE_INDEX|Nifty Bank")
        self.assertEqual(canonicalize_instrument_key("SENSEX"), "BSE_INDEX|SENSEX")
        
        # Test case insensitivity
        self.assertEqual(canonicalize_instrument_key("nifty"), "NSE_INDEX|Nifty 50")
        self.assertEqual(canonicalize_instrument_key("banknifty"), "NSE_INDEX|Nifty Bank")
        
        # Test normal key fallback
        self.assertEqual(canonicalize_instrument_key("NSE_EQ|INE002A01018"), "NSE_EQ|INE002A01018")
        
        # Test empty input handling
        self.assertEqual(canonicalize_instrument_key(""), "")
        self.assertEqual(canonicalize_instrument_key(None), "")

    def test_canonicalize_instrument_keys(self):
        inputs = ["nifty", "NSE_EQ|INE002A01018", "banknifty", "nifty"]
        expected = ["NSE_INDEX|Nifty 50", "NSE_EQ|INE002A01018", "NSE_INDEX|Nifty Bank"]
        self.assertEqual(canonicalize_instrument_keys(inputs), expected)

if __name__ == '__main__':
    unittest.main()
