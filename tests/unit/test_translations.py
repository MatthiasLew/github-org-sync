import pytest

from github_org_sync.i18n.translations import TRANSLATIONS


@pytest.mark.unit
def test_translations_sync() -> None:
    # Ensure locales pl and en are present
    assert "pl" in TRANSLATIONS
    assert "en" in TRANSLATIONS

    pl_keys = set(TRANSLATIONS["pl"].keys())
    en_keys = set(TRANSLATIONS["en"].keys())

    missing_in_en = pl_keys - en_keys
    missing_in_pl = en_keys - pl_keys

    assert not missing_in_en, f"Translation keys present in 'pl' but missing in 'en': {missing_in_en}"
    assert not missing_in_pl, f"Translation keys present in 'en' but missing in 'pl': {missing_in_pl}"
