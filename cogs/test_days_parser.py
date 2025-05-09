# test_days_parser.py

import re
import unittest

def parse_days_line(days_line: str) -> str:
    days_str = None
    if days_line:
        days_val = days_line.lower()
        days_val = re.sub(r"daily\s*:\s*", "", days_val).strip()
        if any(word in days_val for word in ["daily", "dagelijks"]):
            days_str = "0,1,2,3,4,5,6"
        elif "weekdays" in days_val:
            days_str = "0,1,2,3,4"
        elif "weekends" in days_val:
            days_str = "5,6"
        else:
            day_map = {
                "monday": "0", "maandag": "0",
                "tuesday": "1", "dinsdag": "1",
                "wednesday": "2", "woensdag": "2",
                "thursday": "3", "donderdag": "3",
                "friday": "4", "vrijdag": "4",
                "saturday": "5", "zaterdag": "5",
                "sunday": "6", "zondag": "6"
            }
            found_days = []
            for word in re.split(r",\s*|\s+", days_val):
                if word in day_map:
                    found_days.append(day_map[word])
            if found_days:
                days_str = ",".join(sorted(set(found_days)))
    else:
        # fallback
        from datetime import datetime
        days_str = str(datetime.now().weekday())

    return days_str


class TestDaysLineParsing(unittest.TestCase):
    def test_daily(self):
        self.assertEqual(parse_days_line("daily"), "0,1,2,3,4,5,6")
    
    def test_weekends(self):
        self.assertEqual(parse_days_line("weekends"), "5,6")
    
    def test_weekdays(self):
        self.assertEqual(parse_days_line("weekdays"), "0,1,2,3,4")
    
    def test_custom_days(self):
        self.assertEqual(parse_days_line("Monday, Wednesday, Friday"), "0,2,4")
    
    def test_nl_days(self):
        self.assertEqual(parse_days_line("maandag donderdag"), "0,3")
    
    def test_empty(self):
        self.assertTrue(parse_days_line("") in [str(i) for i in range(7)])  # fallback to current weekday

if __name__ == "__main__":
    unittest.main()
