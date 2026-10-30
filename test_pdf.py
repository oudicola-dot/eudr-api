import unittest
from pdf_report import format_loss_year, get_loss_display

class TestPDFLogic(unittest.TestCase):
    
    def test_format_loss_year_bool(self):
        # False == 0 en Python, on doit le rejeter
        self.assertEqual(format_loss_year(False), "N/A")
        self.assertEqual(format_loss_year(True), "N/A")

    def test_format_loss_year_decimal(self):
        # 2023.5 n'est pas une année valide
        self.assertEqual(format_loss_year(2023.5), "N/A")
        self.assertEqual(format_loss_year(2020.1), "N/A")

    def test_format_loss_year_valid(self):
        self.assertEqual(format_loss_year(0), "No loss detected")
        self.assertEqual(format_loss_year(2021), "2021")
        self.assertEqual(format_loss_year(2023), "2023")

    def test_insufficient_data_masks_zero_loss(self):
        # Test de la VRAIE fonction
        self.assertEqual(get_loss_display("INSUFFICIENT DATA", 0), "N/A")

    def test_unavailable_masks_zero_loss(self):
        self.assertEqual(get_loss_display("ANALYSIS UNAVAILABLE", 0), "N/A")

    def test_valid_analysis_allows_zero_loss(self):
        self.assertEqual(get_loss_display("NO POST-2020 LOSS DETECTED", 0), "No loss detected")

    def test_valid_analysis_with_year(self):
        self.assertEqual(get_loss_display("POTENTIAL LOSS SIGNAL", 2022), "2022")

if __name__ == '__main__':
    unittest.main()
