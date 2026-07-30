const App = {

    tg: null,
    initData: "",
    currentCategory: null,
    categories: [],
    selectedVariant: null,
    cartTotal: 0,

    init() {
        this.tg = window.Telegram.WebApp;
        this.tg.ready();
        this.tg.expand();

        this.initData = this.tg.initData || "";

        const theme = this.tg.themeParams;
        if (theme.bg_color) {
            document.body.style.background = theme.bg_color;
        }

        this.loadCategories();
        this.updateCartBadge();
    },

    // ==========================
    // API helpers
    // ==========================

    async api(method, path, body) {
        const opts = {
            method,
            headers: {
                "Authorization": "tma " + this.initData,
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

                return `
                    <div class="product-card" onclick="App.openProduct(${p.id})">
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

        html += `<div class="pd-label">Объём</div>`;
        html += `<div class="variants">`;

        p.variants.forEach((v, i) => {
            const active = i === 0 ? "active" : "";
            html += `
                <button class="variant-btn ${active}" data-vid="${v.id}"
                        onclick="App.selectVariant(${v.id})">
                    ${this.esc(v.volume)}
                    <span class="v-price">${v.price} ₽</span>
                    ${v.burn ? `<span class="v-burn">🔥 ${this.esc(v.burn)}</span>` : ""}
                </button>
            `;
        });

        html += `</div>`;

        html += `<button class="btn-primary btn-add" onclick="App.addToCart(${p.id})">🛒 Добавить в корзину</button>`;

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
        this.selectedVariant = { id: variantId };

        document.querySelectorAll(".variant-btn").forEach(btn => {
            btn.classList.toggle("active", parseInt(btn.dataset.vid) === variantId);
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

            container.innerHTML = cart.items.map(item => `
                <div class="cart-item">
                    <div class="ci-info">
                        <div class="ci-name">${this.esc(item.product_name)}</div>
                        <div class="ci-variant">${this.esc(item.volume)}</div>
                        <div class="ci-price">${item.subtotal} ₽</div>
                    </div>
                    <div class="ci-controls">
                        <button class="qty-btn" onclick="App.changeQty(${item.cart_item_id}, -1)">−</button>
                        <span class="qty-display">${item.quantity}</span>
                        <button class="qty-btn" onclick="App.changeQty(${item.cart_item_id}, 1)">+</button>
                    </div>
                </div>
            `).join("");

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
        document.getElementById("co-total").textContent = `Итого: ${this.cartTotal} ₽`;
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

        if (result.payment === "manual") {
            paymentInfo = `
                <div class="card">
                    <div style="font-weight:600;margin-bottom:8px">💳 Оплата переводом на карту:</div>
                    <div style="font-size:18px;font-weight:700;letter-spacing:1px">${this.esc(result.card_number || "не указан")}</div>
                    ${result.recipient ? `<div style="margin-top:4px;color:var(--hint)">Получатель: ${this.esc(result.recipient)}</div>` : ""}
                </div>
                <div class="info">После оплаты отправьте фото чека боту в чат.</div>
            `;
        } else if (result.payment === "qr") {
            paymentInfo = `<div class="info">Ссылка на оплату через СБП придёт в чат с ботом.</div>`;
        }

        content.innerHTML = `
            <div class="emoji">✅</div>
            <h2>Заказ №${result.order_id} оформлен!</h2>
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
