"""
Script parsing utility for extracting emotion codes and formatting markers.
Processes annotated story scripts with bracketed emotion tags and formatting delimiters.
"""

import re
from typing import List
from dataclasses import dataclass


@dataclass
class EmotionEvent:
    """Emotion tag found in the script at a specific position."""
    emotion_code: str
    position: int


@dataclass
class ScriptMetadata:
    """Parsed script metadata and timeline events matched to the clean text."""
    clean_text: str  # Script text with all formatting removed
    emotion_events: List[EmotionEvent]
    line_breaks: List[int]  # Positions of single line breaks (\n)
    paragraph_breaks: List[int]  # Positions of double line breaks (\n\n)


class ScriptParser:
    """
    Processes annotated story scripts.
    
    Extracts:
    - Emotion tags: <happy>, <sad>, <angry>, etc.
    - Formatting markers: Single \n triggers pose change, \n\n increments paragraph
    """

    def __init__(self):
        """Initialize the parser with precompiled regex patterns."""
        self.emotion_pattern = re.compile(r'<(\w+)>')
        # Matches 2 or more newlines (allowing for accidental trailing whitespace)
        self.para_pattern = re.compile(r'\n\s*\n') 
        self.line_pattern = re.compile(r'\n')

    def parse(self, script_text: str) -> ScriptMetadata:
        """
        Parse the script, extract metadata aligned with the final clean text,
        and clean the string of junk formatting tags.
        """
        # Step 1: Mimic the old script's structural cleanup safely
        script_text = script_text.replace("-", " ")
        for char in ["[", "]", "/"]:
            script_text = script_text.replace(char, "")

        # Step 2: Parse paragraph and line breaks *before* stripping emotions,
        # but normalize them so they track correctly.
        paragraph_breaks = []
        line_breaks = []
        
        # We process line-by-line or with a split-mapping to track positions relative to text
        # But a highly precise way is to extract emotions step-by-step to keep index alignment:
        
        emotion_events = []
        offset = 0
        clean_chunks = []
        last_idx = 0

        # Step 3: Extract emotion tags and adjust their positions dynamically
        for match in self.emotion_pattern.finditer(script_text):
            start, end = match.span()
            # Append text up to this tag
            clean_chunks.append(script_text[last_idx:start])
            
            # Calculate the position *inside the future clean text*
            current_clean_pos = offset + (start - last_idx)
            emotion_events.append(EmotionEvent(
                emotion_code=match.group(1),
                position=current_clean_pos
            ))
            
            offset = current_clean_pos
            last_idx = end
            
        clean_chunks.append(script_text[last_idx:])
        text_sans_emotions = "".join(clean_chunks)

        # Step 4: Find breaks in the emotion-stripped text so indices are 100% accurate
        # Find double line breaks (Paragraphs)
        for match in self.para_pattern.finditer(text_sans_emotions):
            paragraph_breaks.append(match.start())

        # Find single line breaks (skipping ones that are part of paragraphs)
        for match in self.line_pattern.finditer(text_sans_emotions):
            idx = match.start()
            # Ensure this \n isn't part of an already captured paragraph break block
            is_part_of_para = any(p_idx <= idx <= (p_idx + 2) for p_idx in paragraph_breaks)
            if not is_part_of_para:
                line_breaks.append(idx)

        # Step 5: Final text normalization (Old script cleanup rules)
        # Handle trailing whitespaces on lines, double spaces, and leading space
        clean_text = text_sans_emotions
        while "  " in clean_text:
            clean_text = clean_text.replace("  ", " ")
        while "\n " in clean_text:
            clean_text = clean_text.replace("\n ", "\n")
        while " \n" in clean_text:
            clean_text = clean_text.replace(" \n", "\n")
        
        clean_text = clean_text.lstrip(" ")

        return ScriptMetadata(
            clean_text=clean_text,
            emotion_events=emotion_events,
            line_breaks=line_breaks,
            paragraph_breaks=paragraph_breaks,
        )

    def get_emotion_at_position(self, metadata: ScriptMetadata, position: int) -> str:
        """
        Get the active emotion code at a specific text position.
        """
        active_emotion = "explain"
        
        for event in metadata.emotion_events:
            if event.position <= position:
                active_emotion = event.emotion_code
            else:
                break
                
        return active_emotion