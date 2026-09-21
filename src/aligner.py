"""
Gentle API network client for speech-to-text alignment.
Wraps synchronous HTTP communication with the local Gentle transcription service.
"""

import json
import requests
from typing import List, Optional
from .models import AlignedWord, PhonemeInterval


class GentleAligner:
    """
    Synchronous HTTP client for Gentle speech alignment API.
    
    Connects to a local Gentle Docker container instance running on 
    http://localhost:8765 and processes audio/transcript pairs to produce 
    frame-accurate phoneme timing.
    """

    def __init__(self, base_url: str = "http://localhost:8765"):
        """
        Initialize the Gentle API client.
        
        Args:
            base_url: Base URL of the Gentle API service.
        """
        self.base_url = base_url
        # FIX 1: Updated endpoint to include '/transcriptions?async=false'
        # Without this, Gentle returns HTML rather than JSON data.
        self.transcription_endpoint = f"{base_url}/transcriptions?async=false"

    def align(self, audio_path: str, transcript: str) -> List[AlignedWord]:
        """
        Perform phoneme-level alignment on audio against a transcript.
        
        Args:
            audio_path: Path to the audio file (.wav recommended).
            transcript: Clean transcript text to align.
            
        Returns:
            List of AlignedWord objects with phoneme timing.
            
        Raises:
            ConnectionError: If unable to reach the Gentle service.
            ValueError: If alignment fails or produces invalid response.
        """
        try:
            # Open audio file and prepare multipart form data
            with open(audio_path, 'rb') as audio_file:
                files = {'audio': audio_file}
                data = {'transcript': transcript}

                # Send synchronous request
                response = requests.post(
                    self.transcription_endpoint,
                    files=files,
                    data=data,
                    timeout=300,  # Long timeout for processing
                )

            response.raise_for_status()
            result = response.json()

            # FIX 2: Gentle does not return a 'success' key.
            # We now safely check if the expected 'words' list exists instead.
            if 'words' not in result:
                raise ValueError("Alignment failed: Invalid or empty response structure from Gentle.")

            # Parse the response into AlignedWord objects
            return self._parse_alignment_result(result)

        except requests.exceptions.ConnectionError as e:
            raise ConnectionError(
                f"Failed to connect to Gentle API at {self.base_url}. "
                "Verify local Docker container execution via: "
                "docker run -d -p 8765:8765 lowerquality/gentle"
            ) from e
        except FileNotFoundError as e:
            raise FileNotFoundError(f"Audio file not found: {audio_path}") from e

    def _parse_alignment_result(self, result: dict) -> List[AlignedWord]:
        """
        Parse JSON response from Gentle into AlignedWord objects.
        
        Args:
            result: JSON response dictionary from Gentle API.
            
        Returns:
            List of AlignedWord objects.
        """
        aligned_words = []

        words = result.get('words', [])
        for word_data in words:
            # Skip words not found in audio
            if word_data.get('case') == 'not-found-in-audio':
                continue

            word_text = word_data.get('word')
            start_time = word_data.get('start')
            end_time = word_data.get('end')

            if start_time is None or end_time is None:
                continue

            # Parse phonemes for this word
            phones = []
            for phone_data in word_data.get('phones', []):
                phone_str = phone_data.get('phone', 'sil')
                duration = phone_data.get('duration', 0.0)
                phones.append(PhonemeInterval(phone_str, duration))

            aligned_words.append(
                AlignedWord(
                    word=word_text,
                    start_time=start_time,
                    end_time=end_time,
                    phones=phones,
                )
            )
    
        return aligned_words