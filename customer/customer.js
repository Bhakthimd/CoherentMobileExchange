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
            vendor_name: u.vendor_name || 'Verified Partner',
            vendor_id: u.vendor_id,
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

  // Initialize on page load
  document.addEventListener("DOMContentLoaded", () => {
    loadStorefrontCatalog();
  });

})();
