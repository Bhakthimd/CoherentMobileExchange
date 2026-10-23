// CoherentMobiles Customer Enhancements
// Connects storefront SPA to PostgreSQL Catalog, Real Customer Authentication, and Concurrent Order Lock

(function() {
  window.USE_OFFLINE_CATALOG_FALLBACK = false;
  let liveCatalogUnits = [];

  // =========================================================================
  // 1. Live Catalog Synchronization from /api/catalog
  // =========================================================================
  async function loadStorefrontCatalog() {
    try {
      const res = await fetch("/api/catalog?per_page=100");
      if (!res.ok) {
        throw new Error("Catalog response " + res.status);
      }
      const data = await res.json();
      if (!data.success || !Array.isArray(data.items) || data.items.length === 0) {
        console.warn("Backend catalog returned 0 units. Preserving offline fallback.");
        return;
      }

      liveCatalogUnits = data.items;
      window.USE_OFFLINE_CATALOG_FALLBACK = false;

      // Map backend units into the SPA's expected buyPhones array
      if (typeof buyPhones !== "undefined") {
        buyPhones.length = 0;
        data.items.forEach(u => {
          const deviceTitle = `${u.brand || ''} ${u.model || ''}`.trim() || u.device_name;
          const storageNum = parseInt(u.storage) || 128;
          const imgUrl = u.image || (u.images && u.images[0]) || resolveProductImage(u.brand, u.model);

          buyPhones.push({
            unit_id: u.unit_id,
            id: u.unit_id,
            name: `${deviceTitle} (${u.storage || '128 GB'})`,
            model: u.model || deviceTitle,
            brand: u.brand || 'Multi-Brand',
            storage: storageNum,
            storageStr: u.storage || `${storageNum} GB`,
            price: Number(u.selling_price) || 0,
            mrp: Number(u.mrp) || Math.round((Number(u.selling_price) || 0) * 1.15),
            rating: 4.8,
            image: imgUrl,
            condition_grade: u.condition_grade || 'good',
            battery_health: u.battery_health,
            warranty: u.warranty || `${u.warranty_months || 6} Months`,
            warranty_months: u.warranty_months || 6,
            vendor_name: u.store_name || u.vendor_name || 'Verified Partner',
            vendor_id: u.vendor_id,
            store_id: u.store_id || u.vendor_id,
            store_name: u.store_name || u.vendor_name || 'K.T. Street Store',
            store_address: u.store_address || 'K.T. Street, Mysuru',
            store_landmark: u.store_landmark || 'K.T. Street',
            store_phone: u.store_phone,
            store_whatsapp: u.store_whatsapp,
            store_is_open: u.store_is_open,
            store_directions_url: u.store_directions_url,
            imei: u.imei,
            stock: 1,
            total_stock: 1,
            notes: u.notes
          });
        });

        // Trigger UI re-render
        if (typeof displayPhones === "function") {
          displayPhones(buyPhones);
        }
        if (typeof renderHomeFeatured === "function") {
          renderHomeFeatured();
        }
        console.log(`[Storefront] Loaded ${buyPhones.length} live refurbished units from PostgreSQL.`);
      }
    } catch (err) {
      console.warn("[Storefront] Failed to load /api/catalog. Offline fallback active:", err);
      window.USE_OFFLINE_CATALOG_FALLBACK = true;
    }
  }

  // =========================================================================
  // 2. Real Concurrency-Safe Checkout Integration
  // =========================================================================
  window.submitRealOrderCheckout = async function(customerDetails) {
    const selected = (typeof appState !== "undefined" && appState.selectedPhoneForBuy) ? appState.selectedPhoneForBuy : (buyPhones && buyPhones[0]);
    if (!selected || !selected.unit_id) {
      console.warn("No unit_id selected, fallback to standard mock flow.");
      return null;
    }

    const payload = {
      unit_id: selected.unit_id,
      customer_name: customerDetails.name,
      customer_email: customerDetails.email || (customerDetails.phone + "@guest.coherentmobiles.com"),
      customer_phone: customerDetails.phone,
      delivery_address: customerDetails.address,
      payment_method: customerDetails.payment_method || "pod",
      trade_in_credit: customerDetails.trade_in_credit || 0,
      coupon_discount: customerDetails.coupon_discount || 0
    };

    try {
      const res = await fetch("/api/orders", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify(payload)
      });

      const data = await res.json();
      if (res.status === 409) {
        // Concurrency conflict: unit was already sold!
        alert("⚠️ Device Unavailable:\n" + (data.error || "This specific certified device was just purchased by another customer. The catalog has been refreshed. Please select another handset."));
        loadStorefrontCatalog();
        return { success: false, conflict: true };
      }

      if (res.ok && data.success) {
        // Refresh catalog so the sold unit disappears from storefront
        loadStorefrontCatalog();
        return { success: true, order: data.order };
      } else {
        alert("Checkout failed: " + (data.error || "Please try again."));
        return { success: false };
      }
    } catch (err) {
      console.error("Error creating order:", err);
      return { success: false };
    }
  };

  // Intercept the legacy confirmBuyOrder() to use atomic checkout
  if (typeof window.confirmBuyOrder === "function") {
    const originalConfirm = window.confirmBuyOrder;
    window.confirmBuyOrder = async function() {
      const nameInput = document.getElementById("orderName");
      const phoneInput = document.getElementById("orderPhone");
      const addressInput = document.getElementById("orderAddress");

      if (!nameInput || !phoneInput || !addressInput) {
        return originalConfirm.apply(this, arguments);
      }

      const name = nameInput.value.trim();
      const phone = phoneInput.value.trim();
      const address = addressInput.value.trim();

      if (!name || phone.length !== 10 || !address) {
        alert("Please complete your name, 10-digit mobile number, and delivery address.");
        return;
      }

      const selected = appState.selectedPhoneForBuy || (buyPhones && buyPhones[0]) || {};
      const hasCredit = appState.imeiVerified && appState.predictedPrice > 0;
      const tradeCredit = hasCredit ? appState.predictedPrice : 0;
      const couponDisc = appState.appliedCouponDiscount || 0;

      // If unit_id is present, perform atomic PostgreSQL checkout
      if (selected && selected.unit_id) {
        const orderBtn = document.querySelector("#checkoutPage .confirm-order-btn");
        if (orderBtn) {
          orderBtn.disabled = true;
          orderBtn.textContent = "Processing reservation...";
        }

        const result = await window.submitRealOrderCheckout({
          name: name,
          phone: phone,
          address: address,
          trade_in_credit: tradeCredit,
          coupon_discount: couponDisc,
          payment_method: "pod"
        });

        if (orderBtn) {
          orderBtn.disabled = false;
          orderBtn.textContent = "Confirm Order";
        }

        if (result && result.success && result.order) {
          document.getElementById('confirmOrderId').textContent = "Order ID: " + result.order.order_reference;
          navigateTo('confirmationPage');
          showToast("Order confirmed successfully! Device reserved.");
          return;
        } else if (result && result.conflict) {
          navigateTo('buyPage');
          return;
        }
      }

      // Fallback to original flow if no unit_id
      return originalConfirm.apply(this, arguments);
    };
  }

  // =========================================================================
  // 3. Customer "My Orders" Modal & Auth State
  // =========================================================================
  window.openCustomerOrdersModal = async function() {
    let modal = document.getElementById("customerOrdersModal");
    if (!modal) {
      modal = document.createElement("div");
      modal.id = "customerOrdersModal";
      modal.className = "customer-orders-modal";
      modal.innerHTML = `
        <div class="customer-orders-card">
          <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:20px;">
            <h3 style="font-size:18px; font-weight:800;">My Placed Orders</h3>
            <button onclick="document.getElementById('customerOrdersModal').style.display='none'" style="border:none; background:none; font-size:22px; cursor:pointer;">✕</button>
          </div>
          <div id="customerOrdersContent" style="overflow-y:auto; flex:1;">
            <div style="text-align:center; padding:30px; color:#64748b;">Loading your orders...</div>
          </div>
        </div>
      `;
      document.body.appendChild(modal);
    }

    modal.style.display = "flex";
    const content = document.getElementById("customerOrdersContent");

    try {
      const res = await fetch("/api/orders", { credentials: "include" });
      if (!res.ok) {
        content.innerHTML = `
          <div style="text-align:center; padding:30px; color:#64748b;">
            <span style="font-size:32px;">👤</span><br>
            <strong>Sign in or look up your order by phone number:</strong>
            <div style="margin-top:14px; display:flex; justify-content:center; gap:8px;">
              <input type="tel" id="guestOrderPhone" placeholder="Enter 10-digit phone" style="padding:8px 12px; border:1px solid #cbd5e1; border-radius:6px;">
              <button onclick="lookupOrdersByPhone()" style="padding:8px 16px; background:var(--primary); color:#fff; border:none; border-radius:6px; font-weight:700; cursor:pointer;">Track</button>
            </div>
          </div>
        `;
        return;
      }

      const data = await res.json();
      const orders = data.orders || [];
      if (orders.length === 0) {
        content.innerHTML = `<div style="text-align:center; padding:40px; color:#64748b;">You have not placed any orders yet.</div>`;
        return;
      }

      renderOrderListInModal(orders, content);
    } catch (e) {
      content.innerHTML = `<div style="text-align:center; padding:30px; color:#ef4444;">Failed to load orders.</div>`;
    }
  };

  window.lookupOrdersByPhone = async function() {
    const phone = document.getElementById("guestOrderPhone").value.trim();
    if (!phone) return;
    const content = document.getElementById("customerOrdersContent");
    content.innerHTML = `<div style="text-align:center; padding:30px; color:#64748b;">Looking up orders...</div>`;
    try {
      const res = await fetch(`/api/orders?phone=${encodeURIComponent(phone)}`);
      const data = await res.json();
      const orders = data.orders || [];
      if (orders.length === 0) {
        content.innerHTML = `<div style="text-align:center; padding:30px; color:#64748b;">No orders found for mobile ${phone}.</div>`;
        return;
      }
      renderOrderListInModal(orders, content);
    } catch (e) {
      content.innerHTML = `<div style="text-align:center; padding:30px; color:#ef4444;">Lookup failed.</div>`;
    }
  };

  function renderOrderListInModal(orders, container) {
    container.innerHTML = orders.map(o => `
      <div class="customer-order-item">
        <div>
          <strong style="font-size:15px; color:#0f172a;">${o.order_reference}</strong>
          <div style="font-size:12px; color:#64748b;">Placed on ${new Date(o.created_at).toLocaleDateString("en-IN")}</div>
          <div style="font-size:13px; font-weight:600; margin-top:4px;">
            ${o.items && o.items[0] ? o.items[0].device_name : 'Smartphone'}
          </div>
          <div style="font-size:12px; color:#64748b;">Deliver to: ${o.delivery_address || '-'}</div>
        </div>
        <div style="text-align:right;">
          <div style="font-size:16px; font-weight:800; color:var(--primary);">₹${Number(o.total_amount).toLocaleString('en-IN')}</div>
          <span style="display:inline-block; margin-top:4px; font-size:11.5px; font-weight:800; padding:3px 8px; border-radius:6px; background:#eff6ff; color:#1d4ed8;">
            ● ${o.order_status.toUpperCase()}
          </span>
        </div>
      </div>
    `).join("");
  }

  // =========================================================================
  // 4. 24-Hour "Reserve & Visit" Customer Hold Modal
  // =========================================================================
  window.openReserveModal = function(unitId) {
    let unit = (buyPhones || []).find(p => p.unit_id === unitId || p.id === unitId);
    if (!unit && buyPhones && buyPhones.length > 0) {
      unit = buyPhones[0];
    }
    if (!unit) {
      alert("No device currently available to reserve.");
      return;
    }

    let modal = document.getElementById("cmReserveModal");
    if (!modal) {
      modal = document.createElement("div");
      modal.id = "cmReserveModal";
      modal.className = "cm-modal";
      document.body.appendChild(modal);
    }

    modal.innerHTML = `
      <div class="cm-modal-card">
        <div class="cm-modal-header">
          <h3><i class="fa-solid fa-stopwatch" style="color:var(--primary)"></i> Reserve & Visit (Hold for 24h)</h3>
          <button onclick="document.getElementById('cmReserveModal').classList.remove('active')" style="border:none; background:none; font-size:22px; cursor:pointer;">✕</button>
        </div>
        <div class="cm-modal-body" id="reserveModalBody">
          <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:14px; border-bottom:1px solid #e2e8f0; padding-bottom:12px;">
            <div>
              <strong style="font-size:16px; color:#0f172a;">${unit.name || unit.model}</strong>
              <div style="font-size:12px; color:#64748b;">Grade ${unit.condition_grade} &bull; Battery ${unit.battery_health || 90}% &bull; ${unit.warranty}</div>
            </div>
            <div style="text-align:right;">
              <span style="font-size:18px; font-weight:800; color:var(--primary);">₹${unit.price.toLocaleString('en-IN')}</span>
            </div>
          </div>

          <div class="store-meta-box">
            <strong style="color:#0f172a;"><i class="fa-solid fa-store" style="color:var(--primary);"></i> Pickup Location:</strong> ${unit.store_name || unit.vendor_name || 'K.T. Street Partner Store'}
            <div style="color:#64748b; margin-top:3px;"><i class="fa-solid fa-location-dot"></i> ${unit.store_address || 'K.T. Street, Mysuru (570001)'}</div>
            ${unit.store_landmark ? `<div style="color:#475569; font-size:11.5px; margin-top:2px;">Landmark: ${unit.store_landmark}</div>` : ''}
          </div>

          <p style="font-size:12.5px; color:#475569; margin-bottom:14px;">
            Holding this device locks it exclusively for you for <strong>24 hours</strong>. No upfront payment required. Visit the K.T. Street shop, inspect the device in person, and pay cash or UPI if satisfied.
          </p>

          <form id="reserveForm" onsubmit="submitReserveHold(event, ${unit.unit_id})">
            <div style="margin-bottom:12px;">
              <label style="display:block; font-size:12.5px; font-weight:700; margin-bottom:4px;">Your Full Name *</label>
              <input type="text" id="reserveName" required placeholder="e.g. Ramesh Gowda" style="width:100%; padding:8px 12px; border:1px solid #cbd5e1; border-radius:6px; font-size:13px;">
            </div>
            <div style="margin-bottom:12px;">
              <label style="display:block; font-size:12.5px; font-weight:700; margin-bottom:4px;">Mobile Number (10 digits) *</label>
              <input type="tel" id="reservePhone" required maxlength="10" placeholder="e.g. 9845012345" style="width:100%; padding:8px 12px; border:1px solid #cbd5e1; border-radius:6px; font-size:13px;">
            </div>
            <div style="margin-bottom:16px;">
              <label style="display:block; font-size:12.5px; font-weight:700; margin-bottom:4px;">Email (Optional)</label>
              <input type="email" id="reserveEmail" placeholder="for reservation pass" style="width:100%; padding:8px 12px; border:1px solid #cbd5e1; border-radius:6px; font-size:13px;">
            </div>
            <button type="submit" id="btnSubmitHold" style="width:100%; padding:12px; background:var(--primary); color:#fff; border:none; border-radius:8px; font-weight:800; font-size:14px; cursor:pointer;">
              <i class="fa-solid fa-lock"></i> Lock Device & Hold for 24 Hours
            </button>
          </form>
        </div>
      </div>
    `;

    modal.classList.add("active");
  };

  window.submitReserveHold = async function(e, unitId) {
    e.preventDefault();
    const btn = document.getElementById("btnSubmitHold");
    btn.disabled = true;
    btn.innerHTML = `<i class="fa-solid fa-circle-notch fa-spin"></i> Holding device...`;

    const name = document.getElementById("reserveName").value.trim();
    const phone = document.getElementById("reservePhone").value.trim();
    const email = document.getElementById("reserveEmail").value.trim();

    try {
      const res = await fetch("/api/reservations", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          unit_id: unitId,
          customer_name: name,
          customer_phone: phone,
          customer_email: email
        })
      });

      const data = await res.json();
      if (res.ok && data.success) {
        // Refresh catalog so the held unit is no longer listed as in-stock
        loadStorefrontCatalog();

        const body = document.getElementById("reserveModalBody");
        const store = data.store || {};
        body.innerHTML = `
          <div class="reserve-success-box">
            <i class="fa-solid fa-circle-check fa-3x" style="color:#10b981; margin-bottom:8px;"></i>
            <h4 style="font-size:17px; font-weight:800; color:#0f172a;">Device Successfully Held!</h4>
            <p style="font-size:12px; color:#64748b;">Show this reservation pass to the store executive on K.T. Street</p>
            <div class="reserve-code">${data.reservation_reference}</div>
            <div style="font-size:12px; font-weight:700; color:#b02154;"><i class="fa-solid fa-stopwatch"></i> Hold expires in 24 hours</div>
          </div>

          <div class="store-meta-box">
            <strong style="color:#0f172a;"><i class="fa-solid fa-store" style="color:var(--primary);"></i> ${store.name || 'Partner Store'}</strong>
            <div style="color:#475569; margin-top:4px;"><i class="fa-solid fa-location-dot"></i> ${store.address || 'K.T. Street, Mysuru'}</div>
            <div style="display:flex; gap:8px; margin-top:12px;">
              ${store.directions_url ? `
                <a href="${store.directions_url}" target="_blank" style="flex:1; text-align:center; padding:8px; background:#0f172a; color:#fff; text-decoration:none; border-radius:6px; font-size:12px; font-weight:700;">
                  <i class="fa-solid fa-location-arrow"></i> Get Directions
                </a>
              ` : ''}
              ${store.whatsapp ? `
                <a href="https://wa.me/91${(store.whatsapp || '').replace(/\D/g, '')}?text=Hello,%20I%20have%20reserved%20a%20phone%20with%20code%20${data.reservation_reference}!" target="_blank" style="flex:1; text-align:center; padding:8px; background:#25d366; color:#fff; text-decoration:none; border-radius:6px; font-size:12px; font-weight:700;">
                  <i class="fa-brands fa-whatsapp"></i> Chat on WhatsApp
                </a>
              ` : ''}
            </div>
          </div>

          <button onclick="document.getElementById('cmReserveModal').classList.remove('active')" style="width:100%; padding:10px; background:#f1f5f9; color:#334155; border:none; border-radius:6px; font-weight:700; cursor:pointer;">
            Done
          </button>
        `;
      } else {
        alert("Hold failed: " + (data.error || "Device may already be reserved or sold."));
        btn.disabled = false;
        btn.innerHTML = `<i class="fa-solid fa-lock"></i> Lock Device & Hold for 24 Hours`;
        loadStorefrontCatalog();
      }
    } catch (err) {
      alert("Network error. Please try again.");
      btn.disabled = false;
      btn.innerHTML = `<i class="fa-solid fa-lock"></i> Lock Device & Hold for 24 Hours`;
    }
  };

  // =========================================================================
  // 5. Mysuru Sell & Trade-in Flow Wizard
  // =========================================================================
  window.openSellWizardModal = function() {
    let modal = document.getElementById("cmSellWizardModal");
    if (!modal) {
      modal = document.createElement("div");
      modal.id = "cmSellWizardModal";
      modal.className = "cm-modal";
      document.body.appendChild(modal);
    }

    modal.innerHTML = `
      <div class="cm-modal-card">
        <div class="cm-modal-header">
          <h3><i class="fa-solid fa-hand-holding-dollar" style="color:var(--primary)"></i> Sell Your Phone in Mysuru (Instant Payout)</h3>
          <button onclick="document.getElementById('cmSellWizardModal').classList.remove('active')" style="border:none; background:none; font-size:22px; cursor:pointer;">✕</button>
        </div>
        <div class="cm-modal-body" id="sellWizardBody">
          <!-- Step 1: Device Selection -->
          <div id="sellStep1" class="sell-step active">
            <h4 style="font-size:15px; font-weight:700; margin-bottom:6px;">Step 1 of 3: Select Your Phone</h4>
            <p style="font-size:12px; color:#64748b; margin-bottom:12px;">Choose your brand, model, and storage capacity.</p>
            <div style="margin-bottom:12px;">
              <label style="display:block; font-size:12.5px; font-weight:700; margin-bottom:4px;">Brand</label>
              <select id="sellBrand" onchange="onSellBrandChange()" style="width:100%; padding:8px 12px; border:1px solid #cbd5e1; border-radius:6px;">
                <option value="Apple">Apple iPhone</option>
                <option value="Samsung">Samsung Galaxy</option>
                <option value="OnePlus">OnePlus</option>
                <option value="Google">Google Pixel</option>
                <option value="Xiaomi">Xiaomi / Redmi</option>
              </select>
            </div>
            <div style="margin-bottom:12px;">
              <label style="display:block; font-size:12.5px; font-weight:700; margin-bottom:4px;">Model</label>
              <select id="sellModel" style="width:100%; padding:8px 12px; border:1px solid #cbd5e1; border-radius:6px;">
                <option value="iPhone 15">iPhone 15</option>
                <option value="iPhone 14">iPhone 14</option>
                <option value="iPhone 13">iPhone 13</option>
                <option value="iPhone 12">iPhone 12</option>
              </select>
            </div>
            <div style="margin-bottom:16px;">
              <label style="display:block; font-size:12.5px; font-weight:700; margin-bottom:4px;">Storage</label>
              <select id="sellStorage" style="width:100%; padding:8px 12px; border:1px solid #cbd5e1; border-radius:6px;">
                <option value="128">128 GB</option>
                <option value="256">256 GB</option>
              </select>
            </div>
            <button onclick="goToSellStep(2)" style="width:100%; padding:10px; background:var(--primary); color:#fff; border:none; border-radius:6px; font-weight:700; cursor:pointer;">
              Continue to Condition Check <i class="fa-solid fa-arrow-right"></i>
            </button>
          </div>

          <!-- Step 2: Condition Questionnaire -->
          <div id="sellStep2" class="sell-step">
            <h4 style="font-size:15px; font-weight:700; margin-bottom:6px;">Step 2 of 3: Phone Condition</h4>
            <div style="margin-bottom:12px;">
              <label style="display:block; font-size:12.5px; font-weight:700; margin-bottom:4px;">Screen Condition</label>
              <select id="condScreen" style="width:100%; padding:8px 12px; border:1px solid #cbd5e1; border-radius:6px;">
                <option value="flawless">Flawless (No scratches or cracks)</option>
                <option value="minor_scratches">Minor hairline scratches</option>
                <option value="cracked">Cracked or broken glass</option>
              </select>
            </div>
            <div style="margin-bottom:12px;">
              <label style="display:block; font-size:12.5px; font-weight:700; margin-bottom:4px;">Body / Frame Condition</label>
              <select id="condBody" style="width:100%; padding:8px 12px; border:1px solid #cbd5e1; border-radius:6px;">
                <option value="flawless">Flawless / Like New</option>
                <option value="good">Good (Normal minor wear)</option>
                <option value="dented">Dented or heavily scuffed</option>
              </select>
            </div>
            <div style="margin-bottom:12px;">
              <label style="display:block; font-size:12.5px; font-weight:700; margin-bottom:4px;">Battery Health</label>
              <select id="condBattery" style="width:100%; padding:8px 12px; border:1px solid #cbd5e1; border-radius:6px;">
                <option value="above_85">Above 85% Health</option>
                <option value="below_85">Below 85% / Service Required</option>
              </select>
            </div>
            <div style="margin-bottom:16px;">
              <label style="display:block; font-size:12.5px; font-weight:700; margin-bottom:4px;">Accessories Included</label>
              <div style="display:flex; gap:16px; font-size:13px;">
                <label><input type="checkbox" id="accBox" checked> Original Box</label>
                <label><input type="checkbox" id="accCharger" checked> Original Charger</label>
              </div>
            </div>
            <div style="display:flex; gap:8px;">
              <button onclick="goToSellStep(1)" style="flex:1; padding:10px; background:#f1f5f9; color:#334155; border:none; border-radius:6px; font-weight:700; cursor:pointer;">Back</button>
              <button onclick="fetchEstimateAndGoStep3()" style="flex:2; padding:10px; background:var(--primary); color:#fff; border:none; border-radius:6px; font-weight:700; cursor:pointer;">
                Get Instant Valuation <i class="fa-solid fa-arrow-right"></i>
              </button>
            </div>
          </div>

          <!-- Step 3: Estimate, Luhn IMEI & Fulfillment -->
          <div id="sellStep3" class="sell-step">
            <div id="estimateResultBox" style="background:#fdf2f6; border:1px solid #fbcfe8; border-radius:10px; padding:14px; text-align:center; margin-bottom:14px;">
              <div style="font-size:12px; color:#b02154; font-weight:700;">ESTIMATED PAYOUT RANGE</div>
              <div id="estimateRangeTxt" style="font-size:1.6rem; font-weight:800; color:#d6336c; margin:4px 0;">₹0 - ₹0</div>
              <div style="font-size:11px; color:#64748b;">Final offer confirmed after 15-point inspection at store or doorstep</div>
            </div>

            <form id="sellFulfillmentForm" onsubmit="submitSellRequest(event)">
              <div style="margin-bottom:12px;">
                <label style="display:block; font-size:12px; font-weight:700; margin-bottom:4px;">Device IMEI Number (15 Digits) *</label>
                <input type="text" id="sellImei" required maxlength="15" placeholder="Dial *#06# to get IMEI" oninput="validateSellImei(this)" style="width:100%; padding:8px 12px; border:1px solid #cbd5e1; border-radius:6px; font-family:monospace;">
                <div id="imeiFeedback" style="font-size:11px; margin-top:3px; display:none;"></div>
              </div>

              <div style="margin-bottom:12px;">
                <label style="display:block; font-size:12px; font-weight:700; margin-bottom:4px;">Fulfillment Option *</label>
                <div style="display:flex; gap:10px;">
                  <label style="flex:1; border:1.5px solid #d6336c; background:#fdf2f6; border-radius:6px; padding:8px; text-align:center; font-size:12px; font-weight:700; cursor:pointer;">
                    <input type="radio" name="sellFulfilment" value="store_visit" checked onchange="toggleFulfillmentFields('store_visit')"> Visit K.T. Street Store
                  </label>
                  <label style="flex:1; border:1.5px solid #cbd5e1; border-radius:6px; padding:8px; text-align:center; font-size:12px; font-weight:700; cursor:pointer;">
                    <input type="radio" name="sellFulfilment" value="home_pickup" onchange="toggleFulfillmentFields('home_pickup')"> Home Pickup (Mysuru)
                  </label>
                </div>
              </div>

              <!-- Store Visit Selection -->
              <div id="storeVisitFields" style="margin-bottom:12px;">
                <label style="display:block; font-size:12px; font-weight:700; margin-bottom:4px;">Select Partner Store on K.T. Street</label>
                <select id="sellStoreId" style="width:100%; padding:8px 12px; border:1px solid #cbd5e1; border-radius:6px; font-size:13px;">
                  <option value="1">Chamundi Mobile Galleria (42 K.T. Street)</option>
                  <option value="2">Cauvery Phone Junction (78 K.T. Street)</option>
                  <option value="3">Heritage Gadgets & Exchange (115 K.T. Street)</option>
                  <option value="4">Mysuru Mobile Point (152 K.T. Street)</option>
                  <option value="5">K.T. Street Refurb Studio (204 K.T. Street)</option>
                </select>
              </div>

              <!-- Home Pickup Selection -->
              <div id="homePickupFields" style="display:none; margin-bottom:12px;">
                <label style="display:block; font-size:12px; font-weight:700; margin-bottom:4px;">Mysuru Pincode *</label>
                <div style="display:flex; gap:8px;">
                  <input type="text" id="sellPincode" maxlength="6" placeholder="e.g. 570001" style="flex:1; padding:8px 12px; border:1px solid #cbd5e1; border-radius:6px;">
                  <button type="button" onclick="verifyPincode()" style="padding:8px 12px; background:#0f172a; color:#fff; border:none; border-radius:6px; font-size:12px; font-weight:700; cursor:pointer;">Verify</button>
                </div>
                <div id="pincodeCheckMsg" style="font-size:11.5px; margin-top:4px; display:none;"></div>
                <div style="margin-top:8px;">
                  <label style="display:block; font-size:12px; font-weight:700; margin-bottom:4px;">Home / Office Address</label>
                  <input type="text" id="sellAddress" placeholder="Flat, Street, Area in Mysuru" style="width:100%; padding:8px 12px; border:1px solid #cbd5e1; border-radius:6px;">
                </div>
              </div>

              <div style="display:grid; grid-template-columns:1fr 1fr; gap:8px; margin-bottom:12px;">
                <div>
                  <label style="display:block; font-size:12px; font-weight:700; margin-bottom:4px;">Your Name *</label>
                  <input type="text" id="sellCustName" required placeholder="Full Name" style="width:100%; padding:8px; border:1px solid #cbd5e1; border-radius:6px;">
                </div>
                <div>
                  <label style="display:block; font-size:12px; font-weight:700; margin-bottom:4px;">Mobile (10 digits) *</label>
                  <input type="tel" id="sellCustPhone" required maxlength="10" placeholder="98450..." style="width:100%; padding:8px; border:1px solid #cbd5e1; border-radius:6px;">
                </div>
              </div>

              <div style="display:flex; gap:8px;">
                <button type="button" onclick="goToSellStep(2)" style="flex:1; padding:10px; background:#f1f5f9; color:#334155; border:none; border-radius:6px; font-weight:700; cursor:pointer;">Back</button>
                <button type="submit" id="btnSubmitSell" style="flex:2; padding:10px; background:var(--primary); color:#fff; border:none; border-radius:6px; font-weight:700; cursor:pointer;">
                  Confirm Sell Request <i class="fa-solid fa-check"></i>
                </button>
              </div>
            </form>
          </div>
        </div>
      </div>
    `;

    modal.classList.add("active");
  };

  window.onSellBrandChange = function() {
    const brand = document.getElementById("sellBrand").value;
    const modelSelect = document.getElementById("sellModel");
    let options = "";
    if (brand === "Apple") {
      options = `<option value="iPhone 15">iPhone 15</option><option value="iPhone 14">iPhone 14</option><option value="iPhone 13">iPhone 13</option><option value="iPhone 12">iPhone 12</option>`;
    } else if (brand === "Samsung") {
      options = `<option value="Galaxy S23 Ultra">Galaxy S23 Ultra</option><option value="Galaxy S23">Galaxy S23</option><option value="Galaxy S22">Galaxy S22</option>`;
    } else if (brand === "OnePlus") {
      options = `<option value="12">OnePlus 12</option><option value="11">OnePlus 11</option>`;
    } else if (brand === "Google") {
      options = `<option value="Pixel 8">Pixel 8</option><option value="Pixel 7">Pixel 7</option>`;
    } else {
      options = `<option value="13 Pro">Xiaomi 13 Pro</option>`;
    }
    modelSelect.innerHTML = options;
  };

  window.goToSellStep = function(stepNum) {
    document.querySelectorAll(".sell-step").forEach(s => s.classList.remove("active"));
    const target = document.getElementById(`sellStep${stepNum}`);
    if (target) target.classList.add("active");
  };

  window.fetchEstimateAndGoStep3 = async function() {
    const brand = document.getElementById("sellBrand").value;
    const model = document.getElementById("sellModel").value;
    const storage = parseInt(document.getElementById("sellStorage").value);

    const condition = {
      screen: document.getElementById("condScreen").value,
      body: document.getElementById("condBody").value,
      battery: document.getElementById("condBattery").value,
      accessories: []
    };
    if (document.getElementById("accBox").checked) condition.accessories.push("box");
    if (document.getElementById("accCharger").checked) condition.accessories.push("charger");

    try {
      const res = await fetch("/api/estimate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          brand, model, storage_gb: storage, condition_answers: condition
        })
      });
      const data = await res.json();
      if (data.success) {
        document.getElementById("estimateRangeTxt").textContent = `₹${data.estimated_min_price.toLocaleString('en-IN')} - ₹${data.estimated_max_price.toLocaleString('en-IN')}`;
        goToSellStep(3);
      }
    } catch (e) {
      alert("Error calculating estimate.");
    }
  };

  window.validateSellImei = function(input) {
    const val = input.value.trim();
    const fb = document.getElementById("imeiFeedback");
    fb.style.display = "block";
    if (VendorApp.validateLuhn(val)) {
      fb.style.color = "#10b981";
      fb.innerHTML = `<i class="fa-solid fa-check"></i> Valid 15-digit IMEI checksum.`;
    } else {
      fb.style.color = "#ef4444";
      fb.innerHTML = `<i class="fa-solid fa-xmark"></i> Invalid IMEI (Must be 15 digits passing Luhn check).`;
    }
  };

  window.toggleFulfillmentFields = function(val) {
    document.getElementById("storeVisitFields").style.display = (val === 'store_visit') ? 'block' : 'none';
    document.getElementById("homePickupFields").style.display = (val === 'home_pickup') ? 'block' : 'none';
  };

  window.verifyPincode = async function() {
    const pin = document.getElementById("sellPincode").value.trim();
    const msg = document.getElementById("pincodeCheckMsg");
    msg.style.display = "block";
    try {
      const res = await fetch(`/api/pincodes/check?pincode=${encodeURIComponent(pin)}`);
      const data = await res.json();
      if (data.serviceable) {
        msg.style.color = "#10b981";
        msg.innerHTML = `<i class="fa-solid fa-circle-check"></i> ${data.message}`;
      } else {
        msg.style.color = "#ef4444";
        msg.innerHTML = `<i class="fa-solid fa-circle-exclamation"></i> ${data.message}`;
      }
    } catch (e) {
      msg.style.color = "#ef4444";
      msg.textContent = "Error checking pincode.";
    }
  };

  window.submitSellRequest = async function(e) {
    e.preventDefault();
    const imei = document.getElementById("sellImei").value.trim();
    if (!VendorApp.validateLuhn(imei)) {
      alert("Please enter a valid 15-digit IMEI number.");
      return;
    }

    const fulfilment = document.querySelector('input[name="sellFulfilment"]:checked').value;
    const payload = {
      brand: document.getElementById("sellBrand").value,
      model: document.getElementById("sellModel").value,
      storage_gb: parseInt(document.getElementById("sellStorage").value),
      imei: imei,
      customer_name: document.getElementById("sellCustName").value.trim(),
      customer_phone: document.getElementById("sellCustPhone").value.trim(),
      fulfilment_type: fulfilment,
      store_id: fulfilment === 'store_visit' ? parseInt(document.getElementById("sellStoreId").value) : null,
      pincode: fulfilment === 'home_pickup' ? document.getElementById("sellPincode").value.trim() : null,
      customer_address: fulfilment === 'home_pickup' ? document.getElementById("sellAddress").value.trim() : null,
      condition_answers: {
        screen: document.getElementById("condScreen").value,
        body: document.getElementById("condBody").value,
        battery: document.getElementById("condBattery").value,
        accessories: []
      }
    };
    if (document.getElementById("accBox").checked) payload.condition_answers.accessories.push("box");
    if (document.getElementById("accCharger").checked) payload.condition_answers.accessories.push("charger");

    const btn = document.getElementById("btnSubmitSell");
    btn.disabled = true;
    btn.textContent = "Submitting...";

    try {
      const res = await fetch("/api/sell/requests", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      const data = await res.json();
      if (res.ok && data.success) {
        const body = document.getElementById("sellWizardBody");
        const sr = data.sell_request;
        body.innerHTML = `
          <div class="reserve-success-box">
            <i class="fa-solid fa-circle-check fa-3x" style="color:#10b981; margin-bottom:8px;"></i>
            <h4 style="font-size:18px; font-weight:800; color:#0f172a;">Sell Request Booked!</h4>
            <p style="font-size:12px; color:#64748b;">Keep your tracking reference handy for store inspection or pickup</p>
            <div class="reserve-code">${sr.request_reference}</div>
            <div style="font-size:13px; font-weight:700; color:#0f172a; margin-top:6px;">
              ${sr.fulfilment_type === 'store_visit' ? `🏪 Store Visit at ${sr.store_name || 'K.T. Street Store'}` : `🚗 Home Pickup in Mysuru (PIN ${sr.pincode})`}
            </div>
          </div>
          <p style="font-size:13px; color:#475569; text-align:center; margin-bottom:16px;">
            Our certified technician will inspect the 15 diagnostic points and provide your final offer for immediate cash or UPI payout.
          </p>
          <button onclick="document.getElementById('cmSellWizardModal').classList.remove('active')" style="width:100%; padding:10px; background:var(--primary); color:#fff; border:none; border-radius:6px; font-weight:700; cursor:pointer;">
            Done
          </button>
        `;
      } else {
        alert("Submission failed: " + (data.error || "Please check your inputs."));
        btn.disabled = false;
        btn.textContent = "Confirm Sell Request";
      }
    } catch (err) {
      alert("Network error.");
      btn.disabled = false;
      btn.textContent = "Confirm Sell Request";
    }
  };

  // =========================================================================
  // 6. Sell Request Tracking Modal
  // =========================================================================
  window.openSellTrackingModal = async function(prefillRef) {
    let modal = document.getElementById("cmTrackingModal");
    if (!modal) {
      modal = document.createElement("div");
      modal.id = "cmTrackingModal";
      modal.className = "cm-modal";
      document.body.appendChild(modal);
    }

    modal.innerHTML = `
      <div class="cm-modal-card">
        <div class="cm-modal-header">
          <h3><i class="fa-solid fa-route" style="color:var(--primary)"></i> Track Sell Request / Inspection</h3>
          <button onclick="document.getElementById('cmTrackingModal').classList.remove('active')" style="border:none; background:none; font-size:22px; cursor:pointer;">✕</button>
        </div>
        <div class="cm-modal-body">
          <div style="display:flex; gap:8px; margin-bottom:16px;">
            <input type="text" id="trackRefInput" value="${prefillRef || ''}" placeholder="Enter SELL-MYS-XXXXX" style="flex:1; padding:8px 12px; border:1px solid #cbd5e1; border-radius:6px; font-size:13px; font-family:monospace;">
            <button onclick="lookupSellRequest()" style="padding:8px 16px; background:#0f172a; color:#fff; border:none; border-radius:6px; font-weight:700; font-size:13px; cursor:pointer;">Track</button>
          </div>
          <div id="trackingResultArea">
            <p style="color:#64748b; font-size:13px; text-align:center; padding:20px;">Enter your sell request reference code above to see live progress.</p>
          </div>
        </div>
      </div>
    `;

    modal.classList.add("active");
    if (prefillRef) {
      lookupSellRequest();
    }
  };

  window.lookupSellRequest = async function() {
    const ref = document.getElementById("trackRefInput").value.trim();
    if (!ref) return;
    const area = document.getElementById("trackingResultArea");
    area.innerHTML = '<div style="text-align:center; padding:20px;"><i class="fa-solid fa-circle-notch fa-spin fa-2x"></i></div>';

    try {
      const res = await fetch(`/api/sell/requests/${encodeURIComponent(ref)}`);
      const data = await res.json();
      if (res.ok && data.success) {
        const sr = data.sell_request;
        let timelineHtml = (sr.timeline || []).map(t => `
          <div style="display:flex; gap:12px; margin-bottom:12px; font-size:12.5px;">
            <div style="width:8px; height:8px; border-radius:50%; background:var(--primary); margin-top:5px;"></div>
            <div>
              <strong>${t.to_status.replace('_', ' ').toUpperCase()}</strong> &bull; <span style="color:#64748b;">${new Date(t.created_at).toLocaleString('en-IN')}</span>
              <div style="color:#475569; margin-top:2px;">${t.notes || ''}</div>
            </div>
          </div>
        `).join('');

        let offerActionHtml = '';
        if (sr.status === 'offer_revised' || sr.status === 'inspected') {
          offerActionHtml = `
            <div style="background:#fffbfa; border:1.5px solid #d6336c; border-radius:10px; padding:14px; margin-bottom:16px; text-align:center;">
              <div style="font-size:12px; color:#b02154; font-weight:700;">STORE INSPECTION OFFER</div>
              <div style="font-size:1.6rem; font-weight:800; color:#d6336c; margin:4px 0;">₹${Number(sr.final_offer_price).toLocaleString('en-IN')}</div>
              <p style="font-size:12px; color:#64748b; margin-bottom:10px;">${sr.final_offer_notes || 'Inspected and certified by K.T. Street technician.'}</p>
              <div style="display:flex; gap:8px;">
                <button onclick="acceptOffer('${sr.request_reference}')" style="flex:1; padding:8px; background:#10b981; color:#fff; border:none; border-radius:6px; font-weight:700; cursor:pointer;">Accept & Get Paid</button>
                <button onclick="rejectOffer('${sr.request_reference}')" style="flex:1; padding:8px; background:#f1f5f9; color:#ef4444; border:none; border-radius:6px; font-weight:700; cursor:pointer;">Decline</button>
              </div>
            </div>
          `;
        }

        area.innerHTML = `
          <div style="border-bottom:1px solid #e2e8f0; padding-bottom:12px; margin-bottom:14px;">
            <div style="display:flex; justify-content:space-between; align-items:center;">
              <strong style="font-size:16px;">${sr.brand} ${sr.model} (${sr.storage || ''})</strong>
              <span style="font-size:11px; font-weight:800; padding:3px 8px; border-radius:4px; background:#eff6ff; color:#1d4ed8;">● ${sr.status.toUpperCase()}</span>
            </div>
            <div style="font-size:12px; color:#64748b; margin-top:4px;">IMEI: ${sr.imei} &bull; ${sr.fulfilment_type === 'home_pickup' ? 'Home Pickup' : 'Store Visit'}</div>
          </div>

          ${offerActionHtml}

          <h5 style="font-size:13px; font-weight:700; margin-bottom:10px;"><i class="fa-solid fa-timeline"></i> Status Timeline</h5>
          <div>${timelineHtml || '<p style="color:#64748b; font-size:12px;">Submitted and awaiting store confirmation.</p>'}</div>
        `;
      } else {
        area.innerHTML = `<p style="color:#ef4444; text-align:center; padding:20px;">Request not found. Please verify the reference code.</p>`;
      }
    } catch (e) {
      area.innerHTML = `<p style="color:#ef4444; text-align:center; padding:20px;">Error looking up request.</p>`;
    }
  };

  window.acceptOffer = async function(ref) {
    try {
      const res = await fetch(`/api/sell/requests/${encodeURIComponent(ref)}/accept`, { method: "POST" });
      const data = await res.json();
      if (data.success) {
        alert("Offer accepted! The store executive will disburse your payout.");
        lookupSellRequest();
      }
    } catch (e) {
      alert("Error accepting offer.");
    }
  };

  window.rejectOffer = async function(ref) {
    try {
      const res = await fetch(`/api/sell/requests/${encodeURIComponent(ref)}/reject`, { method: "POST" });
      const data = await res.json();
      if (data.success) {
        alert("Offer declined. You may collect your device.");
        lookupSellRequest();
      }
    } catch (e) {
      alert("Error declining offer.");
    }
  };

  // Initialize on page load
  document.addEventListener("DOMContentLoaded", () => {
    loadStorefrontCatalog();
  });

})();
