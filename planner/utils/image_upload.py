"""Decide whether uploaded bytes are an image we will store, and what type.

The type comes from the bytes, never from the client. ``UploadedFile.
content_type`` is whatever the browser (or a script) put in the multipart
header, and the drag-from-URL path used the remote server's Content-Type. Both
were written straight into a ``data:<type>;base64,`` URL.

Pillow identifies the format from the file's own header and ``verify()`` walks
the structure without decoding every pixel. Only JPEG, PNG and WebP are
accepted -- what browsers render in an <img> and what headshots actually are.
SVG is not an option: Pillow cannot open it, so it is refused like any other
non-image.
"""

from io import BytesIO

from PIL import Image, UnidentifiedImageError

MAX_PHOTO_BYTES = 5 * 1024 * 1024
# Header-declared dimensions, checked before anything is decoded. 40 MP is a
# large phone photo; a decompression bomb declares far more.
MAX_PHOTO_PIXELS = 40_000_000

ALLOWED_FORMATS = {
    'JPEG': 'image/jpeg',
    'PNG': 'image/png',
    'WEBP': 'image/webp',
}


class ImageRejected(Exception):
    """The bytes are not an image we accept. ``str()`` is user-safe."""


def validate_photo_bytes(data):
    """Return the MIME type for ``data`` if it is an acceptable photo, else raise."""
    if not data:
        raise ImageRejected('Empty file')
    if len(data) > MAX_PHOTO_BYTES:
        raise ImageRejected(f'Image exceeds {MAX_PHOTO_BYTES // (1024 * 1024)} MB limit')
    try:
        with Image.open(BytesIO(data)) as img:
            fmt = img.format
            width, height = img.size
            if fmt not in ALLOWED_FORMATS:
                raise ImageRejected('Only JPEG, PNG or WebP images are accepted')
            if width * height > MAX_PHOTO_PIXELS:
                raise ImageRejected('Image dimensions are too large')
            img.verify()
    except ImageRejected:
        raise
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError,
            SyntaxError, ValueError):
        raise ImageRejected('That file is not a valid image')
    return ALLOWED_FORMATS[fmt]


def read_upload_capped(uploaded_file):
    """Read an UploadedFile, refusing before reading more than the cap."""
    if uploaded_file.size is not None and uploaded_file.size > MAX_PHOTO_BYTES:
        raise ImageRejected(f'Image exceeds {MAX_PHOTO_BYTES // (1024 * 1024)} MB limit')
    data = uploaded_file.read(MAX_PHOTO_BYTES + 1)
    if len(data) > MAX_PHOTO_BYTES:
        raise ImageRejected(f'Image exceeds {MAX_PHOTO_BYTES // (1024 * 1024)} MB limit')
    return data
