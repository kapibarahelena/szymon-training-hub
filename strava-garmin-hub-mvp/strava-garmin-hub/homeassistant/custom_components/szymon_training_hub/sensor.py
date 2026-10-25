from datetime import timedelta
import logging
import aiohttp
from homeassistant.components.sensor import SensorEntity, SensorDeviceClass
from homeassistant.const import UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, CoordinatorEntity
from .const import DOMAIN, CONF_BASE_URL, CONF_API_KEY, CONF_METRIC_ENTITIES, DEFAULT_SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    cfg = hass.data[DOMAIN][entry.entry_id]
    async def fetch():
        session = aiohttp.ClientSession()
        try:
            headers = {"X-Hub-API-Key": cfg[CONF_API_KEY]}
            async with session.get(cfg[CONF_BASE_URL] + "/api/v1/dashboard", headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                resp.raise_for_status(); dashboard = await resp.json()
            async with session.get(cfg[CONF_BASE_URL] + "/api/v1/analytics/load", headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                resp.raise_for_status(); load = await resp.json()
            async with session.get(cfg[CONF_BASE_URL] + "/api/v1/integrations/status", headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                resp.raise_for_status(); status = await resp.json()
            # Push mapped HA measurements to the hub. Mapping format per line:
            # entity_id;canonical_metric;unit
            metric_items = []
            mapping_text = cfg.get(CONF_METRIC_ENTITIES, "")
            for line in mapping_text.splitlines():
                parts = [part.strip() for part in line.split(";")]
                if len(parts) != 3 or not all(parts):
                    continue
                entity_id, metric, unit = parts
                try:
                    state_obj = hass.states.get(entity_id)
                    if state_obj is None or state_obj.state in ("unknown", "unavailable", "none", ""):
                        continue
                    state_value = float(state_obj.state)
                    if state_value != state_value or state_value in (float("inf"), float("-inf")):
                        continue
                    measured_at = state_obj.last_changed.isoformat()
                    metric_items.append({"metric": metric, "value": state_value, "unit": unit, "measured_at": measured_at, "source_entity_id": entity_id, "attributes": {"friendly_name": state_obj.attributes.get("friendly_name")}})
                except (TypeError, ValueError, aiohttp.ClientError):
                    continue
            if metric_items:
                async with session.post(cfg[CONF_BASE_URL] + "/api/v1/metrics/ingest", headers=headers, json={"source": "home_assistant", "items": metric_items}, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    resp.raise_for_status()
            return {"dashboard": dashboard, "load": load, "status": status}
        finally:
            await session.close()
    coordinator = DataUpdateCoordinator(hass, _LOGGER, name="Szymon Training Hub", update_method=fetch, update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL))
    await coordinator.async_config_entry_first_refresh()
    hass.data[DOMAIN][entry.entry_id + "_coordinator"] = coordinator
    async_add_entities([
        HubSensor(coordinator, "load_today_minutes", "Dzisiejszy czas treningu", "min", lambda d: d["load"].get("today_minutes")),
        HubSensor(coordinator, "activity_count", "Ostatnie aktywności dostępne", "", lambda d: len(d["dashboard"].get("recent_activities", []))),
        HubSensor(coordinator, "sync_status", "Status integracji huba", "", lambda d: ", ".join(f"{x['source']}:{x['status']}" for x in d["status"].get("items", []))),
    ], update_before_add=True)

class HubSensor(CoordinatorEntity, SensorEntity):
    _attr_has_entity_name = True
    def __init__(self, coordinator, key, name, unit, value_fn):
        super().__init__(coordinator)
        self._key, self._value_fn = key, value_fn
        self._attr_unique_id = f"{DOMAIN}_{key}"
        self._attr_name = name
        self._attr_native_unit_of_measurement = unit or None
    @property
    def native_value(self):
        try: return self._value_fn(self.coordinator.data)
        except (KeyError, TypeError, ValueError): return None
