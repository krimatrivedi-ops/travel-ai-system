import re
from youtube_transcript_api import YouTubeTranscriptApi, NoTranscriptFound, NotTranslatable
from typing import Optional, List, Dict

def extract_video_id(url: str) -> Optional[str]:
    """
    Extract the video ID from a YouTube URL.
    """
    patterns = [
        r"(?:v=|\/)([0-9A-Za-z_-]{11}).*",
        r"youtu\.be\/([0-9A-Za-z_-]{11})",
        r"youtube\.com\/embed\/([0-9A-Za-z_-]{11})",
        r"youtube\.com\/shorts\/([0-9A-Za-z_-]{11})"
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None

def get_transcript(video_id: str) -> str:
    """
    Fetch the transcript for a given video ID.
    Returns the concatenated text of the transcript.
    """
    try:
        # transcript_list = YouTubeTranscriptApi.list(video_id)
        api = YouTubeTranscriptApi()
        transcript_list = api.list(video_id) 
        try:
            # 1. Try to get English
            data = transcript_list.find_transcript(['en']).fetch()
        except NoTranscriptFound:
            try:
                # 2. Try to get Hindi and translate it
                data = transcript_list.find_transcript(['hi']).translate('en').fetch()
            except (NotTranslatable, NoTranscriptFound):
                # 3. Fallback: Fetch original Hindi if translation is blocked
                data = transcript_list.find_transcript(['hi']).fetch()

        # ALWAYS join the data into a string before returning
        return " ".join([entry.text for entry in data])

    except Exception as e:
        # Catch-all for videos with NO transcripts at all
        raise Exception(f"Could not retrieve transcript: {str(e)}")