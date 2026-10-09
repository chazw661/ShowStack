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


# The A2 card shows the photo at 70 px and its hover-expand at roughly 200 px;
# 512 on the long edge is sharp on a 2x screen with room to spare.
HEADSHOT_MAX_EDGE = 512
HEADSHOT_JPEG_QUALITY = 85


def normalize_headshot(data):
    """Validate ``data`` and re-encode it as the stored headshot.

    Returns ``(jpeg_bytes, 'image/jpeg', width, height, sha256_hex)``.

    Re-encoding rather than storing the upload is what makes the stored bytes
    trustworthy: whatever was in the file (EXIF GPS, an ICC profile, trailing
    data, a polyglot payload) does not survive a decode to pixels and a fresh
    encode. It also takes the typical 300 KB PNG screenshot to ~30 KB.

    Orientation is applied from EXIF first -- phone photos are stored sideways
    with a rotate tag, and the tag is dropped by the re-encode. Transparency
    is flattened onto white, since JPEG has no alpha.
    """
    import hashlib

    from PIL import ImageOps

    validate_photo_bytes(data)
    try:
        with Image.open(BytesIO(data)) as img:
            img.draft('RGB', (HEADSHOT_MAX_EDGE * 2, HEADSHOT_MAX_EDGE * 2))
            img = ImageOps.exif_transpose(img)
            if img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info):
                rgba = img.convert('RGBA')
                flat = Image.new('RGB', rgba.size, (255, 255, 255))
                flat.paste(rgba, mask=rgba.getchannel('A'))
                img = flat
            else:
                img = img.convert('RGB')
            img.thumbnail((HEADSHOT_MAX_EDGE, HEADSHOT_MAX_EDGE), Image.LANCZOS)
            out = BytesIO()
            img.save(out, format='JPEG', quality=HEADSHOT_JPEG_QUALITY,
                     optimize=True, progressive=True)
            width, height = img.size
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError,
            SyntaxError, ValueError):
        raise ImageRejected('That file is not a valid image')
    content = out.getvalue()
    return content, 'image/jpeg', width, height, hashlib.sha256(content).hexdigest()
