class HackyPayApp {
    constructor() {
        this.apiBaseUrl = '/api';
        this.cart = [];
        this.currentItemType = null;
        this.currentPrice = '0.00';

        // Screen state machine: 'items' | 'cart' | 'payment' | 'done'
        this.currentScreen = 'items';

        // Checkout run tracking. Each checkout bumps _checkoutRunId; any
        // escape from the PAYMENT screen bumps it again, which makes every
        // in-flight polling loop bail on its next tick (no stranded timers,
        // no double-submit).
        this._checkoutActive = false;
        this._checkoutRunId = 0;
        this._doneTimer = null;

        this.initializeElements();
        this.bindEvents();
        this.loadItemTypes();
        this.checkSystemHealth();
        this.verifyBrandFont();

        this.log('System initialized');
    }

    initializeElements() {
        // Screens (SPA state machine)
        this.screens = {
            items: document.getElementById('screenItems'),
            cart: document.getElementById('screenCart'),
            payment: document.getElementById('screenPayment'),
            done: document.getElementById('screenDone')
        };

        // Item selection
        this.itemTypesGrid = document.getElementById('itemTypesGrid');

        // Bottom bar (items + cart screens)
        this.bottomBar = document.getElementById('bottomBar');
        this.cartSummaryBtn = document.getElementById('cartSummaryBtn');
        this.cartCount = document.getElementById('cartCount');
        this.cartTotal = document.getElementById('cartTotal');
        this.checkoutBtn = document.getElementById('checkoutBtn');

        // Cart screen
        this.cartBackBtn = document.getElementById('cartBackBtn');
        this.clearCartBtn = document.getElementById('clearCartBtn');
        this.cartItems = document.getElementById('cartItems');

        // Payment screen
        this.payTotal = document.getElementById('payTotal');
        this.payItemCount = document.getElementById('payItemCount');
        this.payWaiting = document.getElementById('payWaiting');
        this.payStatus = document.getElementById('payStatus');
        this.payFailure = document.getElementById('payFailure');
        this.payFailureMsg = document.getElementById('payFailureMsg');
        this.payRetryBtn = document.getElementById('payRetryBtn');
        this.payBackBtn = document.getElementById('payBackBtn');
        this.payCancelBtn = document.getElementById('payCancelBtn');

        // Done screen
        this.doneAmount = document.getElementById('doneAmount');
        this.doneCountdown = document.getElementById('doneCountdown');
        this.doneContinueBtn = document.getElementById('doneContinueBtn');

        // Status + log (desktop-only surfaces)
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

        // Toast + brand font warning
        this.toast = document.getElementById('toast');
        this.toastText = document.getElementById('toastText');
        this.fontWarning = document.getElementById('fontWarning');
    }

    bindEvents() {
        // Kiosk touchscreen: suppress long-press context menus (save-image/copy UI)
        document.addEventListener('contextmenu', (e) => e.preventDefault());

        // Screen navigation
        this.cartSummaryBtn.addEventListener('click', () => this.showScreen('cart'));
        this.cartBackBtn.addEventListener('click', () => this.showScreen('items'));
        this.checkoutBtn.addEventListener('click', () => this.processCheckout());

        // Cart screen
        this.clearCartBtn.addEventListener('click', () => this.clearCart());

        // Payment screen
        this.payCancelBtn.addEventListener('click', () => this.cancelCheckout());
        this.payRetryBtn.addEventListener('click', () => this.retryCheckout());
        this.payBackBtn.addEventListener('click', () => this.showScreen('items'));

        // Done screen
        this.doneContinueBtn.addEventListener('click', () => this.finishDone());

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

        // Toast + font warning: tap to dismiss
        this.toast.addEventListener('click', () => this.hideToast());
        this.fontWarning.addEventListener('click', () => {
            this.fontWarning.classList.remove('visible');
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
            } else if (this.currentScreen === 'payment' && e.key === 'Escape') {
                // Escape/interrupt safety: leave PAYMENT cleanly, cart kept
                this.cancelCheckout();
            } else if (this.currentScreen === 'done' && (e.key === 'Enter' || e.key === ' ')) {
                this.finishDone();
            }
        });
    }

    // ------------------------------------------------------------
    // Screen state machine
    // ------------------------------------------------------------
    showScreen(name) {
        // Escape/interrupt safety: leaving PAYMENT while a checkout is in
        // flight aborts the polling run cleanly (cart is always kept).
        if (this.currentScreen === 'payment' && name !== 'payment' && this._checkoutActive) {
            this._abortCheckout('Cancelled — cart kept. You can change items and try again.');
        }

        // Leaving DONE stops the auto-return countdown
        if (this.currentScreen === 'done' && name !== 'done') {
            this._clearDoneTimer();
        }

        this.currentScreen = name;
        document.body.dataset.screen = name;
        for (const [key, el] of Object.entries(this.screens)) {
            el.classList.toggle('active', key === name);
        }

        if (name === 'cart') {
            this.cartItems.scrollTop = 0;
        }
    }

    _itemCountText(count) {
        return count === 1 ? '1 item' : `${count} items`;
    }

    // ------------------------------------------------------------
    // Backend: item types + health
    // ------------------------------------------------------------
    async loadItemTypes() {
        try {
            const response = await fetch(`${this.apiBaseUrl}/item-types`);
            const data = await response.json();

            // Store settings and item types for later use
            this.settings = data.settings || {};
            this.itemTypes = data.item_types || [];

            this.itemTypesGrid.textContent = '';
            data.item_types.forEach(itemType => {
                const button = document.createElement('button');
                button.className = 'item-type-btn';
                // Item data comes from the API — build with textContent (XSS-safe)
                const icon = document.createElement('div');
                icon.className = 'item-icon';
                icon.textContent = itemType.icon;
                const name = document.createElement('div');
                name.className = 'item-name';
                name.textContent = itemType.name;
                button.appendChild(icon);
                button.appendChild(name);
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

    // ------------------------------------------------------------
    // Price entry modal (full-screen keypad on the kiosk)
    // ------------------------------------------------------------
    selectItemType(itemType) {
        this.currentItemType = itemType;
        this.currentPrice = '0.00';
        // Item data comes from the API — build with textContent (XSS-safe)
        this.modalItemType.textContent = '';
        const itemHeader = document.createElement('div');
        itemHeader.className = 'modal-item-header';
        const itemIcon = document.createElement('span');
        itemIcon.className = 'modal-item-icon';
        itemIcon.textContent = itemType.icon;
        const itemName = document.createElement('span');
        itemName.className = 'modal-item-name';
        itemName.textContent = itemType.name;
        itemHeader.appendChild(itemIcon);
        itemHeader.appendChild(itemName);
        const itemDescription = document.createElement('div');
        itemDescription.className = 'modal-item-description';
        itemDescription.textContent = itemType.description;
        this.modalItemType.appendChild(itemHeader);
        this.modalItemType.appendChild(itemDescription);
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

    // ------------------------------------------------------------
    // Cart
    // ------------------------------------------------------------
    async addItemToCart() {
        const price = parseFloat(this.currentPrice);
        const maxPrice = this.settings?.max_price || 49.99;

        if (isNaN(price) || price <= 0) {
            this.showToast('Please enter a valid price greater than £0.00', 'error');
            return;
        }

        if (price > maxPrice) {
            this.showToast(`Maximum price is £${maxPrice.toFixed(2)}`, 'error');
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
        this.setStatus(`Added ${item.item_type} (£${price.toFixed(2)}) to cart`);
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
            this.showToast('Cart is already empty');
            return;
        }

        this.cart = [];
        this.updateCartDisplay();
        this.log('Cart cleared');
        this.setStatus('Cart cleared');
    }

    updateCartDisplay() {
        const count = this.cart.length;
        const total = this.cart.reduce((sum, item) => sum + (item.price * item.quantity), 0);

        // Cart screen list (item names come from the API — textContent, XSS-safe)
        this.cartItems.textContent = '';
        if (count === 0) {
            const empty = document.createElement('div');
            empty.className = 'empty-cart-message';
            const message = document.createElement('p');
            message.textContent = 'Your cart is empty';
            const subtitle = document.createElement('p');
            subtitle.className = 'empty-cart-subtitle';
            subtitle.textContent = 'Add items to get started';
            empty.appendChild(message);
            empty.appendChild(subtitle);
            this.cartItems.appendChild(empty);
        } else {
            this.cart.forEach((item, index) => {
                const row = document.createElement('div');
                row.className = 'cart-item';

                const info = document.createElement('div');
                info.className = 'cart-item-info';
                const name = document.createElement('div');
                name.className = 'cart-item-name';
                name.textContent = item.item_type;
                const price = document.createElement('div');
                price.className = 'cart-item-price';
                price.textContent = `£${item.price.toFixed(2)}`;
                info.appendChild(name);
                info.appendChild(price);

                const removeBtn = document.createElement('button');
                removeBtn.className = 'remove-item-btn';
                removeBtn.setAttribute('aria-label', `Remove ${item.item_type}`);
                removeBtn.textContent = '×';
                removeBtn.addEventListener('click', () => this.removeItemFromCart(index));

                row.appendChild(info);
                row.appendChild(removeBtn);
                this.cartItems.appendChild(row);
            });
        }

        // Bottom bar summary (count white + total yellow; hint when empty)
        this.cartCount.textContent = this._itemCountText(count);
        this.cartTotal.textContent = `£${total.toFixed(2)}`;
        this.bottomBar.classList.toggle('is-empty', count === 0);

        // Button states
        this.clearCartBtn.disabled = count === 0;
        this.checkoutBtn.disabled = count === 0;

        // System status
        this.updateSystemStatus(count > 0 ? 'System Active' : 'System Ready', true);

        // Cart emptied while reviewing it → back to ITEMS
        if (count === 0 && this.currentScreen === 'cart') {
            this.showScreen('items');
        }
    }

    // ------------------------------------------------------------
    // Checkout flow — run-token guarded so escapes/cancels stop
    // every polling loop cleanly and checkout can never double-submit
    // ------------------------------------------------------------
    async processCheckout() {
        if (this._checkoutActive) {
            return; // never double-submit
        }

        if (this.cart.length === 0) {
            this.showToast('Please add items to your cart before checking out', 'error');
            return;
        }

        const total = this.cart.reduce((sum, item) => sum + (item.price * item.quantity), 0);
        const minTotal = this.settings?.min_price || 1.00;
        const maxTotal = this.settings?.max_price || 49.99;

        if (total < minTotal) {
            this.showToast(`Minimum total price must be £${minTotal.toFixed(2)}`, 'error');
            return;
        }

        if (total > maxTotal) {
            this.showToast(`Maximum total price is £${maxTotal.toFixed(2)}`, 'error');
            return;
        }

        const checkoutRequest = {
            items: this.cart,
            total_amount: total,
            description: `Self Checkout: ${this.cart.map(item =>
                `${item.item_type} (£${item.price.toFixed(2)})`
            ).join(', ')}`
        };

        this._checkoutActive = true;
        const runId = ++this._checkoutRunId;

        this.showScreen('payment');
        this._setPaymentPhase('waiting');
        this.payTotal.textContent = `£${total.toFixed(2)}`;
        this.payItemCount.textContent = this._itemCountText(this.cart.length);
        this._setPayStatus('Contacting card reader...');
        this.log(`Processing payment for £${total.toFixed(2)}`);

        try {
            const response = await fetch(`${this.apiBaseUrl}/checkout`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(checkoutRequest)
            });

            const result = await response.json();

            if (runId !== this._checkoutRunId) {
                return; // aborted while awaiting the response
            }

            if (!result.success) {
                this.log(`Payment failed: ${result.message}`, 'error');
                this._finishCheckout(false, null, result.message || 'request rejected');
                return;
            }

            this._setPayStatus('Sent to reader — follow the prompts...');
            this.setStatus('Checkout sent to card reader');

            await this._pollReaderForPayment(result.client_transaction_id, runId);

        } catch (error) {
            if (runId !== this._checkoutRunId) {
                return; // aborted while awaiting the response
            }
            this.log(`Payment error: ${error.message}`, 'error');
            console.error('Checkout error:', error);
            this._finishCheckout(false, null, 'ERROR');
        }
    }

    async _pollReaderForPayment(clientTransactionId, runId) {
        const POLL_INTERVAL = 2000;
        const MAX_POLLS = 60;
        const STATE_MESSAGES = {
            'IDLE':               'Reader ready — preparing...',
            'SELECTING_TIP':      'Select tip amount on reader',
            'WAITING_FOR_CARD':   'Tap or insert your card',
            'WAITING_FOR_PIN':    'Enter your PIN on the reader',
            'WAITING_FOR_SIGNATURE': 'Sign on the reader',
            'UPDATING_FIRMWARE':  'Reader updating — please wait...',
            'UNKNOWN':            'Contacting reader...',
            'OFFLINE':            'Reader offline — check connection',
        };

        // A stale run id means the user escaped/cancelled: stop polling.
        const aborted = () => runId !== this._checkoutRunId;

        let wasInPayment = false;

        for (let i = 0; i < MAX_POLLS; i++) {
            await this._sleep(POLL_INTERVAL);
            if (aborted()) return;

            try {
                const resp = await fetch(`${this.apiBaseUrl}/reader/status`);
                const status = await resp.json();
                if (aborted()) return;

                if (!status.online) {
                    this._setPayStatus('Reader offline — check the device');
                    continue;
                }

                const state = status.state || 'IDLE';

                const msg = STATE_MESSAGES[state] || `Reader: ${state}`;
                this._setPayStatus(msg);
                this.setStatus(msg);

                if (state === 'WAITING_FOR_CARD' || state === 'WAITING_FOR_PIN' ||
                    state === 'WAITING_FOR_SIGNATURE' || state === 'SELECTING_TIP') {
                    wasInPayment = true;
                }

                if (wasInPayment && state === 'IDLE') {
                    break;
                }

            } catch {
                this._setPayStatus('Checking reader status...');
            }
        }

        if (aborted()) return;
        this._setPayStatus('Checking payment result...');

        if (!clientTransactionId) {
            this._setPayStatus('Processing complete — check the reader');
            await this._sleep(4000);
            if (aborted()) return;
            this._finishCheckout(true, null, 'Processing complete');
            return;
        }

        for (let attempt = 0; attempt < 6; attempt++) {
            await this._sleep(2000);
            if (aborted()) return;

            try {
                const resp = await fetch(
                    `${this.apiBaseUrl}/transaction/${clientTransactionId}/status`
                );
                const tx = await resp.json();
                if (aborted()) return;

                if (tx.found && tx.status === 'SUCCESSFUL') {
                    this._finishCheckout(true, tx.transaction_id, 'Payment successful!');
                    return;
                }

                if (tx.found && ['FAILED', 'CANCELLED', 'REFUNDED', 'CHARGE_BACK'].includes(tx.status)) {
                    this._finishCheckout(false, null, tx.status);
                    return;
                }

                if (tx.status === 'NOT_FOUND') {
                    this._setPayStatus('Transaction cancelled — no payment taken');
                    await this._sleep(2000);
                    if (aborted()) return;
                    this._finishCheckout(false, null, 'UNVERIFIED');
                    return;
                }

                if (tx.status === 'UNKNOWN') {
                    this._setPayStatus('Cannot verify — check the reader screen');
                    await this._sleep(2000);
                    if (aborted()) return;
                    this._finishCheckout(false, null, 'UNVERIFIED');
                    return;
                }

                this._setPayStatus('Waiting for confirmation...');
            } catch {
                this._setPayStatus('Checking result...');
            }
        }

        this._finishCheckout(false, null, 'CANCELLED');
    }

    _finishCheckout(success, transactionId, message) {
        this._checkoutActive = false;
        this._resetCheckoutButton();

        if (success) {
            const total = this.cart.reduce((sum, item) => sum + (item.price * item.quantity), 0);
            this.log(`Completed — TX: ${transactionId || 'N/A'}`, 'success');
            this.setStatus(`Payment successful — £${total.toFixed(2)}`);

            // Existing semantics: cart cleared on success
            this.cart = [];
            this.updateCartDisplay();

            this._showDone(total);

            setTimeout(() => {
                this.setStatus('Select an item type to add to your cart');
            }, 6000);
            return;
        }

        // Failure paths keep the cart (existing semantics)
        const status = (message || '').toUpperCase();
        let failureMessage;

        if (status === 'CANCELLED') {
            this.log('Transaction cancelled by user', 'info');
            failureMessage = 'Cancelled — no payment taken. Your cart is kept.';
        } else if (status === 'UNVERIFIED') {
            this.log('Could not verify payment result', 'info');
            failureMessage = 'Could not verify the payment result. Check the reader screen.';
        } else if (status === 'ERROR') {
            this.log('Payment error — please try again', 'error');
            failureMessage = 'Payment failed — please try again. Your cart is kept.';
        } else {
            this.log(`Payment failed: ${message}`, 'error');
            const reason = message.replace(/\.\s*$/, '');
            failureMessage = `Declined — ${reason}. Your cart is kept — you can try again.`;
        }

        this.setStatus(failureMessage);
        this._setPaymentPhase('failed', failureMessage);
    }

    _resetCheckoutButton() {
        this.checkoutBtn.disabled = this.cart.length === 0;
    }

    // ------------------------------------------------------------
    // Payment screen phases + escape hatches
    // ------------------------------------------------------------
    _setPaymentPhase(phase, failureMessage) {
        const failed = phase === 'failed';
        this.payWaiting.classList.toggle('hidden', failed);
        this.payFailure.classList.toggle('visible', failed);
        this.payCancelBtn.classList.toggle('hidden', failed);
        if (failed) {
            this.payFailureMsg.textContent = failureMessage || '';
        }
    }

    _setPayStatus(text) {
        this.payStatus.textContent = text;
    }

    cancelCheckout() {
        if (this.currentScreen !== 'payment') {
            return;
        }
        // showScreen aborts the in-flight run (cart kept) when active
        this.showScreen('items');
    }

    retryCheckout() {
        // Re-runs validation + a fresh checkout run from the failure phase
        this.processCheckout();
    }

    _abortCheckout(message) {
        // Invalidate any in-flight polling loops; they stop on their next tick
        this._checkoutRunId += 1;
        this._checkoutActive = false;
        this._resetCheckoutButton();
        this.log('Checkout cancelled by user', 'info');
        if (message) {
            this.showToast(message);
            this.setStatus(message);
        }
    }

    // ------------------------------------------------------------
    // Done screen — success moment, 5s countdown auto-return
    // ------------------------------------------------------------
    _showDone(amount) {
        this.hideToast();
        this.doneAmount.textContent = `£${amount.toFixed(2)}`;
        this.showScreen('done');
        this._startDoneCountdown();
    }

    _startDoneCountdown() {
        this._clearDoneTimer();
        let seconds = 5;
        this.doneCountdown.textContent = `Returning to items in ${seconds}...`;
        this._doneTimer = setInterval(() => {
            seconds -= 1;
            if (seconds <= 0) {
                this.finishDone();
                return;
            }
            this.doneCountdown.textContent = `Returning to items in ${seconds}...`;
        }, 1000);
    }

    finishDone() {
        this._clearDoneTimer();
        this.showScreen('items');
    }

    _clearDoneTimer() {
        if (this._doneTimer) {
            clearInterval(this._doneTimer);
            this._doneTimer = null;
        }
    }

    _sleep(ms) {
        return new Promise(resolve => setTimeout(resolve, ms));
    }

    // ------------------------------------------------------------
    // Status, log, toast
    // ------------------------------------------------------------
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

    showToast(message, type = 'info') {
        this.toastText.textContent = message;
        this.toast.classList.remove('toast-success', 'toast-error');
        if (type === 'success') {
            this.toast.classList.add('toast-success');
        } else if (type === 'error') {
            this.toast.classList.add('toast-error');
        }

        // Restart the reveal transition if a toast is already showing
        this.toast.classList.remove('visible');
        void this.toast.offsetWidth;
        this.toast.classList.add('visible');

        clearTimeout(this._toastTimer);
        this._toastTimer = setTimeout(() => this.hideToast(), 3500);
    }

    hideToast() {
        clearTimeout(this._toastTimer);
        this.toast.classList.remove('visible');
    }

    // Brand font gate: warn visibly when Dunbar Low is not available and the
    // fallback stack is rendering instead (kiosk must never fail silently).
    verifyBrandFont() {
        if (!document.fonts || !document.fonts.ready) {
            this.showFontWarning();
            return;
        }

        document.fonts.ready.then(() => {
            let brandFontLoaded = false;
            try {
                brandFontLoaded = document.fonts.check('bold 1em "Dunbar Low"');
            } catch {
                brandFontLoaded = false;
            }
            if (!brandFontLoaded) {
                this.showFontWarning();
            }
        });
    }

    showFontWarning() {
        this.fontWarning.classList.add('visible');
        this.log('Brand font not found — using fallback display', 'error');
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
