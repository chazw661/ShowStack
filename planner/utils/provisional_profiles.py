"""Power profiles whose figures are borrowed from another model, and the
AmpModel tidy-up that lets amps reach them.

The LA7.16 (touring, SC32) and the LA7.16i (install) are different products.
L-Acoustics publishes mains draw for the LA7.16i only (OM v5.0 pp.24-25); the
LA7.16's spec sheet has output power and nothing on mains draw. Until its
own figures are found, the LA7.16 profile carries a copy of the LA7.16i's,
marked provisional: the profile's ``figures_status`` is set (so its name
reads "... (provisional)") and every copied rating and factor is
``verified=False`` with the provisional source.

Called by data migration 0212 and by load_amp_profiles (for a database that
gets the LA7.16i profile after the migration has run). It takes the model
classes so the migration can pass its historical ones, and it only uses
fields that exist at 0212. Idempotent: nothing already there is changed.
"""

MANUFACTURER = 'L-Acoustics'
# Spellings normalised to MANUFACTURER on AmpModel. Exact matches only.
MANUFACTURER_SPELLINGS = ["L'Acoustics"]

SOURCE_MODEL = 'LA7.16i'
TARGET_MODEL = 'LA7.16'
PROVISIONAL = "provisional: copied from LA7.16i, same platform, unverified for LA7.16"
# Not provisional: the Preset Guide's drive-capacity column is "LA7.16(i)",
# published for both amps.
MIN_LOAD_SOURCE = ("L-Acoustics Preset Guide owner's manual (EN) v25.0 p.119: LA7.16(i) "
                   "column, up to 4 x X4i (16 ohm) per output (4 ohm, p.118)")

# Fields not copied from the source profile.
_NOT_COPIED = {'id', 'manufacturer', 'model', 'figures_status', 'min_load_source',
               'notes', 'created_at', 'updated_at'}


def normalise_manufacturers(AmpModel):
    """"L'Acoustics" -> "L-Acoustics" on every AmpModel row. Returns the
    number of rows changed."""
    return AmpModel.objects.filter(
        manufacturer__in=MANUFACTURER_SPELLINGS).update(manufacturer=MANUFACTURER)


def ensure_la716_profile(AmplifierProfile, AmplifierLoadRating, AmplifierVoltageFactor):
    """The LA7.16 profile, created from the LA7.16i's figures if missing, with
    any of the LA7.16i's ratings and factors it lacks. None when there is no
    LA7.16i profile to copy from."""
    source = AmplifierProfile.objects.filter(
        manufacturer=MANUFACTURER, model=SOURCE_MODEL).first()
    if source is None:
        return None
    values = {
        f.attname: getattr(source, f.attname)
        for f in AmplifierProfile._meta.concrete_fields if f.name not in _NOT_COPIED
    }
    values.update(
        figures_status=PROVISIONAL,
        min_load_source=MIN_LOAD_SOURCE if source.min_load_ohms is not None else '',
        notes=f"16 channels on one SC32 (touring). Power figures {PROVISIONAL}.",
    )
    target, _ = AmplifierProfile.objects.get_or_create(
        manufacturer=MANUFACTURER, model=TARGET_MODEL, defaults=values)

    for r in AmplifierLoadRating.objects.filter(profile=source):
        AmplifierLoadRating.objects.get_or_create(
            profile=target, condition=r.condition, load_ohms=r.load_ohms,
            mains_voltage=r.mains_voltage,
            defaults={
                'current_amps': r.current_amps,
                'current_is_upper_bound': r.current_is_upper_bound,
                'power_watts': r.power_watts,
                'channels_driven': r.channels_driven,
                'source': f"{PROVISIONAL} ({r.source})"[:300],
                'source_url': r.source_url,
                'verified': False,
            })
    for v in AmplifierVoltageFactor.objects.filter(profile=source):
        AmplifierVoltageFactor.objects.get_or_create(
            profile=target, mains_voltage=v.mains_voltage,
            defaults={
                'current_multiplier': v.current_multiplier,
                'source': f"{PROVISIONAL} ({v.source})"[:300],
                'verified': False,
            })
    return target


def link_la716_amp_models(AmpModel, profile):
    """Point every L-Acoustics "LA7.16" AmpModel without a profile at the
    LA7.16 profile. Never the LA7.16i row, and never a row a superuser has
    already linked. Returns the number linked."""
    if profile is None:
        return 0
    return AmpModel.objects.filter(
        manufacturer=MANUFACTURER, model_name__iexact=TARGET_MODEL,
        power_profile__isnull=True,
    ).update(power_profile=profile)


def apply(AmpModel, AmplifierProfile, AmplifierLoadRating, AmplifierVoltageFactor):
    normalise_manufacturers(AmpModel)
    profile = ensure_la716_profile(AmplifierProfile, AmplifierLoadRating,
                                   AmplifierVoltageFactor)
    link_la716_amp_models(AmpModel, profile)
    return profile
