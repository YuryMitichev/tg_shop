const App = {

    tg: null,
    initData: "",
    shopId: 1,
    currentCategory: null,
    categories: [],
    selectedVariant: null,
    cartTotal: 0,
    appliedPromo: null,
    paymentMethods: [],
    selectedPaymentMethod: "manual",
    productAttrs: ["volume"],
    attrLabels: { volume: "Объём" },

    init() {
        this.tg = window.Telegram.WebApp;
        this.tg.ready();
        this.tg.expand();

        this.initData = this.tg.initData || "";

        const params = new URLSearchParams(window.location.search);
        this.shopId = parseInt(params.get("shop")) || 1;

        const theme = this.tg.themeParams;
        if (theme.bg_color) {
            document.body.style.background = theme.bg_color;
        }

        this.loadShopConfig();
        this.loadCategories();
        this.updateCartBadge();
        this.loadOffers();
    },

    // ==========================
    // API helpers
    // ==========================

    async api(method, path, body) {
        const opts = {
            method,
            headers: {
                "Authorization": "tma " + this.initData,
                "X-Shop-Id": String(this.shopId),
            },
        };

        if (body) {
            opts.headers["Content-Type"] = "application/json";
            opts.body = JSON.stringify(body);
        }

        const resp = await fetch("/api/shop" + path, opts);

        if (!resp.ok) {
            const err = await resp.json().catch(() => ({}));
            throw new Error(err.detail || "Ошибка запроса");
        }

        if (resp.status === 204) return null;
        return resp.json();
    },

    photoUrl(photoId) {
        if (!photoId) return null;
        return `/api/shop/photo/${photoId}`;
    },

    // ==========================
    // Navigation
    // ==========================

    offers: {},

    async loadOffers() {
        try {
            const offers = await this.api("GET", "/my-offers");
            this.offers = {};
            if (offers && offers.length) {
                offers.forEach(o => {
                    const key = o.variant_id ? `${o.product_id}_${o.variant_id}` : `${o.product_id}`;
                    this.offers[key] = o;
                });
            }
        } catch (e) { }
    },

    hasOffer(productId) {
        return Object.keys(this.offers).some(k => k.startsWith(`${productId}_`) || k === `${productId}`);
    },

    showView(viewId) {
        document.querySelectorAll(".view").forEach(v => v.classList.remove("active"));

        document.getElementById("view-" + viewId).classList.add("active");

        const showNav = !["product", "checkout", "success"].includes(viewId);
        document.getElementById("bottom-nav").style.display = showNav ? "flex" : "none";

        window.scrollTo(0, 0);

        document.querySelectorAll(".nav-btn").forEach(btn => btn.classList.remove("active"));
    },

    // ==========================
    // Catalog
    // ==========================

    async loadShopConfig() {
        try {
            const cfg = await this.api("GET", "/shop-config");
            if (cfg.product_attrs) this.productAttrs = cfg.product_attrs;
            if (cfg.attr_labels) this.attrLabels = cfg.attr_labels;
        } catch (e) { }
    },

    async loadCategories() {
        try {
            this.categories = await this.api("GET", "/categories");

            if (this.categories.length > 0) {
                this.selectCategory(this.categories[0]);
            }
        } catch (e) {
            document.getElementById("products").innerHTML = `<div class="error-msg">Ошибка загрузки</div>`;
        }
    },

    selectCategory(cat) {
        this.currentCategory = cat;
        this.renderCategoryChips();
        this.loadProducts(cat.id);
    },

    renderCategoryChips() {
        const container = document.getElementById("categories");

        container.innerHTML = this.categories.map(c => `
            <button class="cat-chip ${c.id === this.currentCategory.id ? 'active' : ''}"
                    onclick="App.selectCategory(${JSON.stringify(c).replace(/"/g, '&quot;')})">
                ${c.emoji || ""} ${c.name}
            </button>
        `).join("");
    },

    async loadProducts(categoryId) {
        const grid = document.getElementById("products");
        grid.innerHTML = `<div class="loading">Загрузка...</div>`;

        try {
            const products = await this.api("GET", `/products?category_id=${categoryId}`);

            if (products.length === 0) {
                grid.innerHTML = `<div class="loading">Нет товаров</div>`;
                return;
            }

            grid.innerHTML = products.map(p => {
                const photo = this.photoUrl(p.photo_id);
                const rating = p.rating ? `⭐ ${p.rating.avg} (${p.rating.count})` : "";
                const offerBadge = p.has_offer ? `<div class="offer-badge">🔥 Персональная скидка</div>` : "";

                return `
                    <div class="product-card" onclick="App.openProduct(${p.id})">
                        ${offerBadge}
                        ${photo
                            ? `<img src="${photo}" loading="lazy" onerror="this.style.display='none';this.nextElementSibling.style.display='flex'">
                               <div class="placeholder" style="display:none">${this.catEmoji()}</div>`
                            : `<div class="placeholder">${this.catEmoji()}</div>`
                        }
                        <div class="info">
                            <div class="name">${this.esc(p.name)}</div>
                            <div class="price">от ${p.price_from} ₽</div>
                            ${rating ? `<div class="rating">${rating}</div>` : ""}
                        </div>
                    </div>
                `;
            }).join("");
        } catch (e) {
            grid.innerHTML = `<div class="error-msg">Ошибка загрузки</div>`;
        }
    },

    catEmoji() {
        return this.currentCategory?.emoji || "📦";
    },

    async openProduct(productId) {
        this.showView("product");
        const detail = document.getElementById("product-detail");
        detail.innerHTML = `<div class="loading">Загрузка...</div>`;

        try {
            const p = await this.api("GET", `/products/${productId}`);

            this.selectedVariant = p.variants[0];

            detail.innerHTML = this.renderProductDetail(p);
        } catch (e) {
            detail.innerHTML = `<div class="error-msg">Ошибка: ${this.esc(e.message)}</div>`;
        }
    },

    renderProductDetail(p) {
        const photo = this.photoUrl(p.photos?.[0]?.id);
        const rating = p.rating ? `⭐ ${p.rating.avg} (${p.rating.count} отз.)` : "Нет отзывов";

        let html = "";

        if (photo) {
            html += `<div class="gallery"><img src="${photo}" onerror="this.parentElement.style.display='none'"></div>`;
        } else {
            html += `<div class="gallery-placeholder">${this.catEmoji()}</div>`;
        }

        html += `<div class="pd-title">${this.esc(p.name)}</div>`;
        html += `<div class="pd-rating">${rating}</div>`;
        html += `<div class="pd-desc">${this.esc(p.description)}</div>`;

        const hasAttrs = this.productAttrs.length > 0;
        if (hasAttrs) {
            const labels = this.productAttrs.map(k => this.attrLabels[k] || k).join(" / ");
            html += `<div class="pd-label">${this.esc(labels)}</div>`;
        }
        html += `<div class="variants">`;

        p.variants.forEach((v, i) => {
            const active = i === 0 ? "active" : "";
            const outOfStock = v.stock !== undefined && v.stock === 0;
            const stockHint = v.stock !== undefined && v.stock > 0 && v.stock <= 5
                ? `<span class="v-stock-low">осталось ${v.stock} шт</span>`
                : "";
            const stockBadge = outOfStock ? `<span class="v-out-of-stock">нет в наличии</span>` : stockHint;

            let priceHtml;
            if (v.original_price && v.discount_percent > 0) {
                const timerHtml = v.offer_expires_at
                    ? `<span class="v-timer" id="offer-timer-${v.id}"></span>`
                    : "";
                priceHtml = `<span class="v-price"><span class="price-old">${v.original_price} ₽</span> <span class="price-new">${v.price} ₽</span> ${timerHtml}</span>`;
            } else {
                priceHtml = `<span class="v-price">${v.price} ₽</span>`;
            }

            const attrParts = this.productAttrs
                .map(k => v[k])
                .filter(val => val);
            const attrLabel = attrParts.length > 0 ? attrParts.join(" · ") : "—";

            html += `
                <button class="variant-btn ${active} ${outOfStock ? 'variant-oos' : ''}" data-vid="${v.id}"
                        onclick="App.selectVariant(${v.id})">
                    ${this.esc(attrLabel)}
                    ${priceHtml}
                    ${stockBadge}
                </button>
            `;
        });

        const firstWithExpiry = p.variants.find(v => v.offer_expires_at);
        if (firstWithExpiry) {
            this.startOfferTimer(firstWithExpiry.offer_expires_at, `offer-timer-${firstWithExpiry.id}`);
        }

        html += `</div>`;

        const selected = p.variants[0] || {};
        const allOutOfStock = p.variants.every(v => v.stock !== undefined && v.stock === 0);

        if (allOutOfStock) {
            html += `<button class="btn-primary btn-add" disabled>Нет в наличии</button>`;
        } else {
            html += `<button class="btn-primary btn-add" onclick="App.addToCart(${p.id})">🛒 Добавить в корзину</button>`;
        }

        if (p.reviews && p.reviews.length > 0) {
            html += `<div class="reviews-section">`;
            html += `<h3>Отзывы</h3>`;
            p.reviews.forEach(r => {
                html += `
                    <div class="review-item">
                        <div class="stars">${"⭐".repeat(r.rating)}</div>
                        ${r.text ? `<div class="text">${this.esc(r.text)}</div>` : ""}
                    </div>
                `;
            });
            html += `</div>`;
        }

        return html;
    },

    selectVariant(variantId) {
        const btn = document.querySelector(`.variant-btn[data-vid="${variantId}"]`);
        if (btn && btn.classList.contains("variant-oos")) {
            this.toast("Этот вариант нет в наличии");
            return;
        }

        this.selectedVariant = { id: variantId };

        document.querySelectorAll(".variant-btn").forEach(b => {
            b.classList.toggle("active", parseInt(b.dataset.vid) === variantId);
        });

        this.tg.HapticFeedback?.selectionChanged();
    },

    async addToCart(productId) {
        const variantId = this.selectedVariant?.id;

        if (!variantId) {
            this.toast("Выберите объём");
            return;
        }

        try {
            await this.api("POST", "/cart/add", {
                product_id: productId,
                variant_id: variantId,
            });

            this.toast("Добавлено в корзину ✅");
            this.tg.HapticFeedback?.notificationOccurred("success");
            this.updateCartBadge();
        } catch (e) {
            this.toast(e.message);
        }
    },

    showCatalog() {
        this.showView("catalog");
        document.querySelector('.nav-btn')?.classList.add("active");
    },

    // ==========================
    // Cart
    // ==========================

    async showCart() {
        this.showView("cart");
        document.querySelectorAll(".nav-btn")[1]?.classList.add("active");

        const container = document.getElementById("cart-items");
        const footer = document.getElementById("cart-footer");
        container.innerHTML = `<div class="loading">Загрузка...</div>`;
        footer.innerHTML = "";

        try {
            const cart = await this.api("GET", "/cart");

            if (cart.items.length === 0) {
                container.innerHTML = `
                    <div class="cart-empty">
                        <div class="emoji">🛒</div>
                        <div>Корзина пуста</div>
                    </div>
                `;
                return;
            }

            container.innerHTML = cart.items.map(item => {
                let priceHtml;
                if (item.original_price && item.discount_percent > 0) {
                    priceHtml = `<span class="price-old">${item.original_price} ₽</span> <span class="price-new">${item.price} ₽</span> · ${item.subtotal} ₽`;
                } else {
                    priceHtml = `${item.subtotal} ₽`;
                }

                return `
                <div class="cart-item">
                    <div class="ci-info">
                        <div class="ci-name">${this.esc(item.product_name)}</div>
                        <div class="ci-variant">${this.esc(item.volume)}</div>
                        <div class="ci-price">${priceHtml}</div>
                    </div>
                    <div class="ci-controls">
                        <button class="qty-btn" onclick="App.changeQty(${item.cart_item_id}, -1)">−</button>
                        <span class="qty-display">${item.quantity}</span>
                        <button class="qty-btn" onclick="App.changeQty(${item.cart_item_id}, 1)">+</button>
                    </div>
                </div>
            `}).join("");

            this.cartTotal = cart.total;

            footer.innerHTML = `
                <div class="cart-total">Итого: ${cart.total} ₽</div>
                <button class="btn-primary" onclick="App.showCheckout()">Оформить заказ</button>
            `;
        } catch (e) {
            container.innerHTML = `<div class="error-msg">Ошибка: ${this.esc(e.message)}</div>`;
        }
    },

    async changeQty(itemId, delta) {
        const path = delta > 0 ? "inc" : "dec";

        try {
            await this.api("POST", `/${path}/${itemId}`);
            await this.showCart();
            this.updateCartBadge();
        } catch (e) {
            this.toast(e.message);
        }
    },

    async updateCartBadge() {
        try {
            const cart = await this.api("GET", "/cart");
            const count = cart.items.length;

            const badge = document.getElementById("cart-badge");

            if (count > 0) {
                badge.textContent = count;
                badge.style.display = "flex";
            } else {
                badge.style.display = "none";
            }
        } catch (e) { }
    },

    showCheckout() {
        if (this.cartTotal === 0) {
            this.toast("Корзина пуста");
            return;
        }

        this.showView("checkout");
        this.appliedPromo = null;
        document.getElementById("co-promo").value = "";
        document.getElementById("promo-result").textContent = "";
        document.getElementById("promo-result").className = "";
        this.renderCheckoutTotal();
        this.loadPaymentMethods();
    },

    async loadPaymentMethods() {
        const container = document.getElementById("payment-methods");
        container.innerHTML = `<div class="loading">Загрузка...</div>`;

        try {
            this.paymentMethods = await this.api("GET", "/payment-methods");

            if (this.paymentMethods.length === 0) {
                container.innerHTML = "";
                return;
            }

            this.selectedPaymentMethod = this.paymentMethods[0].id;

            container.innerHTML = this.paymentMethods.map((m, i) => `
                <label class="payment-option ${i === 0 ? 'active' : ''}" data-pm="${m.id}">
                    <input type="radio" name="payment_method" value="${m.id}" ${i === 0 ? 'checked' : ''}
                           onchange="App.selectPaymentMethod('${m.id}')">
                    <div class="pm-info">
                        <div class="pm-label">${this.esc(m.label)}</div>
                        <div class="pm-desc">${this.esc(m.description)}</div>
                    </div>
                </label>
            `).join("");
        } catch (e) {
            container.innerHTML = `<div class="error-msg">Ошибка загрузки способов оплаты</div>`;
        }
    },

    selectPaymentMethod(methodId) {
        this.selectedPaymentMethod = methodId;
        document.querySelectorAll(".payment-option").forEach(el => {
            el.classList.toggle("active", el.dataset.pm === methodId);
        });
        this.tg.HapticFeedback?.selectionChanged();
    },

    async applyPromo() {
        const code = document.getElementById("co-promo").value.trim();
        const result = document.getElementById("promo-result");

        if (!code) {
            result.textContent = "Введите промокод";
            result.className = "error";
            return;
        }

        result.textContent = "Проверка...";

        try {
            const promo = await this.api("POST", "/promo/validate", { code });

            this.appliedPromo = promo;
            result.textContent = `✅ Скидка: ${promo.discount_amount} ₽`;
            result.className = "success";
            this.tg.HapticFeedback?.notificationOccurred("success");
            this.renderCheckoutTotal();
        } catch (e) {
            this.appliedPromo = null;
            result.textContent = "❌ " + e.message;
            result.className = "error";
            this.renderCheckoutTotal();
        }
    },

    renderCheckoutTotal() {
        const el = document.getElementById("co-total");

        if (this.appliedPromo) {
            el.innerHTML = `
                <div class="subtotal-line">Без скидки: ${this.cartTotal} ₽</div>
                <div class="discount-line">Скидка: −${this.appliedPromo.discount_amount} ₽</div>
                <div>Итого: ${this.appliedPromo.final_total} ₽</div>
            `;
        } else {
            el.textContent = `Итого: ${this.cartTotal} ₽`;
        }
    },

    async submitOrder(event) {
        event.preventDefault();

        const name = document.getElementById("co-name").value.trim();
        const phone = document.getElementById("co-phone").value.trim();
        const comment = document.getElementById("co-comment").value.trim() || null;

        if (name.length < 2) {
            this.toast("Введите имя");
            return;
        }

        try {
            const result = await this.api("POST", "/orders", {
                full_name: name,
                phone,
                comment,
                promo_code: this.appliedPromo?.code || null,
                payment_method: this.selectedPaymentMethod,
            });

            this.updateCartBadge();
            this.showSuccess(result);
            this.tg.HapticFeedback?.notificationOccurred("success");
        } catch (e) {
            this.toast(e.message);
        }
    },

    showSuccess(result) {
        this.showView("success");

        const content = document.getElementById("success-content");

        let paymentInfo = "";

        if (result.payment === "yookassa" && result.confirmation_url) {
            paymentInfo = `
                <button class="btn-primary" onclick="window.open('${result.confirmation_url}', '_blank')">
                    💳 Оплатить ${result.total} ₽
                </button>
                <div class="info">После оплаты статус заказа обновится автоматически.</div>
            `;
        } else if (result.payment === "manual") {
            if (result.payment_error) {
                paymentInfo = `
                    <div class="info">⚠️ Онлайн-оплата временно недоступна.</div>
                    <div class="card">
                        <div style="font-weight:600;margin-bottom:8px">💳 Оплата переводом на карту:</div>
                        <div style="font-size:18px;font-weight:700;letter-spacing:1px">${this.esc(result.card_number || "не указан")}</div>
                        ${result.recipient ? `<div style="margin-top:4px;color:var(--hint)">Получатель: ${this.esc(result.recipient)}</div>` : ""}
                    </div>
                `;
            } else {
                paymentInfo = `
                    <div class="card">
                        <div style="font-weight:600;margin-bottom:8px">💳 Оплата переводом на карту:</div>
                        <div style="font-size:18px;font-weight:700;letter-spacing:1px">${this.esc(result.card_number || "не указан")}</div>
                        ${result.recipient ? `<div style="margin-top:4px;color:var(--hint)">Получатель: ${this.esc(result.recipient)}</div>` : ""}
                    </div>
                    <div class="info">После оплаты отправьте фото чека боту в чат.</div>
                `;
            }
        }

        content.innerHTML = `
            <div class="emoji">✅</div>
            <h2>Заказ №${result.order_id} оформлен!</h2>
            ${result.discount > 0
                ? `<div class="info">Скидка: <b>−${result.discount} ₽</b></div>`
                : ""
            }
            <div class="info">Сумма: <b>${result.total} ₽</b></div>
            ${paymentInfo}
            <button class="btn-primary" onclick="App.showCatalog()">Продолжить покупки</button>
        `;
    },

    // ==========================
    // Orders
    // ==========================

    async showOrders() {
        this.showView("orders");
        document.querySelectorAll(".nav-btn")[2]?.classList.add("active");

        const list = document.getElementById("orders-list");
        list.innerHTML = `<div class="loading">Загрузка...</div>`;

        try {
            const orders = await this.api("GET", "/orders");

            if (orders.length === 0) {
                list.innerHTML = `
                    <div class="cart-empty">
                        <div class="emoji">📦</div>
                        <div>Заказов пока нет</div>
                    </div>
                `;
                return;
            }

            const statusLabels = {
                "new": "🆕 Новый",
                "confirmed": "✅ Подтверждён",
                "paid": "💰 Оплачен",
                "shipped": "🚚 Отправлен",
                "done": "🏁 Выполнен",
                "cancelled": "❌ Отменён",
            };

            list.innerHTML = orders.map(o => `
                <div class="order-card">
                    <div class="oc-header">
                        <span class="oc-id">Заказ №${o.id}</span>
                        <span class="oc-status">${statusLabels[o.status] || o.status}</span>
                    </div>
                    <div class="oc-total">${o.total_amount} ₽</div>
                    <div class="oc-date">${new Date(o.created_at).toLocaleDateString("ru-RU")}</div>
                </div>
            `).join("");
        } catch (e) {
            list.innerHTML = `<div class="error-msg">Ошибка: ${this.esc(e.message)}</div>`;
        }
    },

    // ==========================
    // Utils
    // ==========================

    _offerTimerInterval: null,

    startOfferTimer(isoStr, elementId) {
        if (this._offerTimerInterval) {
            clearInterval(this._offerTimerInterval);
        }

        const target = new Date(isoStr).getTime();

        const update = () => {
            const el = document.getElementById(elementId);
            if (!el) {
                clearInterval(this._offerTimerInterval);
                return;
            }

            const remaining = target - Date.now();
            if (remaining <= 0) {
                el.textContent = "истекло";
                clearInterval(this._offerTimerInterval);
                return;
            }

            const h = Math.floor(remaining / 3600000);
            const m = Math.floor((remaining % 3600000) / 60000);
            const s = Math.floor((remaining % 60000) / 1000);

            el.textContent = `⏰ ${h}ч ${m}м ${s}с`;
        };

        update();
        this._offerTimerInterval = setInterval(update, 1000);
    },

    toast(msg) {
        if (this.tg.HapticFeedback) {
            this.tg.HapticFeedback.notificationOccurred("error");
        }
        this.tg.showAlert ? this.tg.showAlert(msg) : alert(msg);
    },

    esc(text) {
        if (!text) return "";
        const div = document.createElement("div");
        div.textContent = text;
        return div.innerHTML;
    },
};

App.init();
