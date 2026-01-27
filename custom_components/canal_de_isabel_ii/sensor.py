"""Sensor platform for Canal de Isabel II."""
import logging
from typing import Any, Dict, List, Optional

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfVolume
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

from homeassistant.components.recorder.models import StatisticData, StatisticMetaData, StatisticMeanType
from homeassistant.util.unit_conversion import VolumeConverter
from homeassistant.components.recorder.statistics import (
    async_import_statistics,
    get_last_statistics,
)
from homeassistant.components.recorder import get_instance
from homeassistant.util import dt as dt_util

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the sensor platform."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    
    if not coordinator.data:
        _LOGGER.warning("No data received from Canal de Isabel II, cannot create sensors yet.")
        return

    contracts = {}
    for row in coordinator.data:
        contract_id = row.get("Contrato")
        if contract_id and contract_id not in contracts:
            contracts[contract_id] = row

    entities = []
    for contract_id, row_data in contracts.items():
        entities.append(CanalIsabelIIConsumptionSensor(coordinator, contract_id, row_data))
        entities.append(CanalIsabelIITotalConsumptionSensor(hass, coordinator, contract_id, row_data))

    async_add_entities(entities)


class CanalIsabelIIConsumptionSensor(CoordinatorEntity, SensorEntity):
    """Representation of a Canal de Isabel II Daily Consumption Sensor."""
    
    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        contract_id: str,
        initial_data: Dict[str, Any],
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._contract_id = contract_id
        self._attr_name = f"Canal de Isabel II Consumption {contract_id}"
        self._attr_unique_id = f"canal_ii_consumption_{contract_id}"
        self._attr_native_unit_of_measurement = UnitOfVolume.LITERS
        self._attr_device_class = SensorDeviceClass.VOLUME
        self._attr_state_class = SensorStateClass.TOTAL
        self._attr_icon = "mdi:water"

    @property
    def native_value(self) -> Optional[float]:
        """Return the state of the sensor (latest daily consumption)."""
        latest_row = self._get_latest_row()
        if latest_row and "Consumo (litros)" in latest_row:
            try:
                return float(latest_row["Consumo (litros)"])
            except ValueError:
                return None
        return None

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return the state attributes."""
        latest_row = self._get_latest_row()
        if latest_row:
            return {
                "reading_date": latest_row.get("Fecha/Hora"),
                "period": latest_row.get("Periodo"),
                "meter_id": latest_row.get("Contador"),
                "address": latest_row.get("Dirección"),
                "frequency": latest_row.get("Frecuencia"),
            }
        return {}
    async def async_added_to_hass(self) -> None:
        """When entity is added to hass."""
        await super().async_added_to_hass()
        self._handle_coordinator_update()

    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        # Process historical statistics in the background
        self.hass.async_create_task(self._import_historical_statistics())
        super()._handle_coordinator_update()

    async def _import_historical_statistics(self) -> None:
        """Import historical statistics from CSV."""
        from homeassistant.components.recorder.statistics import (
            async_import_statistics,
            statistics_during_period,
        )
        from datetime import datetime
        
        rows = self._get_sorted_rows()
        if not rows:
            return

        statistic_id = self.entity_id
        
        # Prepare valid rows first
        valid_rows = []
        timestamps = []
        for row in rows:
            try:
                date_str = row.get("Fecha/Hora")
                dt_val = datetime.strptime(date_str, "%d/%m/%Y %H")
                dt_utc = dt_val.replace(tzinfo=dt_util.DEFAULT_TIME_ZONE).astimezone(dt_util.UTC)
                val = float(row.get("Consumo (litros)", 0))
                valid_rows.append((dt_utc, val))
                timestamps.append(dt_utc)
            except ValueError:
                continue

        if not valid_rows:
            return

        start_time = timestamps[0]
        end_time = timestamps[-1] 
        
        existing_stats = await get_instance(self.hass).async_add_executor_job(
            statistics_during_period,
            self.hass,
            start_time,
            end_time,
            [statistic_id],
            "hour",
            None,
            {"mean"},
        )
        
        existing_timestamps = set()
        if existing_stats and statistic_id in existing_stats:
            for stat in existing_stats[statistic_id]:
                t = stat.get("start")
                if t:
                    if isinstance(t, (float, int)):
                         existing_timestamps.add(dt_util.utc_from_timestamp(t))
                    else:
                         existing_timestamps.add(dt_util.as_utc(t))

        metadata = StatisticMetaData(
            has_mean=True,
            has_sum=False,
            name=self.name,
            source='recorder',
            statistic_id=statistic_id,
            unit_of_measurement=UnitOfVolume.LITERS,
            mean_type=StatisticMeanType.ARITHMETIC,
            unit_class=VolumeConverter.UNIT_CLASS,
        )

        statistics = []
        
        for dt_utc, val in valid_rows:
            # If we already have a stat for this timestamp, skip
            if dt_utc in existing_timestamps:
                continue
                
            statistics.append(
                StatisticData(
                    start=dt_utc,
                    state=val, 
                    mean=val,
                )
            )

        if statistics:
             _LOGGER.debug(f"Importing {len(statistics)} new historical stats for {statistic_id}")
             await get_instance(self.hass).async_add_executor_job(async_import_statistics, self.hass, metadata, statistics)

    def _get_sorted_rows(self) -> List[Dict[str, Any]]:
        """Get rows sorted by date ascending."""
        rows = [row for row in self.coordinator.data if row.get("Contrato") == self._contract_id]
        from datetime import datetime
        def parse_date(row):
            date_str = row.get("Fecha/Hora", "")
            try:
                return datetime.strptime(date_str, "%d/%m/%Y %H")
            except ValueError:
                return datetime.min
        
        # Filter invalid dates
        valid_rows = [r for r in rows if parse_date(r) != datetime.min]
        valid_rows.sort(key=parse_date)
        return valid_rows

    def _get_latest_row(self) -> Optional[Dict[str, Any]]:
        """Find the latest data row for this contract."""
        rows = [row for row in self.coordinator.data if row.get("Contrato") == self._contract_id]
        if not rows:
            return None
        
        from datetime import datetime
        def parse_date(row):
            date_str = row.get("Fecha/Hora", "")
            try:
                # Try hourly format strictly
                return datetime.strptime(date_str, "%d/%m/%Y %H")
            except ValueError:
                return datetime.min

        rows.sort(key=parse_date, reverse=True)
        return rows[0] if rows else None


class CanalIsabelIITotalConsumptionSensor(CoordinatorEntity, SensorEntity):
    """Representation of a Canal de Isabel II Total Consumption Sensor (for Energy Dashboard)."""

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: DataUpdateCoordinator,
        contract_id: str,
        initial_data: Dict[str, Any],
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.hass = hass
        self._contract_id = contract_id
        self._attr_name = f"Canal de Isabel II Total {contract_id}"
        self._attr_unique_id = f"canal_ii_total_{contract_id}"
        self._attr_native_unit_of_measurement = UnitOfVolume.LITERS
        self._attr_device_class = SensorDeviceClass.WATER
        self._attr_state_class = SensorStateClass.TOTAL_INCREASING
        self._attr_icon = "mdi:water-pump"
        
    async def async_added_to_hass(self) -> None:
        """When entity is added to hass."""
        await super().async_added_to_hass()
        # Now self.entity_id is available
        self._handle_coordinator_update()

    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.hass.async_create_task(self._import_historical_statistics())
        super()._handle_coordinator_update()

    @property
    def native_value(self) -> Optional[float]:
        """Return the Cumulative Total."""
        # Calculate total from all available history in CSV
        rows = self._get_sorted_rows()
        if not rows:
            return None
        
        total = 0.0
        for row in rows:
            try:
                val = float(row.get("Consumo (litros)", 0))
                total += val
            except ValueError:
                pass
        return total

    def _get_sorted_rows(self) -> List[Dict[str, Any]]:
        """Get rows sorted by date ascending."""
        rows = [row for row in self.coordinator.data if row.get("Contrato") == self._contract_id]
        from datetime import datetime
        def parse_date(row):
            date_str = row.get("Fecha/Hora", "")
            try:
                return datetime.strptime(date_str, "%d/%m/%Y %H")
            except ValueError:
                return datetime.min
        
        # Filter invalid dates
        valid_rows = [r for r in rows if parse_date(r) != datetime.min]
        valid_rows.sort(key=parse_date)
        return valid_rows

    async def _import_historical_statistics(self) -> None:
        """Import historical statistics from CSV."""
        rows = self._get_sorted_rows()
        if not rows:
            _LOGGER.debug(f"No rows available for historical import for {self.entity_id}")
            return

        # MUST use the entity_id as the statistic_id for source='recorder'
        statistic_id = self.entity_id
        
        _LOGGER.debug(f"Starting historical import for {statistic_id}. Total rows: {len(rows)}")

        metadata = StatisticMetaData(
            has_mean=False,
            has_sum=True,
            name=self.name,
            source='recorder',
            statistic_id=statistic_id,
            unit_of_measurement=UnitOfVolume.LITERS,
            mean_type=StatisticMeanType.NONE,
            unit_class=VolumeConverter.UNIT_CLASS,
        )

        statistics = []
        running_sum = 0.0
        
        from datetime import datetime
        from homeassistant.util import dt as dt_util
        
        for row in rows:
            try:
                date_str = row.get("Fecha/Hora")
                try:
                    dt_val = datetime.strptime(date_str, "%d/%m/%Y %H")
                    # For hourly data, the timestamp is the hour start or end. 
                    # Usually "00" mean 00:00. We can use it as is (aware or utc)
                    # Use UTC for storage
                    dt_utc = dt_val.replace(tzinfo=dt_util.DEFAULT_TIME_ZONE).astimezone(dt_util.UTC)
                except ValueError:
                     _LOGGER.warning(f"Skipping row with invalid hourly date: {date_str}")
                     continue

                daily_val = float(row.get("Consumo (litros)", 0))
                running_sum += daily_val
                
                statistics.append(
                    StatisticData(
                        start=dt_utc,
                        state=running_sum,
                        sum=running_sum,
                    )
                )
            except ValueError as e:
                _LOGGER.error(f"Error parsing row for statistics: {row}. Error: {e}")
                continue

        if statistics:
            _LOGGER.debug(f"Importing {len(statistics)} statistics for {statistic_id}. Last stat: {statistics[-1]}")
            await get_instance(self.hass).async_add_executor_job(async_import_statistics, self.hass, metadata, statistics)
        else:
             _LOGGER.debug("No valid statistics generated despite having rows.")
