import json
import os
from typing import List, Dict, Any
from pathlib import Path

from models import ItemsConfig, ItemTypeConfig

class ItemsService:
    def __init__(self):
        self.config_file = Path(__file__).parent.parent / "items_config.json"
        self._config = None
        self.load_config()
    
    def load_config(self) -> None:
        """Load items configuration from JSON file"""
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
                self._config = ItemsConfig(**config_data)
        except FileNotFoundError:
            # Create default config if file doesn't exist
            self._create_default_config()
        except Exception as e:
            raise Exception(f"Error loading items configuration: {e}")
    
    def _create_default_config(self) -> None:
        """Create default configuration file"""
        default_config = {
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
        }
        
        with open(self.config_file, 'w', encoding='utf-8') as f:
            json.dump(default_config, f, indent=2, ensure_ascii=False)
        
        self._config = ItemsConfig(**default_config)
    
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
