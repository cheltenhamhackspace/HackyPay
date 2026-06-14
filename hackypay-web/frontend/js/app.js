class HackyPayApp {
    constructor() {
        this.apiBaseUrl = '/api';
        this.cart = [];
        this.currentItemType = null;
        this.currentPrice = '0.00';
        
        this.initializeElements();
        this.bindEvents();
        this.loadItemTypes();
        this.checkSystemHealth();
        
        this.log('System initialized');
    }
    
    initializeElements() {
        // Cart elements
        this.cartItems = document.getElementById('cartItems');
        this.totalAmount = document.getElementById('totalAmount');
        this.clearCartBtn = document.getElementById('clearCartBtn');
        this.checkoutBtn = document.getElementById('checkoutBtn');

        // Item selection
        this.itemTypesGrid = document.getElementById('itemTypesGrid');

        // Status elements
        this.statusMessage = document.getElementById('statusMessage');
        this.logContent = document.getElementById('logContent');
        this.systemStatus = document.getElementById('systemStatus');

        // Modal elements
        this.itemModal = document.getElementById('itemModal');
        this.modalItemType = document.getElementById('modalItemType');
        this.priceDisplay = document.getElementById('priceDisplay');
        this.modalClose = document.getElementById('modalClose');
        this.modalCancel = document.getElementById('modalCancel');
        this.modalAdd = document.getElementById('modalAdd');

        // Loading overlay
        this.loadingOverlay = document.getElementById('loadingOverlay');
        this.loadingText = document.getElementById('loadingText');
    }
    
    bindEvents() {
        // Cart events
        this.clearCartBtn.addEventListener('click', () => this.clearCart());
        this.checkoutBtn.addEventListener('click', () => this.processCheckout());
        
        // Modal events
        this.modalClose.addEventListener('click', () => this.closeModal());
        this.modalCancel.addEventListener('click', () => this.closeModal());
        this.modalAdd.addEventListener('click', () => this.addItemToCart());
        
        // Keypad events
        document.querySelectorAll('.keypad-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const digit = e.target.dataset.digit;
                const action = e.target.dataset.action;
                
                if (action === 'clear') {
                    this.clearPrice();
                } else if (digit) {
                    this.addDigit(digit);
                }
            });
        });
        
        // Close modal on overlay click
        this.itemModal.addEventListener('click', (e) => {
            if (e.target === this.itemModal) {
                this.closeModal();
            }
        });
        
        // Keyboard support
        document.addEventListener('keydown', (e) => {
            if (this.itemModal.classList.contains('active')) {
                if (e.key >= '0' && e.key <= '9') {
                    this.addDigit(e.key);
                } else if (e.key === '.') {
                    this.addDigit('.');
                } else if (e.key === 'Backspace' || e.key === 'Delete') {
                    this.clearPrice();
                } else if (e.key === 'Enter') {
                    this.addItemToCart();
                } else if (e.key === 'Escape') {
                    this.closeModal();
                }
            }
        });
    }
    
    async loadItemTypes() {
        try {
            const response = await fetch(`${this.apiBaseUrl}/item-types`);
            const data = await response.json();
            
            // Store settings and item types for later use
            this.settings = data.settings || {};
            this.itemTypes = data.item_types || [];
            
            this.itemTypesGrid.innerHTML = '';
            data.item_types.forEach(itemType => {
                const button = document.createElement('button');
                button.className = 'item-type-btn';
                button.innerHTML = `
                    <div class="item-icon">${itemType.icon}</div>
                    <div class="item-name">${itemType.name}</div>
                `;
                button.title = itemType.description;
                button.addEventListener('click', () => this.selectItemType(itemType));
                this.itemTypesGrid.appendChild(button);
            });
            
            this.log('Item types loaded');
        } catch (error) {
            this.log('Failed to load item types', 'error');
            console.error('Error loading item types:', error);
        }
    }
    
    async checkSystemHealth() {
        try {
            const response = await fetch(`${this.apiBaseUrl}/health`);
            const data = await response.json();
            
            if (data.status === 'healthy') {
                this.updateSystemStatus('System Online', true);
            } else {
                this.updateSystemStatus('System Issues', false);
            }
        } catch (error) {
            this.updateSystemStatus('System Offline', false);
            this.log('System health check failed', 'error');
        }
    }
    
    updateSystemStatus(text, online) {
        const statusIndicator = this.systemStatus.querySelector('.status-indicator');
        const statusText = this.systemStatus.querySelector('.status-text');
        
        statusText.textContent = text;
        statusIndicator.classList.toggle('offline', !online);
    }
    
    selectItemType(itemType) {
        this.currentItemType = itemType;
        this.currentPrice = '0.00';
        this.modalItemType.innerHTML = `
            <div class="modal-item-header">
                <span class="modal-item-icon">${itemType.icon}</span>
                <span class="modal-item-name">${itemType.name}</span>
            </div>
            <div class="modal-item-description">${itemType.description}</div>
        `;
        this.priceDisplay.textContent = '£0.00';
        this.showModal();
        this.log(`Selected item type: ${itemType.name}`);
    }
    
    showModal() {
        this.itemModal.classList.add('active');
        document.body.style.overflow = 'hidden';
    }
    
    closeModal() {
        this.itemModal.classList.remove('active');
        document.body.style.overflow = '';
        this.currentItemType = null;
        this.currentPrice = '0.00';
    }
    
    addDigit(digit) {
        if (digit === '.') {
            if (!this.currentPrice.includes('.')) {
                if (this.currentPrice === '0.00') {
                    this.currentPrice = '0.';
                } else {
                    this.currentPrice += '.';
                }
            }
        } else {
            if (this.currentPrice === '0.00') {
                this.currentPrice = digit;
            } else if (this.currentPrice.includes('.')) {
                const parts = this.currentPrice.split('.');
                if (parts[1].length < 2) {
                    this.currentPrice += digit;
                }
            } else {
                if (this.currentPrice.length < 6) {
                    this.currentPrice += digit;
                }
            }
        }
        
        this.updatePriceDisplay();
    }
    
    clearPrice() {
        this.currentPrice = '0.00';
        this.updatePriceDisplay();
    }
    
    updatePriceDisplay() {
        let displayPrice = this.currentPrice;
        
        // Format the price for display
        if (displayPrice.includes('.')) {
            const parts = displayPrice.split('.');
            if (parts[1].length === 0) {
                displayPrice = parts[0] + '.';
            } else if (parts[1].length === 1) {
                displayPrice = parts[0] + '.' + parts[1];
            } else {
                displayPrice = parts[0] + '.' + parts[1].substring(0, 2);
            }
        } else {
            displayPrice = displayPrice;
        }
        
        this.priceDisplay.textContent = `£${displayPrice}`;
    }
    
    async addItemToCart() {
        const price = parseFloat(this.currentPrice);
        const maxPrice = this.settings?.max_price || 49.99;

        if (isNaN(price) || price <= 0) {
            alert('Please enter a valid price greater than £0.00');
            return;
        }

        if (price > maxPrice) {
            alert(`Maximum price is £${maxPrice.toFixed(2)}`);
            return;
        }

        const item = {
            item_type: this.currentItemType.name,
            price: price,
            quantity: 1
        };

        this.cart.push(item);
        this.updateCartDisplay();
        this.closeModal();

        this.log(`Added ${item.item_type}: £${price.toFixed(2)}`, 'success');
        this.setStatus(`✅ Added ${item.item_type} (£${price.toFixed(2)}) to cart`);
    }
    
    removeItemFromCart(index) {
        const item = this.cart[index];
        this.cart.splice(index, 1);
        this.updateCartDisplay();
        
        this.log(`Removed ${item.item_type}: £${item.price.toFixed(2)}`);
        this.setStatus(`Removed ${item.item_type} from cart`);
    }
    
    clearCart() {
        if (this.cart.length === 0) {
            alert('Cart is already empty');
            return;
        }
        
        this.cart = [];
        this.updateCartDisplay();
        this.log('Cart cleared');
        this.setStatus('Cart cleared');
    }
    
    updateCartDisplay() {
        // Update cart items display
        if (this.cart.length === 0) {
            this.cartItems.innerHTML = `
                <div class="empty-cart-message">
                    <p>Your cart is empty</p>
                    <p class="empty-cart-subtitle">Add items to get started</p>
                </div>
            `;
        } else {
            this.cartItems.innerHTML = this.cart.map((item, index) => `
                <div class="cart-item">
                    <div class="cart-item-info">
                        <div class="cart-item-name">${item.item_type}</div>
                        <div class="cart-item-price">£${item.price.toFixed(2)}</div>
                    </div>
                    <button class="remove-item-btn" onclick="app.removeItemFromCart(${index})">
                        🗑️
                    </button>
                </div>
            `).join('');
        }
        
        // Update total
        const total = this.cart.reduce((sum, item) => sum + (item.price * item.quantity), 0);
        this.totalAmount.textContent = `£${total.toFixed(2)}`;
        
        // Update button states
        this.clearCartBtn.disabled = this.cart.length === 0;
        this.checkoutBtn.disabled = this.cart.length === 0;
        
        // Update system status
        if (this.cart.length > 0) {
            this.updateSystemStatus('System Active', true);
        } else {
            this.updateSystemStatus('System Ready', true);
        }
    }
    
    async processCheckout() {
        if (this.cart.length === 0) {
            alert('Please add items to your cart before checking out');
            return;
        }

        const total = this.cart.reduce((sum, item) => sum + (item.price * item.quantity), 0);
        const minTotal = this.settings?.min_price || 1.00;
        const maxTotal = this.settings?.max_price || 49.99;

        if (total < minTotal) {
            alert(`Minimum total price must be £${minTotal.toFixed(2)}`);
            return;
        }

        if (total > maxTotal) {
            alert(`Maximum total price is £${maxTotal.toFixed(2)}`);
            return;
        }

        const checkoutRequest = {
            items: this.cart,
            total_amount: total,
            description: `Self Checkout: ${this.cart.map(item =>
                `${item.item_type} (£${item.price.toFixed(2)})`
            ).join(', ')}`
        };

        this.checkoutBtn.disabled = true;
        this.checkoutBtn.classList.add('processing');
        this.checkoutBtn.textContent = 'Processing...';
        this.showLoading('Contacting card reader...');
        this.log(`Processing payment for £${total.toFixed(2)}`);

        try {
            const response = await fetch(`${this.apiBaseUrl}/checkout`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(checkoutRequest)
            });

            const result = await response.json();

            if (!result.success) {
                this.log(`✗ Payment failed: ${result.message}`, 'error');
                this.setStatus(`Payment failed: ${result.message}`);
                this.hideLoading();
                this._resetCheckoutButton();
                return;
            }

            this.loadingText.textContent = 'Sent to reader — follow the prompts...';
            this.setStatus('📟 Checkout sent to card reader');

            await this._pollReaderForPayment(result.client_transaction_id);

        } catch (error) {
            this.log(`✗ Payment error: ${error.message}`, 'error');
            this.setStatus('Payment failed. Please try again.');
            console.error('Checkout error:', error);
            this.hideLoading();
            this._resetCheckoutButton();
        }
    }

    async _pollReaderForPayment(clientTransactionId) {
        const POLL_INTERVAL = 2000;
        const MAX_POLLS = 60;
        const STATE_MESSAGES = {
            'IDLE':               'Reader ready — preparing...',
            'SELECTING_TIP':      'Select tip amount on reader',
            'WAITING_FOR_CARD':   '💳 Tap or insert your card',
            'WAITING_FOR_PIN':    '🔢 Enter your PIN on the reader',
            'WAITING_FOR_SIGNATURE': '✍️ Sign on the reader',
            'UPDATING_FIRMWARE':  'Reader updating — please wait...',
            'UNKNOWN':            'Contacting reader...',
            'OFFLINE':            'Reader offline — check connection',
        };

        let wasInPayment = false;
        let lastState = null;

        for (let i = 0; i < MAX_POLLS; i++) {
            await this._sleep(POLL_INTERVAL);

            try {
                const resp = await fetch(`${this.apiBaseUrl}/reader/status`);
                const status = await resp.json();

                if (!status.online) {
                    this.loadingText.textContent = 'Reader is offline — check the device';
                    continue;
                }

                const state = status.state || 'IDLE';
                lastState = state;

                const msg = STATE_MESSAGES[state] || `Reader: ${state}`;
                this.loadingText.textContent = msg;
                this.setStatus(`📟 ${msg}`);

                if (state === 'WAITING_FOR_CARD' || state === 'WAITING_FOR_PIN' ||
                    state === 'WAITING_FOR_SIGNATURE' || state === 'SELECTING_TIP') {
                    wasInPayment = true;
                }

                if (wasInPayment && state === 'IDLE') {
                    break;
                }

            } catch {
                this.loadingText.textContent = 'Checking reader status...';
            }
        }

        this.loadingText.textContent = 'Checking payment result...';

        if (!clientTransactionId) {
            this.loadingText.textContent = 'Processing complete — check the reader';
            await this._sleep(4000);
            this._finishCheckout(true, null, 'Processing complete');
            return;
        }

        for (let attempt = 0; attempt < 6; attempt++) {
            await this._sleep(2000);

            try {
                const resp = await fetch(
                    `${this.apiBaseUrl}/transaction/${clientTransactionId}/status`
                );
                const tx = await resp.json();

                if (tx.found && tx.status === 'SUCCESSFUL') {
                    this._finishCheckout(true, tx.transaction_id, 'Payment successful!');
                    return;
                }

                if (tx.found && ['FAILED', 'CANCELLED', 'REFUNDED', 'CHARGE_BACK'].includes(tx.status)) {
                    this._finishCheckout(false, null, tx.status);
                    return;
                }

                if (tx.status === 'NOT_FOUND') {
                    this.loadingText.textContent = 'Transaction cancelled — no payment taken';
                    await this._sleep(2000);
this._finishCheckout(false, null, 'UNVERIFIED');
                    return;
                }

                if (tx.status === 'UNKNOWN') {
                    this.loadingText.textContent = 'Cannot verify — check the reader screen';
                    await this._sleep(2000);
                    this._finishCheckout(false, null, 'UNVERIFIED');
                    return;
                }

                this.loadingText.textContent = 'Waiting for confirmation...';
            } catch {
                this.loadingText.textContent = 'Checking result...';
            }
        }

        this._finishCheckout(false, null, 'CANCELLED');
    }

    _finishCheckout(success, transactionId, message) {
        this.hideLoading();
        this._resetCheckoutButton();

        if (success) {
            this.log(`✓ Completed — TX: ${transactionId || 'N/A'}`, 'success');
            this.setStatus(`✅ ${message}`);
            this.cart = [];
            this.updateCartDisplay();

            setTimeout(() => {
                this.setStatus('👆 Select an item type to add to your cart');
            }, 6000);
            return;
        }

        const status = (message || '').toUpperCase();

        if (status === 'CANCELLED') {
            this.log('🚫 Transaction cancelled by user', 'info');
            this.setStatus('🚫 Cancelled — cart kept. You can change items and try again.');
            return;
        }

        if (status === 'UNVERIFIED') {
            this.log('❓ Could not verify payment result', 'info');
            this.setStatus('❓ Could not verify payment. Check the reader screen.');
            return;
        }

        this.log(`✗ ${message}`, 'error');
        this.setStatus(`Declined — ${message}. Cart kept — you can try again.`);
    }

    _resetCheckoutButton() {
        this.checkoutBtn.disabled = this.cart.length === 0;
        this.checkoutBtn.classList.remove('processing');
        this.checkoutBtn.textContent = '💳 CHECKOUT';
    }

    _sleep(ms) {
        return new Promise(resolve => setTimeout(resolve, ms));
    }
    
    showLoading(text = 'Loading...') {
        this.loadingText.textContent = text;
        this.loadingOverlay.classList.add('active');
    }
    
    hideLoading() {
        this.loadingOverlay.classList.remove('active');
    }
    
    setStatus(message) {
        this.statusMessage.textContent = message;
    }
    
    log(message, type = 'info') {
        const timestamp = new Date().toLocaleTimeString();
        const logEntry = document.createElement('div');
        logEntry.className = `log-entry ${type}`;
        logEntry.textContent = `[${timestamp}] ${message}`;
        
        this.logContent.appendChild(logEntry);
        this.logContent.scrollTop = this.logContent.scrollHeight;
        
        // Keep only last 50 log entries
        while (this.logContent.children.length > 50) {
            this.logContent.removeChild(this.logContent.firstChild);
        }
    }
}

// Initialize the application when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    window.app = new HackyPayApp();
});

// Handle page visibility changes
document.addEventListener('visibilitychange', () => {
    if (!document.hidden && window.app) {
        // Check system health when page becomes visible
        window.app.checkSystemHealth();
    }
});

// Handle online/offline events
window.addEventListener('online', () => {
    if (window.app) {
        window.app.log('Connection restored', 'success');
        window.app.checkSystemHealth();
    }
});

window.addEventListener('offline', () => {
    if (window.app) {
        window.app.log('Connection lost', 'error');
        window.app.updateSystemStatus('System Offline', false);
    }
});
