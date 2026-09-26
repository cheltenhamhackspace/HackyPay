import json
import logging
import os
from typing import List, Dict, Any
from pathlib import Path

from ..models import ItemsConfig, ItemTypeConfig

# backend/items_config.json in the repo; ITEMS_CONFIG_PATH is set in containers
_DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "items_config.json"

logger = logging.getLogger(__name__)

class ItemsService:
    def __init__(self):
        self.config_file = Path(os.environ.get("ITEMS_CONFIG_PATH") or _DEFAULT_CONFIG_PATH)
        self._config = None
        self.load_config()

    def load_config(self) -> None:
        """Load items configuration from JSON file"""
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
                self._config = ItemsConfig(**config_data)
        except FileNotFoundError:
            # Read-only mounts (K8s) must not crash startup — persisting defaults is best-effort
            self._config = self._build_default_config()
            self._try_write_default_config()
        except Exception as e:
            raise Exception(f"Error loading items configuration: {e}")

    def _build_default_config(self) -> ItemsConfig:
        return ItemsConfig(**{
            "item_types": [
                {
                    "id": "food_drink",
                    "name": "Food & Drink",
                    "icon": "🍕",
                    "description": "Snacks, drinks, and food items",
                    "enabled": True
                },
                {
                    "id": "laser_time",
                    "name": "Laser Time",
                    "icon": "⚡",
                    "description": "Laser cutter usage time",
                    "enabled": True
                },
                {
                    "id": "laser_materials",
                    "name": "Laser Materials",
                    "icon": "📦",
                    "description": "Materials for laser cutting",
                    "enabled": True
                },
                {
                    "id": "printer_time",
                    "name": "3D Printer Time",
                    "icon": "🖨️",
                    "description": "3D printer usage time",
                    "enabled": True
                }
            ],
            "settings": {
                "max_price": 999.99,
                "min_price": 0.01,
                "currency": "GBP",
                "currency_symbol": "£",
                "decimal_places": 2
            }
        })

    def _try_write_default_config(self) -> None:
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self._config.model_dump(), f, indent=2, ensure_ascii=False)
        except OSError:
            logger.warning(
                "Could not write default items config to %s; using in-memory defaults",
                self.config_file,
            )
    
    def get_enabled_item_types(self) -> List[ItemTypeConfig]:
        """Get list of enabled item types"""
        return [item for item in self._config.item_types if item.enabled]
    
    def get_all_item_types(self) -> List[ItemTypeConfig]:
        """Get all item types (enabled and disabled)"""
        return self._config.item_types
    
    def get_item_type_by_id(self, item_id: str) -> ItemTypeConfig:
        """Get specific item type by ID"""
        for item in self._config.item_types:
            if item.id == item_id:
                return item
        raise ValueError(f"Item type with ID '{item_id}' not found")
    
    def get_item_type_by_name(self, name: str) -> ItemTypeConfig:
        """Get specific item type by name"""
        for item in self._config.item_types:
            if item.name == name:
                return item
        raise ValueError(f"Item type with name '{name}' not found")
    
    def get_settings(self) -> Dict[str, Any]:
        """Get configuration settings"""
        return self._config.settings
    
    def get_max_price(self) -> float:
        """Get maximum allowed price"""
        return self._config.settings.get("max_price", 999.99)
    
    def get_min_price(self) -> float:
        """Get minimum allowed price"""
        return self._config.settings.get("min_price", 0.01)
    
    def get_currency_symbol(self) -> str:
        """Get currency symbol"""
        return self._config.settings.get("currency_symbol", "£")
    
    def reload_config(self) -> None:
        """Reload configuration from file"""
        self.load_config()
    
    def validate_item_type(self, item_type_name: str) -> bool:
        """Validate if item type exists and is enabled"""
        try:
            item = self.get_item_type_by_name(item_type_name)
            return item.enabled
        except ValueError:
            return False

# Global service instance
items_service = ItemsService()

def get_items_service() -> ItemsService:
    """Get items service instance"""
    return items_service
