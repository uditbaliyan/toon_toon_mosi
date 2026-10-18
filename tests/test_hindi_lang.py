import unittest

from src.parser import ScriptParser


class ScriptParserLanguageTests(unittest.TestCase):
    def test_script_parser_accepts_hindi_language_and_preserves_unicode_text(self):
        parser = ScriptParser(lang="hi")
        script = "नमस्ते <happy> दुनिया!\n\nकैसे हैं आप?"

        metadata = parser.parse(script)

        self.assertEqual(metadata.clean_text, "नमस्ते दुनिया!\nकैसे हैं आप?")
        self.assertEqual(metadata.emotion_events[0].emotion_code, "happy")
        self.assertEqual(metadata.emotion_events[0].position, 7)

    def test_script_parser_default_language_is_english(self):
        parser = ScriptParser()
        metadata = parser.parse("Hello <happy> world")

        self.assertEqual(metadata.clean_text, "Hello world")
        self.assertEqual(metadata.emotion_events[0].emotion_code, "happy")


if __name__ == "__main__":
    unittest.main()
