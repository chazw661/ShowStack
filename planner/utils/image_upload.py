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


def validate_photo_bytes(data, formats=None, refusal='Only JPEG, PNG or WebP images are accepted'):
    """Return the MIME type for ``data`` if it is an acceptable photo, else
    raise. ``formats`` narrows ALLOWED_FORMATS, with ``refusal`` as the
    message for anything outside it."""
    formats = formats or ALLOWED_FORMATS
    if not data:
        raise ImageRejected('Empty file')
    if len(data) > MAX_PHOTO_BYTES:
        raise ImageRejected(f'Image exceeds {MAX_PHOTO_BYTES // (1024 * 1024)} MB limit')
    try:
        with Image.open(BytesIO(data)) as img:
            fmt = img.format
            width, height = img.size
            if fmt not in formats:
                raise ImageRejected(refusal)
            if width * height > MAX_PHOTO_PIXELS:
                raise ImageRejected('Image dimensions are too large')
            img.verify()
    except ImageRejected:
        raise
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError,
            SyntaxError, ValueError):
        raise ImageRejected('That file is not a valid image')
    return formats[fmt]


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


# A logo prints at most 2" across a 2" label; 1200 px is 600 dpi at that.
LOGO_MAX_EDGE = 1200
LOGO_FORMATS = {'JPEG': 'image/jpeg', 'PNG': 'image/png'}
LOGO_JPEG_QUALITY = 90
# Alpha at or below this, or within this of the corner colour on an opaque
# logo, counts as empty margin and is trimmed.
LOGO_TRIM_THRESHOLD = 16


def normalize_logo(data):
    """Validate ``data`` as a PNG or JPEG logo and re-encode it.

    Returns ``(bytes, content_type, width, height, sha256_hex)``.

    Unlike a headshot, transparency is kept (a logo sits on the label's
    colour), so a logo with alpha comes back as PNG and an opaque one as
    JPEG. Empty margins are trimmed -- transparent ones, or on an opaque
    logo a border the colour of its corner -- so the logo's own artwork is
    what gets sized to 8 mm on the label. SVG and every other format is
    refused: Pillow cannot open SVG, and the formats check refuses the rest.
    """
    import hashlib

    from PIL import ImageChops, ImageOps

    validate_photo_bytes(data, LOGO_FORMATS, 'Logos must be PNG or JPEG')
    try:
        with Image.open(BytesIO(data)) as img:
            img = ImageOps.exif_transpose(img)
            has_alpha = img.mode in ('RGBA', 'LA', 'PA') or (
                img.mode == 'P' and 'transparency' in img.info)
            img = img.convert('RGBA' if has_alpha else 'RGB')
            if has_alpha:
                mask = img.getchannel('A').point(lambda a: 255 if a > LOGO_TRIM_THRESHOLD else 0)
            else:
                corner = Image.new('RGB', img.size, img.getpixel((0, 0)))
                mask = ImageChops.difference(img, corner).convert('L').point(
                    lambda v: 255 if v > LOGO_TRIM_THRESHOLD else 0)
            box = mask.getbbox()
            if box is None:
                raise ImageRejected('That logo is blank')
            img = img.crop(box)
            img.thumbnail((LOGO_MAX_EDGE, LOGO_MAX_EDGE), Image.LANCZOS)
            out = BytesIO()
            if has_alpha:
                img.save(out, format='PNG', optimize=True)
                content_type = 'image/png'
            else:
                img.save(out, format='JPEG', quality=LOGO_JPEG_QUALITY, optimize=True)
                content_type = 'image/jpeg'
            width, height = img.size
    except ImageRejected:
        raise
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError,
            SyntaxError, ValueError):
        raise ImageRejected('That file is not a valid image')
    content = out.getvalue()
    return content, content_type, width, height, hashlib.sha256(content).hexdigest()


def session_photo_data_url(data):
    """``data`` re-encoded like a headshot, as the data URL a slot stores for
    a session-only photo (PresenterSlot.photo_data)."""
    import base64

    content, content_type, _w, _h, _sha = normalize_headshot(data)
    return f'data:{content_type};base64,' + base64.b64encode(content).decode('ascii')


# Two photos whose fingerprints differ in this many bits or fewer are the same
# picture -- a re-upload, a re-crop, a re-save. Measured on prod (October
# 2026): the re-uploads of one headshot came out 1-9 bits apart; different
# speakers on the same mic label 26-36; two genuinely different photos of one
# person 16-18.
NEAR_IDENTICAL_BITS = 10


def photo_fingerprint(data):
    """64-bit difference hash of ``data``: compares neighbouring pixels of a
    9x8 greyscale thumbnail, so it survives re-encoding, rescaling and light
    cropping, and two different faces land about half their bits apart.

    Raises ImageRejected for anything Pillow cannot open.
    """
    from PIL import ImageOps

    try:
        with Image.open(BytesIO(data)) as img:
            img = ImageOps.exif_transpose(img)
            if img.mode != 'RGB':
                rgba = img.convert('RGBA')
                img = Image.new('RGBA', rgba.size, 'white')
                img.alpha_composite(rgba)
            px = list(img.convert('L').resize((9, 8), Image.LANCZOS).getdata())
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError,
            SyntaxError, ValueError):
        raise ImageRejected('That file is not a valid image')
    bits = 0
    for row in range(8):
        for col in range(8):
            bits = (bits << 1) | (px[row * 9 + col] > px[row * 9 + col + 1])
    return bits


def fingerprint_distance(a, b):
    return bin(a ^ b).count('1')
