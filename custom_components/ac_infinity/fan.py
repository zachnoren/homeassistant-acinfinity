# custom_components/acinfinity/fan.py

from homeassistant.components.fan import FanEntity, FanEntityFeature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import DOMAIN  # import domain constant
# Assuming the integration’s main ACInfinity coordinator/class is exposed via hass.data[DOMAIN][entry_id]

async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities):
    """Set up AC Infinity fan entities for each controller port."""
    ac_infinity = hass.data[DOMAIN][entry.entry_id]  # The ACInfinity coordinator/client instance
    entities = []
    # Iterate through all devices and ports managed by this integration instance
    for device_id, device_data in ac_infinity.data.items():
        for port_id, port_data in device_data["ports"].items():
            # Create a fan entity for each port
            name = port_data.get("name") or f"Port {port_id}"  # Use provided name or fallback
            entities.append(ACInfinityFanEntity(ac_infinity, device_id, port_id, name))
    async_add_entities(entities, update_before_add=True)


class ACInfinityFanEntity(CoordinatorEntity, FanEntity):
    """Fan entity to control an AC Infinity device (e.g., fan on a UIS port)."""

    _attr_supported_features = FanEntityFeature.SET_SPEED
    _attr_speed_count = 10  # AC Infinity devices have 10 discrete speed levels (1-10)

    def __init__(self, ac_infinity, device_id: str, port_id: int, name: str):
        """Initialize the AC Infinity Fan entity."""
        super().__init__(ac_infinity)  # use the DataUpdateCoordinator (if ac_infinity is one)
        self._ac_infinity = ac_infinity
        self._device_id = device_id
        self._port_id = port_id
        self._attr_name = name
        # Unique ID combines controller device and port, ensuring uniqueness
        self._attr_unique_id = f"{device_id}_{port_id}_fan"
        # Link this entity to the AC Infinity device in the device registry
        self._attr_device_info = {
            "identifiers": {(DOMAIN, f"{device_id}_{port_id}")},
            "name": name,
            "via_device": (DOMAIN, device_id)
        }

    @property
    def percentage(self) -> int:
        """Return the current speed percentage (0-100)."""
        # Get latest data for this port from the coordinator
        port_data = self._ac_infinity.data[self._device_id]["ports"][self._port_id]
        current_mode = port_data.get("active_mode")
        on_speed = port_data.get("on_spead") or 0
        current_speed = port_data.get("current_speed") or 0
        if current_mode is None:
            return 0
        # If device is in manual On mode, use the configured On Speed
        if current_mode == 1 or current_mode == "On":
            return int(on_speed) * 10
        # If device is Off, speed is 0%
        if current_mode == 0 or current_mode == "Off":
            return 0
        # For Auto or other modes, report the current running speed (if running)
        return int(current_speed) * 10

    @property
    def is_on(self) -> bool:
        """Return True if the fan is on (running)."""
        port_data = self._ac_infinity.data[self._device_id]["ports"][self._port_id]
        current_mode = port_data.get("active_mode")
        current_speed = port_data.get("current_speed") or 0
        if current_mode is None:
            return False
        # Consider the fan "on" if in manual On mode, or if in an automatic mode but currently running
        if (current_mode == 1 or current_mode == "On"):
            return True
        # If in Auto/Cycle/etc., treat as on if the current output speed > 0
        return int(current_speed) > 0

    async def async_turn_on(self, percentage: int | None = None, **kwargs) -> None:
        """Turn the fan on. If percentage given, set to that speed, otherwise use last on_speed."""
        # Determine if a specific speed was requested
        if percentage is not None:
            # Delegate to set_percentage to handle turning on at the specified speed
            await self.async_set_percentage(percentage)
        else:
            # No speed provided: just switch mode to "On" (which will use the previously set on_speed)
            await self._ac_infinity.set_device_port_settings(
                self._device_id,
                self._port_id,
                [("active_mode", "On"), ("on_self_spead", 1)]
            )
        # Mark state for update (will refresh on next poll or after API call)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs) -> None:
        """Turn the fan off."""
        # Set the device mode to "Off"
        await self._ac_infinity.set_device_port_settings(
            self._device_id,
            self._port_id,
            [("active_mode", "Off")]
        )
        await self.coordinator.async_request_refresh()

    async def async_set_percentage(self, percentage: int) -> None:
        """Set the fan speed as a percentage (0-100)."""
        if percentage is None:
            return
        # Convert percentage (1-100) to nearest speed level 1-10
        speed_level = max(1, min(10, round(percentage / 10)))
        if speed_level == 0:
            # Treat 0% as turning off
            await self.async_turn_off()
        else:
            # Set mode to On and update the On Speed value
            await self._ac_infinity.set_device_port_settings(
                self._device_id,
                self._port_id,
                [("active_mode", "On"), ("on_spead", speed_level), ("on_self_spead", 1)]
            )
            await self.coordinator.async_request_refresh()
