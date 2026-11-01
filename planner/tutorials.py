"""Tutorial videos: the one place their YouTube IDs are written down.

A blank ID hides every "Watch how" button for that video (on pages and in
Help), so a video can be pulled by emptying its entry here.
"""

TUTORIAL_VIDEOS = {
    'power': '2okDyuSFzNQ',
    'labels': 'uCbxrglI4Dc',
}

# What the button and the player's dialog call each video, and its length.
TUTORIAL_DETAILS = {
    'power': {'title': 'How the power plan works', 'minutes': '1½'},
    'labels': {'title': 'How to print beltpack labels', 'minutes': '2'},
}

# Played from the privacy-enhanced domain: no YouTube cookies until the
# viewer presses play, and nothing at all is fetched until they open it.
EMBED_URL = 'https://www.youtube-nocookie.com/embed/{}'


def tutorial(key):
    """``{'key', 'video_id', 'title', 'minutes', 'embed_url'}`` for the video
    named ``key``, or None when it has no ID (or no such video)."""
    video_id = (TUTORIAL_VIDEOS.get(key) or '').strip()
    if not video_id:
        return None
    details = TUTORIAL_DETAILS.get(key, {})
    return {
        'key': key,
        'video_id': video_id,
        'title': details.get('title', 'Watch how'),
        'minutes': details.get('minutes', ''),
        'embed_url': EMBED_URL.format(video_id),
    }
