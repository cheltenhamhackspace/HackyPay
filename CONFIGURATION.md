# HackyPay Configuration Guide

This guide explains how to easily configure the HackyPay self-checkout system without modifying code.

## Item Types Configuration

### Configuration File Location
The item types are configured in: `backend/items_config.json`

### Configuration Structure

```json
{
  "item_types": [
    {
      "id": "unique_identifier",
      "name": "Display Name",
      "icon": "🔧",
      "description": "Description shown on hover",
      "enabled": true
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
```

### Item Type Properties

- **id**: Unique identifier (lowercase, underscores allowed)
- **name**: Display name shown on the button
- **icon**: Emoji or Unicode character displayed on the button
- **description**: Tooltip text shown when hovering over the button
- **enabled**: `true` to show the item, `false` to hide it

### Example Configuration

```json
{
  "item_types": [
    {
      "id": "food_drink",
      "name": "Food & Drink",
      "icon": "🍕",
      "description": "Snacks, drinks, and food items",
      "enabled": true
    },
    {
      "id": "laser_time",
      "name": "Laser Time",
      "icon": "⚡",
      "description": "Laser cutter usage time",
      "enabled": true
    },
    {
      "id": "workshop_access",
      "name": "Workshop Access",
      "icon": "🔧",
      "description": "Day pass for workshop access",
      "enabled": false
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
```

## How to Add New Item Types

1. **Edit the configuration file**: Open `backend/items_config.json`

2. **Add a new item type**:
   ```json
   {
     "id": "new_item",
     "name": "New Item Type",
     "icon": "🆕",
     "description": "Description of the new item",
     "enabled": true
   }
   ```

3. **Save the file**

4. **Reload the configuration**:
   - **Option 1**: Restart the backend server
   - **Option 2**: Call the reload endpoint (admin only): `POST http://localhost:8000/api/config/reload` with header `X-Admin-Token: <ADMIN_TOKEN>` when `ADMIN_TOKEN` is set; loopback-only otherwise

## How to Disable Item Types

To temporarily disable an item type without deleting it:

1. Set `"enabled": false` for the item type
2. Save the file
3. Reload the configuration

## Settings Configuration

### Available Settings

- **max_price**: Maximum price allowed per item (default: 999.99)
- **min_price**: Minimum price allowed per item (default: 0.01)
- **currency**: Currency code (default: "GBP")
- **currency_symbol**: Symbol displayed in the interface (default: "£")
- **decimal_places**: Number of decimal places for prices (default: 2)

### Example Settings Modification

```json
{
  "settings": {
    "max_price": 500.00,
    "min_price": 0.50,
    "currency": "EUR",
    "currency_symbol": "€",
    "decimal_places": 2
  }
}
```

## Icon Selection

### Recommended Icons

- 🍕 Food & Drink
- ⚡ Laser/Electronics
- 📦 Materials/Supplies
- 🖨️ 3D Printing
- 🔧 Tools/Workshop
- 🔌 Electronics
- 📚 Books/Learning
- 🎨 Art/Crafts
- 💡 Ideas/Innovation
- 🔬 Science/Research

### Finding Icons

1. **Emoji Picker**: Use your operating system's emoji picker
2. **Unicode Characters**: Browse unicode-table.com
3. **Copy from Examples**: Use icons from the default configuration

## Configuration Validation

The system automatically validates the configuration:

- **Required Fields**: All fields (id, name, icon, description, enabled) are required
- **Unique IDs**: Item IDs must be unique
- **Price Limits**: Settings must have valid min/max prices
- **Data Types**: All fields must be the correct data type

## Reloading Configuration

### Method 1: API Endpoint
```bash
curl -X POST http://localhost:8000/api/config/reload -H "X-Admin-Token: $ADMIN_TOKEN"
```

### Method 2: Restart Backend
```bash
# Stop the backend (Ctrl+C)
# Start it again
cd backend
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

### Method 3: Auto-reload (Development)
If running with `--reload` flag, the server will automatically restart when the file changes.

## Troubleshooting

### Configuration Not Loading
1. Check JSON syntax with a JSON validator
2. Ensure all required fields are present
3. Check the backend logs for error messages
4. Verify file permissions

### Items Not Appearing
1. Check that `"enabled": true`
2. Verify the configuration was reloaded
3. Check browser console for errors
4. Clear browser cache

### Invalid Configuration
If the configuration file is invalid, the system will:
1. Log the error to the backend console
2. Fall back to default configuration
3. Continue operating with default items

## Best Practices

1. **Backup**: Always backup the configuration before making changes
2. **Test**: Test changes in a development environment first
3. **Validate**: Use a JSON validator before saving changes
4. **Document**: Keep notes about why certain items are enabled/disabled
5. **Version Control**: Consider using git to track configuration changes

## Example Configurations

### Hackspace Configuration
```json
{
  "item_types": [
    {
      "id": "food_drink",
      "name": "Food & Drink",
      "icon": "🍕",
      "description": "Snacks and beverages",
      "enabled": true
    },
    {
      "id": "laser_time",
      "name": "Laser Time",
      "icon": "⚡",
      "description": "Laser cutter usage (per hour)",
      "enabled": true
    },
    {
      "id": "3d_print_time",
      "name": "3D Print Time",
      "icon": "🖨️",
      "description": "3D printer usage time",
      "enabled": true
    },
    {
      "id": "materials",
      "name": "Materials",
      "icon": "📦",
      "description": "Raw materials and supplies",
      "enabled": true
    },
    {
      "id": "day_pass",
      "name": "Day Pass",
      "icon": "🎫",
      "description": "Full day workshop access",
      "enabled": true
    }
  ]
}
```

### Retail Configuration
```json
{
  "item_types": [
    {
      "id": "electronics",
      "name": "Electronics",
      "icon": "🔌",
      "description": "Electronic components and devices",
      "enabled": true
    },
    {
      "id": "tools",
      "name": "Tools",
      "icon": "🔧",
      "description": "Hand tools and equipment",
      "enabled": true
    },
    {
      "id": "books",
      "name": "Books",
      "icon": "📚",
      "description": "Technical books and manuals",
      "enabled": true
    }
  ]
}
```

## Support

If you need help with configuration:
1. Check the backend logs for detailed error messages
2. Validate your JSON syntax
3. Refer to the examples in this guide
4. Contact the system administrator
