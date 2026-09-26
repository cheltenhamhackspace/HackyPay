# HackyPay™ Self Checkout System

A secure web-based self-checkout system using the SumUp reader API. This system provides a modern, touch-friendly interface for kiosk use while maintaining strict security by keeping API credentials on the backend only.

## Features

- 🔒 **Secure Architecture**: API keys never exposed to frontend
- 📱 **Touch-Friendly Interface**: Optimized for kiosk and tablet use
- 🛒 **Shopping Cart Management**: Add, remove, and manage items
- 💳 **SumUp Integration**: Direct payment processing through SumUp readers
- 🎨 **Modern UI**: Clean, professional design with animations
- 📊 **Real-time Status**: System health monitoring and transaction logging
- 🔧 **Type Safety**: Full Python type hints and validation

## Architecture

### Backend (Python + FastAPI)
- **FastAPI**: Modern, fast web framework with automatic API documentation
- **Pydantic**: Data validation and type safety
- **Environment Variables**: Secure configuration management
- **CORS**: Properly configured cross-origin resource sharing
- **Logging**: Comprehensive logging for debugging and audit trails

### Frontend (Web App)
- **Vanilla JavaScript**: No heavy frameworks, fast loading
- **Modern CSS**: Responsive design with CSS Grid and Flexbox
- **Touch Optimized**: Large buttons and touch-friendly interactions
- **Real-time Updates**: Live status and transaction feedback

## Security Features

- ✅ API keys stored securely in environment variables (backend only)
- ✅ Input validation on both frontend and backend
- ✅ HTTPS-ready configuration
- ✅ CORS protection
- ✅ Error handling without sensitive data leakage
- ✅ Request timeout and rate limiting
- ✅ Type-safe data models

## Setup Instructions

### Prerequisites

- Python 3.8+
- SumUp merchant account with API access
- SumUp card reader

### Backend Setup

1. **Navigate to backend directory:**
   ```bash
   cd hackypay-web/backend
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure environment variables:**
   - Copy `.env.example` to `.env`
   - Update the values with your SumUp credentials:
   ```bash
   cp .env.example .env
   # Edit .env with your actual SumUp API credentials
   ```

4. **Start the backend server:**
   ```bash
   python main.py
   ```
   
   Or using uvicorn directly:
   ```bash
   uvicorn main:app --host 127.0.0.1 --port 8000 --reload
   ```

### Frontend Setup

1. **Navigate to frontend directory:**
   ```bash
   cd hackypay-web/frontend
   ```

2. **Serve the frontend:**
   
   **Option 1: Python HTTP Server**
   ```bash
   python -m http.server 3000
   ```
   
   **Option 2: Node.js HTTP Server**
   ```bash
   npx http-server -p 3000 -c-1
   ```
   
   **Option 3: Any web server**
   - Serve the `frontend` directory on any web server
   - Ensure the backend API is accessible from the frontend

3. **Access the application:**
   - Open your browser to `http://localhost:3000`
   - The system should show "System Online" if backend is running

## Configuration

### Environment Variables (.env)

```bash
# SumUp API Configuration
SUMUP_API_TOKEN=sup_sk_your_api_token_here
SUMUP_MERCHANT_CODE=your_merchant_code_here
SUMUP_READER_ID=rdr_your_reader_id_here

# Server Configuration
HOST=127.0.0.1
PORT=8000
DEBUG=true

# CORS Configuration
ALLOWED_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
```

### Item Types Configuration

The system uses a **configurable JSON file** for item types, making it easy to customize without code changes:

**Configuration File**: `backend/items_config.json`

**Default Item Types**:
- 🍕 Food & Drink
- ⚡ Laser Time  
- 📦 Laser Materials
- 🖨️ 3D Printer Time

**Additional Available Items** (disabled by default):
- 🔧 Workshop Access
- 🔌 Electronics

**Easy Configuration**:
- Add/remove item types by editing the JSON file
- Enable/disable items with a simple `true`/`false` flag
- Customize icons, names, and descriptions
- Set price limits and currency settings
- Reload configuration without restarting: `GET /api/config/reload`

**See**: `CONFIGURATION.md` for detailed configuration instructions.

## Usage

### For Customers

1. **Select Item Type**: Tap on one of the item type buttons
2. **Enter Price**: Use the on-screen keypad to enter the item price
3. **Add to Cart**: Confirm the item and price
4. **Repeat**: Add more items as needed
5. **Checkout**: Tap the checkout button to process payment
6. **Follow Reader Instructions**: Complete payment on the SumUp reader

### For Administrators

- **Transaction Logs**: View real-time transaction logs in the interface
- **System Status**: Monitor system health and connectivity
- **API Documentation**: Access FastAPI docs at `http://localhost:8000/docs`

## API Endpoints

- `GET /api/health` - System health check
- `GET /api/item-types` - Get available item types
- `GET /api/reader/status` - Check SumUp reader status
- `POST /api/cart/validate` - Validate cart contents
- `POST /api/checkout` - Process payment through SumUp

## Development

### Running in Development Mode

1. **Backend with auto-reload:**
   ```bash
   cd hackypay-web/backend
   uvicorn main:app --reload --host 127.0.0.1 --port 8000
   ```

2. **Frontend with live server:**
   ```bash
   cd hackypay-web/frontend
   python -m http.server 3000
   ```

### API Documentation

FastAPI automatically generates interactive API documentation:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## Production Deployment

### Backend Deployment

1. **Set production environment variables:**
   ```bash
   DEBUG=false
   ALLOWED_ORIGINS=https://yourdomain.com
   ```

2. **Use a production WSGI server:**
   ```bash
   pip install gunicorn
   gunicorn main:app -w 4 -k uvicorn.workers.UvicornWorker
   ```

3. **Set up reverse proxy (nginx example):**
   ```nginx
   server {
       listen 80;
       server_name your-api-domain.com;
       
       location / {
           proxy_pass http://127.0.0.1:8000;
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
       }
   }
   ```

### Frontend Deployment

1. **Serve static files through web server**
2. **Update API base URL in `frontend/js/app.js`**
3. **Enable HTTPS for production**

## Troubleshooting

### Common Issues

1. **"System Offline" Status**
   - Check if backend server is running
   - Verify CORS configuration
   - Check network connectivity

2. **Payment Failures**
   - Verify SumUp API credentials
   - Check reader connectivity
   - Review backend logs for detailed error messages

3. **Import Errors**
   - Ensure all dependencies are installed
   - Check Python path configuration

### Logs

Backend logs are displayed in the console and include:
- API requests and responses
- Payment processing status
- Error details and stack traces

## Security Considerations

- **Never commit `.env` files** to version control
- **Use HTTPS in production**
- **Regularly rotate API keys**
- **Monitor transaction logs** for suspicious activity
- **Keep dependencies updated**

## License

This project is proprietary software for Cheltenham Hackspace.

## Support

For technical support or questions about this system, please contact the development team.
