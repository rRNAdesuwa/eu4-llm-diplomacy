# Shared capital identification and bounded saved-province binding.
from __future__ import annotations

def _native_special_runtime(
        native_probe: dict[str, object], action: str,
        ) -> dict[str, object] | None:
    snapshot = native_probe.get("snapshot")
    runtime = snapshot.get("runtime") if isinstance(snapshot, dict) else None
    if not isinstance(runtime, dict):
        return None
    item = runtime.get(action)
    if not isinstance(item, dict):
        item = runtime.get("special")
    return item if isinstance(item, dict) else None


def _bind_special_capital_save_observation(
        save_probe: dict[str, object], native_probe: dict[str, object],
        action: str, country: str,
        ) -> int | None:
    """Bind the verified native capital id to the bounded save province row.

    The shared save scanner returns requested province rows separately from
    country rows.  The special comparator historically accepted a nested
    country ``capital`` field, so expose the same observation from the
    explicitly requested province without guessing a province id.
    """

    special = _native_special_runtime(native_probe, action)
    capital_id = special.get("capital_province_id") if isinstance(special, dict) else None
    verified = special.get("capital_province_id_verified") if isinstance(special, dict) else False
    if type(capital_id) is not int or verified is not True:
        return None
    parsed = save_probe.get("parsed")
    if not isinstance(parsed, dict):
        return capital_id
    provinces = parsed.get("provinces")
    province = provinces.get(str(capital_id)) if isinstance(provinces, dict) else None
    if not isinstance(province, dict):
        return capital_id
    fields = province.get("fields")
    religion_field = fields.get("religion") if isinstance(fields, dict) else None
    religion_value = (
        religion_field.get("value") if isinstance(religion_field, dict) else None)
    countries = parsed.get("countries")
    country_item = countries.get(country) if isinstance(countries, dict) else None
    if isinstance(country_item, dict):
        country_item["capital_province_id"] = capital_id
        country_item["capital_province_id_verified"] = True
        country_item["capital"] = {
            "province_id": capital_id,
            "religion": religion_value,
            "found": province.get("found") is True,
            "complete": province.get("complete") is True,
        }
        country_item["capital_religion"] = {
            "value": religion_value,
            "found": religion_value is not None,
            "province_id": capital_id,
        }
    save_probe["special_capital_province"] = {
        "action_id": action,
        "country": country,
        "province_id": capital_id,
        "verified_from_native": True,
        "religion": religion_value,
        "province_found": province.get("found") is True,
        "province_complete": province.get("complete") is True,
    }
    return capital_id


